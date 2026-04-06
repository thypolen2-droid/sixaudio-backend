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
                    return self._ensure_schema(json.load(f))
            except Exception:
                # Corrupted file, regenerate
                return self._create_new_progress()
        else:
            return self._create_new_progress()

    def _ensure_schema(self, data: Dict) -> Dict:
        """Backfill new fields for older progress files."""
        data.setdefault("metadata", {})
        data.setdefault("scraping", {})
        data.setdefault("tts", {})

        data["metadata"].setdefault("story_title", self.story_dir.name)
        data["metadata"].setdefault("story_url", "")
        data["metadata"].setdefault("catalog_url", "")
        data["metadata"].setdefault("site", "")
        data["metadata"].setdefault("created_date", datetime.now().isoformat())
        data["metadata"].setdefault("last_updated", datetime.now().isoformat())
        data["metadata"].setdefault("status", "active")

        data["scraping"].setdefault("total_chapters", 0)
        data["scraping"].setdefault("catalog_chapter_count", 0)
        data["scraping"].setdefault("last_chapter_number", 0)
        data["scraping"].setdefault("last_chapter_url", "")
        data["scraping"].setdefault("last_chapter_title", "")
        data["scraping"].setdefault("last_scrape_date", "")
        data["scraping"].setdefault("is_complete", False)
        data["scraping"].setdefault("chapter_index", {})

        data["tts"].setdefault("total_text_files", 0)
        data["tts"].setdefault("total_audio_files", 0)
        data["tts"].setdefault("last_conversion_date", "")
        data["tts"].setdefault("combined_audio_exists", False)
        data["tts"].setdefault("combined_audio_file", None)
        return data
    
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
                "catalog_url": "",
                "site": "",
                "created_date": datetime.now().isoformat(),
                "last_updated": datetime.now().isoformat(),
                "status": "active"  # active, completed, paused
            },
            "scraping": {
                "total_chapters": len(txt_files),
                "catalog_chapter_count": 0,
                "last_chapter_number": len(txt_files),
                "last_chapter_url": "",
                "last_chapter_title": txt_files[-1].stem if txt_files else "",
                "last_scrape_date": datetime.now().isoformat() if txt_files else "",
                "is_complete": False,
                "chapter_index": {}
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
    
    def update_scraping(self, chapter_num: int, url: str, title: str, filename: str = None, advance_last: bool = True):
        """Update scraping progress."""
        chapter_key = str(chapter_num)
        existing = self.data["scraping"]["chapter_index"].get(chapter_key, {})
        self.data["scraping"]["chapter_index"][chapter_key] = {
            "url": url or existing.get("url", ""),
            "title": title or existing.get("title", ""),
            "filename": filename or existing.get("filename", ""),
            "updated_at": datetime.now().isoformat()
        }

        self.data["scraping"]["total_chapters"] = max(
            self.data["scraping"].get("total_chapters", 0),
            chapter_num
        )

        current_last = self.data["scraping"].get("last_chapter_number", 0)
        if advance_last or chapter_num >= current_last:
            self.data["scraping"]["last_chapter_number"] = chapter_num
            self.data["scraping"]["last_chapter_url"] = url
            self.data["scraping"]["last_chapter_title"] = title

        self.data["scraping"]["last_scrape_date"] = datetime.now().isoformat()
        self.save()
    
    def update_metadata(self, story_url: str = None, catalog_url: str = None, site: str = None, status: str = None):
        """Update story metadata."""
        if story_url:
            self.data["metadata"]["story_url"] = story_url
        if catalog_url:
            self.data["metadata"]["catalog_url"] = catalog_url
        if site:
            self.data["metadata"]["site"] = site
        if status:
            self.data["metadata"]["status"] = status
        self.save()

    def update_catalog_index(self, catalog_url: str, chapters: List[Dict]):
        """Persist the table of contents so scraping can resume chapter-by-chapter."""
        if catalog_url:
            self.data["metadata"]["catalog_url"] = catalog_url

        chapter_index = self.data["scraping"].setdefault("chapter_index", {})
        max_chapter_num = self.data["scraping"].get("total_chapters", 0)

        for chapter in chapters or []:
            chapter_num = int(chapter.get("chapter_num", 0) or 0)
            if chapter_num <= 0:
                continue

            chapter_key = str(chapter_num)
            existing = chapter_index.get(chapter_key, {})
            chapter_index[chapter_key] = {
                "url": chapter.get("url") or existing.get("url", ""),
                "title": chapter.get("title") or existing.get("title", ""),
                "filename": existing.get("filename", ""),
                "updated_at": existing.get("updated_at", "")
            }
            max_chapter_num = max(max_chapter_num, chapter_num)

        self.data["scraping"]["catalog_chapter_count"] = len(chapters or [])
        self.data["scraping"]["total_chapters"] = max_chapter_num
        self.data["scraping"]["is_complete"] = False
        self.data["metadata"]["status"] = "active"
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

    def get_recorded_chapters(self) -> Dict[int, Dict]:
        """Get chapter index records keyed by chapter number."""
        records = {}
        for key, value in self.data["scraping"].get("chapter_index", {}).items():
            try:
                records[int(key)] = value
            except (TypeError, ValueError):
                continue
        return dict(sorted(records.items()))

    def get_recoverable_scrape_targets(self, min_size: int = 500) -> List[Dict]:
        """Return chapters with known URLs whose text files are missing or too small."""
        targets = []
        for chapter_num, record in self.get_recorded_chapters().items():
            url = record.get("url")
            if not url:
                continue

            filename = record.get("filename") or ""
            file_path = self.story_dir / filename if filename else None

            if not file_path or not file_path.exists():
                matches = sorted(self.story_dir.glob(f"{chapter_num:04d}_*.txt"))
                file_path = matches[0] if matches else (self.story_dir / filename if filename else None)

            is_incomplete = (file_path is None) or (not file_path.exists()) or (file_path.stat().st_size < min_size)
            if is_incomplete:
                targets.append({
                    "chapter_num": chapter_num,
                    "url": url,
                    "title": record.get("title", ""),
                    "filename": file_path.name if file_path and file_path.exists() else filename
                })

        return targets
    
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
