# ⚡ CYBERPUNK TTS & NOVEL TOOLKIT v3.0 ⚡

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Edge TTS](https://img.shields.io/badge/TTS-Microsoft%20Edge-cyan)](https://github.com/rany2/edge-tts)

An immersive, high-performance toolkit for the modern bibliophile. Scrape your favorite web novels, transform them into premium neural audiobooks, and sync them across all your devices with a single click.

---

## 🚀 Key Features

### 🛠️ Core Engine
- **Web Scraping (DrissionPage)**: Bypass bot detection on ScribbleHub, NovelBin, and more.
- **Advanced TTS (edge-tts v7.2.8)**: Leveraging the latest neural voices from Microsoft Edge with automated 403-error mitigation.
- **Dual-Speaker Mode**: Intelligent SSML generation that distinguishes between Narrator and Dialogue for an immersive experience.
- **Batch Processing**: Convert entire volumes in minutes with multi-threaded efficiency.
- **Audiobook Concatenation**: Seamlessly merge chapters into high-bitrate MP3s using FFmpeg.

### 📱 Connectivity & Cloud
- **Mobile Sync / Web Player**: A built-in local server with a **premium Web UI**. Listen to your library on any mobile device on your network.
- **Cloud Sync**: One-click synchronization to **Firebase / Google Cloud Storage**. Access your stories from anywhere in the world.
- **Local Network Discovery**: Smart IP detection for instant mobile access without manual configuration.

### 🧹 Intelligence & Cleanup
- **Smart Cleaner**: Automatic removal of "Author Notes", "Promo Content", and site-specific metadata to keep your audio clean.
- **Corruption Fixer**: Deep scan algorithm that identifies and repairs empty, truncated, or failed audio files instantly.
- **Progress Tracking**: Persistent JSON-based state management. Never lose your place in a 1,000-chapter epic.

---

## 🛠️ Cyberpunk Tech Stack

| Layer | Technology |
| :--- | :--- |
| **Logic** | Python 3.12+ / Asyncio |
| **TUI** | [Rich](https://github.com/Textualize/rich) (Cyan/Magenta Cyberpunk Theme) |
| **Scraper** | [DrissionPage](https://github.com/g1879/DrissionPage) |
| **TTS Engine** | [edge-tts](https://github.com/rany2/edge-tts) (v7.2.8+) |
| **Server** | Flask / Python-Dotenv |
| **Frontend** | Vanilla JS / CSS3 (Glassmorphism UI) |
| **Cloud** | Firebase Storage / Service Accounts |
| **Audio** | FFmpeg / Pydub |

---

## 📥 Installation

### Prerequisites
- **Python 3.10+**
- **FFmpeg**: Required for audio merging. 
  - *Windows*: `choco install ffmpeg`
  - *Mac*: `brew install ffmpeg`
  - *Linux*: `sudo apt install ffmpeg`

### Setup
1. **Clone the project**:
   ```bash
   git clone https://github.com/youruser/cyber-tts-toolkit.git
   cd cyber-tts-toolkit
   ```

2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure Environment** (Optional for Cloud Sync):
   Create a `.env` file or provide credentials in the UI for Firebase integration.

---

## 🎮 Usage

Launch the **Cyberpunk Dashboard**:

```bash
python app.py
```

### Dashboard Commands:
- `1` **Scraping Mode**: Enter a novel URL to begin ingestion.
- `2` **Batch TTS**: Convert local text folders to audio.
- `5` **Fix Corrupted**: Auto-repair failed generations.
- `7` **Mobile Server**: Start the local web portal for mobile listening.
- `10` **Cloud Sync**: Push your library to the stars.

---

## 📂 Project Structure

```text
├── app.py              # Main Entry Point (TUI Dashboard)
├── modules/
│   ├── scraper.py     # Chromium-based scraping engine
│   ├── tts.py         # edge-tts manager & SSML logic
│   ├── ui.py          # Rich-based UI components
│   ├── server.py      # Flask Mobile Server
│   └── storage.py     # Firebase / Local IO management
├── Library/           # Default Story Output (Scraped Text + MP3s)
└── static/            # Frontend assets for Web Player
```

---

## 🛡️ Support & Development

**Encountering 403 Errors?**
The system now uses `edge-tts 7.2.8+`. If you see connection issues, run:
`pip install --upgrade edge-tts`

**Missing Chapters?**
Check the `progress.json` in your story folder to see the scraping status.

**Contributing**
Pull requests are welcome! For major changes, please open an issue first.

---

*Built with ⚡ by Antigravity*
