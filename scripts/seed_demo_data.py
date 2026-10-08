"""
seed_demo_data.py
-----------------
Seeds the SQLite database with realistic demo data for hackathon presentation.

Run ONCE before the demo so the dashboard looks live and populated:
    venv\\Scripts\\python.exe scripts/seed_demo_data.py

What it inserts:
  • 6 demo students with room numbers and roll numbers
  • ~60 access events throughout today (entries, exits, violations, unknowns)
  • Realistic timestamps from 7:00 AM through current time
"""

import os
import sys
import sqlite3
import random
from datetime import datetime, date, timedelta

# Allow importing from src/
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from config import DATABASE_PATH, DEFAULT_CURFEW_TIME

# ─────────────────────────────────────────────────────────────
# Demo Student Profiles
# ─────────────────────────────────────────────────────────────
DEMO_STUDENTS = [
    {"name": "alice",  "roll_number": "2024CS001", "room_number": "A-101", "hostel_block": "A"},
    {"name": "bob",    "roll_number": "2024CS002", "room_number": "A-102", "hostel_block": "A"},
    {"name": "carol",  "roll_number": "2024ME003", "room_number": "B-201", "hostel_block": "B"},
    {"name": "dave",   "roll_number": "2024EE004", "room_number": "B-304", "hostel_block": "B"},
    {"name": "evan",   "roll_number": "2024CS005", "room_number": "A-203", "hostel_block": "A"},
    {"name": "fiona",  "roll_number": "2024ME006", "room_number": "C-105", "hostel_block": "C"},
]

# ─────────────────────────────────────────────────────────────
# Seed Logic
# ─────────────────────────────────────────────────────────────

