"""Bridges NovelScraper events into the FastAPI task-tracking state.

The scraper reports progress through the EventHandler interface (the same one
the TUI uses). This handler updates the server's ``active_tasks`` dict and
pushes a WebSocket broadcast, so a scrape started from the web UI shows live
progress in the dashboard sidebar without any HTTP round-trips.

Called from the scraper's worker thread, so every mutation of shared state is
scheduled onto the server event loop rather than applied directly.
"""

import asyncio
import time
import uuid
from typing import Any, Awaitable, Callable, Dict, List, Optional, Set

from .events import EventHandler


class ServerEventHandler(EventHandler):
    """EventHandler that reports scraper progress to connected web clients."""

    def __init__(
        self,
        task_id: str,
        loop: asyncio.AbstractEventLoop,
        active_tasks: Dict[str, dict],
        broadcast: Callable[[Dict[str, Any]], Awaitable[None]],
        tracked_task_ids: Optional[Set[str]] = None,
        key: str = "",
    ):
        self.task_id = task_id
        self._key = key
        self._loop = loop
        self._tasks = active_tasks
        self._broadcast = broadcast
        # The scraper also emits progress for its inter-chapter delay under a
        # separate id ("wait"). Forwarding that would overwrite the scrape
        # counters, so only the ids we care about are reported.
        self._tracked = tracked_task_ids if tracked_task_ids is not None else {"scrape"}

    def _submit(self, factory: Callable[[], Awaitable[None]]):
        """Schedule a coroutine on the server loop, from any thread."""
        try:
            asyncio.run_coroutine_threadsafe(factory(), self._loop)
        except RuntimeError:
            # Loop already closed (server shutting down) - nothing to report to.
            pass

    def _store(self) -> Dict[str, Any]:
        """The dict this handler owns, either directly or under ``_key``."""
        if not self._key:
            return self._tasks  # type: ignore[return-value]
        return self._tasks[self._key]

    async def _push(self, event_type: str):
        try:
            task = self._store()
        except KeyError:
            return
        if not task:
            return
        total = task.get("total", 0) or 0
        current = task.get("current", 0) or 0
        await self._broadcast({
            "type": event_type,
            "task_id": self.task_id,
            "data": {**task, "progress": (current / total * 100) if total > 0 else 0},
        })

    async def _apply(self, mutate: Callable[[dict], None], event_type: str = "task_update"):
        """Mutate task state on the loop, then broadcast the result."""
        try:
            task = self._store()
        except KeyError:
            return
        if task is None:
            return
        mutate(task)
        task["last_update"] = time.time()
        await self._push(event_type)

    # --- EventHandler interface ---

    def _relevant(self, task_id: Optional[str]) -> bool:
        return task_id in self._tracked

    def log(self, message: str, level: str = "info"):
        # Only surface warnings/errors; per-chapter lines would flood the sidebar.
        if level in ("error", "warning"):
            self._submit(lambda: self._apply(lambda t: t.update(message=message)))

    def progress_start(self, task_id: str, total: int, description: str):
        if not self._relevant(task_id):
            return

        async def start():
            self._tasks[self._key or self.task_id] = {
                "total": total or 100,
                "current": 0,
                "message": description,
                "status": "running",
                "logs": [description] if description else [],
                "last_update": time.time(),
            }
            await self._push("task_update")

        self._submit(start)

    def progress_update(self, task_id: str, advance: int = 1, description: Optional[str] = None):
        if not self._relevant(task_id):
            return

        def mutate(task: dict):
            task["current"] = (task.get("current", 0) or 0) + advance
            if description:
                task["message"] = description
                logs = task.setdefault("logs", [])
                logs.append(description)
                if len(logs) > 20:
                    logs.pop(0)

        self._submit(lambda: self._apply(mutate))

    def progress_finish(self, task_id: str):
        if not self._relevant(task_id):
            return

        def mutate(task: dict):
            task["current"] = task.get("total", 0) or 0
            task["status"] = "completed"

        self._submit(lambda: self._apply(mutate, "task_finish"))

    def confirm(self, question: str, default: bool = True) -> bool:
        return default

    def ask(
        self,
        question: str,
        choices: Optional[List[Any]] = None,
        default: Optional[str] = None,
    ) -> str:
        return default or ""

    def status(self, message: str) -> "ServerEventHandler":
        self._submit(lambda: self._apply(lambda t: t.update(message=message)))
        return self


def make_task_id() -> str:
    """Generate a unique task id for a new scrape job."""
    return f"scrape_{int(time.time())}_{uuid.uuid4().hex[:6]}"
