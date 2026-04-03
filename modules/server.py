from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import uvicorn
import socket
try:
    import qrcode
except ImportError:
    qrcode = None

import os
import asyncio
import time
from pathlib import Path
from typing import Dict, Optional
from pydantic import BaseModel

# Internal imports
from .storage import get_storage_provider

# Scraper and TTS are only needed locally
try:
    from .scraper import NovelScraper
except ImportError:
    NovelScraper = None

try:
    from .tts import TTSManager, TTSConfig
except ImportError:
    TTSManager = None
    TTSConfig = None

from fastapi.middleware.cors import CORSMiddleware

# Global instance for Cloud Run
app = FastAPI(title="Cyberpunk TTS Player")

# Add CORS middleware to allow cross-origin requests (essential for some mobile browsers)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configuration
BASE_DIR = Path(__file__).parent
TEMPLATES = Jinja2Templates(directory=str(BASE_DIR / "templates"))
STATIC_DIR = BASE_DIR / "templates" / "static"

if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Dynamic task status
active_tasks: Dict[str, dict] = {}

class ScrapeRequest(BaseModel):
    url: str
    fast_mode: bool = True
    headless: bool = True

class ActionRequest(BaseModel):
    story_name: str
# Global storage provider initialized once
STORAGE = get_storage_provider()

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

# ... (Original API actions remain similar but should only run locally) ...
@app.post("/api/actions/scrape")
async def scrape_story(req: ScrapeRequest):
    # This should technically fail gracefully if in Cloud mode without a browser
    # but for now we leave it intact for local dev
    return {"error": "Scraping only available locally."}

# (Existing task-based endpoints can be kept or removed for cloud, we'll keep them simplified)
@app.get("/api/tasks/status")
async def get_tasks_status():
    return active_tasks

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

