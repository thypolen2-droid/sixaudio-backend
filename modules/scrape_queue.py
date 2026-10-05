"""Persistent scrape queue backed by SQLite.

Jobs are stored in a small SQLite database (stdlib, no extra dependency) so a
queued list of URLs survives a server restart. A job that was ``running`` when
the process died is reset to ``pending`` on load, so scraping resumes where it
left off instead of being stuck forever.

Statuses: pending -> running -> completed | failed
"""

import os
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

# Terminal states; anything else is retried after a restart.
DONE_STATUSES = ("completed", "failed", "cancelled")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS scrape_jobs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    url         TEXT    NOT NULL,
    site        TEXT    NOT NULL DEFAULT '',
    status      TEXT    NOT NULL DEFAULT 'pending',
    position    INTEGER NOT NULL DEFAULT 0,
    attempts    INTEGER NOT NULL DEFAULT 0,
    error       TEXT    NOT NULL DEFAULT '',
    story_name  TEXT    NOT NULL DEFAULT '',
    created_at  REAL    NOT NULL,
    started_at  REAL,
    finished_at REAL
);

CREATE INDEX IF NOT EXISTS idx_scrape_jobs_status ON scrape_jobs(status, position);
"""


class ScrapeQueue:
    """Thread-safe persistent queue of scrape jobs.

    A single connection is shared across the server thread and scrape worker
    threads, guarded by a lock. SQLite in WAL mode handles the concurrent
    readers cheaply.
    """

    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.executescript(_SCHEMA)
            self._conn.commit()
        self._recover_interrupted()

    def _recover_interrupted(self):
        """Requeue jobs that were mid-flight when the server stopped."""
        with self._lock:
            cur = self._conn.execute(
                "UPDATE scrape_jobs SET status='pending' WHERE status='running'"
            )
            if cur.rowcount:
                print(f"🔄 Requeued {cur.rowcount} interrupted scrape job(s) after restart.")

    # --- writes ---

    def enqueue(self, url: str, site: str = "") -> Dict[str, Any]:
        """Add a URL to the queue and return the created job."""
        now = time.time()
        with self._lock:
            row = self._conn.execute(
                "SELECT COALESCE(MAX(position), 0) AS m FROM scrape_jobs WHERE status='pending'"
            ).fetchone()
            position = (row["m"] or 0) + 1

            cur = self._conn.execute(
                "INSERT INTO scrape_jobs (url, site, status, position, created_at) "
                "VALUES (?, ?, 'pending', ?, ?)",
                (url, site, position, now),
            )
            job_id = cur.lastrowid
            self._conn.commit()
        return self.get(job_id)  # type: ignore[return-value]

    def claim_next(self) -> Optional[Dict[str, Any]]:
        """Atomically mark the oldest pending job as running and return it."""
        now = time.time()
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM scrape_jobs WHERE status='pending' ORDER BY position, id LIMIT 1"
            ).fetchone()
            if row is None:
                return None
            self._conn.execute(
                "UPDATE scrape_jobs SET status='running', started_at=?, "
                "attempts=attempts+1 WHERE id=? AND status='pending'",
                (now, row["id"]),
            )
            self._conn.commit()
            # Re-read so the caller sees the incremented attempt count and the
            # 'running' status, not the pre-claim snapshot.
            fresh = self._conn.execute(
                "SELECT * FROM scrape_jobs WHERE id=?", (row["id"],)
            ).fetchone()
            return dict(fresh) if fresh else dict(row)

    def mark_completed(self, job_id: int, story_name: str = ""):
        with self._lock:
            self._conn.execute(
                "UPDATE scrape_jobs SET status='completed', finished_at=?, story_name=?, error='' "
                "WHERE id=?",
                (time.time(), story_name, job_id),
            )
            self._conn.commit()

    def mark_failed(self, job_id: int, error: str, retryable: bool = True):
        """Fail a job. Retryable failures go back to pending for another pass."""
        now = time.time()
        status = "pending" if retryable else "failed"
        with self._lock:
            self._conn.execute(
                "UPDATE scrape_jobs SET status=?, finished_at=?, error=? WHERE id=?",
                (status, now if not retryable else None, error[:500], job_id),
            )
            self._conn.commit()

    def cancel(self, job_id: int) -> bool:
        """Cancel a pending job. Returns False if it already started."""
        with self._lock:
            cur = self._conn.execute(
                "UPDATE scrape_jobs SET status='cancelled', finished_at=? "
                "WHERE id=? AND status='pending'",
                (time.time(), job_id),
            )
            self._conn.commit()
            return cur.rowcount > 0

    def retry(self, job_id: int) -> bool:
        """Move a failed job back to pending."""
        with self._lock:
            cur = self._conn.execute(
                "UPDATE scrape_jobs SET status='pending', error='', position=0 WHERE id=?",
                (job_id,),
            )
            self._conn.commit()
            return cur.rowcount > 0

    def clear_finished(self) -> int:
        """Delete completed/failed/cancelled jobs. Returns rows removed."""
        with self._lock:
            cur = self._conn.execute(
                f"DELETE FROM scrape_jobs WHERE status IN {DONE_STATUSES}"
            )
            self._conn.commit()
            return cur.rowcount

    # --- reads ---

    def get(self, job_id: int) -> Optional[Dict[str, Any]]:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM scrape_jobs WHERE id=?", (job_id,)
            ).fetchone()
            return dict(row) if row else None

    def list_jobs(self, limit: int = 100) -> List[Dict[str, Any]]:
        """All jobs, running first, then pending in queue order, then finished."""
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT * FROM scrape_jobs
                ORDER BY CASE status
                    WHEN 'running' THEN 0
                    WHEN 'pending'  THEN 1
                    WHEN 'failed'   THEN 2
                    WHEN 'completed' THEN 3
                    ELSE 4
                END, position, id
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
            return [dict(r) for r in rows]

    def counts(self) -> Dict[str, int]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT status, COUNT(*) AS n FROM scrape_jobs GROUP BY status"
            ).fetchall()
            return {r["status"]: r["n"] for r in rows}

    def close(self):
        with self._lock:
            self._conn.close()


def get_default_queue_path() -> Path:
    """Queue DB lives beside the library so it moves with the data."""
    library = Path(os.environ.get("LIBRARY_PATH", "Library"))
    return library.parent / ".scrape_queue.db"