import asyncio
import sys
from pathlib import Path
from rich.prompt import Prompt

# Import modules
from modules.ui import show_banner, create_menu_table, console, CyberpunkTheme, ConsoleEventHandler
from modules.scraper import NovelScraper
from modules.tts import TTSManager, TTSConfig
from modules.progress_tracker import ProgressTracker
from modules.update_checker import UpdateChecker
from modules.tools import ToolsManager

class UnifiedDashboard:
    def __init__(self):
        self.root_dir = Path("Library")
        self.root_dir.mkdir(exist_ok=True)
        
        # Initialize Event Handler for TUI
        self.event_handler = ConsoleEventHandler()
        
        # Initialize Components with Event Handler
        self.scraper = NovelScraper(output_dir=str(self.root_dir), event_handler=self.event_handler)
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
                "1": "📖 Scraping Mode (ScribbleHub / NovelBin)",
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
        console.print(create_menu_table({}, title="SCRAPING MODE"))
        
        url = Prompt.ask("[bold magenta]Enter Story URL[/bold magenta] (ScribbleHub/NovelBin)")
        if not url: return

        # Optional: Ask for headless mode
        # headless = Confirm.ask("Run Headless?", default=True)
        # self.scraper.headless = headless
        
        await self.scraper.start_scraping(url)
        Prompt.ask("\n[dim]Press Enter to continue...[/dim]")

    async def batch_tts_mode(self):
        console.clear()
        console.print(create_menu_table({}, title="BATCH TTS MODE"))
        
        # List folders in Library/
        folders = [d for d in self.root_dir.iterdir() if d.is_dir()]
        folders.sort(key=lambda x: x.name.lower())
        
        if not folders:
            console.print("[yellow]No folders found in Library/.[/yellow]")
            folder_str = Prompt.ask("[bold magenta]Enter Folder Name manually[/bold magenta]", default=".")
            folder_path = self.root_dir / folder_str
        else:
            console.print("[cyan]Select Folder to Process:[/cyan]")
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
            # Support absolute paths as fallback
            if not folder_path.exists():
                folder_path = Path(folder_path)
            
        if not folder_path.exists():
            console.print(f"[bold red]❌ Folder not found: {folder_path}[/bold red]")
            await asyncio.sleep(2)
            return

        console.print("\n[bold cyan]Select Mode:[/bold cyan]")
        console.print("  [magenta]1.[/magenta] Single Speaker")
        console.print("  [magenta]2.[/magenta] Dual Speaker (Narrator + Dialogue)")
        
        mode = Prompt.ask("Mode", choices=["1", "2"], default="1")
        use_dual = (mode == "2")
        
        await self.tts_manager.process_folder(folder_path, dual_speaker=use_dual)
        await self.tts_manager.auto_combine_audios(folder_path)
        
        Prompt.ask("\n[dim]Press Enter to continue...[/dim]")

    async def full_auto_mode(self):
        console.clear()
        console.print(create_menu_table({}, title="FULL AUTO (SCRAPE + TTS)"))
        
        url = Prompt.ask("[bold magenta]Enter Story URL[/bold magenta]")
        if not url: return

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
        
        stories = [d for d in self.root_dir.iterdir() if d.is_dir() and (d / "progress.json").exists()]
        
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
        if tracker.data["scraping"]["status"] == "completed":
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
        
        folder_str = Prompt.ask("[bold magenta]Enter Folder Name in Library/[/bold magenta]", default=".")
        folder_path = self.root_dir / folder_str
         
        if not folder_path.exists():
            folder_path = Path(folder_str)

        if not folder_path.exists():
            console.print(f"[bold red]❌ Folder not found[/bold red]")
            await asyncio.sleep(2)
            return

        await self.tts_manager.fix_corrupted_files(folder_path)
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
