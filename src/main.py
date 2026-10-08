"""
main.py
-------
Application entry point for the AI-Powered Smart Hostel Access & Security System.

Usage
─────
  python src/main.py                              # Live camera + recognition
  python src/main.py --register --image PATH --name NAME
  python src/main.py --register-cam --name NAME
  python src/main.py --logs
  python src/main.py --reload
  python src/main.py --add-student
"""

import argparse
import os
import random
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))

import cv2

from config import (
    CAMERA_INDEX, CAMERA_WIDTH, CAMERA_HEIGHT, TARGET_FPS,
    MODELS_DIR, KNOWN_FACES_DIR, LOGS_DIR,
    DOOR_OPEN_DURATION, HOSTEL_NAME, GATE_ID, DEFAULT_CURFEW_TIME,
    NETWORK_4G_DELAY_SECS,
)
from database import AccessLogger
from face_engine import FaceEngine
from hostel import (
    EntryExitTracker, AlarmManager,
    classify_event, is_lockdown_active, curfew_status,
    get_network_mode, read_system_state, write_system_state,
)
from utils import (
    FPSCounter, draw_face_result, draw_hud,
    draw_no_face_message, draw_keybinds,
    draw_door_bar, draw_network_badge,
)




# ─────────────────────────────────────────────────────────────
# Audio Alerts  (Windows winsound — built-in, no install)
# ─────────────────────────────────────────────────────────────

def _beep(freq: int, duration: int):
    """Play a system beep. Silent on non-Windows platforms."""
    try:
        import winsound
        winsound.Beep(freq, duration)
    except Exception:
        pass   # Linux/macOS — skip silently


# ─────────────────────────────────────────────────────────────
# CLI Argument Parsing
# ─────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="smart-security",
        description="AI-Powered Smart Hostel Access & Security System",
    )
    parser.add_argument("--register",     action="store_true")
    parser.add_argument("--register-cam", action="store_true", dest="register_cam")
    parser.add_argument("--image",        type=str, default=None)
    parser.add_argument("--name",         type=str, default=None)
    parser.add_argument("--logs",         action="store_true")
    parser.add_argument("--reload",       action="store_true")
    parser.add_argument("--add-student",  action="store_true", dest="add_student")
    parser.add_argument("--threshold",    type=float, default=None)
    return parser.parse_args()


# ─────────────────────────────────────────────────────────────
# Registration Helpers
# ─────────────────────────────────────────────────────────────

def cmd_register_image(engine: FaceEngine, image_path: str, name: str):
    if not image_path:
        print("[ERROR] --image PATH required."); sys.exit(1)
    if not name:
        print("[ERROR] --name NAME required."); sys.exit(1)
    if not os.path.isfile(image_path):
        print(f"[ERROR] File not found: {image_path}"); sys.exit(1)
    sys.exit(0 if engine.register_from_file(image_path, name) else 1)


def cmd_register_webcam(engine: FaceEngine, name: str):
    if not name:
        print("[ERROR] --name NAME required."); sys.exit(1)
    cap = _open_camera()
    print(f"[INFO] Registering '{name}' — SPACE to capture, ESC to cancel.")
    captured = False
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        cv2.putText(frame, f"Register: {name}  |  SPACE=capture  ESC=cancel",
                    (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 220, 80), 2, cv2.LINE_AA)
        cv2.imshow("Registration", frame)
        key = cv2.waitKey(1) & 0xFF
        if key == 27:
            break
        elif key == 32:
            captured = engine.register_from_frame(frame, name)
            break
    cap.release(); cv2.destroyAllWindows()
    sys.exit(0 if captured else 1)


def cmd_add_student(logger: AccessLogger):
    print("\n── Register Student Metadata ──────────────────────")
    print("Name must match the image filename stem in data/known_faces/")
    name   = input("Name         : ").strip()
    roll   = input("Roll Number  : ").strip()
    room   = input("Room Number  : ").strip()
    block  = input("Hostel Block : ").strip() or "A"
    curfew = input(f"Curfew HH:MM [{DEFAULT_CURFEW_TIME}]: ").strip() or DEFAULT_CURFEW_TIME
    if not name:
        print("[ERROR] Name is required."); sys.exit(1)
    ok = logger.register_student(name, roll, room, block, curfew)
    print(f"\n  ✔ '{name}' registered." if ok else "[ERROR] Failed.")


# ─────────────────────────────────────────────────────────────
# Camera
# ─────────────────────────────────────────────────────────────

def _open_camera() -> cv2.VideoCapture:
    cap = cv2.VideoCapture(CAMERA_INDEX, cv2.CAP_DSHOW)
    if not cap.isOpened():
        cap = cv2.VideoCapture(CAMERA_INDEX)
    if not cap.isOpened():
        print(f"[ERROR] Cannot open camera {CAMERA_INDEX}."); sys.exit(1)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH,  CAMERA_WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAMERA_HEIGHT)
    cap.set(cv2.CAP_PROP_FPS,          TARGET_FPS)
    return cap


