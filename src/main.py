"""
main.py
-------
Application entry point for the AI-Powered Smart Hostel Access & Security System.

Usage
─────
  python src/main.py                              # Run live camera + recognition
  python src/main.py --register --image PATH --name NAME   # Register from image
  python src/main.py --register-cam --name NAME   # Register from webcam snapshot
  python src/main.py --logs                       # View recent access logs
  python src/main.py --reload                     # Rebuild gallery then exit
  python src/main.py --add-student                # Register student metadata interactively
"""

import argparse
import os
import sys
import time

# Allow sibling imports when running as `python src/main.py`
sys.path.insert(0, os.path.dirname(__file__))

import cv2

from config import (
    CAMERA_INDEX,
    CAMERA_WIDTH,
    CAMERA_HEIGHT,
    TARGET_FPS,
    LOGS_DISPLAY_ROWS,
    MODELS_DIR,
    KNOWN_FACES_DIR,
    LOGS_DIR,
    DOOR_OPEN_DURATION,
    COLOR_AUTHORIZED,
    COLOR_UNKNOWN,
    HOSTEL_NAME,
    GATE_ID,
    DEFAULT_CURFEW_TIME,
)
from database import AccessLogger
from face_engine import FaceEngine
from hostel import EntryExitTracker, classify_event, is_lockdown_active, curfew_status
from utils import (
    FPSCounter,
    draw_face_result,
    draw_hud,
    draw_no_face_message,
    draw_keybinds,
)


# ─────────────────────────────────────────────────────────────
# CLI Argument Parsing
# ─────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="smart-security",
        description="AI-Powered Smart Hostel Access & Security System",
    )
    parser.add_argument("--register",     action="store_true",
                        help="Register from image (requires --image, --name).")
    parser.add_argument("--register-cam", action="store_true", dest="register_cam",
                        help="Register from webcam (requires --name).")
    parser.add_argument("--image",        type=str, default=None)
    parser.add_argument("--name",         type=str, default=None)
    parser.add_argument("--logs",         action="store_true",
                        help="Print recent access logs and exit.")
    parser.add_argument("--reload",       action="store_true",
                        help="Rebuild face embedding gallery and exit.")
    parser.add_argument("--add-student",  action="store_true", dest="add_student",
                        help="Interactively register student metadata in the DB.")
    parser.add_argument("--threshold",    type=float, default=None,
                        help="Override recognition threshold for this session.")
    return parser.parse_args()


# ─────────────────────────────────────────────────────────────
# Registration Helpers
# ─────────────────────────────────────────────────────────────

def cmd_register_image(engine: FaceEngine, image_path: str, name: str):
    if not image_path:
        print("[ERROR] --image PATH is required with --register."); sys.exit(1)
    if not name:
        print("[ERROR] --name NAME is required with --register."); sys.exit(1)
    if not os.path.isfile(image_path):
        print(f"[ERROR] Image file not found: {image_path}"); sys.exit(1)
    ok = engine.register_from_file(image_path, name)
    sys.exit(0 if ok else 1)


def cmd_register_webcam(engine: FaceEngine, name: str):
    if not name:
        print("[ERROR] --name NAME is required with --register-cam."); sys.exit(1)
    cap = _open_camera()
    print(f"[INFO] Point camera at '{name}' — SPACE to capture, ESC to cancel.")
    captured = False
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        cv2.putText(frame, f"Registering: {name}  |  SPACE=capture  ESC=cancel",
                    (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 220, 80), 2, cv2.LINE_AA)
        cv2.imshow("Registration", frame)
        key = cv2.waitKey(1) & 0xFF
        if key == 27:
            print("[INFO] Registration cancelled."); break
        elif key == 32:
            ok = engine.register_from_frame(frame, name)
            if ok:
                captured = True
            break
    cap.release()
    cv2.destroyAllWindows()
    sys.exit(0 if captured else 1)


def cmd_add_student(logger: AccessLogger):
    """Interactive CLI to add student metadata to the DB."""
    print("\n── Register Student Metadata ──────────────────────")
    print("(Name must match the image filename in data/known_faces/)")
    name   = input("Name         : ").strip()
    roll   = input("Roll Number  : ").strip()
    room   = input("Room Number  : ").strip()
    block  = input("Hostel Block : ").strip() or "A"
    curfew = input(f"Curfew (HH:MM) [{DEFAULT_CURFEW_TIME}]: ").strip() or DEFAULT_CURFEW_TIME
    if not name:
        print("[ERROR] Name is required."); sys.exit(1)
    ok = logger.register_student(name, roll, room, block, curfew)
    if ok:
        print(f"\n✔ Student '{name}' registered — Room {room or '—'}, Roll {roll or '—'}")
    else:
        print("[ERROR] Failed to register student."); sys.exit(1)


# ─────────────────────────────────────────────────────────────
# Camera Helper
# ─────────────────────────────────────────────────────────────

def _open_camera() -> cv2.VideoCapture:
    cap = cv2.VideoCapture(CAMERA_INDEX, cv2.CAP_DSHOW)
    if not cap.isOpened():
        cap = cv2.VideoCapture(CAMERA_INDEX)
    if not cap.isOpened():
        print(f"[ERROR] Cannot open camera (index {CAMERA_INDEX}).")
        sys.exit(1)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH,  CAMERA_WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAMERA_HEIGHT)
    cap.set(cv2.CAP_PROP_FPS,          TARGET_FPS)
    return cap


# ─────────────────────────────────────────────────────────────
# Door State Overlay
# ─────────────────────────────────────────────────────────────

