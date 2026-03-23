# Unified TTS & Scraper Toolkit

A comprehensive Python application for scraping web novel chapters and converting text to speech using Microsoft Edge TTS (`edge-tts`). Features a highly functional Terminal User Interface (TUI).

## Features

- ✅ **Web Scraping**: Built-in scraper for ScribbleHub and NovelBin using DrissionPage.
- ✅ **Edge TTS Integration**: Completely free text-to-speech using high-quality Microsoft Edge voices. No API keys required.
- ✅ **Batch Processing**: Automatically convert entire folders of text chapters into audio.
- ✅ **Automatic Audio Concatenation**: Merges generated TTS files into single audiobook files using FFmpeg.
- ✅ **Interactive TUI**: Easy-to-use terminal dashboard menu logic.
- ✅ **Dual-Speaker Mode**: Separate voices for narration and dialogue (using SSML).
- ✅ **Progress Tracking**: Resume interrupted scraping or TTS tasks seamlessly.
- ✅ **Auto-Cleaner**: Cleans raw scraped text (removes promo content) before TTS processing.

## Installation

1. **Clone or download this repository**
2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```
   *Ensure you have also installed FFmpeg on your system and added it to your PATH for audio concatenation.*

## Usage

Start the interactive Terminal User Interface:

```bash
python app.py
```

From the dashboard, you can:
1. **Scrape stories** (Provide a URL, it creates a folder and saves `.txt` files in `Library/`).
2. **Run Batch TTS** (Select a scraped folder to convert text to MP3 files).
3. **Run Full Auto** (Scrape + TTS automatically).
4. **Resume** broken tasks or fix corrupted downloads.

## Architecture

- `app.py`: Main dashboard and menu application.
- `modules/scraper.py`: Chromium-based target-site scraping logic.
- `modules/tts.py`: Audio generation using `edge-tts`.
- `modules/cleaner.py`: Text sanitization.
- `Library/`: Default generated folder containing output stories/audio.

## Support & Troubleshooting

If you encounter missing dependencies, ensure you have ran `pip install -r requirements.txt`.
For FFmpeg-related errors when concatenating audio, please verify `ffmpeg` is globally accessible via your command line.
