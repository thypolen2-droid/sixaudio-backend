import requests
import json
import threading
from abc import ABC, abstractmethod
from typing import Optional, Any, List

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

class MultiEventHandler(EventHandler):
    """Dispatches events to multiple handlers."""
    def __init__(self, handlers: List[EventHandler]):
        self.handlers = [h for h in handlers if h is not None]

    def log(self, message: str, level: str = "info"):
        for h in self.handlers:
            h.log(message, level)

    def progress_start(self, task_id: str, total: int, description: str):
        for h in self.handlers:
            h.progress_start(task_id, total, description)

    def progress_update(self, task_id: str, advance: int = 1, description: str = None):
        for h in self.handlers:
            h.progress_update(task_id, advance, description)

    def progress_finish(self, task_id: str):
        for h in self.handlers:
            h.progress_finish(task_id)

    def confirm(self, question: str, default: bool = True) -> bool:
        # For interactions, use the first handler that returns a value (or all if needed)
        # Usually only the TUI handler responds.
        for h in self.handlers:
            res = h.confirm(question, default)
            if res is not None:
                return res
        return default

    def ask(self, question: str, choices: list = None, default: str = None) -> str:
        for h in self.handlers:
            res = h.ask(question, choices, default)
            if res is not None:
                return res
        return default

    def status(self, message: str):
        # We need a proxy for context managers
        return MultiStatusProxy(self.handlers, message)

class MultiStatusProxy:
    def __init__(self, handlers, message):
        self.proxies = [h.status(message) for h in handlers]
    
    def __enter__(self):
        for p in self.proxies:
            if hasattr(p, '__enter__'): p.__enter__()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        for p in self.proxies:
            if hasattr(p, '__exit__'): p.__exit__(exc_type, exc_val, exc_tb)

class RemoteEventHandler(EventHandler):
    """Sends events to a remote server's tracking API."""
    def __init__(self, server_url: str = "http://localhost:8001"):
        self.server_url = server_url.rstrip('/')
        self.is_active = self._check_connection()
        if not self.is_active:
            print(f"📡 RemoteEventHandler: Server not found at {self.server_url}. Local only mode.")

    def _check_connection(self) -> bool:
        try:
            # Simple heartbeat check
            response = requests.get(f"{self.server_url}/api/library/status", timeout=1.0)
            return response.status_code == 200
        except Exception:
            return False

    def _send_update(self, endpoint: str, data: dict):
        if not self.is_active:
            return
        
        # Fire and forget (mostly) - using a thread for the actual network call to not block worker
        def do_request():
            try:
                requests.post(f"{self.server_url}/api/internal/task/{endpoint}", json=data, timeout=1.0)
            except Exception:
                pass # Silent fail for remote reporting

        threading.Thread(target=do_request, daemon=True).start()

    def log(self, message: str, level: str = "info"):
        # We only send logs if they are important or combined with progress
        pass

    def progress_start(self, task_id: str, total: int, description: str):
        self._send_update("start", {
            "task_id": task_id,
            "total": total,
            "message": description,
            "status": "running"
        })

    def progress_update(self, task_id: str, advance: int = 1, description: str = None):
        self._send_update("update", {
            "task_id": task_id,
            "advance": advance,
            "message": description
        })

    def progress_finish(self, task_id: str):
        self._send_update("finish", {
            "task_id": task_id,
            "status": "completed"
        })

    def confirm(self, question: str, default: bool = True) -> bool:
        return None  # Cannot interact remotely yet

    def ask(self, question: str, choices: list = None, default: str = None) -> str:
        return None

    def status(self, message: str):
        # We can report status as a "static" progress update
        self._send_update("update", {
            "task_id": "status",
            "message": message,
            "status": "active"
        })
        return self # No nested proxy needed yet
