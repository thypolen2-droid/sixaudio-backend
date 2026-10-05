"""Drains the persistent scrape queue one job at a time.

Only one Chromium instance runs at any moment (they would otherwise fight over
the shared user-data profile). When a job finishes, the next pending job is
picked up automatically, including after a server restart.
"""

import asyncio
import threading
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from .scrape_queue import ScrapeQueue


class ScrapeWorker:
    """Background worker that runs queued scrape jobs sequentially."""

    def __init__(
        self,
        queue: ScrapeQueue,
        scraper_factory: Callable[..., Any],
        event_sink: Callable[[Dict[str, Any]], None],
        browser_profile: Path,
        library_path: Path,
        headless: bool = True,
        fast_mode: bool = True,
        loop: Optional[asyncio.AbstractEventLoop] = None,
    ):
        self.queue = queue
        self._scraper_factory = scraper_factory
        self._event_sink = event_sink
        self._browser_profile = browser_profile
        self._library_path = library_path
        self._headless = headless
        self._fast_mode = fast_mode
        self._loop = loop

        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._current_job_id: Optional[int] = None
        self._started = False

    # --- lifecycle ---

    def start(self):
        """Start the worker thread (idempotent)."""
        if self._started:
            return
        self._started = True
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="scrape-worker", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 5.0):
        """Ask the worker to finish after the current job."""
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout)

    @property
    def is_running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    @property
    def current_job_id(self) -> Optional[int]:
        return self._current_job_id

    # --- worker loop ---

    def _run(self):
        # Jobs interrupted by a previous shutdown were already reset to
        # pending by ScrapeQueue._recover_interrupted.
        while not self._stop.is_set():
            job = self.queue.claim_next()
            if job is None:
                # Nothing waiting; sleep briefly so we notice new work promptly.
                self._stop.wait(2.0)
                continue
            self._run_job(job)

    def _run_job(self, job: Dict[str, Any]):
        job_id = job["id"]
        self._current_job_id = job_id
        url = job["url"]
        try:
            scraper = self._scraper_factory(
                output_dir=str(self._library_path),
                user_data_dir=str(self._browser_profile),
                headless=self._headless,
                fast_mode=self._fast_mode,
                event_handler=self._make_handler(job_id),
            )
            asyncio.run(scraper.start_scraping(url))

            story_name = self._detect_story_name()
            self.queue.mark_completed(job_id, story_name)
            self._emit(job_id, "completed", f"Finished: {story_name or url}")
        except Exception as exc:
            # A failure here (browser init, network down) should not wedge the
            # queue: retry it a couple of times, then park it as failed.
            # claim_next() increments attempts before returning, so this is the
            # attempt number that just failed: 1, 2, 3...
            attempt = job.get("attempts", 1)
            max_attempts = 3
            retryable = attempt < max_attempts
            self.queue.mark_failed(job_id, str(exc), retryable=retryable)
            self._emit(
                job_id,
                "pending" if retryable else "failed",
                f"{'Retrying after error' if retryable else 'Failed'}: {exc}",
            )
        finally:
            self._current_job_id = None

    def _make_handler(self, job_id: int):
        """EventHandler that forwards scraper progress for one job."""
        if self._loop is None or self._loop.is_closed():
            return None

        from .server_events import ServerEventHandler

        # Live progress lives in this dict; durable state stays in SQLite.
        task_view: Dict[str, Any] = {
            "total": 100,
            "current": 0,
            "message": f"Scraping job {job_id}",
            "status": "running",
            "logs": [],
        }

        def broadcast(message: Dict[str, Any]):
            data = message.get("data", {})
            self._emit(job_id, "running", data.get("message", ""))

        return ServerEventHandler(
            f"job_{job_id}",
            self._loop,
            {"job": task_view},
            broadcast,
            key="job",
        )

    def _detect_story_name(self) -> str:
        """Best-effort story name from the most recently modified story dir."""
        try:
            candidates = [
                d for d in self._library_path.iterdir()
                if d.is_dir() and not d.name.startswith(".")
            ]
            if not candidates:
                return ""
            newest = max(candidates, key=lambda d: d.stat().st_mtime)
            return newest.name
        except Exception:
            return ""

    def _emit(self, job_id: int, status: str, message: str):
        try:
            self._event_sink({
                "type": "queue_update",
                "job_id": job_id,
                "status": status,
                "message": message,
            })
        except Exception:
            pass
