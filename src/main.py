"""
main.py
-------
Application entry point for the AI-Powered Smart Access & Security System.

Usage
─────
  python src/main.py                              # Run live camera + recognition
  python src/main.py --register --image PATH --name NAME   # Register from image file
  python src/main.py --register-cam --name NAME   # Register from webcam snapshot
  python src/main.py --logs                       # View recent access logs
  python src/main.py --reload                     # Rebuild gallery then exit
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
)
from database import AccessLogger
from face_engine import FaceEngine
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
        description="AI-Powered Smart Access & Security System — baseline prototype",
    )
    parser.add_argument(
        "--register",
        action="store_true",
        help="Register a new person from an image file (requires --image and --name).",
    )
    parser.add_argument(
        "--register-cam",
        action="store_true",
        dest="register_cam",
        help="Capture a face from the webcam and register it (requires --name).",
    )
    parser.add_argument(
        "--image",
        type=str,
        default=None,
        help="Path to the source image when using --register.",
    )
    parser.add_argument(
        "--name",
        type=str,
        default=None,
        help="Identity name used for registration.",
    )
    parser.add_argument(
        "--logs",
        action="store_true",
        help=f"Display the last {LOGS_DISPLAY_ROWS} access log entries and exit.",
    )
    parser.add_argument(
        "--reload",
        action="store_true",
        help="Rebuild the face embedding gallery from known_faces/ and exit.",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=None,
        help="Override recognition threshold for this session (e.g. 0.55).",
    )
    return parser.parse_args()


# ─────────────────────────────────────────────────────────────
# Registration Helpers
# ─────────────────────────────────────────────────────────────

def cmd_register_image(engine: FaceEngine, image_path: str, name: str):
    """Register an identity from a static image file."""
    if not image_path:
        print("[ERROR] --image PATH is required with --register.")
        sys.exit(1)
    if not name:
        print("[ERROR] --name NAME is required with --register.")
        sys.exit(1)
    if not os.path.isfile(image_path):
        print(f"[ERROR] Image file not found: {image_path}")
        sys.exit(1)

    ok = engine.register_from_file(image_path, name)
    sys.exit(0 if ok else 1)


def cmd_register_webcam(engine: FaceEngine, name: str):
    """Capture a face from the webcam for registration."""
    if not name:
        print("[ERROR] --name NAME is required with --register-cam.")
        sys.exit(1)

    cap = _open_camera()

    print(f"[INFO] Point the camera at '{name}' and press SPACE to capture, ESC to cancel.")
    captured = False

    while True:
        ret, frame = cap.read()
        if not ret:
            print("[ERROR] Failed to read from camera.")
            break

        cv2.putText(
            frame,
            f"Registering: {name}  |  SPACE=capture  ESC=cancel",
            (10, 30),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (0, 220, 80),
            2,
            cv2.LINE_AA,
        )
        cv2.imshow("Registration", frame)

        key = cv2.waitKey(1) & 0xFF
        if key == 27:   # ESC
            print("[INFO] Registration cancelled.")
            break
        elif key == 32:  # SPACE
            ok = engine.register_from_frame(frame, name)
            if ok:
                print(f"[INFO] '{name}' registered successfully.")
                captured = True
            break

    cap.release()
    cv2.destroyAllWindows()
    sys.exit(0 if captured else 1)


# ─────────────────────────────────────────────────────────────
# Camera Helpers
# ─────────────────────────────────────────────────────────────

def _open_camera() -> cv2.VideoCapture:
    """Open the webcam and apply resolution settings. Exits on failure."""
    cap = cv2.VideoCapture(CAMERA_INDEX, cv2.CAP_DSHOW)  # CAP_DSHOW faster on Windows
    if not cap.isOpened():
        # Try without backend hint
        cap = cv2.VideoCapture(CAMERA_INDEX)
    if not cap.isOpened():
        print(f"[ERROR] Cannot open camera (index {CAMERA_INDEX}). "
              "Check that your webcam is connected and not in use by another application.")
        sys.exit(1)

    cap.set(cv2.CAP_PROP_FRAME_WIDTH,  CAMERA_WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAMERA_HEIGHT)
    cap.set(cv2.CAP_PROP_FPS,          TARGET_FPS)
    return cap


# ─────────────────────────────────────────────────────────────
# Main Recognition Loop
# ─────────────────────────────────────────────────────────────

def run_recognition_loop(engine: FaceEngine, logger: AccessLogger):
    """
    Open the webcam and run the full recognition pipeline until the user
    presses Q (quit), R (reload gallery), or S (save snapshot).
    """
    cap = _open_camera()
    fps_counter = FPSCounter()
    snapshot_counter = 0

    os.makedirs(LOGS_DIR, exist_ok=True)

    print("[INFO] Camera started. Press Q to quit, R to reload gallery, S to snapshot.")

    while True:
        ret, frame = cap.read()
        if not ret:
            print("[WARNING] Dropped frame — retrying …")
            time.sleep(0.05)
            continue

        # ── Face Detection + Recognition ──────────────────────
        results = engine.process_frame(frame)

        # ── Log Events (debounced) ────────────────────────────
        for res in results:
            logger.log(
                name=res["name"],
                status=res["status"],
                similarity=res["similarity"],
                face_count=len(results),
            )

        # ── Draw UI ───────────────────────────────────────────
        fps = fps_counter.tick()

        draw_hud(frame, fps=fps, face_count=len(results), gallery_size=len(engine._gallery))

        if results:
            for res in results:
                draw_face_result(frame, res)
        else:
            draw_no_face_message(frame)

        draw_keybinds(frame)

        cv2.imshow("AI Smart Security", frame)

        # ── Key Handling ──────────────────────────────────────
        key = cv2.waitKey(1) & 0xFF

        if key == ord("q"):
            print("[INFO] Quitting …")
            break

        elif key == ord("r"):
            print("[INFO] Reloading gallery …")
            engine.reload_gallery()

        elif key == ord("s"):
            snapshot_counter += 1
            snap_path = os.path.join(LOGS_DIR, f"snapshot_{snapshot_counter:04d}.jpg")
            cv2.imwrite(snap_path, frame)
            print(f"[INFO] Snapshot saved → {snap_path}")

    cap.release()
    cv2.destroyAllWindows()


# ─────────────────────────────────────────────────────────────
# Entry Point
# ─────────────────────────────────────────────────────────────

def main():
    # Ensure required directories exist before anything else
    for d in [KNOWN_FACES_DIR, MODELS_DIR, LOGS_DIR]:
        os.makedirs(d, exist_ok=True)

    args = parse_args()

    # ── Runtime threshold override ────────────────────────────
    if args.threshold is not None:
        import config
        config.RECOGNITION_THRESHOLD = args.threshold
        print(f"[INFO] Recognition threshold overridden → {args.threshold}")

    # ── --logs mode ───────────────────────────────────────────
    if args.logs:
        logger = AccessLogger()
        logger.print_logs()
        return

    # ── Load model and gallery ────────────────────────────────
    print("[INFO] Initialising face engine …")
    engine = FaceEngine()
    logger = AccessLogger()

    # ── --reload mode ─────────────────────────────────────────
    if args.reload:
        engine.reload_gallery()
        return

    # ── --register mode (from image file) ────────────────────
    if args.register:
        cmd_register_image(engine, args.image, args.name)
        return  # cmd_register_image calls sys.exit internally

    # ── --register-cam mode ───────────────────────────────────
    if args.register_cam:
        cmd_register_webcam(engine, args.name)
        return

    # ── Default: live recognition loop ───────────────────────
    run_recognition_loop(engine, logger)


if __name__ == "__main__":
    main()
