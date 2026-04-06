import os
import re
import sys
import time
import random
from DrissionPage import ChromiumPage, ChromiumOptions
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
from rich.text import Text
from rich import print as rprint

# Initialize Console
console = Console()

# Site configurations
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
        'next_button_selector': 'css:a.cha-next, css:a.j_next_cha',
        'next_disabled_check': lambda btn: not btn.attr('href') or 'javascript' in (btn.attr('href') or ''),
        'url_title_pattern': r"/book/([^/]+?)_\d+/?",
    }
}

def detect_site(url):
    """Detect which site configuration to use based on URL."""
    for site_key, config in SITE_CONFIGS.items():
        if config['domain'] in url:
            return site_key, config
    return None, None

def sanitize_filename(name):
    """Sanitizes a string to be safe for filenames."""
    return re.sub(r'[<>:"/\\|?*]', '', name).strip()

def clean_string(s):
    """Normalize string for comparison."""
    return re.sub(r'[^a-zA-Z0-9]', '', s).lower()

def get_story_title(page, site_config):
    """Attempts to find the story title from the chapter page."""
    try:
        url = page.url
        pattern = site_config.get('url_title_pattern')
        if pattern:
            match = re.search(pattern, url)
            if match:
                slug = match.group(1)
                return slug.replace('--', ' - ').replace('-', ' ').replace('_', ' ').title().strip()
        
        page_title = page.title
        if "|" in page_title:
            return page_title.split("|")[1].strip()
        if " - " in page_title:
            return page_title.split(" - ")[0].strip()
        
        return "Unknown_Story"
    except Exception as e:
        console.print(f"[red]Error in title detection: {e}[/red]")
        return "Unknown_Story"

def extract_webnovel_paragraphs(elements):
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

def parse_chapter_number(title, fallback=None):
    if title:
        match = re.search(r'chapter\s+(\d+)', title, re.IGNORECASE)
        if match:
            return int(match.group(1))
    return fallback

def collect_webnovel_chapter_blocks(page):
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

def extract_webnovel_page_chapters(page, start_chapter_index, fallback_title=None):
    chapter_blocks = collect_webnovel_chapter_blocks(page)
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

        chapter_num = parse_chapter_number(title, fallback=next_fallback_num)
        if chapter_num is None:
            chapter_num = next_fallback_num
        next_fallback_num = max(next_fallback_num, chapter_num + 1)

        try:
            paragraphs = block.eles('css:div.cha-paragraph', timeout=1)
            if not paragraphs:
                paragraphs = block.eles('tag:p')
        except Exception:
            paragraphs = []

        chapter_text = "\n\n".join(extract_webnovel_paragraphs(paragraphs)).strip()
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

def get_webnovel_scroll_state(page):
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

def collect_webnovel_paragraphs(page, site_config=None):
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

def progressive_scroll_webnovel(page, site_config=None):
    console.print("[cyan]Progressively scrolling Webnovel to load the full chapter...[/cyan]")

    stable_rounds = 0
    bottom_rounds = 0
    stuck_rounds = 0
    last_count = -1
    last_scroll_height = -1
    last_scroll_top = -1

    for _ in range(120):
        paragraphs = collect_webnovel_paragraphs(page, site_config)

        count = len(extract_webnovel_paragraphs(paragraphs))
        scroll_state = get_webnovel_scroll_state(page)
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
        time.sleep(0.8)

    try:
        page.scroll.to_bottom()
    except Exception:
        pass
    time.sleep(0.8)

