"""
database.py
-----------
SQLite-backed access log store with:
  • Thread-safe writes and in-process debounce guard
  • Students table (name, roll_number, room_number, curfew_time)
  • Extended access_logs (event_type: ENTRY/EXIT/VIOLATION/DENIED)
  • Stats queries used by the Streamlit warden dashboard
"""

import sqlite3
import threading
import time
from datetime import datetime, date
from typing import Optional

from config import (
    DATABASE_PATH,
    LOG_COOLDOWN_SECONDS,
    UNKNOWN_COOLDOWN_SECONDS,
    LOGS_DISPLAY_ROWS,
    DEFAULT_CURFEW_TIME,
)

# ─────────────────────────────────────────────────────────────
# Schema
# ─────────────────────────────────────────────────────────────

_SCHEMA_LOGS = """
CREATE TABLE IF NOT EXISTS access_logs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp   TEXT    NOT NULL,
    name        TEXT    NOT NULL,
    status      TEXT    NOT NULL,       -- 'AUTHORIZED' | 'DENIED'
    event_type  TEXT    NOT NULL DEFAULT 'ENTRY',  -- 'ENTRY'|'EXIT'|'VIOLATION'|'DENIED'
    similarity  REAL    NOT NULL,
    room_number TEXT    NOT NULL DEFAULT '',
    face_count  INTEGER DEFAULT 1
);
"""

_SCHEMA_STUDENTS = """
CREATE TABLE IF NOT EXISTS students (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    name         TEXT    NOT NULL UNIQUE,   -- must match known_faces filename stem
    roll_number  TEXT    NOT NULL DEFAULT '',
    room_number  TEXT    NOT NULL DEFAULT '',
    hostel_block TEXT    NOT NULL DEFAULT 'A',
    curfew_time  TEXT    NOT NULL DEFAULT '{curfew}',  -- HH:MM override
    registered_at TEXT   NOT NULL DEFAULT CURRENT_TIMESTAMP
);
""".format(curfew=DEFAULT_CURFEW_TIME)


