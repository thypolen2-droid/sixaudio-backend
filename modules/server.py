from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import HTMLResponse, FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import uvicorn
import socket
import sys

# Fix Windows asyncio ProactorEventLoop WinError 10054 bug
if sys.platform == "win32":
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    from asyncio.proactor_events import _ProactorBasePipeTransport
    from functools import wraps

    def _silence_connection_lost(func):
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            try:
                return func(self, *args, **kwargs)
            except (ConnectionResetError, OSError):
                pass
        return wrapper

    _ProactorBasePipeTransport._call_connection_lost = _silence_connection_lost(
        _ProactorBasePipeTransport._call_connection_lost
    )
try:
    import qrcode
except ImportError:
    qrcode = None

import os
import asyncio
import threading
import time
import json
from pathlib import Path
from typing import Dict, List, Optional
from pydantic import BaseModel

# Internal imports
from .storage import get_storage_provider
from .utils import extract_url
from .server_events import ServerEventHandler, make_task_id
from .scrape_queue import ScrapeQueue, get_default_queue_path
from .scrape_worker import ScrapeWorker

# Scraper and TTS are only needed locally
try:
    from .scraper import NovelScraper
    _SCRAPER_SITES = NovelScraper(output_dir=os.environ.get("LIBRARY_PATH", "Library"))
except ImportError:
    NovelScraper = None
    _SCRAPER_SITES = None

try:
    from .tts import TTSManager, TTSConfig
except ImportError:
    TTSManager = None
    TTSConfig = None

from fastapi.middleware.cors import CORSMiddleware

# Global instance for Cloud Run
app = FastAPI(title="Cyberpunk TTS Player")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configuration
# Configuration
BASE_DIR = Path(__file__).resolve().parent
TEMPLATES = Jinja2Templates(directory=str(BASE_DIR / "templates"))
STATIC_DIR = BASE_DIR / "templates" / "static"

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# --- REAL-TIME TASK TRACKING ---

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                pass # Stale connection

manager = ConnectionManager()

# Global task state
active_tasks: Dict[str, dict] = {}

class TaskUpdate(BaseModel):
    task_id: str
    total: Optional[int] = None
    current: Optional[int] = None
    advance: Optional[int] = None
    message: Optional[str] = None
    status: Optional[str] = None

# WebSocket for real-time updates
manager = ConnectionManager()

@app.websocket("/ws/tasks")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        # Send initial state
        await websocket.send_json({"type": "sync", "tasks": active_tasks})
        while True:
            await websocket.receive_text() 
    except WebSocketDisconnect:
        manager.disconnect(websocket)

async def broadcast_task_update(task_id: str, event_type: str = "task_update"):
    if task_id not in active_tasks:
        return
    
    task = active_tasks[task_id]
    # Add calculated progress for UI
    progress = (task["current"] / task["total"] * 100) if task["total"] > 0 else 0
    
    await manager.broadcast({
        "type": event_type,
        "task_id": task_id,
        "data": {
            **task,
            "progress": progress
        }
    })

@app.post("/api/internal/task/start")
async def task_start(update: TaskUpdate):
    active_tasks[update.task_id] = {
        "total": update.total or 100,
        "current": 0,
        "message": update.message or "Task started...",
        "status": update.status or "running",
        "logs": [update.message] if update.message else [],
        "last_update": time.time()
    }
    await broadcast_task_update(update.task_id)
    return {"status": "ok"}

@app.post("/api/internal/task/update")
async def task_update(update: TaskUpdate):
    if update.task_id not in active_tasks:
        return {"status": "error", "message": "Task not found"}
    
    task = active_tasks[update.task_id]
    if update.current is not None:
        task["current"] = update.current
    elif update.advance is not None:
        task["current"] += update.advance
    
    if update.message:
        task["message"] = update.message
        task["logs"].append(update.message)
        if len(task["logs"]) > 20:
            task["logs"].pop(0)
            
    if update.status:
        task["status"] = update.status
        
    task["last_update"] = time.time()
    await broadcast_task_update(update.task_id)
    return {"status": "ok"}

@app.post("/api/internal/task/finish")
async def task_finish(update: TaskUpdate):
    if update.task_id in active_tasks:
        task = active_tasks[update.task_id]
        task["current"] = task["total"]
        task["status"] = update.status or "completed"
        if update.message:
            task["message"] = update.message
            task["logs"].append(update.message)
        
        task["last_update"] = time.time()
        await broadcast_task_update(update.task_id, "task_finish")
        
        # Keep completed tasks for a while so user sees the 'DONE' status
        async def clear_later(tid):
            await asyncio.sleep(30)
            if tid in active_tasks and active_tasks[tid]["status"] in ["completed", "failed"]:
                del active_tasks[tid]
                await manager.broadcast({"type": "task_remove", "task_id": tid})
        
        asyncio.create_task(clear_later(update.task_id))
        
    return {"status": "ok"}

# --- END REAL-TIME TASK TRACKING ---

class ScrapeRequest(BaseModel):
    url: str
    fast_mode: bool = True
    headless: bool = True

