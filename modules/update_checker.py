import time
from pathlib import Path
from typing import List, Dict, Optional
from DrissionPage import ChromiumPage, ChromiumOptions
from rich.progress import Progress, SpinnerColumn, TextColumn
from .progress_tracker import ProgressTracker
from .ui import console

class UpdateChecker:
    """Checks for new chapters on novel sites."""
    
    def __init__(self, headless: bool = True):
        self.headless = headless
        self.page = None
    
    def _init_browser(self):
        """Initialize browser if not already initialized."""
        if self.page is None:
            co = ChromiumOptions()
            co.auto_port()
            co.headless(self.headless)
            co.mute(True)
            try:
                self.page = ChromiumPage(co)
            except Exception as e:
                console.print(f"[bold red]❌ Browser init failed: {e}[/bold red]")
                return False
        return True
    
    def _close_browser(self):
        """Close browser if open."""
        if self.page:
            try:
                self.page.quit()
            except:
                pass
            self.page = None
    
    def check_story_for_updates(self, tracker: ProgressTracker) -> Optional[Dict]:
        """
        Check if a story has new chapters.
        
        Returns:
            Dict with update info if new chapters found, None otherwise
        """
        last_url = tracker.data["scraping"]["last_chapter_url"]
        last_chapter_num = tracker.data["scraping"]["last_chapter_number"]
        site = tracker.data["metadata"]["site"]
        
        # Skip if no URL or site info
        if not last_url or not site:
            return None
        
        # Skip if marked as completed
        if tracker.data["scraping"]["is_complete"]:
            return None
        
        # Get site config
        from .scraper import NovelScraper
        scraper = NovelScraper()
        site_key, site_config = scraper.detect_site(last_url)
        
        if not site_config:
            return None
        
        try:
            if not self._init_browser():
                return None
            
            # Load the last known chapter
            self.page.get(last_url)
            time.sleep(1)  # Wait for page load
            
            # Try to find next button
            try:
                next_btn = self.page.ele(site_config['next_button_selector'], timeout=2)
                if next_btn:
                    # Check if next button is disabled
                    if site_config['next_disabled_check'](next_btn):
                        # No new chapters
                        return None
                    
                    # Next button exists and is enabled - new chapters available!
                    # Try to count how many new chapters
                    new_chapter_count = self._count_new_chapters(site_config, last_chapter_num)
                    
                    return {
                        "story_name": tracker.data["metadata"]["story_title"],
                        "last_chapter": last_chapter_num,
                        "new_chapters": new_chapter_count,
                        "total_chapters": last_chapter_num + new_chapter_count,
                        "next_url": next_btn.link if next_btn.link else last_url
                    }
            except:
                # Next button not found or error
                return None
                
        except Exception as e:
            console.print(f"[dim]Warning: Could not check {tracker.data['metadata']['story_title']}: {e}[/dim]")
            return None
    
    def _count_new_chapters(self, site_config: Dict, start_from: int, max_check: int = 50) -> int:
        """
        Count how many new chapters are available.
        
        Args:
            site_config: Site configuration
            start_from: Chapter number to start counting from
            max_check: Maximum number of chapters to check (to avoid infinite loops)
        
        Returns:
            Number of new chapters found
        """
        count = 0
        
        try:
            for i in range(max_check):
                # Try to find next button
                try:
                    next_btn = self.page.ele(site_config['next_button_selector'], timeout=1)
                    if next_btn and not site_config['next_disabled_check'](next_btn):
                        count += 1
                        # Navigate to next chapter
                        next_url = next_btn.link
                        if next_url and "javascript" not in next_url:
                            self.page.get(next_url)
                            time.sleep(0.5)  # Quick delay
                        else:
                            break
                    else:
                        break
                except:
                    break
        except:
            pass
        
        return count
    
    def check_all_stories(self, library_dir: Path) -> List[Dict]:
        """
        Check all active stories for updates.
        
        Returns:
            List of stories with updates
        """
        stories_with_updates = []
        
        # Get all stories
        all_stories = ProgressTracker.get_all_stories(library_dir)
        
        # Filter to only active stories with URLs
        active_stories = [
            s for s in all_stories 
            if s["status"] == "active" and s["tracker"].data["scraping"]["last_chapter_url"]
        ]
        
        if not active_stories:
            return []
        
        console.print(f"[cyan]🔍 Checking {len(active_stories)} active stories for updates...[/cyan]\n")
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[bold cyan]{task.description}[/bold cyan]"),
            console=console
        ) as progress:
            task = progress.add_task("Checking for updates...", total=len(active_stories))
            
            for story in active_stories:
                progress.update(task, description=f"Checking: {story['name']}")
                
                update_info = self.check_story_for_updates(story["tracker"])
                if update_info:
                    stories_with_updates.append(update_info)
                
                progress.update(task, advance=1)
        
        # Close browser when done
        self._close_browser()
        
        return stories_with_updates
    
    def __del__(self):
        """Cleanup browser on deletion."""
        self._close_browser()
