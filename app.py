import asyncio
import sys
from pathlib import Path
from rich.prompt import Prompt
import os

# Import modules
from modules.ui import show_banner, create_menu_table, console, CyberpunkTheme, ConsoleEventHandler
from modules.events import RemoteEventHandler, MultiEventHandler
from modules.scraper import NovelScraper
from modules.tts import TTSManager, TTSConfig
from modules.progress_tracker import ProgressTracker
from modules.update_checker import UpdateChecker
from modules.tools import ToolsManager
from modules.utils import extract_url

class UnifiedDashboard:
    def __init__(self):
        self.root_dir = Path("Library")
        self.root_dir.mkdir(exist_ok=True)
        
        # Initialize Browser Profile Dir for Persistence (Cloudflare avoidance)
        self.browser_profile = Path(".browser_profile")
        self.browser_profile.mkdir(exist_ok=True)
        
        # Initialize Event Handler (Multi-handler: TUI + Web Remote)
        tui_handler = ConsoleEventHandler()
        remote_handler = RemoteEventHandler() # Defaults to http://localhost:8001
        self.event_handler = MultiEventHandler([tui_handler, remote_handler])
        
        # Initialize Components with Event Handler and Profile
        self.scraper = NovelScraper(
            output_dir=str(self.root_dir), 
            user_data_dir=str(self.browser_profile.absolute()),
            event_handler=self.event_handler
        )
        self.tts_manager = TTSManager(config=TTSConfig(output_dir="Library"), event_handler=self.event_handler) 
        self.tools_manager = ToolsManager(self.tts_manager)

    async def main_menu(self):
        """Displays the main menu and handles user input."""
        show_banner()
        
        # Check for updates in background
        # update_checker = UpdateChecker()
        # await update_checker.check_updates()

        while True:
            console.clear()
            show_banner()
            
            menu_items = {
                "1": "📖 Scraping Mode (Webnovel / SH / NovelBin)",
                "2": "Batch Text-to-Speech (Folder)",
                "3": "Process Single Story (Scrape + TTS)",
                "4": "Resume Last Task",
                "5": "Fix Corrupted Files (Auto-Scan)",
                "6": "🧹 Clean Text Files (Remove Promo Content)",
                "7": "📲 Mobile Sync / Web Player",
                "10": "☁️ Cloud Sync (Push to Firebase)",
                "8": "🔧 Settings (Coming Soon)",
                "9": "🛠️ Tools & Utilities",
                "0": "EXIT"
            }
            
            console.print(create_menu_table(menu_items))
            
            choice = Prompt.ask(
                "[bold cyan]SELECT OPTION[/bold cyan]", 
                choices=list(menu_items.keys()),
                default="1"
            )

            if choice == "0":
                console.print(f"[bold {CyberpunkTheme.COLOR_SECONDARY}]Goodbye, Choom! ⚡[/bold {CyberpunkTheme.COLOR_SECONDARY}]")
                break
                
            elif choice == "1":
                await self.scraping_mode()
            elif choice == "2":
                await self.batch_tts_mode()
            elif choice == "3":
                await self.full_auto_mode()
            elif choice == "4":
                await self.resume_task()
            elif choice == "5":
                await self.fix_corrupted_mode()
            elif choice == "6":
                await self.cleaner_mode()
            elif choice == "7":
                await self.flow_mobile_sync()
            elif choice == "10":
                await self.cloud_sync_mode()
            elif choice == "8":
                console.print("[dim]Feature coming in v3.1...[/dim]")
                await asyncio.sleep(1)
            elif choice == "9":
                await self.tools_manager.flow_tools_menu()

    async def cloud_sync_mode(self):
        console.clear()
        console.print(create_menu_table({}, title="CLOUD SYNC (PUSH TO FIREBASE)"))
        
        # Load env vars if they exist
        project_id = os.environ.get("GCLOUD_PROJECT_ID")
        bucket_url = os.environ.get("FIREBASE_STORAGE_BUCKET")
        
        if not project_id:
            project_id = Prompt.ask("[bold yellow]Enter Google Cloud Project ID[/bold yellow]")
        if not bucket_url:
            bucket_url = Prompt.ask("[bold yellow]Enter Firebase Storage Bucket URL[/bold yellow]", default=f"{project_id}.appspot.com")

        if not project_id:
            console.print("[red]Project ID is required.[/red]")
            await asyncio.sleep(2)
            return

        console.print(f"[cyan]Syncing Library to {bucket_url}...[/cyan]")
        
        # Use our sync script
        sync_path = Path("sync_to_cloud.py")
        if not sync_path.exists():
            console.print("[red]❌ sync_to_cloud.py not found![/red]")
            await asyncio.sleep(2)
            return

        command = [sys.executable, str(sync_path), "--project", project_id, "--bucket", bucket_url]
        
        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        with console.status("[bold magenta]📤 Pushing to Cloud...[/bold magenta]", spinner="cyber"):
            stdout, stderr = await process.communicate()
            
        if process.returncode == 0:
            console.print("[bold green]✅ Success! Your stories are live.[/bold green]")
        else:
            console.print(f"[bold red]❌ Sync Failed:[/bold red]\n{stderr.decode()}")
            
        Prompt.ask("\n[dim]Press Enter to continue...[/dim]")

    async def scraping_mode(self):
        console.clear()
        raw_input = Prompt.ask("[bold magenta]Enter Story URL[/bold magenta] (Webnovel/ScribbleHub/NovelBin)")
        if not raw_input: return
        
        url = extract_url(raw_input)
        
        if "webnovel.com" in url:
            console.print("[bold yellow]⚠️  Webnovel detected![/bold yellow]")
            console.print("[dim]Note: Scraping Webnovel requires a visible browser (non-headless) to solve potential security checks.[/dim]")
            self.scraper.headless = False
            await asyncio.sleep(1)

        await self.scraper.start_scraping(url)
        Prompt.ask("\n[dim]Press Enter to continue...[/dim]")

    async def batch_tts_mode(self):
        console.clear()
        console.print(create_menu_table({}, title="BATCH TTS MODE"))
        
        # List folders in Library/ and check progress
        all_folders = [d for d in self.root_dir.iterdir() if d.is_dir()]
        incomplete_folders = []
        
        with console.status("[bold cyan]🔍 Scanning library for pending tasks...[/bold cyan]"):
            for folder in all_folders:
                tracker = ProgressTracker(folder)
                # Ensure metadata is fresh by syncing with disk state
                tracker.update_tts()
                progress = tracker.get_tts_progress()
                # If there are text files and not all have audio, it's incomplete
                if progress["total"] > 0 and progress["converted"] < progress["total"]:
                    incomplete_folders.append(folder)
        
        incomplete_folders.sort(key=lambda x: x.name.lower())
        
        if not incomplete_folders:
            console.print("[bold green]✅ ALL STORIES ARE UP TO DATE![/bold green]")
            console.print("[dim]No stories found that require TTS conversion.[/dim]")
            await asyncio.sleep(2)
            return

        console.print(f"[cyan]Found {len(incomplete_folders)} stories with pending chapters:[/cyan]")
        for folder in incomplete_folders:
            tracker = ProgressTracker(folder)
            stats = tracker.get_tts_progress()
            console.print(f"  [dim]•[/dim] [magenta]{folder.name}[/magenta] [dim]({stats['converted']}/{stats['total']} chapters)[/dim]")
        
        console.print("\n[cyan]Select Action:[/cyan]")
        console.print("  [bold magenta]1.[/bold magenta] Process ALL Incomplete Stories")
        console.print("  [bold magenta]2.[/bold magenta] Select Specific Story to Process")
        console.print("  [bold magenta]0.[/bold magenta] BACK")
        
        sub_choice = Prompt.ask("Action", choices=["0", "1", "2"], default="0")
        
        if sub_choice == "0":
            return

        # Common mode selection for the chosen task
        console.print("\n[bold cyan]Select Speaker Mode:[/bold cyan]")
        console.print("  [magenta]1.[/magenta] Single Speaker")
        console.print("  [magenta]2.[/magenta] Dual Speaker (Narrator + Dialogue)")
        mode = Prompt.ask("Mode", choices=["1", "2"], default="1")
        use_dual = (mode == "2")

        if sub_choice == "1":
            console.print(f"\n[bold green]🚀 Processing ALL {len(incomplete_folders)} stories...[/bold green]\n")
            for folder in incomplete_folders:
                await self.tts_manager.process_folder(folder, dual_speaker=use_dual)
                await self.tts_manager.auto_combine_audios(folder)
        else:
            console.print("\n[cyan]Select Story to Process:[/cyan]")
            for i, folder in enumerate(incomplete_folders, 1):
                tracker = ProgressTracker(folder)
                stats = tracker.get_tts_progress()
                console.print(f"  [bold magenta]{i:3}.[/bold magenta] {folder.name} [dim]({stats['converted']}/{stats['total']} chapters)[/dim]")
            
            choice = Prompt.ask(
                "[bold cyan]Select Story[/bold cyan]", 
                choices=[str(i) for i in range(1, len(incomplete_folders) + 1)]
            )
            selected_folder = incomplete_folders[int(choice) - 1]
            await self.tts_manager.process_folder(selected_folder, dual_speaker=use_dual)
            await self.tts_manager.auto_combine_audios(selected_folder)
        
        Prompt.ask("\n[dim]Press Enter to continue...[/dim]")

    async def full_auto_mode(self):
        console.clear()
        console.print(create_menu_table({}, title="FULL AUTO (SCRAPE + TTS)"))
        
        raw_input = Prompt.ask("[bold magenta]Enter Story URL[/bold magenta]")
        if not raw_input: return
        
        url = extract_url(raw_input)
        
        if "webnovel.com" in url:
            self.scraper.headless = False
            console.print("[bold yellow]⚠️  Webnovel detected! (Non-headless enabled)[/bold yellow]")

        # 1. Scrape
        console.print("\n[bold cyan]STEP 1: SCRAPING[/bold cyan]")
        await self.scraper.start_scraping(url)
        
        # Determine folder name (it's created by scraper)
        # We need to find the latest folder or ask scraper for it.
        # For now, let's ask user to confirm or find the most recently modified folder in Library
        
        latest_folder = max(self.root_dir.glob("*/"), key=os.path.getmtime)
        console.print(f"\n[bold green]Detected latest folder: {latest_folder.name}[/bold green]")
        
        if Prompt.ask("Proceed with TTS for this folder?", choices=["y", "n"], default="y") == "y":
             # 2. TTS
            console.print("\n[bold cyan]STEP 2: TTS GENERATION[/bold cyan]")
            
            console.print("  [magenta]1.[/magenta] Single Speaker")
            console.print("  [magenta]2.[/magenta] Dual Speaker")
            mode = Prompt.ask("Mode", choices=["1", "2"], default="1")
            
            await self.tts_manager.process_folder(latest_folder, dual_speaker=(mode=="2"))
            await self.tts_manager.auto_combine_audios(latest_folder)
            
        Prompt.ask("\n[dim]Press Enter to continue...[/dim]")

    async def resume_task(self):
        console.clear()
        console.print(create_menu_table({}, title="RESUME TASK"))
        
        # Scraper resume logic is inside scraper.resume_scraping which takes a folder
        # We need to find folders with progress.json
        
        stories = [d for d in self.root_dir.iterdir() if d.is_dir() and (d / ".story_progress.json").exists()]
        
        if not stories:
            console.print("[yellow]No tasks with progress found.[/yellow]")
            await asyncio.sleep(2)
            return
            
        console.print("[cyan]Select Story to Resume:[/cyan]")
        for i, story in enumerate(stories, 1):
            console.print(f"  [bold magenta]{i}.[/bold magenta] {story.name}")
            
        choice = Prompt.ask("Select", choices=[str(i) for i in range(1, len(stories)+1)])
        selected_story = stories[int(choice)-1]
        
        # Check metadata to see if scraping is done
        tracker = ProgressTracker(selected_story)
        if tracker.data["metadata"]["status"] == "completed":
            recoverable = tracker.get_recoverable_scrape_targets()
            if recoverable:
                console.print(f"[yellow]Found {len(recoverable)} incomplete chapter files. Repairing them first...[/yellow]")
                await self.scraper.recover_incomplete_chapters(selected_story)
                tracker = ProgressTracker(selected_story)
            console.print("[green]Scraping marked as complete. Checking TTS...[/green]")
            # TODO: Resume processing TTS if partial?
            # For now, just trigger TTS process
            await self.tts_manager.process_folder(selected_story)
        else:
             console.print(f"[cyan]Resuming scraping for {selected_story.name}...[/cyan]")
             await self.scraper.resume_scraping(selected_story)
             
        Prompt.ask("\n[dim]Press Enter to continue...[/dim]")

    async def fix_corrupted_mode(self):
        console.clear()
        console.print(create_menu_table({}, title="FIX CORRUPTED FILES"))
        
        folders = [d for d in self.root_dir.iterdir() if d.is_dir()]
        folders.sort(key=lambda x: x.name.lower())
        
        if not folders:
            console.print("[yellow]No stories found in Library.[/yellow]")
            await asyncio.sleep(2)
            return

        console.print(f"[cyan]Found {len(folders)} folders in Library:[/cyan]")
        for folder in folders:
            console.print(f"  [dim]•[/dim] [magenta]{folder.name}[/magenta]")
        
        console.print("\n[cyan]Select Action:[/cyan]")
        console.print("  [bold magenta]1.[/bold magenta] Fix ALL Folders (Full Scan)")
        console.print("  [bold magenta]2.[/bold magenta] Select Specific Folder to Fix")
        console.print("  [bold magenta]0.[/bold magenta] BACK")
        
        sub_choice = Prompt.ask("Action", choices=["0", "1", "2"], default="0")
        
        if sub_choice == "0":
            return
            
        if sub_choice == "1":
            console.print(f"\n[bold green]🚀 Scanning ALL {len(folders)} folders for corruption...[/bold green]\n")
            for folder in folders:
                await self.tts_manager.fix_corrupted_files(folder, auto_fix=True)
        else:
            console.print("\n[cyan]Select Folder to Scan/Fix:[/cyan]")
            for i, folder in enumerate(folders, 1):
                console.print(f"  [bold magenta]{i:3}.[/bold magenta] {folder.name}")
            
            choice = Prompt.ask(
                "[bold cyan]Select Folder[/bold cyan]", 
                choices=[str(i) for i in range(1, len(folders) + 1)]
            )
            selected_folder = folders[int(choice) - 1]
            await self.tts_manager.fix_corrupted_files(selected_folder)
            
        Prompt.ask("\n[dim]Press Enter to continue...[/dim]")

    async def cleaner_mode(self):
        from modules.cleaner import clean_text
        console.clear()
        console.print(create_menu_table({}, title="TEXT CLEANER TOOL"))
        
        # List folders in Library/
        folders = [d for d in self.root_dir.iterdir() if d.is_dir()]
        folders.sort(key=lambda x: x.name.lower())
        
        if not folders:
            console.print("[yellow]No folders found in Library/.[/yellow]")
            folder_str = Prompt.ask("[bold magenta]Enter Folder Name manually[/bold magenta]", default=".")
            folder_path = self.root_dir / folder_str
        else:
            console.print("[cyan]Select Folder to Clean:[/cyan]")
            for i, folder in enumerate(folders, 1):
                console.print(f"  [bold magenta]{i}.[/bold magenta] {folder.name}")
            console.print("  [bold magenta]0.[/bold magenta] BACK")
            
            choice = Prompt.ask(
                "[bold cyan]Select[/bold cyan]", 
                choices=[str(i) for i in range(len(folders) + 1)],
                default="0"
            )
            
            if choice == "0":
                return
                
            folder_path = folders[int(choice) - 1]

        if not folder_path.exists():
            folder_path = Path(folder_path)
             
        if not folder_path.exists():
            console.print(f"[bold red]❌ Folder not found[/bold red]")
            await asyncio.sleep(2)
            return

        txt_files = list(folder_path.glob("*.txt"))
        if not txt_files:
            console.print("[yellow]No .txt files found.[/yellow]")
            return

        with console.status("[bold cyan]Cleaning files...[/bold cyan]"):
            count = 0
            for f in txt_files:
                original = f.read_text(encoding='utf-8')
                cleaned = clean_text(original)
                if cleaned != original:
                    f.write_text(cleaned, encoding='utf-8')
                    count += 1
            
        console.print(f"[bold green]✅ Cleaned {count} files.[/bold green]")
        Prompt.ask("\n[dim]Press Enter to continue...[/dim]")

    async def flow_mobile_sync(self):
        console.clear()
        show_banner()
        console.print(create_menu_table({}, title="MOBILE SERVER"))
        console.print("[dim]Starting local web server...[/dim]")
        
        from modules.server import start_server
        try:
            # This blocks until Ctrl+C
            await start_server(library_path=str(self.root_dir))
        except KeyboardInterrupt:
            pass
        
        console.print("\n[bold yellow]Server stopped.[/bold yellow]")
        Prompt.ask("[dim]Press Enter to return to menu...[/dim]")

if __name__ == "__main__":
    try:
        app = UnifiedDashboard()
        asyncio.run(app.main_menu())
    except KeyboardInterrupt:
        print("\nExiting...")
        sys.exit(0)
