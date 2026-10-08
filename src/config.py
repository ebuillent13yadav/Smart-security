"""
config.py
---------
Central configuration for the AI-Powered Smart Access & Security System.
All tunable parameters live here — do NOT hardcode them in other modules.
"""

import os

# ─────────────────────────────────────────────
# Project Root
# ─────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ─────────────────────────────────────────────
# Directory Paths
# ─────────────────────────────────────────────
KNOWN_FACES_DIR   = os.path.join(BASE_DIR, "data", "known_faces")
EMBEDDINGS_CACHE  = os.path.join(BASE_DIR, "data", "embeddings.pkl")
# InsightFace's FaceAnalysis(root=INSIGHTFACE_ROOT) internally stores models at
# root/models/<pack_name>. So we pass BASE_DIR as the root so models end up
# cleanly in  smart-security/models/buffalo_sc/  (not models/models/buffalo_sc/).
INSIGHTFACE_ROOT  = BASE_DIR
MODELS_DIR        = os.path.join(BASE_DIR, "models")   # for reference / gitignore
LOGS_DIR          = os.path.join(BASE_DIR, "logs")
DATABASE_PATH     = os.path.join(LOGS_DIR, "access.db")

# ─────────────────────────────────────────────
# InsightFace Model Settings
# ─────────────────────────────────────────────
# "buffalo_sc" is the small, fast, CPU-friendly pack (det + recog)
# Alternatives: "buffalo_l" (larger, more accurate), "buffalo_s"
INSIGHTFACE_MODEL_PACK = "buffalo_sc"

# Execution providers tried in order of preference
ONNX_PROVIDERS = ["CUDAExecutionProvider", "CPUExecutionProvider"]

# Detection confidence threshold — faces below this are ignored
DETECTION_THRESHOLD = 0.50

# ─────────────────────────────────────────────
# Recognition / Identity Decision
# ─────────────────────────────────────────────
# Cosine similarity ∈ [−1, 1].  ArcFace embeddings:
#   ≥ 0.50  →  same person (conservative default)
#   < 0.50  →  UNKNOWN / DENIED
RECOGNITION_THRESHOLD = 0.50

# ─────────────────────────────────────────────
# Camera Settings
# ─────────────────────────────────────────────
CAMERA_INDEX      = 0      # device index (0 = default webcam)
CAMERA_WIDTH      = 1280
CAMERA_HEIGHT     = 720
TARGET_FPS        = 30

# ─────────────────────────────────────────────
# Access Logging / Debounce
# ─────────────────────────────────────────────
# Minimum seconds between consecutive log entries for the *same* identity.
# Prevents flooding the DB when a person stands in front of the camera.
LOG_COOLDOWN_SECONDS = 5.0

# Minimum seconds between UNKNOWN log entries (grouped, not per-person)
UNKNOWN_COOLDOWN_SECONDS = 5.0

# ─────────────────────────────────────────────
# UI / Visual Styling
# ─────────────────────────────────────────────
# BGR colour tuples for OpenCV drawing

COLOR_AUTHORIZED = (0, 200, 80)     # Emerald green
COLOR_UNKNOWN    = (0, 60, 220)     # Bold red
COLOR_HUD        = (220, 200, 0)    # Cyan/gold HUD text
COLOR_BOX_KNOWN  = (0, 200, 80)     # Bounding box for known person
COLOR_BOX_UNK    = (0, 60, 220)     # Bounding box for unknown

FONT_SCALE_LABEL  = 0.65
FONT_SCALE_STATUS = 0.75
FONT_THICKNESS    = 2

# Number of rows to show when printing logs via --logs flag
LOGS_DISPLAY_ROWS = 20

# Supported image extensions for face registration
SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}

# ─────────────────────────────────────────────
# Hostel Settings
# ─────────────────────────────────────────────
HOSTEL_NAME          = "Block A — Men's Hostel"
GATE_ID              = "MAIN_GATE_01"

# Curfew time in 24-hour HH:MM format.
# Any AUTHORIZED entry AFTER this time is logged as a VIOLATION.
DEFAULT_CURFEW_TIME  = "22:00"

# How many minutes before curfew to show a "Curfew Soon" warning on the HUD
CURFEW_WARNING_MINS  = 30

# ─────────────────────────────────────────────
# Door / Lock Simulation
# ─────────────────────────────────────────────
# Seconds the gate stays "OPEN" after an AUTHORIZED entry before re-locking
DOOR_OPEN_DURATION   = 5.0

# ─────────────────────────────────────────────
# System State File  (shared between camera & dashboard)
# ─────────────────────────────────────────────
# JSON file written by the dashboard (lockdown) and read by main.py (gate control)
SYSTEM_STATE_FILE    = os.path.join(LOGS_DIR, "system_state.json")

# ─────────────────────────────────────────────
# Dashboard Settings
# ─────────────────────────────────────────────
DASHBOARD_REFRESH_SECS  = 3    # auto-refresh interval for Streamlit dashboard
DASHBOARD_LOG_ROWS      = 50   # rows shown in the access log table

# ─────────────────────────────────────────────
# Network Mode Simulation  (4G vs 5G demo)
# ─────────────────────────────────────────────
# Artificial delay injected per frame in 4G mode (seconds).
# Simulates the ~400-600ms latency of a congested 4G network vs <30ms 5G URLLC.
NETWORK_4G_DELAY_SECS   = 0.50

# ─────────────────────────────────────────────
# Alarm Settings
# ─────────────────────────────────────────────
# Seconds before the alarm auto-resets without warden intervention
ALARM_AUTO_RESET_SECS   = 10.0

# Event types that trigger the security alarm
ALARM_TRIGGER_EVENTS    = {"DENIED", "VIOLATION"}

