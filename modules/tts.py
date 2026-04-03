import os
import sys
import logging
import asyncio
import re
import struct
import subprocess
import tempfile
from pathlib import Path
from datetime import datetime
import edge_tts

from .utils import natural_sort_key
from .progress_tracker import ProgressTracker
from .events import EventHandler

try:
    from pydub import AudioSegment
    PYDUB_AVAILABLE = True
except ImportError:
    PYDUB_AVAILABLE = False

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class TTSConfig:
    def __init__(self, voice="en-US-AriaNeural", rate="+0%", volume="+0%", output_dir="Audios"):
        self.voice = voice
        self.rate = rate
        self.volume = volume
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

class TTSManager:
    def __init__(self, config: TTSConfig = None, event_handler: EventHandler = None):
        self.config = config if config else TTSConfig()
        self.events = event_handler

    def set_event_handler(self, handler: EventHandler):
        self.events = handler

    def _log(self, msg, level="info"):
        if self.events:
            self.events.log(msg, level)
        else:
            logger.info(msg) # Fallback

    async def _check_tts_connectivity(self) -> bool:
        """Check if we can reach the TTS service."""
        try:
            import socket
            socket.create_connection(("speech.platform.bing.com", 443), timeout=5)
            return True
        except Exception:
            return False

    async def _convert_with_retry(self, text: str, output_path: Path, use_ssml=False, max_retries=3) -> bool:
        """Convert text to speech with retry logic and exponential backoff."""
        last_error = None
        
        for attempt in range(max_retries):
            try:
                if use_ssml:
                    # In edge-tts 7.x, SSML strings are handled automatically by Communicate
                    communicate = edge_tts.Communicate(text)
                else:
                    communicate = edge_tts.Communicate(text, self.config.voice, rate=self.config.rate, volume=self.config.volume)
                
                await communicate.save(str(output_path))
                return True
                
            except Exception as e:
                last_error = e
                error_msg = str(e)
                
                # Check if it's a connection error
                if "Cannot connect" in error_msg or "getaddrinfo failed" in error_msg or "ssl" in error_msg.lower():
                    if attempt < max_retries - 1:
                        # Exponential backoff: 2s, 4s, 8s
                        wait_time = 2 ** (attempt + 1)
                        logger.warning(f"Connection failed (attempt {attempt + 1}/{max_retries}), retrying in {wait_time}s...")
                        continue
                
                # For other errors, don't retry
                logger.error(f"Failed to convert text: {e}")
                raise
        
        # All retries exhausted
        logger.error(f"Failed after {max_retries} attempts: {last_error}")
        raise last_error

    async def convert_text(self, text: str, output_filename: str, use_ssml=False) -> Path:
        """Convert distinct string to audio."""
        if not text or not text.strip():
            return None
        
        output_path = self.config.output_dir / output_filename
        output_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            await self._convert_with_retry(text, output_path, use_ssml)
            return output_path
        except Exception as e:
            logger.error(f"Failed to convert text: {e}")
            raise

    async def process_folder(self, folder_path: Path, dual_speaker=False, progress_callback=None):
        """Batch process a folder of text files."""
        if not folder_path.exists():
            self._log(f"Invalid directory: {folder_path}", "error")
            return

        files = sorted(list(folder_path.glob("*.txt")), key=lambda p: natural_sort_key(p.name))
        if not files:
            self._log(f"No .txt files found in {folder_path.name}", "warning")
            return

        # Check network connectivity before starting
        if self.events: self.events.log("[dim]Checking TTS service connectivity...[/dim]")
        
        if not await self._check_tts_connectivity():
            self._log("Warning: Cannot reach TTS service. Conversion may fail.", "warning")
            if self.events and not self.events.confirm("Continue anyway?", default=True):
                return
            elif not self.events:
                return # If no UI, assume safely abort

        # Setup output in a subfolder 'Audios' within the story folder
        audio_output_dir = folder_path / "Audios"
        audio_output_dir.mkdir(exist_ok=True)
        
        # Save old config output
        original_output = self.config.output_dir
        self.config.output_dir = audio_output_dir

        mode_str = "Dual Speaker" if dual_speaker else "Single Speaker"
        self._log(f"🚀 Starting Batch Conversion ({mode_str}) for: {folder_path.name}")
        self._log(f"[dim]Found {len(files)} chapters. Saving to {audio_output_dir.name}/[/dim]\n")
        
        # Init SSML Builder if needed
        ssml_builder = None
        if dual_speaker:
            from .ssml_builder import SSMLBuilder
            ssml_builder = SSMLBuilder(narrator_voice=self.config.voice)

        success_count = 0
        failed_files = []  # Track failed conversions
        
        if self.events:
            self.events.progress_start("batch_tts", len(files), "Converting...")

        for idx, file_path in enumerate(files):
            output_filename = f"{file_path.stem}.mp3"
            
            if self.events:
                 self.events.progress_update("batch_tts", advance=0, description=f"[cyan]Processing: {file_path.name}")
            
            # Fire progress callback for web UI
            if progress_callback:
                progress_callback({
                    'current': idx + 1,
                    'total': len(files),
                    'filename': file_path.name
                })
            
            # Check if already exists
            output_path = self.config.output_dir / output_filename
            if output_path.exists() and output_path.stat().st_size > 1024:
                 if self.events: self.events.progress_update("batch_tts", advance=1)
                 success_count += 1
                 continue

            try:
                text = file_path.read_text(encoding='utf-8').strip()
                if text:
                    # Clean text
                    from .cleaner import clean_text
                    cleaned_text = clean_text(text)
                    
                    if cleaned_text:
                        final_text = cleaned_text
                        is_ssml = False
                        
                        if dual_speaker and ssml_builder:
                            final_text = ssml_builder.build_ssml(cleaned_text)
                            is_ssml = True
                            
                        await self.convert_text(final_text, output_filename, use_ssml=is_ssml)
                        success_count += 1
                    else:
                        self._log(f"Skipped {file_path.name} (Empty after cleaning)", "warning")
            except Exception as e:
                error_msg = str(e)
                failed_files.append((file_path.name, error_msg))
                self._log(f"Error {file_path.name}: {error_msg[:80]}", "error")
            
            if self.events: self.events.progress_update("batch_tts", advance=1)

        # Stop progress
        if self.events and hasattr(self.events, 'stop_progress'):
            self.events.stop_progress()

        # Summary
        self._log(f"\n🎉 Batch complete! {success_count}/{len(files)} files processed successfully.", "success")
        
        if failed_files:
            self._log(f"\n⚠️  {len(failed_files)} file(s) failed:", "warning")
            for filename, error in failed_files[:5]:  # Show first 5
                self._log(f"  • {filename}: {error[:60]}...")

        
        self.config.output_dir = original_output # Restore
        
        # Update progress tracker
        tracker = ProgressTracker(folder_path)
        tracker.update_tts()


    async def auto_combine_audios(self, folder_path: Path):
        """Combine all MP3s in the Audios subfolder."""
        audio_dir = folder_path / "Audios"
        if not audio_dir.exists():
            self._log("No Audios folder found to combine.", "error")
            return

        mp3_files = sorted(list(audio_dir.glob("*.mp3")), key=lambda p: natural_sort_key(p.name))
        mp3_files = [f for f in mp3_files if not f.name.startswith("combined_")]
        
        if not mp3_files:
            return

        self._log(f"🎵 Combining {len(mp3_files)} audio files...")
        
        # FFmpeg Method (Fastest/Safe)
        try:
            with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8') as f:
                concat_file = f.name
                for mp3_file in mp3_files:
                    escaped_path = str(mp3_file.absolute()).replace("\\", "/").replace("'", "'\\\\'\'")
                    f.write(f"file '{escaped_path}'\n")
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_filename = f"combined_audio_{timestamp}.mp3"
            output_path = audio_dir / output_filename
            
            cmd = ['ffmpeg', '-f', 'concat', '-safe', '0', '-i', concat_file, '-c', 'copy', '-y', str(output_path)]
            
            subprocess.run(cmd, capture_output=True, check=True)
            
            os.unlink(concat_file)
            self._log(f"✅ Combined Audio Saved: {output_filename}", "success")
            
        except Exception as e:
            self._log(f"Combine failed: {e}", "error")

    async def fix_corrupted_files(self, folder_path: Path, auto_fix=False):
        """Scan and fix corrupted audio files in the folder."""
        audio_dir = folder_path / "Audios"
        if not audio_dir.exists():
             self._log(f"No Audios folder found in: {folder_path.name}", "error")
             return

        self._log(f"🔍 [cyan]Scanning {folder_path.name}...[/cyan]")
        mp3_files = sorted(list(audio_dir.glob("*.mp3")), key=lambda p: natural_sort_key(p.name))
        corrupted = []
        MIN_SIZE = 1024 # 1KB

        for mp3 in mp3_files:
            if mp3.name.startswith("combined_"): continue
            
            try:
                size = mp3.stat().st_size
                reason = None
                if size == 0: reason = "Empty file"
                elif size < MIN_SIZE: reason = "Too small"
                elif PYDUB_AVAILABLE:
                    try:
                        if len(AudioSegment.from_mp3(str(mp3))) < 100: reason = "Too short"
                    except: reason = "Decode error"
                
                if reason:
                    corrupted.append((mp3, reason))
            except: pass

        if not corrupted:
            self._log("✅ No corrupted files found.", "success")
            return

        if not auto_fix:
            self._log(f"Found {len(corrupted)} corrupted files.", "warning")
            if self.events and not self.events.confirm("Attempt to fix?"): 
                 return
            elif not self.events:
                 return # Abort if no UI
        else:
             self._log(f"Auto-fixing {len(corrupted)} corrupted files in {folder_path.name}...", "info")

        # Restore output dir temporarily
        original_output = self.config.output_dir
        self.config.output_dir = audio_dir
        
        fixed = 0
        
        if self.events:
             self.events.progress_start("fix_tts", len(corrupted), "Fixing...")
        
        for mp3, reason in corrupted:
            txt_name = mp3.stem + ".txt"
            txt_path = folder_path / txt_name
            
            if self.events:
                 self.events.progress_update("fix_tts", advance=0, description=f"Fixing {mp3.name}...")

            if txt_path.exists():
                try:
                    text = txt_path.read_text(encoding='utf-8').strip()
                    if text:
                        await self.convert_text(text, mp3.name)
                        fixed += 1
                except Exception as e:
                    self._log(f"Failed {mp3.name}: {e}", "error")
            else:
                self._log(f"Missing source text for {mp3.name}", "error")
            
            if self.events: self.events.progress_update("fix_tts", advance=1)

        if self.events and hasattr(self.events, 'stop_progress'):
             self.events.stop_progress()

        self._log(f"Fixed {fixed}/{len(corrupted)} files.", "success")
        self.config.output_dir = original_output
