# 🔒 AI-Powered Smart Hostel Access & Security System

> **5G-Edge Face Recognition for Student Hostel Security**  
> Hackathon Prototype — Real-time, Local, Production-Ready

---

## 🎯 What It Does

Traditional hostel security relies on RFID cards (shareable, loseable) or manual sign-in registers (faked, slow). This system replaces both with **instant AI face recognition** — identifying registered students in real time, logging every entry/exit, detecting curfew violations, and alerting the warden via the dashboard.

The **5G angle**: Standard campus Wi-Fi over 4G introduces 400–600ms latency, creating visible queue build-up at hostel gates during peak hours (post-curfew rush). A **5G URLLC dedicated network slice** reduces this to **<30ms**, enabling instant door actuation with zero queue formation.

---

## 🏗️ Architecture

```
Webcam Feed
    │
    ▼
Face Detection ──────── RetinaFace (InsightFace)
    │
    ▼
Face Embedding ──────── ArcFace 512-d vector
    │
    ▼
Cosine Similarity ────── vs. Registered Gallery
    │
    ├── AUTHORIZED ──► Gate OPEN (5s) + DB Log
    ├── VIOLATION  ──► Gate OPEN + 🚨 Alarm + 🔔 Beep
    └── DENIED     ──► Gate LOCKED + 🚨 Alarm + 🔔 Beep
         │
         ▼
    SQLite DB (logs/access.db)
         │
         ▼
    Streamlit Dashboard ◄──► system_state.json ◄──► Camera
    (Warden Web UI)          (Lockdown / 4G-5G Toggle / Alarm)
```

---

## ✨ Features

| Category | Feature |
|---|---|
| 🧠 **Recognition** | InsightFace ArcFace (512-d embeddings), configurable similarity threshold |
| 🎥 **Camera HUD** | Bounding box + corner accents, status badge, similarity score, live FPS |
| 🚪 **Gate Simulation** | Full-width OPEN / LOCKED / ALARM door bar with countdown timer |
| 📡 **5G Demo** | Live URLLC metrics panel; one-click 4G/5G toggle with real latency injection |
| 🚨 **Alarm System** | Flashing red border + beep sound on UNKNOWN/VIOLATION; auto-resets in 10s |
| 📋 **Warden Dashboard** | Streamlit UI — live log, today's stats, lockdown button, student registry |
| 🏠 **Hostel Logic** | Curfew tracking, entry/exit state machine, per-student curfew override |
| 🗃️ **SQLite Logs** | Debounced logging — ENTRY / EXIT / VIOLATION / DENIED with room number |
| 🔒 **Lockdown** | Dashboard button instantly denies all access; camera reads state in real time |

---

## ⚡ Quick Start

### 1. Setup
```powershell
cd d:\Hacks\face_auth\smart-security

# Create venv with Python 3.11
py -3.11 -m venv venv

# Install all dependencies
venv\Scripts\pip.exe install -r requirements.txt
```

### 2. Register Known People

**Option A — Drop photos into the folder:**
```
data/known_faces/
├── alice.jpg      ← filename becomes the identity name
└── bob.jpg
```

**Option B — Live webcam capture:**
```powershell
venv\Scripts\python.exe src\main.py --register-cam --name alice
```

**Option C — From an existing image file:**
```powershell
venv\Scripts\python.exe src\main.py --register --image "C:\photo.jpg" --name alice
```

### 3. (Optional) Add Student Metadata
```powershell
venv\Scripts\python.exe src\main.py --add-student
# Prompts for: name, roll number, room number, curfew time
```

### 4. (Optional) Seed Demo Data
```powershell
# Populates DB with 6 students + a realistic full-day event history
venv\Scripts\python.exe scripts\seed_demo_data.py
```

### 5. Launch

**Terminal 1 — Camera:**
```powershell
.\start_camera.bat
```

**Terminal 2 — Warden Dashboard:**
```powershell
.\start_dashboard.bat
# Opens: http://localhost:8501
```

---

## 🖥️ Project Structure

```
smart-security/
│
├── data/
│   ├── known_faces/          # Registration images  (name.jpg → identity)
│   └── embeddings.pkl        # Auto-cached face embeddings
│
├── models/                   # InsightFace ONNX models (~16 MB, auto-downloaded)
│
├── logs/
│   ├── access.db             # SQLite access log database
│   ├── system_state.json     # Shared state: lockdown, network mode, alarm flag
│   └── snapshot_*.jpg        # Manual snapshots saved with S key
│
├── scripts/
│   └── seed_demo_data.py     # Seed DB with realistic demo data
│
├── src/
│   ├── config.py             # ← All tunable settings (start here)
│   ├── database.py           # SQLite logger + student registry
│   ├── face_engine.py        # InsightFace detector + ArcFace matcher
│   ├── hostel.py             # Curfew logic, alarm manager, entry/exit machine
│   ├── utils.py              # OpenCV HUD rendering (door bar, network badge, etc.)
│   ├── dashboard.py          # Streamlit warden dashboard
│   └── main.py               # Entry point + camera loop
│
├── start_camera.bat          # One-click camera launch
├── start_dashboard.bat       # One-click dashboard launch
├── requirements.txt
├── .gitignore
└── README.md
```

