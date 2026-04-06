import os
import asyncio
import random
import re
from pathlib import Path
from urllib.parse import urljoin
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
            if site_key == 'webnovel':
                await self._scrape_webnovel_catalog(
                    page,
                    last_url,
                    site_config,
                    progress_callback=progress_callback,
                    story_dir_override=str(story_dir),
                    progress_tracker=tracker
                )
                return

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
                
                page_last_chapter = chapter_index
                if 'webnovel.com' in current_url:
                    result = await self._save_webnovel_page_chapters(
                        page,
                        site_config,
                        story_dir_str,
                        chapter_index,
                        current_url,
                        progress_tracker=tracker,
                        progress_callback=progress_callback
                    )
                    if result["saved_any"]:
                        page_last_chapter = result["last_chapter_num"]
                    else:
                        self._log(f"⚠️ Warning: No content found for {current_url}", "warning")
                else:
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
                            tracker.update_scraping(
                                chapter_index,
                                current_url,
                                chapter_title_text,
                                filename=filename
                            )
                            
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
                chapter_index = page_last_chapter + 1
                
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

    async def recover_incomplete_chapters(self, story_dir: Path, progress_callback=None, tracker: ProgressTracker = None, page=None, site_config=None):
        """Revisit known chapter URLs and repair only missing or tiny chapter files."""
        tracker = tracker or ProgressTracker(story_dir)
        targets = tracker.get_recoverable_scrape_targets()
        if not targets:
            self._log("✅ No incomplete text chapters with saved URLs were found.", "success")
            return 0

        story_url = tracker.data["metadata"].get("story_url") or tracker.data["scraping"].get("last_chapter_url", "")
        site_key, detected_config = self.detect_site(story_url)
        site_config = site_config or detected_config
        if not site_config:
            self._log("❌ Could not determine site configuration for chapter recovery.", "error")
            return 0

        own_page = False
        if page is None:
            co = ChromiumOptions()
            if self.user_data_dir:
                co.set_user_data_path(self.user_data_dir)
            co.auto_port()
            co.headless(self.headless)
            co.mute(True)
            co.set_argument('--no-sandbox')
            co.set_argument('--disable-blink-features=AutomationControlled')
            co.set_user_agent('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36')
            page = ChromiumPage(co)
            own_page = True

        repaired = 0
        try:
            self._log(f"🔧 Recovering {len(targets)} incomplete chapter files from saved URLs...", "warning")
            for target in targets:
                chapter_num = target["chapter_num"]
                chapter_url = target["url"]

                try:
                    page.get(chapter_url)
                    await asyncio.sleep(0.5 if self.fast_mode else 1.5)
                except Exception as e:
                    self._log(f"❌ Failed to open chapter {chapter_num}: {e}", "error")
                    continue

                chapter_title_text = self._get_chapter_title(page, site_config, chapter_num)
                if not chapter_title_text or chapter_title_text == f"Chapter {chapter_num}":
                    chapter_title_text = target.get("title") or chapter_title_text

                safe_chapter_title = sanitize_filename(chapter_title_text)
                filename = target.get("filename") or f"{str(chapter_num).zfill(4)}_{safe_chapter_title}.txt"
                file_path = story_dir / filename

                if await self._save_chapter_content(page, site_config, str(file_path), chapter_title_text):
                    tracker.update_scraping(
                        chapter_num,
                        chapter_url,
                        chapter_title_text,
                        filename=file_path.name,
                        advance_last=False
                    )
                    repaired += 1

                    if progress_callback:
                        progress_callback({
                            "chapter_num": chapter_num,
                            "chapter_title": chapter_title_text,
                            "status": "recovered"
                        })
                else:
                    self._log(f"⚠️ Could not recover chapter {chapter_num} from saved URL.", "warning")
        finally:
            if own_page:
                try:
                    page.quit()
                except Exception:
                    pass

        return repaired

    async def _resolve_resume_point(self, page, tracker: ProgressTracker, site_config):
        """Find the next chapter URL after the last successfully scraped chapter."""
        last_url = tracker.data["scraping"].get("last_chapter_url")
        last_chapter_num = tracker.data["scraping"].get("last_chapter_number", 0)
        if not last_url or last_chapter_num <= 0:
            return None, None

        try:
            page.get(last_url)
            await asyncio.sleep(0.5 if self.fast_mode else 1.5)
        except Exception as e:
            self._log(f"⚠️ Could not reopen the last scraped chapter for resume: {e}", "warning")
            return None, None

        next_url = await self._get_next_url(page, site_config)
        if not next_url:
            return None, None
        return next_url, last_chapter_num + 1


    async def start_scraping(self, start_url, progress_callback=None):

        """Scrapes chapters starting from start_url."""
        
        # Detect site
        site_key, site_config = self.detect_site(start_url)
        if not site_config:
            self._log("❌ Error: Unsupported website!", "error")
            self._log("Supported sites: ScribbleHub, NovelBin, Webnovel")
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
            if site_key == 'webnovel':
                await self._scrape_webnovel_catalog(
                    page,
                    start_url,
                    site_config,
                    progress_callback=progress_callback
                )
                return

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
                    story_path = Path(story_dir)
                    story_already_exists = os.path.exists(story_dir)
                    
                    if not story_already_exists:
                        os.makedirs(story_dir)
                        self._log(f"📂 Created directory: {story_dir}")
                    else:
                        self._log(f"📂 Using existing directory: {story_dir}", "success")
                    
                    # Initialize progress tracker
                    progress_tracker = ProgressTracker(story_path)
                    progress_tracker.update_metadata(story_url=start_url, site=site_key)

                    if story_already_exists:
                        repaired = await self.recover_incomplete_chapters(
                            story_path,
                            progress_callback=progress_callback,
                            tracker=progress_tracker,
                            page=page,
                            site_config=site_config
                        )
                        next_url, next_index = await self._resolve_resume_point(page, progress_tracker, site_config)
                        if next_url:
                            self._log(f"🔄 Resuming from chapter {next_index} using saved progress...", "info")
                            current_url = next_url
                            chapter_index = next_index
                            continue
                        if progress_tracker.data["scraping"].get("last_chapter_url"):
                            if repaired:
                                self._log("✅ Recovered incomplete chapters. No newer chapters found.", "success")
                            else:
                                self._log("✅ No newer chapters found. Story is already up to date.", "success")
                            progress_tracker.mark_complete()
                            break

                page_last_chapter = chapter_index
                if 'webnovel.com' in current_url:
                    result = await self._save_webnovel_page_chapters(
                        page,
                        site_config,
                        story_dir,
                        chapter_index,
                        current_url,
                        progress_tracker=progress_tracker,
                        progress_callback=progress_callback
                    )
                    if result["saved_any"]:
                        page_last_chapter = result["last_chapter_num"]
                    else:
                        self._log(f"⚠️ Warning: No content found for {current_url}", "warning")
                else:
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
                                progress_tracker.update_scraping(
                                    chapter_index,
                                    current_url,
                                    chapter_title_text,
                                    filename=filename
                                )
                            
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
                chapter_index = page_last_chapter + 1
                
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
            if 'webnovel.com' in url and '/catalog' in url:
                try:
                    story_title_ele = page.ele('tag:h1', timeout=2)
                    story_title_text = (story_title_ele.text or "").strip() if story_title_ele else ""
                    if story_title_text:
                        return story_title_text
                except Exception:
                    pass

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

    def _extract_webnovel_paragraphs(self, elements):
        valid_paras = []
        seen = set()

        for p in elements:
            try:
                txt = p.text.strip()
            except Exception:
                continue

            if not txt:
                continue

            cls = p.attr('class') or ''
            if 'creators-thought' in cls or 'ad-container' in cls:
                continue

            if txt not in seen:
                seen.add(txt)
                valid_paras.append(txt)

        return valid_paras

    def _parse_chapter_number(self, title, fallback=None):
        if title:
            match = re.search(r'chapter\s+(\d+)', title, re.IGNORECASE)
            if match:
                return int(match.group(1))
        return fallback

    async def _wait_for_browser_challenge(self, page):
        if "Just a moment..." not in page.title and not page.ele('text:Verify you are human'):
            return True

        self._log("🛡️ Cloudflare detection active! Please solve the challenge in the browser window.", "warning")
        for _ in range(30):
            if "Just a moment..." not in page.title and not page.ele('text:Verify you are human'):
                self._log("✅ Challenge cleared!", "success")
                return True
            await asyncio.sleep(1)

        self._log("⚠️ Timeout waiting for human verification.", "error")
        return False

    def _extract_webnovel_book_id(self, url):
        match = re.search(r'webnovel\.com/book(?:/[^/?#]+?_(\d+)|/(\d+))', url or "", re.IGNORECASE)
        if not match:
            return None
        return match.group(1) or match.group(2)

    def _build_webnovel_catalog_url(self, url):
        book_id = self._extract_webnovel_book_id(url)
        if not book_id:
            return None
        return f"https://www.webnovel.com/book/{book_id}/catalog"

    def _normalize_webnovel_url(self, url, page_url="https://www.webnovel.com"):
        if not url:
            return ""
        if url.startswith("http://") or url.startswith("https://"):
            return url
        return urljoin(page_url, url)

    def _extract_webnovel_catalog_chapter_links(self, page, catalog_url=None):
        chapter_entries = []
        seen_urls = set()
        book_id = self._extract_webnovel_book_id(catalog_url or page.url)
        selectors = [
            'css:a.c_000.db.pr.clearfix.pt8.pb8.pr8.pl8',
            'css:a[href*="/book/"][title]'
        ]

        anchors = []
        for selector in selectors:
            try:
                anchors = page.eles(selector, timeout=2)
            except Exception:
                anchors = []
            if anchors:
                break

        for anchor in anchors:
            try:
                href = self._normalize_webnovel_url(anchor.attr('href') or '', page.url)
                title = (anchor.attr('title') or '').strip()
                text = (anchor.text or '').strip()
            except Exception:
                continue

            if not href or '/book/' not in href or href in seen_urls:
                continue

            if book_id and f"_{book_id}" not in href and f"/book/{book_id}/" not in href:
                continue

            chapter_num = None
            try:
                num_ele = anchor.ele('css:i._num', timeout=1)
                raw_num = (num_ele.text or '').strip() if num_ele else ""
                if raw_num.isdigit():
                    chapter_num = int(raw_num)
            except Exception:
                pass

            if chapter_num is None:
                num_match = re.match(r'^\s*(\d+)', text.replace('\n', ' '))
                if num_match:
                    chapter_num = int(num_match.group(1))

            if chapter_num is None:
                continue

            if not title:
                text_lines = [line.strip() for line in text.splitlines() if line.strip()]
                if len(text_lines) >= 2 and text_lines[0].isdigit():
                    title = text_lines[1]
                elif text_lines:
                    title = re.sub(r'^\d+\s*', '', text_lines[0]).strip()

            seen_urls.add(href)
            chapter_entries.append({
                "chapter_num": chapter_num,
                "title": title or f"Chapter {chapter_num}",
                "url": href,
            })

        return sorted(chapter_entries, key=lambda item: item["chapter_num"])

    def _resolve_webnovel_catalog_start_index(self, chapter_entries, progress_tracker=None, start_url=None):
        if not chapter_entries:
            return 0

        normalized_start_url = self._normalize_webnovel_url(start_url or "")
        catalog_url = self._build_webnovel_catalog_url(normalized_start_url) or ""
        last_url = ""
        last_chapter_num = 0

        if progress_tracker:
            last_url = self._normalize_webnovel_url(progress_tracker.data["scraping"].get("last_chapter_url", ""))
            last_chapter_num = int(progress_tracker.data["scraping"].get("last_chapter_number", 0) or 0)

        if last_url:
            for index, entry in enumerate(chapter_entries):
                if self._normalize_webnovel_url(entry["url"]) == last_url:
                    return index + 1

        if last_chapter_num > 0:
            for index, entry in enumerate(chapter_entries):
                if entry["chapter_num"] > last_chapter_num:
                    return index
            return len(chapter_entries)

        if normalized_start_url and normalized_start_url != catalog_url:
            for index, entry in enumerate(chapter_entries):
                if self._normalize_webnovel_url(entry["url"]) == normalized_start_url:
                    return index

        return 0

    async def _scrape_webnovel_catalog(self, page, start_url, site_config, progress_callback=None, story_dir_override=None, progress_tracker=None):
        saved_catalog_url = ""
        if progress_tracker:
            saved_catalog_url = (progress_tracker.data.get("metadata", {}) or {}).get("catalog_url", "")

        catalog_url = saved_catalog_url or self._build_webnovel_catalog_url(start_url)
        if not catalog_url:
            self._log("❌ Could not determine the Webnovel book ID from the provided URL.", "error")
            return

        try:
            page.get(catalog_url)
            await asyncio.sleep(0.8 if self.fast_mode else 1.5)
        except Exception as e:
            self._log(f"❌ Could not open the Webnovel catalog page: {e}", "error")
            return

        if not await self._wait_for_browser_challenge(page):
            return

        try:
            page.wait.ele_display('css:a.c_000.db.pr.clearfix.pt8.pb8.pr8.pl8', timeout=10)
        except Exception:
            await asyncio.sleep(1)

        story_title = self._get_story_title(page, site_config)
        safe_title = sanitize_filename(story_title)
        story_dir = story_dir_override or os.path.join(self.output_dir, safe_title)
        story_path = Path(story_dir)
        story_already_exists = story_path.exists()
        story_path.mkdir(parents=True, exist_ok=True)

        if story_already_exists:
            self._log(f"📂 Using existing directory: {story_dir}", "success")
        else:
            self._log(f"📂 Created directory: {story_dir}", "info")

        progress_tracker = progress_tracker or ProgressTracker(story_path)
        progress_tracker.update_metadata(
            story_url=start_url,
            catalog_url=catalog_url,
            site='webnovel',
            status='active'
        )

        chapter_entries = self._extract_webnovel_catalog_chapter_links(page, catalog_url)
        if not chapter_entries:
            self._log("❌ No Webnovel chapter links were found on the catalog page.", "error")
            return

        self._log(f"📚 Found {len(chapter_entries)} chapters in the Webnovel catalog.", "info")
        progress_tracker.update_catalog_index(catalog_url, chapter_entries)
        self._log("🗂️ Saved catalog URL and chapter link index to .story_progress.json.", "info")

        repaired = 0
        if story_already_exists:
            repaired = await self.recover_incomplete_chapters(
                story_path,
                progress_callback=progress_callback,
                tracker=progress_tracker,
                page=page,
                site_config=site_config
            )

        start_index = self._resolve_webnovel_catalog_start_index(
            chapter_entries,
            progress_tracker=progress_tracker,
            start_url=start_url
        )

        if start_index >= len(chapter_entries):
            if repaired:
                self._log("✅ Recovered incomplete chapters. No newer chapters were found in the catalog.", "success")
            else:
                self._log("✅ No newer chapters were found in the catalog. Story is already up to date.", "success")
            progress_tracker.mark_complete()
            return

        first_pending = chapter_entries[start_index]
        self._log(
            f"🔗 Scraping Webnovel from catalog chapter {first_pending['chapter_num']} to {chapter_entries[-1]['chapter_num']}.",
            "info"
        )

        completed = True
        for index, entry in enumerate(chapter_entries[start_index:], start=start_index):
            chapter_num = entry["chapter_num"]
            current_url = entry["url"]
            fallback_title = entry["title"] or f"Chapter {chapter_num}"

            try:
                page.get(current_url)
                await asyncio.sleep(0.5 if self.fast_mode else 1.5)
            except Exception as e:
                self._log(f"❌ Failed to open Webnovel chapter {chapter_num}: {e}", "error")
                completed = False
                break

            chapter_title_text = self._get_chapter_title(page, site_config, chapter_num)
            if not chapter_title_text or chapter_title_text == f"Chapter {chapter_num}":
                chapter_title_text = fallback_title

            safe_chapter_title = sanitize_filename(chapter_title_text)
            filename = f"{str(chapter_num).zfill(4)}_{safe_chapter_title}.txt"
            file_path = os.path.join(story_dir, filename)

            if not self._should_scrape(file_path):
                self._log(f"[dim]⏭️  Skipping (Already exists): {filename}[/dim]")
                progress_tracker.update_scraping(
                    chapter_num,
                    current_url,
                    chapter_title_text,
                    filename=filename
                )
            else:
                if await self._save_chapter_content(page, site_config, file_path, chapter_title_text):
                    self._log(f"✅ Saved: {filename}", "success")
                    progress_tracker.update_scraping(
                        chapter_num,
                        current_url,
                        chapter_title_text,
                        filename=filename
                    )

                    if progress_callback:
                        progress_callback({
                            "chapter_num": chapter_num,
                            "chapter_title": chapter_title_text,
                            "status": "scraping"
                        })
                else:
                    self._log(f"⚠️ Warning: No content found for {current_url}", "warning")

            if index < len(chapter_entries) - 1:
                await self._wait_smart_delay()

        if completed:
            progress_tracker.mark_complete()
            self._log("✅ Scraping Completed!", "success")

    def _collect_webnovel_chapter_blocks(self, page):
        selectors = [
            'css:div.chapter_content[class*=j_chapter_]',
            'css:div.chapter_content',
            'css:div[class*=j_chapter_]'
        ]

        for selector in selectors:
            try:
                blocks = page.eles(selector, timeout=1)
            except Exception:
                blocks = []
            if blocks:
                return blocks
        return []

    def _extract_webnovel_page_chapters(self, page, start_chapter_index, fallback_title=None):
        chapter_blocks = self._collect_webnovel_chapter_blocks(page)
        chapters = []
        next_fallback_num = start_chapter_index
        seen_keys = set()

        for block in chapter_blocks:
            try:
                title_ele = block.ele('css:h1.dib.mb0.fw700.fs24.lh1\\.5', timeout=1) or block.ele('tag:h1', timeout=1)
            except Exception:
                title_ele = None

            try:
                title = (title_ele.text or "").strip() if title_ele else ""
            except Exception:
                title = ""

            if not title and len(chapter_blocks) == 1 and fallback_title:
                title = fallback_title

            chapter_num = self._parse_chapter_number(title, fallback=next_fallback_num)
            if chapter_num is None:
                chapter_num = next_fallback_num
            next_fallback_num = max(next_fallback_num, chapter_num + 1)

            try:
                paragraphs = block.eles('css:div.cha-paragraph', timeout=1)
                if not paragraphs:
                    paragraphs = block.eles('tag:p')
            except Exception:
                paragraphs = []

            chapter_text = "\n\n".join(self._extract_webnovel_paragraphs(paragraphs)).strip()
            if len(chapter_text) <= 10:
                continue

            clean_title = title or f"Chapter {chapter_num}"
            dedupe_key = (chapter_num, clean_title)
            if dedupe_key in seen_keys:
                continue
            seen_keys.add(dedupe_key)

            chapters.append({
                "chapter_num": chapter_num,
                "title": clean_title,
                "text": chapter_text
            })

        return chapters

    async def _save_webnovel_page_chapters(self, page, site_config, story_dir, start_chapter_index, current_url, progress_tracker=None, progress_callback=None):
        await self._progressive_scroll_webnovel(page, site_config)

        chapters = self._extract_webnovel_page_chapters(page, start_chapter_index)
        self._log(f"📝 Extracted {len(chapters)} Webnovel chapter blocks from the page.", "info")
        if not chapters:
            return {"saved_any": False, "saved_count": 0, "last_chapter_num": start_chapter_index - 1}

        chapter_numbers = [chapter["chapter_num"] for chapter in chapters]
        if chapter_numbers:
            self._log(
                f"📚 Webnovel page contains chapters {min(chapter_numbers)}-{max(chapter_numbers)}.",
                "info"
            )

        saved_count = 0
        last_chapter_num = start_chapter_index - 1

        for chapter in chapters:
            chapter_num = chapter["chapter_num"]
            chapter_title_text = chapter["title"]
            chapter_text = re.sub(r'Report .*? chapter', '', chapter["text"])
            chapter_text = re.sub(r'Wait for the next .*?', '', chapter_text)
            safe_chapter_title = sanitize_filename(chapter_title_text)
            filename = f"{str(chapter_num).zfill(4)}_{safe_chapter_title}.txt"
            file_path = os.path.join(story_dir, filename)

            last_chapter_num = max(last_chapter_num, chapter_num)
            if not self._should_scrape(file_path):
                self._log(f"[dim]⏭️  Skipping (Already exists): {filename}[/dim]")
                if progress_tracker:
                    progress_tracker.update_scraping(
                        chapter_num,
                        current_url,
                        chapter_title_text,
                        filename=filename
                    )
                continue

            with open(file_path, "w", encoding="utf-8") as f:
                if chapter_title_text.lower() not in chapter_text[:200].lower():
                    f.write(chapter_title_text + "\n\n")
                f.write(chapter_text)

            saved_count += 1
            self._log(f"✅ Saved: {filename}", "success")

            if progress_tracker:
                progress_tracker.update_scraping(
                    chapter_num,
                    current_url,
                    chapter_title_text,
                    filename=filename
                )

            if progress_callback:
                progress_callback({
                    "chapter_num": chapter_num,
                    "chapter_title": chapter_title_text,
                    "status": "scraping"
                })

        return {
            "saved_any": saved_count > 0,
            "saved_count": saved_count,
            "last_chapter_num": last_chapter_num
        }

    def _get_webnovel_scroll_state(self, page):
        try:
            state = page.run_js("""
                return {
                    scrollTop: window.scrollY || document.documentElement.scrollTop || document.body.scrollTop || 0,
                    innerHeight: window.innerHeight || document.documentElement.clientHeight || 0,
                    scrollHeight: Math.max(
                        document.body ? document.body.scrollHeight : 0,
                        document.documentElement ? document.documentElement.scrollHeight : 0
                    )
                };
            """)
            if isinstance(state, dict):
                return {
                    "scroll_top": int(state.get("scrollTop", 0) or 0),
                    "inner_height": int(state.get("innerHeight", 0) or 0),
                    "scroll_height": int(state.get("scrollHeight", 0) or 0),
                }
        except Exception:
            pass
        return {"scroll_top": 0, "inner_height": 0, "scroll_height": 0}

    def _collect_webnovel_paragraphs(self, page, site_config=None):
        paragraphs = []

        selectors = []
        if site_config:
            selectors.extend(site_config.get('content_selectors', []))

        for selector in selectors:
            try:
                container = page.ele(selector, timeout=1)
            except Exception:
                container = None

            if not container:
                continue

            try:
                paragraphs = container.eles('tag:p')
                if not paragraphs:
                    paragraphs = container.eles('css:div.cha-paragraph')
                if not paragraphs:
                    paragraphs = [d for d in container.eles('tag:div', timeout=1) if len((d.text or '').strip()) > 30]
            except Exception:
                paragraphs = []

            if paragraphs:
                break

        if not paragraphs:
            try:
                paragraphs = page.eles('css:div.cha-paragraph', timeout=1)
            except Exception:
                paragraphs = []

        return paragraphs

    async def _progressive_scroll_webnovel(self, page, site_config=None):
        self._log("📜 Progressively scrolling Webnovel to load the full chapter...", "info")

        stable_rounds = 0
        bottom_rounds = 0
        stuck_rounds = 0
        last_count = -1
        last_scroll_height = -1
        last_scroll_top = -1
        max_rounds = 120 if self.fast_mode else 180

        for _ in range(max_rounds):
            paragraphs = self._collect_webnovel_paragraphs(page, site_config)

            count = len(self._extract_webnovel_paragraphs(paragraphs))
            scroll_state = self._get_webnovel_scroll_state(page)
            scroll_height = scroll_state["scroll_height"]
            viewport_bottom = scroll_state["scroll_top"] + scroll_state["inner_height"]
            near_bottom = scroll_height > 0 and viewport_bottom >= (scroll_height - 80)

            if count == last_count:
                stable_rounds += 1
            else:
                stable_rounds = 0
                last_count = count

            if scroll_height == last_scroll_height and near_bottom:
                bottom_rounds += 1
            else:
                bottom_rounds = 0
                last_scroll_height = scroll_height

            if near_bottom and scroll_state["scroll_top"] == last_scroll_top and count == last_count:
                stuck_rounds += 1
            else:
                stuck_rounds = 0
            last_scroll_top = scroll_state["scroll_top"]

            # Stop only after we've actually reached the end of the page and
            # both the page height and extracted text have stabilized.
            if near_bottom and count > 0 and stable_rounds >= 3 and (bottom_rounds >= 2 or stuck_rounds >= 4):
                break

            try:
                page.run_js("""
                    const current = window.scrollY || document.documentElement.scrollTop || document.body.scrollTop || 0;
                    const step = Math.max(window.innerHeight * 0.9, 650);
                    window.scrollTo(0, current + step);
                """)
            except Exception:
                page.scroll.to_bottom()

            await asyncio.sleep(0.8 if self.fast_mode else 1.2)

        try:
            page.scroll.to_bottom()
        except Exception:
            pass
        await asyncio.sleep(0.8 if self.fast_mode else 1.2)

    async def _save_chapter_content(self, page, site_config, file_path, title):
        content_ele = None
        # Increase timeout for complex sites like Webnovel
        timeout = 5 if 'webnovel.com' in page.url else (3 if self.fast_mode else 5)
        chapter_text = ""
        
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

        # Attempt extraction
        for selector in site_config['content_selectors']:
            try:
                # Use a slightly longer timeout for the primary selector
                content_ele = page.ele(selector, timeout=timeout)
                if content_ele: 
                    self._log(f"✅ Found content with selector: {selector}", "debug")
                    break
            except: continue

        if 'webnovel.com' in page.url:
            # For direct chapter URLs, try extracting immediately first.
            # If Webnovel hasn't rendered enough text yet, we scroll and retry once.
            try:
                page.wait.ele_display('css:div.cha-paragraph, tag:p', timeout=4)
            except:
                self._log("⏳ Webnovel text was not immediately visible, trying current DOM first.", "debug")

            paragraphs = self._collect_webnovel_paragraphs(page, site_config)
            self._log(f"📝 Extracting {len(paragraphs)} paragraphs from Webnovel...", "info")

            if paragraphs:
                chapter_text = "\n\n".join(self._extract_webnovel_paragraphs(paragraphs))

            if len(chapter_text) <= 10 and content_ele:
                self._log("⚠️ No paragraph tags found inside content container, falling back to full text.", "warning")
                chapter_text = content_ele.text.strip()

            if len(chapter_text) <= 10:
                self._log("📜 Webnovel chapter looks incomplete on first load, scrolling and retrying extraction...", "info")
                await self._progressive_scroll_webnovel(page, site_config)

                paragraphs = self._collect_webnovel_paragraphs(page, site_config)
                self._log(f"📝 Retry extracted {len(paragraphs)} paragraphs from Webnovel after scrolling.", "info")

                if paragraphs:
                    chapter_text = "\n\n".join(self._extract_webnovel_paragraphs(paragraphs))
                elif content_ele:
                    chapter_text = content_ele.text.strip()
        elif content_ele:
            chapter_text = content_ele.text.strip()
            
            # Simple content cleaning
        if 'webnovel.com' in page.url and chapter_text:
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
        elif 'webnovel.com' in page.url or content_ele:
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
            await self._progressive_scroll_webnovel(page, site_config)

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
                        if 'webnovel.com' in page.url:
                            await self._progressive_scroll_webnovel(page, site_config)
                        else:
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
        recovered = await self.recover_incomplete_chapters(story_dir, progress_callback=progress_callback, tracker=tracker)
        if recovered:
            self._log(f"✅ Recovered {recovered} incomplete chapters without a full restart.", "success")
            return

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

        self._log("⚠️ Empty chapters were found, but no per-chapter URL index exists yet.", "warning")
        self._log("Falling back to a full rescrape from the saved story URL.", "warning")
        
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
