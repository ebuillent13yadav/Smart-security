# AI-Powered Smart Access & Security System
### Baseline Prototype — Real-Time Face Recognition

---

## Overview

A local, real-time face recognition security system built with Python, OpenCV, and InsightFace (ArcFace + RetinaFace).  
No cloud, no mobile app, no liveness detection in this version — just a solid, fast, hackathon-ready recognition pipeline.

```
Webcam → Face Detection → ArcFace Embedding → Cosine Similarity Match
      → AUTHORIZED / DENIED Decision → HUD Display → SQLite Log
```

---

## Quick Start

### 1. Prerequisites

- Python 3.10+
- A webcam
- (Optional) NVIDIA GPU with CUDA for faster inference

### 2. Install Dependencies

```bash
cd smart-security
pip install -r requirements.txt
```

> **Note:** On first run, InsightFace will automatically download the `buffalo_sc` ONNX model pack (~200 MB) into the `models/` directory.

### 3. Register Known People

**Option A — Drop images into the folder (easiest):**
```
data/known_faces/
├── alice.jpg
└── bob.jpg
```
The filename (without extension) becomes the person's identity name.

**Option B — Register from an image file via CLI:**
```bash
python src/main.py --register --image "C:/path/to/photo.jpg" --name Alice
```

**Option C — Register directly from your webcam:**
```bash
python src/main.py --register-cam --name Alice
# → Camera opens; press SPACE to capture, ESC to cancel
```

### 4. Run the System

```bash
python src/main.py
```

---

## Project Structure

```
smart-security/
│
├── data/
│   ├── known_faces/          # Source identity images (name.jpg → identity "name")
│   └── embeddings.pkl        # Auto-generated embedding cache (gitignored)
│
├── models/                   # Downloaded InsightFace ONNX models (gitignored)
│
├── logs/
│   └── access.db             # SQLite access log database
│
├── src/
│   ├── config.py             # ← All tunable settings live here
│   ├── database.py           # SQLite logger with debounce guard
│   ├── face_engine.py        # InsightFace detector + ArcFace matcher
│   ├── utils.py              # OpenCV drawing / HUD rendering
│   └── main.py               # Entry point & CLI commands
│
├── requirements.txt
├── README.md
└── .gitignore
```

---

## CLI Reference

| Command | Description |
|---|---|
| `python src/main.py` | Launch live recognition |
| `python src/main.py --register --image PATH --name NAME` | Register from image |
| `python src/main.py --register-cam --name NAME` | Register from webcam |
| `python src/main.py --logs` | View last 20 access log entries |
| `python src/main.py --reload` | Rebuild embedding gallery and exit |
| `python src/main.py --threshold 0.55` | Override similarity threshold for this session |

### Live Camera Keybindings

| Key | Action |
|---|---|
| `Q` | Quit |
| `R` | Reload face gallery from disk |
| `S` | Save snapshot to `logs/snapshot_NNNN.jpg` |

---

## Configuration (`src/config.py`)

| Parameter | Default | Description |
|---|---|---|
| `RECOGNITION_THRESHOLD` | `0.50` | Cosine similarity cutoff — raise to tighten security |
| `DETECTION_THRESHOLD` | `0.50` | Min face-detection confidence |
| `LOG_COOLDOWN_SECONDS` | `5.0` | Debounce — min gap between DB entries per identity |
| `UNKNOWN_COOLDOWN_SECONDS` | `5.0` | Same, for UNKNOWN detections |
| `CAMERA_INDEX` | `0` | Webcam device index |
| `CAMERA_WIDTH / HEIGHT` | `1280×720` | Requested resolution |
| `INSIGHTFACE_MODEL_PACK` | `buffalo_sc` | InsightFace model pack name |

---

## Access Log Schema

Stored in `logs/access.db` (SQLite):

```sql
CREATE TABLE access_logs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp   TEXT    NOT NULL,   -- "2026-10-04 11:30:22"
    name        TEXT    NOT NULL,   -- "Alice" or "UNKNOWN"
    status      TEXT    NOT NULL,   -- "AUTHORIZED" or "DENIED"
    similarity  REAL    NOT NULL,   -- cosine similarity score
    face_count  INTEGER DEFAULT 1
);
```

Example records:
```
2026-10-04 11:30:22 | Alice   | AUTHORIZED | 0.8412
2026-10-04 11:31:04 | UNKNOWN | DENIED     | 0.3200
```

---

## Recognition Pipeline (Technical)

1. **Detection** — InsightFace's bundled RetinaFace detector finds face bounding boxes.
2. **Embedding** — ArcFace model produces a **512-dimensional L2-normalised vector** per face.
3. **Matching** — Cosine similarity computed against every registered embedding:
   $$\text{sim}(\mathbf{u}, \mathbf{v}) = \frac{\mathbf{u} \cdot \mathbf{v}}{\|\mathbf{u}\| \|\mathbf{v}\|}$$
4. **Decision** — Best match ≥ `RECOGNITION_THRESHOLD` → **AUTHORIZED**; else → **DENIED**.
5. **Logging** — Debounced write to SQLite (max 1 entry per identity per 5 seconds).

---

## GPU Acceleration (Optional)

For faster inference, install the GPU runtime:
```bash
pip uninstall onnxruntime
pip install onnxruntime-gpu
```
The system automatically prefers `CUDAExecutionProvider` when available (see `ONNX_PROVIDERS` in `config.py`).

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `Cannot open camera` | Check webcam is connected and not used by another app; try `CAMERA_INDEX = 1` in config.py |
| `No face detected` in registration image | Use a clear, well-lit front-facing photo |
| Everyone classified as UNKNOWN | Lower `RECOGNITION_THRESHOLD` slightly (e.g. `0.45`) |
| False matches (wrong person authorised) | Raise `RECOGNITION_THRESHOLD` (e.g. `0.60`) |
| Models not downloading | Ensure internet access; check firewall/proxy settings |
| Slow performance | Use `buffalo_sc` (default — lightweight); install `onnxruntime-gpu` for NVIDIA GPUs |

---

## Roadmap (Future Versions)

- [ ] Liveness detection (anti-spoofing)
- [ ] Web dashboard with live MJPEG stream
- [ ] Mobile app integration
- [ ] 5G / edge cloud deployment
- [ ] Physical door lock actuation (GPIO / relay)
- [ ] Multi-camera support