class AccessLogger:
    """
    Thread-safe SQLite access logger with debounce and student lookup.
    """

    def __init__(self, db_path: str = DATABASE_PATH):
        self._db_path = db_path
        self._lock    = threading.Lock()
        self._last_logged: dict[str, float] = {}   # identity_key → epoch timestamp
        self._init_db()

    # ── Internal ──────────────────────────────────────────────

    def _init_db(self):
        """Create DB file, tables, and migrate any existing table missing columns."""
        import os
        os.makedirs(os.path.dirname(self._db_path), exist_ok=True)
        with sqlite3.connect(self._db_path) as conn:
            conn.execute(_SCHEMA_LOGS)
            conn.execute(_SCHEMA_STUDENTS)
            conn.commit()
            # Migrate older access_logs tables that may be missing new columns
            self._migrate(conn)

    def _migrate(self, conn: sqlite3.Connection):
        """Safely add columns that didn't exist in the original schema."""
        migrations = [
            "ALTER TABLE access_logs ADD COLUMN event_type  TEXT NOT NULL DEFAULT 'ENTRY'",
            "ALTER TABLE access_logs ADD COLUMN room_number TEXT NOT NULL DEFAULT ''",
        ]
        for sql in migrations:
            try:
                conn.execute(sql)
                conn.commit()
            except sqlite3.OperationalError:
                pass  # column already exists — ignore

    def _cooldown_ok(self, key: str, cooldown: float) -> bool:
        """Return True if enough time has passed since the last log for *key*."""
        now  = time.monotonic()
        last = self._last_logged.get(key, 0.0)
        if (now - last) >= cooldown:
            self._last_logged[key] = now
            return True
        return False

    def _get_room(self, conn: sqlite3.Connection, name: str) -> str:
        """Look up a student's room number (empty string if not registered)."""
        row = conn.execute(
            "SELECT room_number FROM students WHERE name=?", (name,)
        ).fetchone()
        return row[0] if row else ""

    def _get_curfew(self, conn: sqlite3.Connection, name: str) -> str:
        """Return per-student curfew override, or global default."""
        row = conn.execute(
            "SELECT curfew_time FROM students WHERE name=?", (name,)
        ).fetchone()
        return row[0] if row else DEFAULT_CURFEW_TIME

    # ── Public Logging API ────────────────────────────────────

    def log(
        self,
        name: str,
        status: str,           # "AUTHORIZED" | "DENIED"
        similarity: float,
        event_type: str = "ENTRY",   # "ENTRY" | "EXIT" | "VIOLATION" | "DENIED"
        face_count: int = 1,
    ) -> bool:
        """
        Write a debounced access event to the DB.
        Returns True if a row was inserted, False if suppressed by cooldown.
        """
        cooldown_key = name if name != "UNKNOWN" else "__UNKNOWN__"
        cooldown_val = (
            LOG_COOLDOWN_SECONDS if name != "UNKNOWN"
            else UNKNOWN_COOLDOWN_SECONDS
        )

        with self._lock:
            if not self._cooldown_ok(cooldown_key, cooldown_val):
                return False

            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            with sqlite3.connect(self._db_path) as conn:
                room = self._get_room(conn, name)
                conn.execute(
                    """
                    INSERT INTO access_logs
                        (timestamp, name, status, event_type, similarity, room_number, face_count)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (timestamp, name, status, event_type,
                     round(similarity, 4), room, face_count),
                )
                conn.commit()
            return True

    # ── Student Registry API ──────────────────────────────────

    def register_student(
        self,
        name: str,
        roll_number: str  = "",
        room_number: str  = "",
        hostel_block: str = "A",
        curfew_time: str  = DEFAULT_CURFEW_TIME,
    ) -> bool:
        """
        Add or update a student record.
        'name' must exactly match the filename stem in data/known_faces/.
        Returns True on success.
        """
        try:
            with sqlite3.connect(self._db_path) as conn:
                conn.execute(
                    """
                    INSERT INTO students (name, roll_number, room_number, hostel_block, curfew_time)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(name) DO UPDATE SET
                        roll_number  = excluded.roll_number,
                        room_number  = excluded.room_number,
                        hostel_block = excluded.hostel_block,
                        curfew_time  = excluded.curfew_time
                    """,
                    (name, roll_number, room_number, hostel_block, curfew_time),
                )
                conn.commit()
            return True
        except sqlite3.Error as e:
            print(f"[ERROR] Student registration failed: {e}")
            return False

    def get_student(self, name: str) -> Optional[dict]:
        """Return a student's metadata dict or None if not found."""
        with sqlite3.connect(self._db_path) as conn:
            row = conn.execute(
                "SELECT name,roll_number,room_number,hostel_block,curfew_time FROM students WHERE name=?",
                (name,),
            ).fetchone()
        if not row:
            return None
        return dict(zip(["name","roll_number","room_number","hostel_block","curfew_time"], row))

    def get_all_students(self) -> list[dict]:
        """Return all registered students as a list of dicts."""
        with sqlite3.connect(self._db_path) as conn:
            rows = conn.execute(
                "SELECT name,roll_number,room_number,hostel_block,curfew_time,registered_at FROM students ORDER BY name"
            ).fetchall()
        cols = ["name","roll_number","room_number","hostel_block","curfew_time","registered_at"]
        return [dict(zip(cols, r)) for r in rows]

    # ── Statistics API (used by dashboard) ────────────────────

    def get_stats_today(self) -> dict:
        """
        Return a summary dict for today's activity:
            total_entries, exits, violations, unknown_attempts, authorized_count
        """
        today = date.today().strftime("%Y-%m-%d")
        with sqlite3.connect(self._db_path) as conn:
            def count(where: str, params=()) -> int:
                row = conn.execute(
                    f"SELECT COUNT(*) FROM access_logs WHERE timestamp LIKE ? {where}",
                    (today + "%", *params),
                ).fetchone()
                return row[0] if row else 0

            return {
                "total_entries":     count("AND event_type='ENTRY'"),
                "exits":             count("AND event_type='EXIT'"),
                "violations":        count("AND event_type='VIOLATION'"),
                "unknown_attempts":  count("AND event_type='DENIED'"),
                "authorized_count":  count("AND status='AUTHORIZED'"),
                "total_events":      count(""),
            }

    def fetch_recent(self, n: int = LOGS_DISPLAY_ROWS) -> list[tuple]:
        """Return the *n* most recent log rows as a list of tuples."""
        with sqlite3.connect(self._db_path) as conn:
            cursor = conn.execute(
                """
                SELECT timestamp, name, event_type, status, similarity, room_number, face_count
                FROM access_logs
                ORDER BY id DESC
                LIMIT ?
                """,
                (n,),
            )
            return cursor.fetchall()

    def fetch_recent_as_dicts(self, n: int = LOGS_DISPLAY_ROWS) -> list[dict]:
        """Return recent logs as list of dicts (for pandas/dashboard use)."""
        rows = self.fetch_recent(n)
        cols = ["Timestamp","Name","Event","Status","Similarity","Room","Faces"]
        return [dict(zip(cols, r)) for r in rows]

    def print_logs(self, n: int = LOGS_DISPLAY_ROWS):
        """Pretty-print recent access logs to stdout."""
        rows = self.fetch_recent(n)
        if not rows:
            print("No access log entries found.")
            return
        try:
            from tabulate import tabulate
            headers = ["Timestamp","Name","Event","Status","Similarity","Room","Faces"]
            print(tabulate(rows, headers=headers, tablefmt="rounded_outline"))
        except ImportError:
            for r in rows:
                print(r)