def scrape_chain(start_url):
    """Scrapes chapters starting from start_url using DrissionPage."""
    
    # Detect site
    site_key, site_config = detect_site(start_url)
    if not site_config:
        console.print("[bold red]Error: Unsupported website![/bold red]")
        console.print("Supported sites: ScribbleHub, NovelBin")
        return
    
    site_name = site_config['name']
    console.print(Panel(
        f"[bold blue]Starting Scraper[/bold blue]\n"
        f"Site: [bold cyan]{site_name}[/bold cyan]\n"
        f"Target: [u]{start_url}[/u]", 
        title=f"{site_name} Scraper"
    ))

    # Initialize Browser
    with console.status("[bold green]Initializing Browser...[/bold green]", spinner="dots"):
        co = ChromiumOptions()
        co.auto_port()
        co.headless(False)  # Run non-headless for easier bypass
        co.mute(True)
        co.set_argument('--no-sandbox')
        co.set_user_agent('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
        page = ChromiumPage(co)
    
    current_url = start_url
    chapter_index = 1
    story_dir = None
    
    try:
        while current_url:
            # console.print(f"[cyan]Loading:[/cyan] {current_url}")
            
            with console.status(f"[bold yellow]Loading Chapter {chapter_index}...[/bold yellow]", spinner="earth"):
                page.get(current_url)
                time.sleep(2)  # Wait for page to load
            
            # 1. Setup Story Directory (One time)
            if story_dir is None:
                detected_title = get_story_title(page, site_config)
                
                base_dir = os.path.dirname(os.path.abspath(__file__))
                
                # Check for existing directory with similar name
                detected_clean = clean_string(detected_title)
                existing_dirs = [d for d in os.listdir(base_dir) if os.path.isdir(os.path.join(base_dir, d))]
                
                matched_dir = None
                for d in existing_dirs:
                    if clean_string(d) == detected_clean:
                        matched_dir = d
                        break
                
                if matched_dir:
                    story_title = matched_dir
                    console.print(f"[green]Found existing directory:[/green] [bold]{story_title}[/bold]")
                else:
                    story_title = detected_title
                    console.print(f"[green]Detected New Story:[/green] [bold]{story_title}[/bold]")

                safe_title = sanitize_filename(story_title)
                story_dir = os.path.join(base_dir, safe_title)
                
                if not os.path.exists(story_dir):
                    os.makedirs(story_dir)
                    console.print(f"[blue]Created directory:[/blue] {story_dir}")

            page_last_chapter = chapter_index
            if 'webnovel.com' in current_url:
                progressive_scroll_webnovel(page, site_config)
                chapters = extract_webnovel_page_chapters(page, chapter_index)
                console.print(f"[cyan]Extracted {len(chapters)} Webnovel chapter blocks from the page.[/cyan]")
                if chapters:
                    chapter_numbers = [chapter["chapter_num"] for chapter in chapters]
                    console.print(f"[cyan]Webnovel page contains chapters {min(chapter_numbers)}-{max(chapter_numbers)}.[/cyan]")
                if not chapters:
                    console.print(f"[bold red]Warning: No content found for {current_url}[/bold red]")
                for chapter in chapters:
                    chapter_num = chapter["chapter_num"]
                    chapter_title_text = chapter["title"]
                    chapter_text = re.sub(r'Report .*? chapter', '', chapter["text"])
                    chapter_text = re.sub(r'Wait for the next .*?', '', chapter_text)
                    safe_chapter_title = sanitize_filename(chapter_title_text)
                    filename = f"{str(chapter_num).zfill(4)}_{safe_chapter_title}.txt"
                    file_path = os.path.join(story_dir, filename)
                    page_last_chapter = max(page_last_chapter, chapter_num)

                    if os.path.exists(file_path):
                        console.print(f"[dim]Skipping (Already exists): {filename}[/dim]")
                        continue

                    with open(file_path, "w", encoding="utf-8") as f:
                        if chapter_title_text.lower() not in chapter_text[:200].lower():
                            f.write(chapter_title_text + "\n\n")
                        f.write(chapter_text)
                    console.print(f"[bold green]Saved:[/bold green] {filename}")
            else:
                # 2. Get Chapter Title
                chp_title_ele = None
                for selector in site_config['title_selectors']:
                    try:
                        chp_title_ele = page.ele(selector, timeout=5)
                        if chp_title_ele:
                            break
                    except Exception as e:
                        # Handle page disconnection or element not found
                        if "PageDisconnectedError" in str(type(e).__name__):
                            console.print(f"[bold red]Page disconnected while getting title. Stopping scraper.[/bold red]")
                            return
                        continue
                
                chapter_title_text = f"Chapter {chapter_index}"
                if chp_title_ele:
                    chapter_title_text = chp_title_ele.text.strip()
                
                # 3. Check for Resume (Skip if file exists)
                safe_chapter_title = sanitize_filename(chapter_title_text)
                filename = f"{str(chapter_index).zfill(4)}_{safe_chapter_title}.txt"
                file_path = os.path.join(story_dir, filename)
                
                if os.path.exists(file_path):
                    console.print(f"[dim]Skipping (Already exists): {filename}[/dim]")
                else:
                    # 4. Get Chapter Content
                    content_ele = None
                    chapter_text = ""
                    for selector in site_config['content_selectors']:
                        try:
                            content_ele = page.ele(selector, timeout=5)
                            if content_ele:
                                break
                        except Exception as e:
                            if "PageDisconnectedError" in str(type(e).__name__):
                                console.print(f"[bold red]Page disconnected while getting content. Stopping scraper.[/bold red]")
                                return
                            continue
                    
                    if content_ele:
                        chapter_text = content_ele.text.strip()

                    if chapter_text:
                        with open(file_path, "w", encoding="utf-8") as f:
                            f.write(chapter_title_text + "\n\n")
                            f.write(chapter_text)
                        console.print(f"[bold green]Saved:[/bold green] {filename}")
                    else:
                        console.print(f"[bold red]Warning: No content found for {current_url}[/bold red]")

            # 5. Find Next Link
            try:
                next_btn = page.ele(site_config['next_button_selector'], timeout=5)
            except Exception as e:
                if "PageDisconnectedError" in str(type(e).__name__):
                    console.print(f"[bold red]Page disconnected while finding next button. Stopping scraper.[/bold red]")
                    return
                next_btn = None
            
            # Check if next button exists and is not disabled
            if next_btn:
                # Check if button is disabled (site-specific check)
                if site_config['next_disabled_check'](next_btn):
                    console.print(Panel(
                        "[bold green]Scraping Completed![/bold green]\n"
                        "Next button is disabled (end of story).", 
                        border_style="green"
                    ))
                    break
                
                # Check if button has a valid link
                next_url = next_btn.link
                if not next_url or "javascript" in next_url:
                    console.print("[bold red]End of story (Next link invalid).[/bold red]")
                    break
                
                current_url = next_url
                chapter_index = page_last_chapter + 1
                
                # 6. Smart Delay with Progress Bar
                delay = random.uniform(5, 10)
                # console.print(f"Waiting {delay:.2f}s...")
                
                # Using a transient progress bar for the delay
                with Progress(
                    SpinnerColumn(),
                    TextColumn("[progress.description]{task.description}"),
                    BarColumn(),
                    transient=True
                ) as progress:
                    task = progress.add_task(f"[cyan]Waiting safe delay...[/cyan]", total=int(delay*10))
                    
                    steps = int(delay * 10)
                    for _ in range(steps):
                        time.sleep(0.1)
                        progress.update(task, advance=1)
                
            else:
                console.print(Panel(
                    "[bold green]Scraping Completed![/bold green]\n"
                    "No 'Next' button found.", 
                    border_style="green"
                ))
                break
                
    except KeyboardInterrupt:
        console.print("\n[bold yellow]Scraping interrupted by user.[/bold yellow]")
    except Exception as e:
        console.print(f"[bold red]An error occurred:[/bold red] {e}")
        import traceback
        console.print(traceback.format_exc())
    finally:
        console.print("[bold blue]Process Finished.[/bold blue]")

if __name__ == "__main__":
    console.print(Panel.fit("Multi-Site Novel Scraper (ScribbleHub & NovelBin)", border_style="blue"))
    if len(sys.argv) > 1:
        start_url = sys.argv[1]
        scrape_chain(start_url)
    else:
        start_url = console.input("[bold yellow]Please enter the FIRST chapter URL:[/bold yellow] ").strip()
        if start_url:
            scrape_chain(start_url)
        else:
            console.print("[red]No URL provided.[/red]")