---

## ⌨️ Camera Keybindings

| Key | Action |
|---|---|
| `Q` | Quit |
| `R` | Reload face gallery from disk |
| `S` | Save snapshot to `logs/` |
| `N` | Toggle 4G ↔ 5G network mode |
| `A` | Manually reset alarm |

---

## ⚙️ Configuration (`src/config.py`)

| Parameter | Default | Description |
|---|---|---|
| `RECOGNITION_THRESHOLD` | `0.50` | Cosine similarity cutoff (raise = stricter) |
| `DETECTION_THRESHOLD` | `0.50` | Min face detection confidence |
| `DEFAULT_CURFEW_TIME` | `"22:00"` | Curfew in HH:MM 24h format |
| `DOOR_OPEN_DURATION` | `5.0` | Seconds gate stays open after auth |
| `LOG_COOLDOWN_SECONDS` | `5.0` | DB debounce per identity |
| `ALARM_AUTO_RESET_SECS` | `10.0` | Alarm auto-clears after N seconds |
| `NETWORK_4G_DELAY_SECS` | `0.50` | Artificial delay injected in 4G demo mode |
| `CAMERA_INDEX` | `0` | Webcam device number |

---

## 🗄️ Database Schema

```sql
-- Access Events
CREATE TABLE access_logs (
    id          INTEGER PRIMARY KEY,
    timestamp   TEXT,     -- "2026-10-04 22:47:13"
    name        TEXT,     -- "alice" or "UNKNOWN"
    status      TEXT,     -- "AUTHORIZED" | "DENIED"
    event_type  TEXT,     -- "ENTRY" | "EXIT" | "VIOLATION" | "DENIED"
    similarity  REAL,     -- cosine similarity score (0–1)
    room_number TEXT,     -- "B-204"
    face_count  INTEGER
);

-- Student Registry
CREATE TABLE students (
    name         TEXT UNIQUE,
    roll_number  TEXT,
    room_number  TEXT,
    hostel_block TEXT,
    curfew_time  TEXT    -- per-student override (HH:MM)
);
```

---

## 🧠 Face Recognition Pipeline

1. **Detection** — RetinaFace finds face bounding boxes in each frame
2. **Embedding** — ArcFace outputs a **512-dimensional L2-normalized vector**
3. **Matching** — Cosine similarity against every registered embedding:

$$\text{sim}(\mathbf{u}, \mathbf{v}) = \frac{\mathbf{u} \cdot \mathbf{v}}{\|\mathbf{u}\| \|\mathbf{v}\|}$$

4. **Decision** — Best match ≥ `RECOGNITION_THRESHOLD` → **AUTHORIZED**; else → **DENIED**
5. **Curfew** — AUTHORIZED ENTRY after `DEFAULT_CURFEW_TIME` → **VIOLATION**
6. **Log** — Debounced write to SQLite (max 1 entry per identity per 5s)

---

## 🚀 Hackathon Demo Script (3 minutes)

**Opening (30 sec)**
> "Hostel RFID cards get shared, lost, and proxied. Standard 4G cameras lag 500ms at the gate — students pile up at curfew. We built an AI face recognition system on a dedicated 5G URLLC network slice that authenticates in under 30ms with zero queue formation."

**Live Demo (90 sec)**
1. Registered face appears → recognized instantly → **GATE OPEN** bar turns green ✅
2. Unknown person → **ALARM** flashes red on screen + audible beep 🚨
3. Click **4G mode** on dashboard → camera visibly lags → explain the queuing problem
4. Click back to **5G** → instant again → the difference is obvious

**Dashboard (60 sec)**
1. Show live access log updating in real time
2. Show today's stats: entries, exits, violations, unknown attempts
3. Hit **Emergency Lockdown** → camera immediately shows red LOCKDOWN banner
4. Show curfew violation highlighted in the log table

---

## 🔧 Troubleshooting

| Problem | Fix |
|---|---|
| `Cannot open camera` | Check webcam is connected; try `CAMERA_INDEX = 1` in `config.py` |
| `No face detected` in registration | Use a clear, well-lit, front-facing photo |
| Everyone classified as UNKNOWN | Lower `RECOGNITION_THRESHOLD` to `0.45` |
| False positive matches | Raise `RECOGNITION_THRESHOLD` to `0.60` |
| No beep sound | Only works on Windows (uses built-in `winsound`) |
| Slow FPS | Default model (`buffalo_sc`) is CPU-optimised; install `onnxruntime-gpu` for NVIDIA GPU |

---

## 🗺️ Roadmap (Post-Hackathon)

- [ ] Liveness detection (anti-spoofing — blink/head-turn challenge)
- [ ] Physical door lock via Arduino relay / GPIO
- [ ] Real 5G CPE hardware integration (replacing simulation)
- [ ] Multi-camera support (entrance + exit + common areas)
- [ ] Mobile warden app (Flutter / React Native)
- [ ] Cloud dashboard for college administration