def seed():
    os.makedirs(os.path.dirname(DATABASE_PATH), exist_ok=True)
    conn = sqlite3.connect(DATABASE_PATH)
    cur  = conn.cursor()

    # Ensure tables exist (same as database.py schema)
    cur.executescript("""
    CREATE TABLE IF NOT EXISTS access_logs (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp   TEXT    NOT NULL,
        name        TEXT    NOT NULL,
        status      TEXT    NOT NULL,
        event_type  TEXT    NOT NULL DEFAULT 'ENTRY',
        similarity  REAL    NOT NULL,
        room_number TEXT    NOT NULL DEFAULT '',
        face_count  INTEGER DEFAULT 1
    );
    CREATE TABLE IF NOT EXISTS students (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        name         TEXT    NOT NULL UNIQUE,
        roll_number  TEXT    NOT NULL DEFAULT '',
        room_number  TEXT    NOT NULL DEFAULT '',
        hostel_block TEXT    NOT NULL DEFAULT 'A',
        curfew_time  TEXT    NOT NULL DEFAULT '22:00',
        registered_at TEXT   NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # Add migration columns (safe on existing DB)
    for col_sql in [
        "ALTER TABLE access_logs ADD COLUMN event_type  TEXT NOT NULL DEFAULT 'ENTRY'",
        "ALTER TABLE access_logs ADD COLUMN room_number TEXT NOT NULL DEFAULT ''",
    ]:
        try:
            cur.execute(col_sql)
        except sqlite3.OperationalError:
            pass

    conn.commit()

    # ── Insert Demo Students ──────────────────────────────────
    print("-- Inserting demo students ...")
    for s in DEMO_STUDENTS:
        cur.execute("""
            INSERT INTO students (name, roll_number, room_number, hostel_block, curfew_time)
            VALUES (?, ?, ?, ?, '22:00')
            ON CONFLICT(name) DO UPDATE SET
                roll_number  = excluded.roll_number,
                room_number  = excluded.room_number,
                hostel_block = excluded.hostel_block
        """, (s["name"], s["roll_number"], s["room_number"], s["hostel_block"]))
        print(f"  [OK] {s['name']} -- Room {s['room_number']}")

    conn.commit()

    # ── Generate Access Events ────────────────────────────────
    print("\n-- Generating access events for today ...")
    today = date.today()
    events_added = 0

    # Simulate a full day's access log timeline
    # Format: (time_hhmm, name, event_type, status, similarity)
    timeline = [
        # Early morning exits (students left last night, re-enter now)
        ("07:12", "alice",   "ENTRY",     "AUTHORIZED", 0.87),
        ("07:34", "bob",     "ENTRY",     "AUTHORIZED", 0.82),
        ("07:45", "UNKNOWN", "DENIED",    "DENIED",     0.28),
        ("08:02", "carol",   "ENTRY",     "AUTHORIZED", 0.91),
        ("08:15", "dave",    "ENTRY",     "AUTHORIZED", 0.79),
        ("08:47", "evan",    "ENTRY",     "AUTHORIZED", 0.85),
        ("09:10", "fiona",   "ENTRY",     "AUTHORIZED", 0.88),

        # Mid-morning exits (going to class)
        ("09:30", "alice",   "EXIT",      "AUTHORIZED", 0.86),
        ("09:45", "bob",     "EXIT",      "AUTHORIZED", 0.81),
        ("10:00", "carol",   "EXIT",      "AUTHORIZED", 0.90),
        ("10:15", "UNKNOWN", "DENIED",    "DENIED",     0.21),

        # Afternoon re-entries
        ("12:30", "alice",   "ENTRY",     "AUTHORIZED", 0.88),
        ("12:55", "bob",     "ENTRY",     "AUTHORIZED", 0.83),
        ("13:10", "carol",   "ENTRY",     "AUTHORIZED", 0.92),
        ("13:30", "dave",    "EXIT",      "AUTHORIZED", 0.78),
        ("14:00", "evan",    "EXIT",      "AUTHORIZED", 0.84),
        ("14:20", "UNKNOWN", "DENIED",    "DENIED",     0.31),

        # Evening exits
        ("17:00", "alice",   "EXIT",      "AUTHORIZED", 0.87),
        ("17:15", "bob",     "EXIT",      "AUTHORIZED", 0.80),
        ("17:45", "carol",   "EXIT",      "AUTHORIZED", 0.91),
        ("18:00", "fiona",   "EXIT",      "AUTHORIZED", 0.87),
        ("18:30", "UNKNOWN", "DENIED",    "DENIED",     0.19),
        ("18:45", "UNKNOWN", "DENIED",    "DENIED",     0.24),

        # Evening re-entries (before curfew)
        ("19:30", "alice",   "ENTRY",     "AUTHORIZED", 0.86),
        ("20:00", "dave",    "ENTRY",     "AUTHORIZED", 0.77),
        ("20:15", "evan",    "ENTRY",     "AUTHORIZED", 0.83),
        ("20:45", "fiona",   "ENTRY",     "AUTHORIZED", 0.89),
        ("21:00", "bob",     "ENTRY",     "AUTHORIZED", 0.82),
        ("21:30", "carol",   "ENTRY",     "AUTHORIZED", 0.90),

        # Late night violations (after 22:00 curfew)
        ("22:15", "dave",    "VIOLATION", "AUTHORIZED", 0.78),
        ("22:47", "evan",    "VIOLATION", "AUTHORIZED", 0.84),
        ("23:10", "UNKNOWN", "DENIED",    "DENIED",     0.27),
        ("23:30", "fiona",   "VIOLATION", "AUTHORIZED", 0.88),
    ]

    now = datetime.now()

    for time_str, name, event_type, status, similarity in timeline:
        h, m = map(int, time_str.split(":"))
        event_dt = datetime(today.year, today.month, today.day, h, m,
                            random.randint(0, 59))

        # Only insert events that have already happened
        if event_dt > now:
            continue

        # Jitter similarity slightly for realism
        sim = round(min(0.99, max(0.10, similarity + random.uniform(-0.02, 0.02))), 4)
        ts  = event_dt.strftime("%Y-%m-%d %H:%M:%S")

        # Get room number
        room = ""
        if name != "UNKNOWN":
            student = next((s for s in DEMO_STUDENTS if s["name"] == name), None)
            room = student["room_number"] if student else ""

        cur.execute("""
            INSERT INTO access_logs (timestamp, name, status, event_type, similarity, room_number, face_count)
            VALUES (?, ?, ?, ?, ?, ?, 1)
        """, (ts, name if name != "UNKNOWN" else "UNKNOWN", status, event_type, sim, room))
        events_added += 1
        print(f"  {event_dt.strftime('%H:%M')}  {name:<10}  {event_type:<10}  sim={sim:.2f}")

    conn.commit()
    conn.close()

    print(f"\n[DONE] Inserted {len(DEMO_STUDENTS)} students and {events_added} access events.")
    print(f"       Database: {DATABASE_PATH}")
    print(f"\nRun the dashboard to see your data:")
    print(f"   .\\start_dashboard.bat")


if __name__ == "__main__":
    seed()
