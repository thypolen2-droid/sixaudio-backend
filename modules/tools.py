import sys
import os
import asyncio
from pathlib import Path
from .tts import TTSManager
from .ui import create_menu_table, console # Keep console for menu display for now, or move menu to UI? 
# Actually, tools.py is part of the TUI flow, so it's okay to use TUI elements for the MENU, 
# but the operations should use the event handler. 
# However, for consistency, we should try to use the event handler for everything including prompts.

class ToolsManager:
    """
    Manages utility tools migrated from the legacy main.py.
    """
    def __init__(self, tts_manager: TTSManager):
        self.tts_manager = tts_manager
        self.events = self.tts_manager.events # Shortcut

    async def flow_tools_menu(self):
        """Display the Tools & Utilities menu."""
        while True:
            # We still use console for the menu layout itself as that's specific to TUI
            console.clear()
            console.print(create_menu_table({}, title="TOOLS & UTILITIES"))
            
            menu_items = {
                "1": "📝 Paste Text Mode (Direct Input)",
                "2": "📄 Process Single File (story.txt)",
                "3": "📁 Process Arbitrary Folder",
                "4": "🔧 Fix Corrupted Audio (Manual Path)",
                "5": "🎵 Combine Audio Files (Manual Path)",
                "0": "🔙 Back to Main Menu"
            }
            
            console.print(create_menu_table(menu_items))
            
            if self.events:
                choice = self.events.ask("[bold cyan]SELECT OPTION[/bold cyan]", choices=list(menu_items.keys()), default="1")
            else:
                 # Fallback if no events attached (shouldn't happen in app.py)
                 choice = input("Select Option: ")

            if choice == "0":
                break
            elif choice == "1":
                await self.paste_text_mode()
            elif choice == "2":
                await self.process_single_file()
            elif choice == "3":
                await self.process_arbitrary_folder()
            elif choice == "4":
                await self.fix_corrupted_manual()
            elif choice == "5":
                await self.combine_audio_manual()

    async def paste_text_mode(self):
        """Process pasted text."""
        console.clear()
        console.print(create_menu_table({}, title="PASTE TEXT MODE"))
        console.print("[dim]Paste your text below. Enter 'END' on a new line to finish, or Press Ctrl+Z (Windows) / Ctrl+D (Linux/Mac) then Enter.[/dim]\n")
        
        lines = []
        try:
            print(">>> ", end='', flush=True) 
            while True:
                line = sys.stdin.readline()
                if not line:
                    break
                if line.strip() == "END":
                    break
                lines.append(line)
        except KeyboardInterrupt:
            pass
        
        text = "".join(lines).strip()
        
        if not text:
            if self.events: self.events.log("⚠️  No text provided", "warning")
            await asyncio.sleep(1.5)
            return
        
        if self.events: self.events.log(f"Captured {len(text)} characters.", "success")
        
        filename = "pasted_output.mp3"
        if self.events:
             filename = self.events.ask("[bold magenta]Output filename[/bold magenta]", default="pasted_output.mp3")
        
        if not filename.endswith(".mp3"):
            filename += ".mp3"
        
        # Determine output directory
        output_dir = "output"
        if self.events:
            output_dir = self.events.ask("[bold magenta]Output directory[/bold magenta]", default="output")
            
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        # Update config temporarily
        original_dir = self.tts_manager.config.output_dir
        self.tts_manager.config.output_dir = output_path
        
        try:
            if self.events: self.events.progress_start("paste_task", 100, "Converting...")
            
            await self.tts_manager.convert_text(text, filename)
            
            if self.events: 
                self.events.progress_update("paste_task", completed=100)
                self.events.log(f"Success: {filename}", "success")
                self.events.log(f"[dim]Saved to: {output_path.absolute()}[/dim]")
            
        except Exception as e:
             if self.events: self.events.log(f"Conversion failed: {e}", "error")
        finally:
            self.tts_manager.config.output_dir = original_dir
            if self.events: self.events.ask("\n[dim]Press Enter to continue...[/dim]")

    async def process_single_file(self):
        """Process a single text file."""
        console.clear()
        console.print(create_menu_table({}, title="SINGLE FILE MODE"))
        
        file_path_str = "story.txt"
        if self.events:
            file_path_str = self.events.ask("[bold magenta]Enter file path (e.g., story.txt)[/bold magenta]", default="story.txt")
        
        file_path = Path(file_path_str)
        
        if not file_path.exists():
            if self.events: self.events.log(f"File not found: {file_path}", "error")
            await asyncio.sleep(2)
            return
            
        try:
            text = file_path.read_text(encoding='utf-8').strip()
            if not text:
                if self.events: self.events.log("File is empty", "warning")
                return
            
            output_filename = f"{file_path.stem}.mp3"
            
            if self.events: self.events.log(f"Converting {file_path.name}...")
            await self.tts_manager.convert_text(text, output_filename)
            if self.events: self.events.log(f"Success: {output_filename}", "success")
            
        except Exception as e:
            if self.events: self.events.log(f"Error: {e}", "error")
            
        if self.events: self.events.ask("\n[dim]Press Enter to continue...[/dim]")

    async def process_arbitrary_folder(self):
        """Process any folder containing .txt files."""
        console.clear()
        console.print(create_menu_table({}, title="BATCH FOLDER MODE"))
        
        folder_str = "."
        if self.events:
            folder_str = self.events.ask("[bold magenta]Enter folder path[/bold magenta]", default=".")
        
        folder_path = Path(folder_str)
        
        if not folder_path.exists() or not folder_path.is_dir():
            if self.events: self.events.log(f"Invalid directory: {folder_path}", "error")
            await asyncio.sleep(2)
            return

        # Use dual speaker mode?
        console.print("\n[bold cyan]Select Mode:[/bold cyan]")
        console.print("  [magenta]1.[/magenta] Single Speaker")
        console.print("  [magenta]2.[/magenta] Dual Speaker (Narrator + Dialogue)")
        
        mode = "1"
        if self.events:
             mode = self.events.ask("Mode", choices=["1", "2"], default="1")
             
        use_dual = (mode == "2")
        
        await self.tts_manager.process_folder(folder_path, dual_speaker=use_dual)
        if self.events: self.events.ask("\n[dim]Press Enter to continue...[/dim]")

    async def fix_corrupted_manual(self):
        """Fix files in a user-specified folder."""
        console.clear()
        console.print(create_menu_table({}, title="FIX CORRUPTED FILES"))
        
        folder_str = "."
        if self.events:
            folder_str = self.events.ask("[bold magenta]Enter folder path containing 'Audios' subfolder[/bold magenta]", default=".")
            
        folder_path = Path(folder_str)
        
        await self.tts_manager.fix_corrupted_files(folder_path)
        if self.events: self.events.ask("\n[dim]Press Enter to continue...[/dim]")

    async def combine_audio_manual(self):
        """Combine files in a user-specified folder."""
        console.clear()
        console.print(create_menu_table({}, title="COMBINE AUDIO"))
        
        folder_str = "."
        if self.events:
            folder_str = self.events.ask("[bold magenta]Enter folder path containing 'Audios' subfolder[/bold magenta]", default=".")
        
        folder_path = Path(folder_str)
        
        await self.tts_manager.auto_combine_audios(folder_path)
        if self.events: self.events.ask("\n[dim]Press Enter to continue...[/dim]")