class ActionRequest(BaseModel):
    story_name: str
# Global storage provider initialized once
STORAGE = get_storage_provider()

# Persistent scrape queue. Jobs survive restarts; the worker runs them one at a
# time because two Chromium instances would fight over the same user-data profile.
_SCRAPE_QUEUE: Optional[ScrapeQueue] = None
_SCRAPE_WORKER: Optional[ScrapeWorker] = None

# Persistent browser profile, matching the TUI's so Cloudflare clearance and
# logins are shared between the terminal and the web UI.
_BROWSER_PROFILE = Path(".browser_profile").resolve()

@app.get("/", response_class=HTMLResponse)
async def get_player(request: Request):
    return TEMPLATES.TemplateResponse(request=request, name="player.html")

@app.get("/dashboard", response_class=HTMLResponse)
async def get_dashboard(request: Request):
    return TEMPLATES.TemplateResponse(request=request, name="dashboard.html")

from .progress_tracker import ProgressTracker

@app.get("/api/library/status")
async def get_library_status():
    try:
        lib_path = Path(os.environ.get("LIBRARY_PATH", "Library"))
        print(f"🔍 API: Scanning library status in {lib_path}...")
        stories_data = ProgressTracker.get_all_stories(lib_path)
        
        # Format for dashboard.js
        results = []
        for s in stories_data:
            results.append({
                "name": s["name"],
                "txt_count": s["txt_count"],
                "mp3_count": s["mp3_count"],
                "status": s["status"],
                "progress": s["tracker"].data
            })
            
        print(f"📊 Dashboard: Returning status for {len(results)} stories.")
        return results
    except Exception as e:
        print(f"❌ Error getting library status: {str(e)}")
        return {"error": str(e)}

@app.get("/api/stories")
async def list_stories(request: Request):
    try:
        client_host = request.client.host
        print(f"🔍 API: Listing stories for client {client_host}...")
        stories = STORAGE.list_stories()
        print(f"📖 Found {len(stories)} stories in storage.")
        return {"stories": stories}
    except Exception as e:
        print(f"❌ Error listing stories: {str(e)}")
        return {"stories": [], "error": str(e)}

@app.get("/api/stories/{story_name}")
async def list_chapters(story_name: str):
    try:
        print(f"🔍 API: Listing chapters for {story_name}...")
        files = STORAGE.list_chapters(story_name)
        print(f"🎵 Found {len(files)} files for {story_name}.")
        return {"files": files}
    except Exception as e:
        print(f"❌ Error listing chapters: {str(e)}")
        return {"files": [], "error": str(e)}

@app.get("/api/stories/{story_name}/transcript/{filename}")
async def get_chapter_transcript(story_name: str, filename: str):
    """Return the text source paired with exact timestamps or estimated text."""
    if Path(story_name).name != story_name or Path(filename).name != filename:
        return {"error": "Invalid chapter path"}
    try:
        library_path = Path(os.environ.get("LIBRARY_PATH", "Library"))
        stem = Path(filename).stem

        # 1. Check for exact JSON cues file
        json_candidates = [
            library_path / story_name / "Audios" / f"{stem}.json",
            library_path / story_name / f"{stem}.json"
        ]
        for json_path in json_candidates:
            if json_path.is_file():
                cues = json.loads(json_path.read_text(encoding="utf-8"))
                full_text = " ".join([c.get("text", "") for c in cues])
                return {"text": full_text, "cues": cues, "timing": "exact"}

        # 2. Fallback to clean text file with estimated timing
        text_path = library_path / story_name / f"{stem}.txt"
        if not text_path.is_file():
            return {"error": "Transcript not found"}
        from .cleaner import clean_text
        return {"text": clean_text(text_path.read_text(encoding="utf-8")).strip(), "timing": "estimated"}
    except Exception as e:
        print(f"Transcript error: {e}")
        return {"error": "Unable to read transcript"}

@app.get("/stream/{story_name}/{filename}")
async def stream_audio(story_name: str, filename: str):
    storage = get_storage_provider()
    
    # If using Google Drive storage, redirect to the direct URL
    if hasattr(storage, 'folder_id'): # It's a GoogleDriveStorageProvider
        url = storage.get_audio_url(story_name, filename)
        return RedirectResponse(url)
        
    # If using cloud storage, return a Redirect to the signed URL
    if hasattr(storage, 'bucket'): # It's a CloudStorageProvider
        url = storage.get_audio_url(story_name, filename)
        return RedirectResponse(url)
    
    # Fallback to local
    lib_path = os.environ.get("LIBRARY_PATH", "Library")
    file_path = Path(lib_path) / story_name / "Audios" / filename
    if file_path.exists():
        return FileResponse(file_path, media_type="audio/mpeg")
    
    return {"error": "File not found"}

