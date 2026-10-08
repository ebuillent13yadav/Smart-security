"""
utils.py
--------
All OpenCV drawing utilities: bounding boxes, HUD overlays, status badges, FPS counter.
Kept entirely separate from ML logic so the visual style can be tweaked without
touching recognition code.
"""

import time
import cv2
import numpy as np

from config import (
    COLOR_AUTHORIZED,
    COLOR_UNKNOWN,
    COLOR_HUD,
    COLOR_BOX_KNOWN,
    COLOR_BOX_UNK,
    FONT_SCALE_LABEL,
    FONT_SCALE_STATUS,
    FONT_THICKNESS,
)

FONT = cv2.FONT_HERSHEY_SIMPLEX


# ─────────────────────────────────────────────────────────────
# FPS Tracker
# ─────────────────────────────────────────────────────────────

class FPSCounter:
    """Simple exponential-moving-average FPS tracker."""

    def __init__(self, alpha: float = 0.1):
        self._alpha    = alpha
        self._fps      = 0.0
        self._last_ts  = time.perf_counter()

    def tick(self) -> float:
        now        = time.perf_counter()
        inst_fps   = 1.0 / max(now - self._last_ts, 1e-6)
        self._fps  = self._alpha * inst_fps + (1 - self._alpha) * self._fps
        self._last_ts = now
        return self._fps

    @property
    def fps(self) -> float:
        return self._fps


# ─────────────────────────────────────────────────────────────
# Drawing primitives
# ─────────────────────────────────────────────────────────────

def _put_text_with_bg(
    img: np.ndarray,
    text: str,
    origin: tuple[int, int],
    font_scale: float,
    color: tuple[int, int, int],
    thickness: int = FONT_THICKNESS,
    bg_alpha: float = 0.55,
) -> int:
    """
    Draw *text* at *origin* (bottom-left corner) with a semi-transparent
    background rectangle for readability.

    Returns the pixel height of the rendered text block.
    """
    (tw, th), baseline = cv2.getTextSize(text, FONT, font_scale, thickness)
    x, y = origin
    pad = 4

    # Semi-transparent background
    overlay = img.copy()
    cv2.rectangle(
        overlay,
        (x - pad, y - th - pad),
        (x + tw + pad, y + baseline + pad),
        (0, 0, 0),
        cv2.FILLED,
    )
    cv2.addWeighted(overlay, bg_alpha, img, 1 - bg_alpha, 0, img)

    cv2.putText(img, text, (x, y), FONT, font_scale, color, thickness, cv2.LINE_AA)
    return th + baseline + 2 * pad


def draw_face_result(img: np.ndarray, result: dict):
    """
    Draw a bounding box, status badge, name, and similarity score
    for a single face recognition result dict.

    Expected keys: bbox, name, status, similarity
    """
    x1, y1, x2, y2 = result["bbox"]
    status     = result["status"]      # "AUTHORIZED" | "DENIED"
    name       = result["name"]
    similarity = result["similarity"]

    is_authorized = (status == "AUTHORIZED")
    box_color     = COLOR_BOX_KNOWN if is_authorized else COLOR_BOX_UNK
    label_color   = COLOR_AUTHORIZED if is_authorized else COLOR_UNKNOWN

    # ── Bounding Box ───────────────────────────────────────────
    cv2.rectangle(img, (x1, y1), (x2, y2), box_color, 2)

    # Corner accents (hackathon-demo aesthetic)
    _draw_corner_accents(img, x1, y1, x2, y2, box_color, length=20, thickness=3)

    # ── Info card above the face box ──────────────────────────
    card_x = x1
    card_y = y1 - 10   # start just above the top of the bounding box

    # Status line (AUTHORIZED / UNKNOWN)
    status_text = f"  {status}  "
    line_h = _put_text_with_bg(
        img, status_text,
        origin=(card_x, card_y),
        font_scale=FONT_SCALE_STATUS,
        color=label_color,
        thickness=FONT_THICKNESS,
    )
    card_y -= line_h

    # Name line (only if authorised, else skip)
    if is_authorized:
        name_text = f"Person: {name}"
        line_h = _put_text_with_bg(
            img, name_text,
            origin=(card_x, card_y),
            font_scale=FONT_SCALE_LABEL,
            color=(255, 255, 255),
            thickness=1,
        )
        card_y -= line_h

    # Similarity score
    sim_text = f"Similarity: {similarity:.2f}"
    _put_text_with_bg(
        img, sim_text,
        origin=(card_x, card_y),
        font_scale=FONT_SCALE_LABEL,
        color=(200, 200, 200),
        thickness=1,
    )


