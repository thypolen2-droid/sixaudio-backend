# ⚡ SixAudio: Setup & Startup Guide ⚡

Welcome to **SixAudio** — an advanced Cyberpunk TTS & Web Novel Toolkit. This guide walks you through setting up your environment, configuring settings, and running the application.

---

## 📋 Prerequisites

Before running SixAudio, ensure you have the following installed:

1. **Python 3.11+** (Python 3.11 or 3.12 recommended)
2. **FFmpeg**: Required for audio processing, merging, and MP3 concatenation.
   - *Windows*: Pre-installed or install via `winget install Gyan.FFmpeg` / `choco install ffmpeg`
   - *Mac*: `brew install ffmpeg`
   - *Linux*: `sudo apt install ffmpeg`
   - *Verify*: Run `ffmpeg -version` in your terminal.
3. **Google Chrome / Chromium**: Required by DrissionPage for automated scraping and Cloudflare bypass.

---

## 🚀 Quick Start (Step-by-Step)

### **Step 1: Activate the Virtual Environment**

A virtual environment (`venv`) keeps project dependencies isolated.

- **PowerShell (Windows)**:
  ```powershell
  .\venv\Scripts\Activate.ps1
  ```
- **Command Prompt (Windows)**:
  ```cmd
  .\venv\Scripts\activate.bat
  ```
- **Linux / macOS**:
  ```bash
  source venv/bin/activate
  ```

*(You will see `(venv)` appear at the beginning of your terminal prompt).*

> [!TIP]
> If PowerShell gives a script execution policy error, run this once:
> ```powershell
> Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
> ```

---

### **Step 2: Install or Update Dependencies**

If you haven't installed requirements yet or after pulling updates:

```powershell
pip install -r requirements.txt
```

---

### **Step 3: Configure Environment Variables (`.env`)**

The project includes a `.env` file for customizable settings:

```env
# Directory where scraped novels and generated audiobooks are stored
LIBRARY_PATH=Library

# (Optional) Cloud Sync Configuration (Firebase / GCS)
FIREBASE_STORAGE_BUCKET=your-bucket-name.appspot.com
GCLOUD_PROJECT_ID=your-project-id

# (Optional) Google Drive Sync Configuration
DRIVE_FOLDER_ID=your-google-drive-folder-id
```

---

### **Step 4: Run the Application**

#### **Option A: Full Interactive Cyberpunk TUI Dashboard (Recommended)**

```powershell
python app.py
```

This launches the rich interactive terminal menu with all tools:
- `1` : 📖 **Scraping Mode** — Scrape web novels from ScribbleHub, NovelBin, Webnovel, etc.
- `2` : 🎙️ **Batch Text-to-Speech** — Convert text chapter folders into neural audio.
- `3` : ⚡ **Process Single Story** — Scrape and generate TTS end-to-end.
- `4` : 🔄 **Resume Last Task** — Pick up incomplete scraping or TTS jobs.
- `5` : 🛠️ **Fix Corrupted Files** — Auto-scan and repair empty/truncated audio files.
- `6` : 🧹 **Clean Text Files** — Strip promo links, translator notes, and noise.
- `7` : 📲 **Mobile Sync & Web Player** — Launch web server & display QR code.
- `10`: ☁️ **Cloud Sync** — Push your library to Firebase or Google Drive.

#### **Option B: Standalone Web Player & Mobile Sync Server**

To run just the FastAPI Web Player directly:

```powershell
python -m uvicorn modules.server:app --host 0.0.0.0 --port 8000 --reload
```
- Local Web Player: [http://localhost:8000](http://localhost:8000)
- Mobile Access: Connect phone to the same Wi-Fi and open `http://<your-local-ip>:8000` (or scan the QR code generated in `app.py`).

---

## ⚡ One-Liner Startup Command

To activate and run SixAudio with a single command in PowerShell:

```powershell
.\venv\Scripts\Activate.ps1; python app.py
```

---

## 🐛 Troubleshooting

| Issue | Solution |
| :--- | :--- |
| **`Execution Policy` error** | Run `Set-ExecutionPolicy RemoteSigned -Scope CurrentUser` in PowerShell. |
| **`ffmpeg not found`** | Ensure `ffmpeg` is in your system PATH (`ffmpeg -version`). |
| **`ModuleNotFoundError`** | Ensure virtual environment is activated (`.\venv\Scripts\Activate.ps1`). |
| **Cloudflare block during scraping** | SixAudio uses DrissionPage with `.browser_profile` to remember Cloudflare sessions. Ensure Chrome is installed and allowed. |
| **Port 8000 / 8001 in use** | Ensure another instance of `app.py` or `uvicorn` is not already running. |

---

## 📁 Project Structure

```
sixaudio-backend/
├── app.py                  # Main Cyberpunk TUI Dashboard & Controller
├── modules/
│   ├── scraper.py          # DrissionPage Novel Scraper Engine
│   ├── tts.py              # Microsoft Edge Neural TTS Engine
│   ├── server.py           # FastAPI Web Player & WebSocket Server
│   ├── cleaner.py          # Smart Novel Text Cleaner
│   ├── storage.py          # Local / Firebase Storage Provider
│   ├── events.py           # Event system for TUI & Remote Web UI
│   └── ui.py               # Rich Cyberpunk Terminal Interface
├── public/                 # Glassmorphism Web Player Static Files
├── Library/                # Scraped Novels and Generated Audiobooks
├── requirements.txt        # Python Dependencies
├── HOW_TO_START.md         # This Guide
└── README.md               # Project Overview
```