def _ensure_scrape_runtime() -> tuple[ScrapeQueue, ScrapeWorker]:
    """Lazily build the queue + worker on first use (needs a running loop)."""
    global _SCRAPE_QUEUE, _SCRAPE_WORKER

    if NovelScraper is None:
        raise HTTPException(
            status_code=503,
            detail="Scraping is unavailable in this deployment (DrissionPage not installed).",
        )

    if _SCRAPE_QUEUE is None:
        _SCRAPE_QUEUE = ScrapeQueue(get_default_queue_path())

    if _SCRAPE_WORKER is None:
        loop = asyncio.get_running_loop()

        def event_sink(message: dict):
            # Called from the worker thread; hand the broadcast to the loop.
            asyncio.run_coroutine_threadsafe(manager.broadcast(message), loop)

        _SCRAPE_WORKER = ScrapeWorker(
            queue=_SCRAPE_QUEUE,
            scraper_factory=NovelScraper,
            event_sink=event_sink,
            browser_profile=_BROWSER_PROFILE,
            library_path=Path(os.environ.get("LIBRARY_PATH", "Library")),
            headless=True,
            fast_mode=True,
            loop=loop,
        )
        _SCRAPE_WORKER.start()

    return _SCRAPE_QUEUE, _SCRAPE_WORKER


@app.post("/api/actions/scrape")
async def scrape_story(req: ScrapeRequest):
    """Queue a story URL for scraping.

    Every accepted URL is persisted to SQLite and picked up by the background
    worker in FIFO order, so nothing is lost when several are submitted at once
    or the server restarts mid-queue.
    """
    queue, _worker = _ensure_scrape_runtime()

    url = extract_url(req.url)
    if not url:
        raise HTTPException(status_code=400, detail="No valid URL provided.")

    site_key, _ = _SCRAPER_SITES.detect_site(url)
    if site_key is None:
        supported = ", ".join(sorted(NovelScraper.SITE_CONFIGS))
        raise HTTPException(status_code=400, detail=f"Unsupported site. Supported: {supported}.")

    job = queue.enqueue(url, site=site_key or "")
    await manager.broadcast({
        "type": "queue_update",
        "job": job,
        "counts": queue.counts(),
    })
    return {"status": "queued", "job": job, "counts": queue.counts()}


@app.get("/api/scrape/queue")
async def get_scrape_queue():
    """List queued jobs and per-status counts."""
    queue, _worker = _ensure_scrape_runtime()
    return {"jobs": queue.list_jobs(), "counts": queue.counts()}


@app.delete("/api/scrape/queue/{job_id}")
async def cancel_queue_job(job_id: int):
    """Cancel a pending job. Returns 409 if it already started running."""
    queue, _worker = _ensure_scrape_runtime()
    if not queue.cancel(job_id):
        raise HTTPException(status_code=409, detail="Job is already running or finished.")
    return {"status": "cancelled", "job_id": job_id, "counts": queue.counts()}


@app.post("/api/scrape/queue/{job_id}/retry")
async def retry_queue_job(job_id: int):
    """Move a failed job back to pending."""
    queue, _worker = _ensure_scrape_runtime()
    if not queue.retry(job_id):
        raise HTTPException(status_code=404, detail="Job not found.")
    return {"status": "requeued", "job": queue.get(job_id), "counts": queue.counts()}


@app.delete("/api/scrape/queue")
async def clear_scrape_queue():
    """Remove all finished jobs. Pending and running jobs are left alone."""
    queue, _worker = _ensure_scrape_runtime()
    removed = queue.clear_finished()
    return {"status": "cleared", "removed": removed, "counts": queue.counts()}



# (Existing task-based endpoints can be kept or removed for cloud, we'll keep them simplified)
@app.get("/api/tasks/status")
async def get_tasks_status():
    return active_tasks


@app.on_event("shutdown")
async def _stop_scrape_worker():
    """Stop the queue worker so an in-flight job is not killed mid-write."""
    if _SCRAPE_WORKER is not None:
        _SCRAPE_WORKER.stop(timeout=10.0)

async def start_server(host="0.0.0.0", port=8001, library_path="Library"):
    global STORAGE
    os.environ["LIBRARY_PATH"] = library_path
    
    # Re-initialize storage provider with the correct path after setting LIBRARY_PATH
    STORAGE = get_storage_provider()
    
    # Helper to get local IP for QR code
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('10.255.255.255', 1))
        IP = s.getsockname()[0]
    except Exception:
        IP = '127.0.0.1'
    finally:
        s.close()
    
    print("\n" * 2 + "=" * 60 + "\n🌐 SERVER STARTED SUCCESSFULLY\n" + "=" * 60)
    print(f"💻 LOCAL ACCESS: http://localhost:{port}")
    print(f"📱 NETWORK ACCESS: http://{IP}:{port}\n" + "=" * 60)
    
    if qrcode:
        qr = qrcode.QRCode()
        qr.add_data(f"http://{IP}:{port}")
        qr.make(fit=True)
        qr.print_ascii(invert=True)
    else:
        print("[Notice] qrcode library not installed, skipping QR code display.")
    print("=" * 60 + "\nPress Ctrl+C to stop the server\n")

    config = uvicorn.Config(app, host=host, port=port, log_level="error")
    server = uvicorn.Server(config)
    await server.serve()

