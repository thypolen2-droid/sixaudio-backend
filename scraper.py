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
        # Priority 1: Extract from URL slug if available (Most reliable)
        url = page.url
        pattern = site_config['url_title_pattern']
        match = re.search(pattern, url)
        if match:
            slug = match.group(1)
            title = slug.replace('--', ' - ').replace('-', ' ').title()
            return title.strip()
        
        # Priority 2: Page Title fallback
        page_title = page.title
        if "|" in page_title:
            parts = page_title.split("|")
            if len(parts) >= 2:
                return parts[1].strip()
        
        # Priority 3: First part of page title
        if " - " in page_title:
            return page_title.split(" - ")[0].strip()
        
        return "Unknown_Story"
    except Exception as e:
        console.print(f"[red]Error in title detection: {e}[/red]")
        return "Unknown_Story"

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
        co.auto_port()  # Auto-assign a port and launch new browser
        co.headless(False)  # Run non-headless to pass Cloudflare more easily
        co.mute(True)  # Mute audio
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
                chapter_index += 1
                
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