def _draw_corner_accents(
    img: np.ndarray,
    x1: int, y1: int, x2: int, y2: int,
    color: tuple[int, int, int],
    length: int = 20,
    thickness: int = 3,
):
    """Draw L-shaped corner accents inside the bounding box corners."""
    corners = [
        # (start_h, start_v, end_h, end_v)
        ((x1, y1), (x1 + length, y1), (x1, y1 + length)),  # top-left
        ((x2, y1), (x2 - length, y1), (x2, y1 + length)),  # top-right
        ((x1, y2), (x1 + length, y2), (x1, y2 - length)),  # bottom-left
        ((x2, y2), (x2 - length, y2), (x2, y2 - length)),  # bottom-right
    ]
    for apex, h_end, v_end in corners:
        cv2.line(img, apex, h_end, color, thickness, cv2.LINE_AA)
        cv2.line(img, apex, v_end, color, thickness, cv2.LINE_AA)


def draw_hud(img: np.ndarray, fps: float, face_count: int, gallery_size: int):
    """
    Draw a top header bar showing system name, FPS, detected face count,
    and number of registered identities.
    """
    h, w = img.shape[:2]
    bar_height = 38

    # Dark semi-transparent banner
    overlay = img.copy()
    cv2.rectangle(overlay, (0, 0), (w, bar_height), (20, 20, 20), cv2.FILLED)
    cv2.addWeighted(overlay, 0.70, img, 0.30, 0, img)

    # Left label
    cv2.putText(
        img, "AI Smart Security",
        (10, bar_height - 10),
        FONT, 0.65, COLOR_HUD, 2, cv2.LINE_AA,
    )

    # Right-aligned stats
    stats = (
        f"FPS: {fps:5.1f}  |  Faces: {face_count}  |  Registered: {gallery_size}"
    )
    (tw, _), _ = cv2.getTextSize(stats, FONT, 0.55, 1)
    cv2.putText(
        img, stats,
        (w - tw - 10, bar_height - 10),
        FONT, 0.55, (200, 200, 200), 1, cv2.LINE_AA,
    )


