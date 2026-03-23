from abc import ABC, abstractmethod
from typing import Optional, Any

class EventHandler(ABC):
    """Abstract base class for handling events (logs, progress, input)."""

    @abstractmethod
    def log(self, message: str, level: str = "info"):
        """Log a message."""
        pass

    @abstractmethod
    def progress_start(self, task_id: str, total: int, description: str):
        """Start a progress task."""
        pass

    @abstractmethod
    def progress_update(self, task_id: str, advance: int = 1, description: str = None):
        """Update a progress task."""
        pass

    @abstractmethod
    def progress_finish(self, task_id: str):
        """Finish a progress task."""
        pass

    @abstractmethod
    def confirm(self, question: str, default: bool = True) -> bool:
        """Ask for user confirmation."""
        pass
        
    @abstractmethod
    def ask(self, question: str, choices: list = None, default: str = None) -> str:
        """Ask for user input."""
        pass

    @abstractmethod
    def status(self, message: str):
         """Context manager for showing status/spinner."""
         pass
