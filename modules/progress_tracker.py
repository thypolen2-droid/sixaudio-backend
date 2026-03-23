import json
import os
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, List

class ProgressTracker:
    """Manages progress tracking for scraping and TTS conversion."""
    
    PROGRESS_FILE = ".story_progress.json"
    
    def __init__(self, story_dir: Path):
        """Initialize progress tracker for a story directory."""
        self.story_dir = Path(story_dir)
        self.progress_file = self.story_dir / self.PROGRESS_FILE
        self.data = self._load_or_create()
    
    def _load_or_create(self) -> Dict:
        """Load existing progress or create new structure."""
        if self.progress_file.exists():
            try:
                with open(self.progress_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                # Corrupted file, regenerate
                return self._create_new_progress()
        else:
            return self._create_new_progress()
    
    def _create_new_progress(self) -> Dict:
        """Create new progress structure."""
        story_name = self.story_dir.name
        
        # Count existing files to determine current state
        txt_files = sorted(list(self.story_dir.glob("*.txt")))
        txt_files = [f for f in txt_files if not f.name.startswith('.')]
        
        audio_dir = self.story_dir / "Audios"
        mp3_files = []
        if audio_dir.exists():
            mp3_files = sorted(list(audio_dir.glob("*.mp3")))
            mp3_files = [f for f in mp3_files if not f.name.startswith('combined_')]
        
        return {
            "metadata": {
                "story_title": story_name,
                "story_url": "",
                "site": "",
                "created_date": datetime.now().isoformat(),
                "last_updated": datetime.now().isoformat(),
                "status": "active"  # active, completed, paused
            },
            "scraping": {
                "total_chapters": len(txt_files),
                "last_chapter_number": len(txt_files),
                "last_chapter_url": "",
                "last_chapter_title": txt_files[-1].stem if txt_files else "",
                "last_scrape_date": datetime.now().isoformat() if txt_files else "",
                "is_complete": False
            },
            "tts": {
                "total_text_files": len(txt_files),
                "total_audio_files": len(mp3_files),
                "last_conversion_date": datetime.now().isoformat() if mp3_files else "",
                "combined_audio_exists": self._check_combined_audio_exists(),
                "combined_audio_file": self._get_combined_audio_file()
            }
        }
    
    def _check_combined_audio_exists(self) -> bool:
        """Check if combined audio file exists."""
        audio_dir = self.story_dir / "Audios"
        if not audio_dir.exists():
            return False
        combined_files = list(audio_dir.glob("combined_*.mp3"))
        return len(combined_files) > 0
    
    def _get_combined_audio_file(self) -> Optional[str]:
        """Get the name of the combined audio file."""
        audio_dir = self.story_dir / "Audios"
        if not audio_dir.exists():
            return None
        combined_files = sorted(list(audio_dir.glob("combined_*.mp3")))
        return combined_files[-1].name if combined_files else None
    
    def save(self):
        """Save progress to file."""
        self.data["metadata"]["last_updated"] = datetime.now().isoformat()
        try:
            with open(self.progress_file, 'w', encoding='utf-8') as f:
                json.dump(self.data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Warning: Could not save progress: {e}")
    
    def update_scraping(self, chapter_num: int, url: str, title: str):
        """Update scraping progress."""
        self.data["scraping"]["total_chapters"] = chapter_num
        self.data["scraping"]["last_chapter_number"] = chapter_num
        self.data["scraping"]["last_chapter_url"] = url
        self.data["scraping"]["last_chapter_title"] = title
        self.data["scraping"]["last_scrape_date"] = datetime.now().isoformat()
        self.save()
    
    def update_metadata(self, story_url: str = None, site: str = None, status: str = None):
        """Update story metadata."""
        if story_url:
            self.data["metadata"]["story_url"] = story_url
        if site:
            self.data["metadata"]["site"] = site
        if status:
            self.data["metadata"]["status"] = status
        self.save()
    
    def mark_complete(self):
        """Mark scraping as complete."""
        self.data["scraping"]["is_complete"] = True
        self.data["metadata"]["status"] = "completed"
        self.save()
    
    def update_tts(self):
        """Update TTS progress by scanning files."""
        txt_files = sorted(list(self.story_dir.glob("*.txt")))
        txt_files = [f for f in txt_files if not f.name.startswith('.')]
        
        audio_dir = self.story_dir / "Audios"
        mp3_files = []
        if audio_dir.exists():
            mp3_files = sorted(list(audio_dir.glob("*.mp3")))
            mp3_files = [f for f in mp3_files if not f.name.startswith('combined_')]
        
        self.data["tts"]["total_text_files"] = len(txt_files)
        self.data["tts"]["total_audio_files"] = len(mp3_files)
        self.data["tts"]["last_conversion_date"] = datetime.now().isoformat()
        self.data["tts"]["combined_audio_exists"] = self._check_combined_audio_exists()
        self.data["tts"]["combined_audio_file"] = self._get_combined_audio_file()
        self.save()
    
    def get_tts_progress(self) -> Dict:
        """Get TTS conversion progress."""
        total = self.data["tts"]["total_text_files"]
        converted = self.data["tts"]["total_audio_files"]
        percentage = (converted / total * 100) if total > 0 else 0
        
        return {
            "total": total,
            "converted": converted,
            "percentage": percentage,
            "pending": total - converted
        }
    
    def get_last_chapter_info(self) -> Dict:
        """Get information about the last scraped chapter."""
        return {
            "number": self.data["scraping"]["last_chapter_number"],
            "url": self.data["scraping"]["last_chapter_url"],
            "title": self.data["scraping"]["last_chapter_title"]
        }
    
    def get_story_status(self) -> str:
        """Get human-readable story status."""
        return self.data["metadata"]["status"]
    
    def get_site(self) -> str:
        """Get the site this story is from."""
        return self.data["metadata"]["site"]
    
    @staticmethod
    def get_all_stories(library_dir: Path) -> List[Dict]:
        """Get all stories with their progress from the library."""
        stories = []
        
        if not library_dir.exists():
            return stories
        
        for story_dir in library_dir.iterdir():
            if story_dir.is_dir():
                tracker = ProgressTracker(story_dir)
                
                # Get file counts
                txt_count = len([f for f in story_dir.glob("*.txt") if not f.name.startswith('.')])
                
                audio_dir = story_dir / "Audios"
                mp3_count = 0
                if audio_dir.exists():
                    mp3_count = len([f for f in audio_dir.glob("*.mp3") if not f.name.startswith('combined_')])
                
                stories.append({
                    "name": story_dir.name,
                    "path": story_dir,
                    "tracker": tracker,
                    "txt_count": txt_count,
                    "mp3_count": mp3_count,
                    "last_updated": tracker.data["metadata"]["last_updated"],
                    "status": tracker.data["metadata"]["status"]
                })
        
        # Sort by last updated (most recent first)
        stories.sort(key=lambda x: x["last_updated"], reverse=True)
        return stories