def draw_no_face_message(img: np.ndarray):
    """Overlay a subtle message when no face is detected in the frame."""
    h, w = img.shape[:2]
    text = "No face detected"
    (tw, th), _ = cv2.getTextSize(text, FONT, 0.6, 1)
    cv2.putText(
        img, text,
        ((w - tw) // 2, h - 20),
        FONT, 0.6, (100, 100, 100), 1, cv2.LINE_AA,
    )


def draw_keybinds(img: np.ndarray):
    """Draw keybinding hints in the bottom-left corner."""
    hints = [
        "Q: Quit",
        "R: Reload gallery",
        "S: Save snapshot",
    ]
    h = img.shape[0]
    y = h - 10 - (len(hints) - 1) * 22
    for hint in hints:
        cv2.putText(img, hint, (10, y), FONT, 0.45, (130, 130, 130), 1, cv2.LINE_AA)
        y += 22


# ─────────────────────────────────────────────────────────────
# Phase 3 — Door Bar, Alarm Overlay, Network Badge
# ─────────────────────────────────────────────────────────────

def draw_door_bar(
    img: np.ndarray,
    door_open_until: float,
    lockdown: bool,
    alarm_active: bool,
    flash_state: int = 0,
):
    """
    Draw a full-width status bar at the BOTTOM of the frame showing gate state.

    States (highest to lowest priority):
      ALARM    — flashing red bar — unknown intruder / curfew violation
      LOCKDOWN — solid dark-red bar — emergency lockdown active
      OPEN     — green bar with countdown timer — door is open after auth
      LOCKED   — dark neutral bar — default idle state
    """
    h, w = img.shape[:2]
    BAR_H = 52
    y_top = h - BAR_H

    now = time.perf_counter()

    if alarm_active:
        # Alternate between two reds for a flash effect
        color = (0, 0, 230) if flash_state == 0 else (0, 0, 160)
        label = "  SECURITY ALARM  —  UNKNOWN / VIOLATION DETECTED  "
        text_color = (255, 255, 255)
    elif lockdown:
        color      = (30, 0, 120)
        label      = "  EMERGENCY LOCKDOWN ACTIVE  —  ALL ACCESS DENIED  "
        text_color = (255, 180, 180)
    elif now < door_open_until:
        remaining  = max(0.0, door_open_until - now)
        color      = (20, 140, 40)
        label      = f"  GATE OPEN  —  Auto-locks in {remaining:.1f}s  "
        text_color = (255, 255, 255)
    else:
        color      = (30, 30, 50)
        label      = "  GATE LOCKED  "
        text_color = (160, 160, 180)

    # Fill bar
    overlay = img.copy()
    cv2.rectangle(overlay, (0, y_top), (w, h), color, cv2.FILLED)
    alpha = 0.90 if alarm_active else 0.85
    cv2.addWeighted(overlay, alpha, img, 1 - alpha, 0, img)

    # Centred text
    (tw, th), _ = cv2.getTextSize(label, FONT, 0.72, 2)
    tx = (w - tw) // 2
    ty = y_top + (BAR_H + th) // 2
    cv2.putText(img, label, (tx, ty), FONT, 0.72, text_color, 2, cv2.LINE_AA)

    # Alarm flashing border around the entire frame
    if alarm_active and flash_state == 0:
        cv2.rectangle(img, (0, 0), (w - 1, h - 1), (0, 0, 220), 6)
        cv2.rectangle(img, (6, 6), (w - 7, h - 7), (0, 0, 180), 3)


def draw_network_badge(img: np.ndarray, mode: str, latency_ms: float):
    """
    Draw a small network-mode badge in the top-right of the HUD area.
    Shows the current mode (5G / 4G) and simulated round-trip latency.

    Colour coding:
      5G — teal/green (low latency, URLLC)
      4G — orange/amber (high latency, congested)
    """
    is_5g  = (mode == "5G")
    color  = (0, 210, 120) if is_5g else (0, 140, 255)
    label  = f"{'⚡' if is_5g else '🐌'} {mode}  |  {latency_ms:.0f} ms"

    h, w = img.shape[:2]
    (tw, th), _ = cv2.getTextSize(label, FONT, 0.58, 1)
    x = w - tw - 14
    y = 76   # just below the main HUD bar

    # Badge background
    pad = 4
    overlay = img.copy()
    cv2.rectangle(
        overlay,
        (x - pad, y - th - pad),
        (x + tw + pad, y + pad),
        (10, 10, 10),
        cv2.FILLED,
    )
    cv2.addWeighted(overlay, 0.70, img, 0.30, 0, img)

    # Badge text
    cv2.putText(img, label, (x, y), FONT, 0.58, color, 1, cv2.LINE_AA)

    # Mode label pill (left of badge)
    pill = f" {mode} "
    (pw, ph), _ = cv2.getTextSize(pill, FONT, 0.48, 1)
    px = x - pw - 10
    overlay2 = img.copy()
    cv2.rectangle(overlay2, (px - 3, y - ph - 3), (px + pw + 3, y + 3), color, cv2.FILLED)
    cv2.addWeighted(overlay2, 0.75, img, 0.25, 0, img)
    cv2.putText(img, pill, (px, y), FONT, 0.48, (0, 0, 0), 1, cv2.LINE_AA)
