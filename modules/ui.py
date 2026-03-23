from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box
from rich.align import Align
from rich.text import Text
from rich.layout import Layout
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeRemainingColumn
from rich.prompt import Prompt, Confirm

# Import the abstract base class
from .events import EventHandler

console = Console()

class CyberpunkTheme:
    """Centralized theme configuration."""
    COLOR_PRIMARY = "cyan"
    COLOR_SECONDARY = "magenta"
    COLOR_SUCCESS = "green"
    COLOR_WARNING = "yellow"
    COLOR_ERROR = "red"
    BORDER_STYLE = "cyan"
    BOX_STYLE = box.HEAVY

def create_header(title="CYBERPUNK TTS DASHBOARD"):
    """Creates a standardized header panel."""
    grid = Table.grid(expand=True)
    grid.add_column(justify="center", ratio=1)
    grid.add_row(f"[bold {CyberpunkTheme.COLOR_SECONDARY}]⚡ {title} ⚡[/bold {CyberpunkTheme.COLOR_SECONDARY}]")
    return Panel(
        grid, 
        style=f"on black", 
        border_style=CyberpunkTheme.BORDER_STYLE
    )

def show_banner():
    """Display the large ASCII banner."""
    banner = """
[bold cyan]╔═══════════════════════════════════════════════════════════════╗[/bold cyan]
[bold cyan]║[/bold cyan]  [bold magenta]▀█▀ ▀█▀ █▀▀   █▄ █ █▀▀ █ █ █▀█ ▄▀█ █     [/bold magenta]  [bold cyan]║[/bold cyan]
[bold cyan]║[/bold cyan]  [bold magenta] █   █  ▄▄█   █ ▀█ ██▄ █▄█ █▀▄ █▀█ █▄▄   [/bold magenta]  [bold cyan]║[/bold cyan]
[bold cyan]║[/bold cyan]  [bold green]█ █ █▀█ █ █▀▀ █▀▀   █▀ █ █ █▄ █ ▀█▀ █ █   [/bold green]  [bold cyan]║[/bold cyan]
[bold cyan]║[/bold cyan]  [bold green]▀▄▀ █▄█ █ █▄▄ ██▄   ▄█ ▀▄▀ █ ▀█  █  █▀█   [/bold green]  [bold cyan]║[/bold cyan]
[bold cyan]║[/bold cyan]                                                             [bold cyan]║[/bold cyan]
[bold cyan]║[/bold cyan]  [bold yellow]⚡ CYBERPUNK EDITION v3.0 ⚡[/bold yellow]  [dim]Unified System[/dim]       [bold cyan]║[/bold cyan]
[bold cyan]╚═══════════════════════════════════════════════════════════════╝[/bold cyan]
"""
    console.print(banner)

def create_menu_table(items, title="MAIN MENU"):
    """Creates a menu table from a dict of {key: description}."""
    table = Table(show_header=False, box=CyberpunkTheme.BOX_STYLE, border_style=CyberpunkTheme.BORDER_STYLE, expand=True)
    table.add_column("Key", style=f"bold {CyberpunkTheme.COLOR_SECONDARY}", justify="center", width=4)
    table.add_column("Action", style="bold white")
    
    for key, desc in items.items():
        table.add_row(key, desc)
        
    return Panel(
        table,
        title=f"[bold {CyberpunkTheme.COLOR_SUCCESS}]⚡ {title} ⚡[/bold {CyberpunkTheme.COLOR_SUCCESS}]",
        border_style=CyberpunkTheme.COLOR_SUCCESS,
        box=box.DOUBLE
    )

class ConsoleEventHandler(EventHandler):
    """Handles events using the Rich TUI."""
    
    def __init__(self):
        self.progress = None
        self.tasks = {}

    def log(self, message: str, level: str = "info"):
        """Log a message to the console."""
        if level == "error":
            console.print(f"[bold red]❌ {message}[/bold red]")
        elif level == "warning":
            console.print(f"[bold yellow]⚠️  {message}[/bold yellow]")
        elif level == "success":
             console.print(f"[bold green]✅ {message}[/bold green]")
        else:
            console.print(message)

    def progress_start(self, task_id: str, total: int, description: str):
        if self.progress is None:
             self.progress = Progress(
                SpinnerColumn(style="cyan"),
                TextColumn("[bold cyan]{task.description}[/bold cyan]"),
                BarColumn(complete_style="green"),
                TextColumn("[bold magenta]{task.completed}/{task.total}[/bold magenta]"),
                TimeRemainingColumn(),
                console=console
             )
             self.progress.start()
        
        self.tasks[task_id] = self.progress.add_task(description, total=total)

    def progress_update(self, task_id: str, advance: int = 1, description: str = None):
        if self.progress and task_id in self.tasks:
            self.progress.update(self.tasks[task_id], advance=advance, description=description)

    def progress_finish(self, task_id: str):
        # We don't auto-stop progress here to allow multiple tasks
        pass

    def stop_progress(self):
        """Stop the progress display."""
        if self.progress:
            self.progress.stop()
            self.progress = None
            self.tasks = {}

    def confirm(self, question: str, default: bool = True) -> bool:
        return Confirm.ask(question, default=default, console=console)

    def ask(self, question: str, choices: list = None, default: str = None) -> str:
        return Prompt.ask(question, choices=choices, default=default, console=console)

    def status(self, message: str):
        return console.status(message, spinner="dots")
