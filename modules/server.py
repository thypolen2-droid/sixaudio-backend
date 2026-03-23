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
from .scraper import NovelScraper
from .tts import TTSManager, TTSConfig

# Global instance for Cloud Run
app = FastAPI(title="Cyberpunk TTS Player")

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

@app.get("/", response_class=HTMLResponse)
async def get_player(request: Request):
    return TEMPLATES.TemplateResponse("player.html", {"request": request})

@app.get("/dashboard", response_class=HTMLResponse)
async def get_dashboard(request: Request):
    return TEMPLATES.TemplateResponse("dashboard.html", {"request": request})

@app.get("/api/stories")
async def list_stories():
    storage = get_storage_provider()
    stories = storage.list_stories()
    return {"stories": stories}

@app.get("/api/stories/{story_name}")
async def list_chapters(story_name: str):
    storage = get_storage_provider()
    files = storage.list_chapters(story_name)
    return {"files": files}

@app.get("/stream/{story_name}/{filename}")
async def stream_audio(story_name: str, filename: str):
    storage = get_storage_provider()
    
    # If using local storage, return FileResponse
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

async def start_server(host="0.0.0.0", port=8000, library_path="Library"):
    os.environ["LIBRARY_PATH"] = library_path
    
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

