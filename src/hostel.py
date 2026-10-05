"""
hostel.py
---------
Hostel-specific business logic:
  • Student metadata registry (name → room, roll number, curfew override)
  • Entry / Exit state machine (alternates per person)
  • Curfew violation detection
  • System state (lockdown flag shared with dashboard via JSON file)
"""

import json
import os
import threading
from datetime import datetime, time as dtime
from typing import Optional

from config import (
    DEFAULT_CURFEW_TIME,
    CURFEW_WARNING_MINS,
    SYSTEM_STATE_FILE,
    LOGS_DIR,
)


# ─────────────────────────────────────────────────────────────
# Default system state written when the file doesn't exist yet
# ─────────────────────────────────────────────────────────────
_DEFAULT_STATE = {
    "lockdown":     False,
    "lockdown_by":  None,
    "lockdown_at":  None,
    "gate_status":  "ACTIVE",   # "ACTIVE" | "LOCKED"
}


# ─────────────────────────────────────────────────────────────
# System State  (lockdown / gate override)
# ─────────────────────────────────────────────────────────────

def read_system_state() -> dict:
    """
    Read the shared system-state JSON file.
    Returns the default state if the file doesn't exist yet.
    This file is written by the Streamlit dashboard and polled by main.py
    so the warden can trigger an emergency lockdown without touching the camera.
    """
    os.makedirs(LOGS_DIR, exist_ok=True)
    if not os.path.exists(SYSTEM_STATE_FILE):
        write_system_state(_DEFAULT_STATE)
        return dict(_DEFAULT_STATE)
    try:
        with open(SYSTEM_STATE_FILE, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return dict(_DEFAULT_STATE)


def write_system_state(state: dict):
    """Persist the system state JSON atomically."""
    os.makedirs(LOGS_DIR, exist_ok=True)
    tmp = SYSTEM_STATE_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(state, f, indent=2)
    os.replace(tmp, SYSTEM_STATE_FILE)


def is_lockdown_active() -> bool:
    """Quick helper — True if an emergency lockdown is currently active."""
    return read_system_state().get("lockdown", False)


# ─────────────────────────────────────────────────────────────
# Curfew Logic
# ─────────────────────────────────────────────────────────────

def parse_curfew_time(curfew_str: str) -> dtime:
    """Parse a 'HH:MM' curfew string into a datetime.time object."""
    h, m = map(int, curfew_str.split(":"))
    return dtime(h, m)


def is_curfew_violation(curfew_str: str, check_time: Optional[datetime] = None) -> bool:
    """
    Return True if *check_time* (defaults to now) is past the curfew.
    Only the time-of-day portion is compared, so curfew resets every day.
    """
    now = check_time or datetime.now()
    curfew = parse_curfew_time(curfew_str)
    return now.time() > curfew


def curfew_status(curfew_str: str) -> str:
    """
    Returns one of:
      "OK"      — well before curfew
      "WARNING" — within CURFEW_WARNING_MINS of curfew
      "PAST"    — curfew has passed for today
    """
    now    = datetime.now()
    curfew = parse_curfew_time(curfew_str)
    now_t  = now.time()

    if now_t > curfew:
        return "PAST"

    # Minutes remaining until curfew
    now_mins    = now_t.hour * 60 + now_t.minute
    curfew_mins = curfew.hour * 60 + curfew.minute
    remaining   = curfew_mins - now_mins

    if remaining <= CURFEW_WARNING_MINS:
        return "WARNING"
    return "OK"


# ─────────────────────────────────────────────────────────────
# Entry / Exit State Machine
# ─────────────────────────────────────────────────────────────

class EntryExitTracker:
    """
    Keeps track of each known person's last event (ENTRY / EXIT).
    The first event for any person defaults to ENTRY; subsequent events alternate.
    Thread-safe via a lock.
    """

    def __init__(self):
        self._lock  = threading.Lock()
        # {name: "ENTRY" | "EXIT"}
        self._state: dict[str, str] = {}

    def next_event(self, name: str) -> str:
        """Return what the next event type should be for this person."""
        with self._lock:
            last = self._state.get(name)
            if last is None or last == "EXIT":
                event = "ENTRY"
            else:
                event = "EXIT"
            self._state[name] = event
            return event

    def last_event(self, name: str) -> Optional[str]:
        """Return the most recent event type for a person without advancing it."""
        with self._lock:
            return self._state.get(name)

    def reset(self, name: str):
        """Reset a person's state (e.g. on shift change)."""
        with self._lock:
            self._state.pop(name, None)


# ─────────────────────────────────────────────────────────────
# Hostel Event Classifier
# ─────────────────────────────────────────────────────────────

def classify_event(
    name: str,
    status: str,
    tracker: EntryExitTracker,
    student_curfew: Optional[str] = None,
) -> str:
    """
    Given a recognition result, determine the full event type:

      ENTRY      — authorised, entering
      EXIT       — authorised, exiting
      VIOLATION  — authorised ENTRY but past curfew
      DENIED     — unknown / unregistered person

    Args:
        name:           Recognised name or "UNKNOWN"
        status:         "AUTHORIZED" | "DENIED" from face engine
        tracker:        EntryExitTracker instance shared across frames
        student_curfew: Per-student curfew override (falls back to DEFAULT)
    """
    if status == "DENIED":
        return "DENIED"

    # Determine ENTRY or EXIT
    event = tracker.next_event(name)

    # Only ENTRY events can be violations (you can't violate curfew by leaving)
    if event == "ENTRY":
        curfew = student_curfew or DEFAULT_CURFEW_TIME
        if is_curfew_violation(curfew):
            return "VIOLATION"

    return event