def _draw_curfew_badge(img, status: str):
    if status == "OK":
        return
    h, w = img.shape[:2]
    text  = "  CURFEW SOON  " if status == "WARNING" else "  PAST CURFEW  "
    color = (0, 160, 255) if status == "WARNING" else (0, 60, 220)
    (tw, _), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 1)
    cv2.putText(img, text, (w - tw - 10, img.shape[0] - 60),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 1, cv2.LINE_AA)


# ─────────────────────────────────────────────────────────────
# Main Recognition Loop
# ─────────────────────────────────────────────────────────────

def run_recognition_loop(engine: FaceEngine, logger: AccessLogger):
    cap             = _open_camera()
    fps_counter     = FPSCounter()
    tracker         = EntryExitTracker()
    alarm           = AlarmManager()
    snapshot_ctr    = 0
    door_open_until = 0.0
    _sim_latency    = 18.0

    os.makedirs(LOGS_DIR, exist_ok=True)

    print(f"[INFO] System online — {HOSTEL_NAME} | Gate: {GATE_ID}")
    print("[INFO] Keys: Q=quit  R=reload  S=snapshot  N=network toggle  A=reset alarm")

    while True:
        ret, frame = cap.read()
        if not ret:
            time.sleep(0.05)
            continue

        # ── Shared state (written by dashboard) ───────────────
        state    = read_system_state()
        lockdown = state.get("lockdown", False)
        net_mode = state.get("network_mode", "5G")

        # ── 4G latency simulation ─────────────────────────────
        if net_mode == "4G":
            delay = NETWORK_4G_DELAY_SECS + random.uniform(-0.05, 0.10)
            time.sleep(max(0.0, delay))
            _sim_latency = round(random.uniform(380, 620), 0)
        else:
            _sim_latency = round(random.uniform(12, 28), 1)

        # ── Face Recognition ──────────────────────────────────
        results = engine.process_frame(frame)
        if lockdown:
            for r in results:
                r["status"] = "DENIED"

        # ── Hostel Logic + Alerts ─────────────────────────────
        for res in results:
            student    = logger.get_student(res["name"])
            s_curfew   = student["curfew_time"] if student else None
            s_room     = student["room_number"]  if student else ""

            event_type = classify_event(
                name=res["name"], status=res["status"],
                tracker=tracker, student_curfew=s_curfew,
            )
            res["event_type"] = event_type

            # ── Alarm + Beep ──────────────────────────────────
            if event_type == "VIOLATION":
                alarm.check_and_trigger(event_type, name=res["name"])
                _beep(880, 300)   # High beep = curfew violation

            elif event_type == "DENIED":
                alarm.check_and_trigger(event_type, name="UNKNOWN")
                _beep(440, 500)   # Low beep = unknown person

            # ── Gate door control ─────────────────────────────
            if res["status"] == "AUTHORIZED" and not lockdown:
                door_open_until = time.perf_counter() + DOOR_OPEN_DURATION

            # ── DB write (debounced) ──────────────────────────
            logger.log(
                name=res["name"], status=res["status"],
                similarity=res["similarity"],
                event_type=event_type, face_count=len(results),
            )

        # ── Render frame ──────────────────────────────────────
        fps = fps_counter.tick()

        draw_hud(frame, fps=fps, face_count=len(results),
                 gallery_size=len(engine._gallery))
        draw_network_badge(frame, net_mode, _sim_latency)

        if results:
            for res in results:
                draw_face_result(frame, res)
        else:
            draw_no_face_message(frame)

        _draw_curfew_badge(frame, curfew_status(DEFAULT_CURFEW_TIME))
        draw_door_bar(frame,
                      door_open_until=door_open_until,
                      lockdown=lockdown,
                      alarm_active=alarm.is_active,
                      flash_state=alarm.flash_state)
        draw_keybinds(frame)
        cv2.imshow("AI Smart Security — Hostel Gate", frame)

        # ── Key Handling ──────────────────────────────────────
        key = cv2.waitKey(1) & 0xFF
        if key == ord("q"):
            print("[INFO] Quitting …"); break
        elif key == ord("r"):
            engine.reload_gallery()
        elif key == ord("s"):
            snapshot_ctr += 1
            p = os.path.join(LOGS_DIR, f"snapshot_{snapshot_ctr:04d}.jpg")
            cv2.imwrite(p, frame)
            print(f"[INFO] Snapshot → {p}")
        elif key == ord("n"):
            new = "4G" if net_mode == "5G" else "5G"
            state["network_mode"] = new
            write_system_state(state)
            print(f"[INFO] Network → {new}")
        elif key == ord("a"):
            alarm.reset()
            print("[INFO] Alarm reset by operator.")

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
        print(f"[INFO] Threshold → {args.threshold}")

    if args.logs:
        AccessLogger().print_logs(); return

    print("[INFO] Initialising face engine …")
    engine = FaceEngine()
    logger = AccessLogger()

    if args.reload:      engine.reload_gallery(); return
    if args.register:    cmd_register_image(engine, args.image, args.name); return
    if args.register_cam: cmd_register_webcam(engine, args.name); return
    if args.add_student:  cmd_add_student(logger); return

    run_recognition_loop(engine, logger)


if __name__ == "__main__":
    main()
