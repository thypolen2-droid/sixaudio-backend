import os
import asyncio
import random
import re
from pathlib import Path
from DrissionPage import ChromiumPage, ChromiumOptions
from .utils import sanitize_filename, clean_string
from .progress_tracker import ProgressTracker
from .events import EventHandler

class NovelScraper:
    """Handles the scraping logic for supported novel sites."""
    
    SITE_CONFIGS = {
        'scribblehub': {
            'name': 'ScribbleHub',
            'domain': 'scribblehub.com',
            'content_selectors': ['.chp_raw', '#chp_raw'],
            'title_selectors': ['.chapter-title', 'tag:h1'],
            'next_button_selector': 'css:.btn-wi.btn-next',
            'next_disabled_check': lambda btn: 'disabled' in (btn.attr('class') or ''),
            'url_title_pattern': r"/read/\d+-(.*?)/",
        },
        'novelbin': {
            'name': 'NovelBin',
            'domain': 'novelbin.com',
            'content_selectors': ['#chr-content', '.chr-c'],
            'title_selectors': ['#chr-content h4', 'tag:h4', 'tag:h1'],
            'next_button_selector': 'css:#next_chap',
            'next_disabled_check': lambda btn: btn.attr('disabled') is not None or '/null' in (btn.link or ''),
            'url_title_pattern': r"/b/(.*?)/chapter",
        },
        'webnovel': {
            'name': 'Webnovel',
            'domain': 'webnovel.com',
            'content_selectors': ['.cha-words', '.cha-content', '.j_cha_content', '#cha-content', '_j_cha_cnt'],
            'title_selectors': ['.cha-hd-title h1', '.cha-title', 'tag:h1'],
            'next_button_selector': 'css:a.cha-next, css:a.j_next_cha, css:a.j_next_chapter',
            'next_disabled_check': lambda btn: not btn.attr('href') or 'javascript' in (btn.attr('href') or ''),
            'url_title_pattern': r"/book/([^/]+?)_\d+/?",
        }
    }

    def __init__(self, output_dir="Library", user_data_dir=None, headless=False, fast_mode=True, event_handler: EventHandler = None):
        self.output_dir = output_dir
        self.user_data_dir = user_data_dir
        self.headless = headless
        self.fast_mode = fast_mode
        self.events = event_handler
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir)

    def set_event_handler(self, handler: EventHandler):
        self.events = handler

    def _log(self, msg, level="info"):
        if self.events:
            self.events.log(msg, level)
        else:
            print(f"[{level.upper()}] {msg}")

    def detect_site(self, url):
        """Detect which site configuration to use based on URL."""
        for site_key, config in self.SITE_CONFIGS.items():
            if config['domain'] in url:
                return site_key, config
        return None, None
    
    async def resume_scraping(self, story_dir: Path, progress_callback=None):

        """Resume scraping from a story directory using saved progress."""
        tracker = ProgressTracker(story_dir)
        
        last_url = tracker.data["scraping"]["last_chapter_url"]
        last_chapter_num = tracker.data["scraping"]["last_chapter_number"]
        
        if not last_url:
            self._log("❌ No previous scraping progress found!", "error")
            self._log("Tip: This story needs to be scraped from the beginning.", "warning")
            return
        
        self._log(f"📖 Resuming: {tracker.data['metadata']['story_title']}", "info")
        self._log(f"[dim]Last chapter: #{last_chapter_num} - {tracker.data['scraping']['last_chapter_title']}[/dim]")
        
        # Detect site from saved URL
        site_key, site_config = self.detect_site(last_url)
        if not site_config:
            self._log("❌ Could not detect site from saved URL!", "error")
            return
        
        # Initialize browser
        if self.events: self.events.log("Initializing Browser...", "info") # TODO: use status if implemented
        
        co = ChromiumOptions()
        # Set user data path first 
        if self.user_data_dir:
            co.set_user_data_path(self.user_data_dir)
            
        co.auto_port()
        co.headless(self.headless)
        co.mute(True)
        co.set_argument('--no-sandbox')
        co.set_argument('--disable-blink-features=AutomationControlled') # Hide bot signature
        co.set_user_agent('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36')
        try:
            page = ChromiumPage(co)
        except Exception as e:
            self._log(f"❌ Browser init failed: {e}", "error")
            return
        
        try:
            # Load last chapter to find next URL
            page.get(last_url)
            await asyncio.sleep(1)

            
            next_url = await self._get_next_url(page, site_config)
            
            if not next_url:
                self._log("✅ No new chapters found. Story is up to date!", "success")
                tracker.mark_complete()
                page.quit()
                return
            
            self._log(f"🆕 New chapters detected! Continuing from chapter {last_chapter_num + 1}...\n", "success")
            
            # Continue scraping from next chapter
            current_url = next_url
            chapter_index = last_chapter_num + 1
            story_dir_str = str(story_dir)
            
            while current_url:
                # TODO: use status context properly via events if needed, for now just log
                # self._log(f"Loading Chapter {chapter_index}...", "info")
                try:
                    page.get(current_url)
                    wait_time = 0.5 if self.fast_mode else 1.5
                    await asyncio.sleep(wait_time)

                except Exception as e:
                    self._log(f"❌ Network error: {e}", "error")
                    break
                
                # Get Chapter Title
                chapter_title_text = self._get_chapter_title(page, site_config, chapter_index)
                
                # Check for Resume (Skip if file exists)
                safe_chapter_title = sanitize_filename(chapter_title_text)
                filename = f"{str(chapter_index).zfill(4)}_{safe_chapter_title}.txt"
                file_path = os.path.join(story_dir_str, filename)
                
                if os.path.exists(file_path):
                    self._log(f"[dim]⏭️  Skipping (Already exists): {filename}[/dim]")
                else:
                    # Get Chapter Content
                    if await self._save_chapter_content(page, site_config, file_path, chapter_title_text):

                        self._log(f"✅ Saved: {filename}", "success")
                        
                        # Update progress after successful save
                        tracker.update_scraping(chapter_index, current_url, chapter_title_text)
                        
                        if progress_callback:
                            progress_callback({
                                "chapter_num": chapter_index,
                                "chapter_title": chapter_title_text,
                                "status": "scraping"
                            })
                    else:
                        self._log(f"⚠️ Warning: No content found for {current_url}", "warning")
                
                # Find Next Link
                next_url = await self._get_next_url(page, site_config)

                if not next_url:
                    self._log("✅ Scraping Completed! (No next link)", "success")
                    tracker.mark_complete()
                    break
                
                current_url = next_url
                chapter_index += 1
                
                # Smart Delay
                await self._wait_smart_delay()

        
        except KeyboardInterrupt:
            self._log("\n🛑 Scraping interrupted by user.", "warning")
        except Exception as e:
            self._log(f"❌ An error occurred: {e}", "error")
        finally:
            try:
                page.quit()
            except:
                pass


    async def start_scraping(self, start_url, progress_callback=None):

        """Scrapes chapters starting from start_url."""
        
        # Detect site
        site_key, site_config = self.detect_site(start_url)
        if not site_config:
            self._log("❌ Error: Unsupported website!", "error")
            self._log("Supported sites: ScribbleHub, NovelBin")
            return

        site_name = site_config['name']
        self._log(f"Starting Scraper - Site: {site_name} - Target: {start_url}", "info")

        # Initialize Browser
        if self.events: self.events.log("Initializing Browser...", "info")

        co = ChromiumOptions()
        # Set user data path first 
        if self.user_data_dir:
            co.set_user_data_path(self.user_data_dir)
            
        co.auto_port()
        co.headless(self.headless)
        co.mute(True)
        co.set_argument('--no-sandbox')
        co.set_argument('--disable-blink-features=AutomationControlled') # Hide bot signature
        co.set_user_agent('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36')
        try:
            page = ChromiumPage(co)
        except Exception as e:
            self._log(f"❌ Browser init failed: {e}", "error")
            return

        current_url = start_url
        chapter_index = 1
        story_dir = None
        progress_tracker = None
        
        try:
            while current_url:
                try:
                    page.get(current_url)
                    # Dynamic wait based on mode - much faster than fixed 2s
                    wait_time = 0.5 if self.fast_mode else 1.5
                    await asyncio.sleep(wait_time)

                except Exception as e:
                        self._log(f"❌ Network error: {e}", "error")
                        break

                # 1. Setup Story Directory (One time)
                if story_dir is None:
                    story_title = self._get_story_title(page, site_config)
                    safe_title = sanitize_filename(story_title)
                    story_dir = os.path.join(self.output_dir, safe_title)
                    
                    if not os.path.exists(story_dir):
                        os.makedirs(story_dir)
                        self._log(f"📂 Created directory: {story_dir}")
                    else:
                        self._log(f"📂 Using existing directory: {story_dir}", "success")
                    
                    # Initialize progress tracker
                    progress_tracker = ProgressTracker(Path(story_dir))
                    progress_tracker.update_metadata(story_url=start_url, site=site_key)

                # 2. Get Chapter Title
                chapter_title_text = self._get_chapter_title(page, site_config, chapter_index)
                
                # 3. Prepare file path
                safe_chapter_title = sanitize_filename(chapter_title_text)
                filename = f"{str(chapter_index).zfill(4)}_{safe_chapter_title}.txt"
                file_path = os.path.join(story_dir, filename)
                
                if not self._should_scrape(file_path):
                    self._log(f"[dim]⏭️  Skipping (Already exists): {filename}[/dim]")
                else:
                    # 4. Get Chapter Content
                    if await self._save_chapter_content(page, site_config, file_path, chapter_title_text):

                        self._log(f"✅ Saved: {filename}", "success")
                        
                        # Update progress after successful save
                        if progress_tracker:
                            progress_tracker.update_scraping(chapter_index, current_url, chapter_title_text)
                        
                        if progress_callback:
                            progress_callback({
                                "chapter_num": chapter_index,
                                "chapter_title": chapter_title_text,
                                "status": "scraping"
                            })
                    else:
                        self._log(f"⚠️ Warning: No content found for {current_url}", "warning")

                # 5. Find Next Link
                next_url = await self._get_next_url(page, site_config)

                if not next_url:
                    self._log("✅ Scraping Completed!", "success")
                    if progress_tracker:
                        progress_tracker.mark_complete()
                    break
                
                current_url = next_url
                chapter_index += 1
                
                # 6. Smart Delay
                await self._wait_smart_delay()


        except KeyboardInterrupt:
            self._log("\n🛑 Scraping interrupted by user.", "warning")
        except Exception as e:
            self._log(f"❌ An error occurred: {e}", "error")
        finally:
            try:
                page.quit() # Close browser
            except:
                pass

    def _get_story_title(self, page, site_config):
        try:
            url = page.url
            pattern = site_config.get('url_title_pattern')
            if pattern:
                match = re.search(pattern, url)
                if match:
                    slug = match.group(1)
                    # Clean up slug
                    return slug.replace('--', ' - ').replace('-', ' ').replace('_', ' ').title().strip()
            
            # Alternative: Get from page metadata or title
            page_title = page.title
            if "|" in page_title:
                return page_title.split("|")[1].strip()
            if " - " in page_title:
                parts = page_title.split(" - ")
                # Usually: [Story Title] - [Chapter Name] - [Site Name]
                if len(parts) >= 1:
                    return parts[0].strip()
            
            return "Unknown_Story"
        except:
            return "Unknown_Story"

    def _get_chapter_title(self, page, site_config, index):
        chp_title_ele = None
        timeout = 1 if self.fast_mode else 2  # Faster element detection
        for selector in site_config['title_selectors']:
            try:
                chp_title_ele = page.ele(selector, timeout=timeout)
                if chp_title_ele: break
            except: continue
        
        if chp_title_ele:
            return chp_title_ele.text.strip()
        return f"Chapter {index}"

    async def _save_chapter_content(self, page, site_config, file_path, title):
        content_ele = None
        # Increase timeout for complex sites like Webnovel
        timeout = 5 if 'webnovel.com' in page.url else (3 if self.fast_mode else 5)
        
        # Site-specific handling
        if 'scribblehub.com' in page.url:
            try:
                # Age Gate
                age_gate_btn = page.ele('css:.btn-wi.btn-confirm', timeout=1)
                if age_gate_btn:
                    self._log("🔞 Bypassing Age Gate...", "warning")
                    age_gate_btn.click()
                    await asyncio.sleep(1)
            except: pass

        if 'webnovel.com' in page.url:
            self._log("📜 Scrolling and waiting for Webnovel heavy assets...", "info")
            page.scroll.to_bottom()
            await asyncio.sleep(2) # Extra wait for lazy loading

        # Attempt extraction
        for selector in site_config['content_selectors']:
            try:
                # Use a slightly longer timeout for the primary selector
                content_ele = page.ele(selector, timeout=timeout)
                if content_ele: 
                    self._log(f"✅ Found content with selector: {selector}", "debug")
                    break
            except: continue
        
        if content_ele:
            # Domain-Specific Detailed Extraction (e.g. for Webnovel paragraph comments)
            if 'webnovel.com' in page.url:
                # Wait explicitly for text content to appear (Webnovel can be slow)
                try:
                    page.wait.ele_display('css:div.cha-paragraph, tag:p', timeout=10)
                except:
                    self._log("⏳ Page loading slowly, continuing with current DOM...", "debug")

                # Webnovel specific: Extract from <p>, <div.cha-paragraph>, or <div.dib.pr>
                # We use a set of selectors to catch various Webnovel layouts
                paragraphs = content_ele.eles('tag:p')
                if not paragraphs:
                    paragraphs = content_ele.eles('css:div.cha-paragraph')
                if not paragraphs:
                    # Last ditch effort: find any div with text that looks like a paragraph
                    paragraphs = [d for d in content_ele.eles('tag:div', timeout=1) if len(d.text.strip()) > 30]
                
                self._log(f"📝 Extracting {len(paragraphs)} paragraphs from Webnovel...", "info")
                
                if paragraphs:
                    # Filter out creators thoughts if the user just wants the story
                    valid_paras = []
                    for p in paragraphs:
                        txt = p.text.strip()
                        if not txt: continue
                        
                        # Avoid comment indicators or ads often found inside paragraphs
                        cls = p.attr('class') or ''
                        if 'creators-thought' in cls or 'ad-container' in cls:
                            continue
                            
                        # If a paragraph contains another paragraph (sometimes found in Webnovel nesting)
                        # only add unique content
                        if txt not in valid_paras:
                            valid_paras.append(txt)
                            
                    chapter_text = "\n\n".join(valid_paras)
                else:
                    self._log("⚠️ No paragraph tags found inside content container, falling back to full text.", "warning")
                    chapter_text = content_ele.text.strip()
            else:
                chapter_text = content_ele.text.strip()
            
            # Simple content cleaning
            if 'webnovel.com' in page.url:
                # Remove common footers of webnovel
                chapter_text = re.sub(r'Report .*? chapter', '', chapter_text)
                chapter_text = re.sub(r'Wait for the next .*?', '', chapter_text)

            content_len = len(chapter_text)
            if content_len > 10:
                self._log(f"💾 Saving {content_len} characters to file...", "info")
                with open(file_path, "w", encoding="utf-8") as f:
                    if title.lower() not in chapter_text[:200].lower():
                        f.write(title + "\n\n")
                    f.write(chapter_text)
                return True
            else:
                self._log(f"⚠️ Content too short ({content_len} chars). Might be empty or protected.", "warning")
        return False

    async def _get_next_url(self, page, site_config):
        """Get next chapter URL with retry logic for reliability."""
        max_retries = 3
        
        # Check for Cloudflare/Challenge
        if "Just a moment..." in page.title or page.ele('text:Verify you are human'):
            self._log("🛡️ Cloudflare detection active! Please solve the challenge in the browser window.", "warning")
            # Wait for user to solve it or for it to redirect
            for _ in range(30): # Wait up to 30s
                if "Just a moment..." not in page.title and not page.ele('text:Verify you are human'):
                    self._log("✅ Challenge cleared!", "success")
                    break
                await asyncio.sleep(1)
            else:
                self._log("⚠️ Timeout waiting for human verification.", "error")
                return None

        # For Webnovel, ensure we scroll down to make the button interactable/visible
        if 'webnovel.com' in page.url:
            page.scroll.to_bottom()
            await asyncio.sleep(0.5)

        for attempt in range(max_retries):
            try:
                timeout = 2 if attempt > 0 else (1 if self.fast_mode else 2)
                next_btn = page.ele(site_config['next_button_selector'], timeout=timeout)
                
                if next_btn:
                    # Check if button is disabled
                    if site_config['next_disabled_check'](next_btn):
                        return None
                    
                    next_url = next_btn.attr('href') or next_btn.link
                    if not next_url or "javascript" in next_url:
                        if attempt < max_retries - 1:
                            await asyncio.sleep(0.5)
                            continue
                        return None
                    
                    # Absolute URL check
                    if next_url.startswith('/'):
                        from urllib.parse import urlparse
                        o = urlparse(page.url)
                        next_url = f"{o.scheme}://{o.netloc}{next_url}"

                    return next_url
                else:
                    # Button not found, might need to wait for page load or scroll
                    if attempt < max_retries - 1:
                        page.scroll.to_bottom()
                        await asyncio.sleep(1)
                        continue
            except Exception as e:
                if attempt < max_retries - 1:
                    await asyncio.sleep(0.5)
                    continue
        return None

    async def fix_empty_chapters(self, story_dir: Path, progress_callback=None):
        """Finds and re-scrapes chapters that were saved without content."""
        if not story_dir.exists():
            return
        
        tracker = ProgressTracker(story_dir)
        story_url = tracker.data["metadata"].get("story_url")
        if not story_url:
            self._log("❌ No story URL found for recovery!", "error")
            return

        # Find .txt files smaller than 500 bytes (likely just title + newline)
        txt_files = sorted(list(story_dir.glob("*.txt")), key=lambda p: p.name)
        empty_files = []
        for f in txt_files:
            if f.stat().st_size < 500:
                empty_files.append(f)
        
        if not empty_files:
            self._log("✅ No empty chapters found!", "success")
            return

        self._log(f"🔧 Found {len(empty_files)} empty chapters! Starting recovery...", "warning")
        
        # Initialize browser once for all fixes
        co = ChromiumOptions().auto_port().headless(self.headless).mute(True)
        page = ChromiumPage(co)
        
        try:
            site_key, site_config = self.detect_site(story_url)
            
            # Since we already have the start_url, we can re-scrape the whole thing 
            # but ONLY save files that are currently empty.
            # We will reuse start_scraping but we need to pass a flag or handle logic there.
            # For now, just call start_scraping which checks _should_scrape
            
            await self.start_scraping(story_url, progress_callback=progress_callback)
            
        finally:
            page.quit()

    def _should_scrape(self, file_path):
        """Returns True if file doesn't exist or is too small (incomplete)."""
        if not os.path.exists(file_path):
            return True
        return os.path.getsize(file_path) < 500

    async def _wait_smart_delay(self):
        # Much faster delays while still being safe
        if self.fast_mode:
            delay = random.uniform(1, 3)  # Fast mode: 1-3 seconds
        else:
            delay = random.uniform(2, 4)  # Standard mode: 2-4 seconds
        
        if self.events:
             self.events.progress_start("wait", int(delay*10), f"Waiting {delay:.1f}s...")
             for _ in range(int(delay * 10)):
                await asyncio.sleep(0.1)
                self.events.progress_update("wait", advance=1)
             # self.events.progress_finish("wait") # optional
        else:
             await asyncio.sleep(delay)


# Helper function extracted to keep class clean
def get_story_title_logic(page, site_config):

    try:
        url = page.url
        pattern = site_config.get('url_title_pattern')
        if pattern:
             match = re.search(pattern, url)
             if match:
                slug = match.group(1)
                return slug.replace('--', ' - ').replace('-', ' ').title().strip()
        
        page_title = page.title
        if "|" in page_title:
             return page_title.split("|")[1].strip()
        if " - " in page_title:
             return page_title.split(" - ")[0].strip()
        return "Unknown_Story"
    except:
        return "Unknown_Story"