def draw_door_state(img, door_open_until: float, lockdown: bool):
    """Draw a door / gate status badge in the top-right corner."""
    h, w = img.shape[:2]
    now  = time.monotonic()

    if lockdown:
        label = "🚨 LOCKDOWN"
        color = (0, 0, 200)
    elif now < door_open_until:
        remaining = max(0, door_open_until - now)
        label = f"GATE OPEN  {remaining:.1f}s"
        color = (0, 200, 80)
    else:
        label = "GATE LOCKED"
        color = (60, 60, 180)

    (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.65, 2)
    x = w - tw - 20
    y = 65
    overlay = img.copy()
    cv2.rectangle(overlay, (x - 8, y - th - 8), (x + tw + 8, y + 8), (20, 20, 20), cv2.FILLED)
    cv2.addWeighted(overlay, 0.7, img, 0.3, 0, img)
    cv2.putText(img, label, (x, y), cv2.FONT_HERSHEY_SIMPLEX, 0.65, color, 2, cv2.LINE_AA)


def draw_curfew_badge(img, status: str):
    """Draw a curfew status badge at the bottom-right."""
    h, w = img.shape[:2]
    if status == "OK":
        return
    text  = "⚠ CURFEW SOON" if status == "WARNING" else "🔴 PAST CURFEW"
    color = (0, 160, 255) if status == "WARNING" else (0, 60, 220)
    cv2.putText(img, text, (w - 250, h - 15),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2, cv2.LINE_AA)


# ─────────────────────────────────────────────────────────────
# Main Recognition Loop
# ─────────────────────────────────────────────────────────────

def run_recognition_loop(engine: FaceEngine, logger: AccessLogger):
    cap          = _open_camera()
    fps_counter  = FPSCounter()
    tracker      = EntryExitTracker()
    snapshot_ctr = 0
    door_open_until = 0.0   # epoch time when gate should re-lock

    os.makedirs(LOGS_DIR, exist_ok=True)
    print("[INFO] Camera started.")
    print("[INFO] Keys: Q=quit  R=reload gallery  S=snapshot")
    print(f"[INFO] Hostel: {HOSTEL_NAME}  |  Gate: {GATE_ID}")

    while True:
        ret, frame = cap.read()
        if not ret:
            time.sleep(0.05)
            continue

        # ── Check lockdown state from shared JSON (set by dashboard) ──
        lockdown = is_lockdown_active()

        # ── Face Detection + Recognition ──────────────────────────────
        if not lockdown:
            results = engine.process_frame(frame)
        else:
            # In lockdown: still detect faces for display, but force DENY all
            raw = engine.process_frame(frame)
            results = []
            for r in raw:
                r["status"]    = "DENIED"
                r["name"]      = r["name"] if r["name"] != "UNKNOWN" else "UNKNOWN"
                results.append(r)

        # ── Hostel logic + Logging ────────────────────────────────────
        for res in results:
            # Get student's curfew from DB (per-student override)
            student = logger.get_student(res["name"])
            s_curfew = student["curfew_time"] if student else None

            # Classify: ENTRY / EXIT / VIOLATION / DENIED
            event_type = classify_event(
                name=res["name"],
                status=res["status"],
                tracker=tracker,
                student_curfew=s_curfew,
            )
            res["event_type"] = event_type   # attach for UI use

            # Open gate briefly on successful authorized ENTRY or EXIT
            if res["status"] == "AUTHORIZED" and not lockdown:
                door_open_until = time.monotonic() + DOOR_OPEN_DURATION

            # Debounced DB write
            logger.log(
                name=res["name"],
                status=res["status"],
                similarity=res["similarity"],
                event_type=event_type,
                face_count=len(results),
            )

        # ── Draw UI ───────────────────────────────────────────────────
        fps = fps_counter.tick()
        draw_hud(frame, fps=fps, face_count=len(results), gallery_size=len(engine._gallery))

        if results:
            for res in results:
                draw_face_result(frame, res)
        else:
            draw_no_face_message(frame)

        draw_door_state(frame, door_open_until, lockdown)
        draw_curfew_badge(frame, curfew_status(DEFAULT_CURFEW_TIME))
        draw_keybinds(frame)

        cv2.imshow("AI Smart Security", frame)

        # ── Key Handling ──────────────────────────────────────────────
        key = cv2.waitKey(1) & 0xFF
        if key == ord("q"):
            print("[INFO] Quitting …"); break
        elif key == ord("r"):
            engine.reload_gallery()
        elif key == ord("s"):
            snapshot_ctr += 1
            snap_path = os.path.join(LOGS_DIR, f"snapshot_{snapshot_ctr:04d}.jpg")
            cv2.imwrite(snap_path, frame)
            print(f"[INFO] Snapshot → {snap_path}")

    cap.release()
    cv2.destroyAllWindows()


# ─────────────────────────────────────────────────────────────
# Entry Point
# ─────────────────────────────────────────────────────────────

def main():
    for d in [KNOWN_FACES_DIR, MODELS_DIR, LOGS_DIR]:
        os.makedirs(d, exist_ok=True)

    args = parse_args()

    if args.threshold is not None:
        import config
        config.RECOGNITION_THRESHOLD = args.threshold
        print(f"[INFO] Threshold overridden → {args.threshold}")

    # --logs: no model needed
    if args.logs:
        logger = AccessLogger()
        logger.print_logs()
        return

    print("[INFO] Initialising face engine …")
    engine = FaceEngine()
    logger = AccessLogger()

    if args.reload:
        engine.reload_gallery(); return

    if args.register:
        cmd_register_image(engine, args.image, args.name); return

    if args.register_cam:
        cmd_register_webcam(engine, args.name); return

    if args.add_student:
        cmd_add_student(logger); return

    # Default — live recognition loop
    run_recognition_loop(engine, logger)


if __name__ == "__main__":
    main()
