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
