"""
database.py
-----------
SQLite-backed access log store with thread-safe operations and an
in-process debounce/cooldown guard to prevent DB flooding.
"""

import sqlite3
import threading
import time
from datetime import datetime
from typing import Optional

from config import (
    DATABASE_PATH,
    LOG_COOLDOWN_SECONDS,
    UNKNOWN_COOLDOWN_SECONDS,
    LOGS_DISPLAY_ROWS,
)

# ─────────────────────────────────────────────────────────────
# Schema
# ─────────────────────────────────────────────────────────────
_SCHEMA = """
CREATE TABLE IF NOT EXISTS access_logs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp   TEXT    NOT NULL,
    name        TEXT    NOT NULL,
    status      TEXT    NOT NULL,
    similarity  REAL    NOT NULL,
    face_count  INTEGER DEFAULT 1
);
"""


class AccessLogger:
    """
    Thread-safe SQLite access logger.

    Debounce logic
    ──────────────
    An in-memory dict maps each identity key → last insertion time.
    A new row is only written when the gap since the last write exceeds
    the configured cooldown, preventing hundreds of duplicate entries
    for a person who stands in frame for several seconds.
    """

    def __init__(self, db_path: str = DATABASE_PATH):
        self._db_path = db_path
        self._lock = threading.Lock()
        self._last_logged: dict[str, float] = {}  # identity_key → epoch timestamp
        self._init_db()

    # ── Internal ──────────────────────────────────────────────

    def _init_db(self):
        """Create the DB file and table if they don't exist yet."""
        import os
        os.makedirs(os.path.dirname(self._db_path), exist_ok=True)
        with sqlite3.connect(self._db_path) as conn:
            conn.execute(_SCHEMA)
            conn.commit()

    def _cooldown_ok(self, key: str, cooldown: float) -> bool:
        """Return True if enough time has passed since the last log for *key*."""
        now = time.monotonic()
        last = self._last_logged.get(key, 0.0)
        if (now - last) >= cooldown:
            self._last_logged[key] = now
            return True
        return False

    # ── Public API ────────────────────────────────────────────

    def log(
        self,
        name: str,
        status: str,          # "AUTHORIZED" | "DENIED"
        similarity: float,
        face_count: int = 1,
    ) -> bool:
        """
        Attempt to write an access event to the DB.

        Returns True if a row was actually inserted (cooldown passed),
        False if the entry was suppressed by the debounce guard.
        """
        # Use a unified key for all UNKNOWN detections so they share
        # a single cooldown bucket rather than one per similarity value.
        cooldown_key = name if name != "UNKNOWN" else "__UNKNOWN__"
        cooldown_val = (
            LOG_COOLDOWN_SECONDS if name != "UNKNOWN"
            else UNKNOWN_COOLDOWN_SECONDS
        )

        with self._lock:
            if not self._cooldown_ok(cooldown_key, cooldown_val):
                return False  # suppressed — still within cooldown

            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            with sqlite3.connect(self._db_path) as conn:
                conn.execute(
                    """
                    INSERT INTO access_logs
                        (timestamp, name, status, similarity, face_count)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (timestamp, name, status, round(similarity, 4), face_count),
                )
                conn.commit()
            return True

    def fetch_recent(self, n: int = LOGS_DISPLAY_ROWS) -> list[tuple]:
        """Return the *n* most recent log rows as a list of tuples."""
        with sqlite3.connect(self._db_path) as conn:
            cursor = conn.execute(
                """
                SELECT timestamp, name, status, similarity, face_count
                FROM access_logs
                ORDER BY id DESC
                LIMIT ?
                """,
                (n,),
            )
            return cursor.fetchall()

    def print_logs(self, n: int = LOGS_DISPLAY_ROWS):
        """Pretty-print recent access logs to stdout."""
        rows = self.fetch_recent(n)
        if not rows:
            print("No access log entries found.")
            return

        # Try tabulate for nice formatting, fall back to plain text
        try:
            from tabulate import tabulate
            headers = ["Timestamp", "Name", "Status", "Similarity", "Faces"]
            print(tabulate(rows, headers=headers, tablefmt="rounded_outline"))
        except ImportError:
            header = f"{'Timestamp':<22} {'Name':<20} {'Status':<12} {'Sim':>8} {'Faces':>6}"
            print(header)
            print("─" * len(header))
            for r in rows:
                print(f"{r[0]:<22} {r[1]:<20} {r[2]:<12} {r[3]:>8.4f} {r[4]:>6}")
