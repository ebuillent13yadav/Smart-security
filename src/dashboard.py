"""
dashboard.py
------------
Streamlit warden dashboard for the AI-Powered Smart Hostel Security System.

Run with:
    venv\\Scripts\\streamlit.exe run src/dashboard.py

Features:
  • Live access log table (auto-refreshes every 3s)
  • Today's stats: entries, exits, violations, unknown attempts
  • Simulated 5G URLLC metrics panel
  • Emergency lockdown / manual unlock controls
  • Student registry management (add / view students)
"""

import os
import sys
import json
import random
import time
from datetime import datetime

import pandas as pd
import streamlit as st

# Allow running from project root or from src/
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from config import (
    HOSTEL_NAME,
    GATE_ID,
    DEFAULT_CURFEW_TIME,
    DASHBOARD_REFRESH_SECS,
    DASHBOARD_LOG_ROWS,
    SYSTEM_STATE_FILE,
    LOGS_DIR,
)
from database import AccessLogger
from hostel import read_system_state, write_system_state

# ─────────────────────────────────────────────────────────────
# Page Configuration
# ─────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Hostel Security Dashboard",
    page_icon="🔒",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─────────────────────────────────────────────────────────────
# Custom CSS
# ─────────────────────────────────────────────────────────────
st.markdown("""
<style>
    /* Dark theme tweaks */
    .stApp { background-color: #0e1117; }

    /* Metric cards */
    [data-testid="metric-container"] {
        background: #1c2130;
        border: 1px solid #2d3748;
        border-radius: 10px;
        padding: 12px;
    }

    /* Status badges */
    .badge-authorized { color: #48bb78; font-weight: 700; }
    .badge-denied     { color: #fc8181; font-weight: 700; }
    .badge-violation  { color: #f6ad55; font-weight: 700; }
    .badge-exit       { color: #63b3ed; font-weight: 700; }

    /* 5G panel */
    .fiveg-panel {
        background: linear-gradient(135deg, #0d1b2a 0%, #1a2a4a 100%);
        border: 1px solid #3182ce;
        border-radius: 10px;
        padding: 16px;
        margin-bottom: 16px;
    }
    .fiveg-title { color: #63b3ed; font-size: 0.85rem; font-weight: 600; }
    .fiveg-value { color: #90cdf4; font-size: 1.4rem; font-weight: 700; }

    /* Lockdown banner */
    .lockdown-banner {
        background: #c53030;
        color: white;
        text-align: center;
        padding: 12px;
        border-radius: 8px;
        font-size: 1.1rem;
        font-weight: 700;
        animation: pulse 1.5s infinite;
    }
    @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:0.7} }

    /* Header */
    .dash-header {
        background: linear-gradient(90deg, #1a365d 0%, #2c5282 100%);
        border-radius: 10px;
        padding: 16px 20px;
        margin-bottom: 20px;
    }
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────
# Data helpers
# ─────────────────────────────────────────────────────────────
@st.cache_resource
def get_logger():
    return AccessLogger()

def color_event(val: str) -> str:
    colors = {
        "ENTRY":     "color: #48bb78; font-weight:600",
        "EXIT":      "color: #63b3ed; font-weight:600",
        "VIOLATION": "color: #f6ad55; font-weight:700",
        "DENIED":    "color: #fc8181; font-weight:600",
    }
    return colors.get(val, "")

def color_status(val: str) -> str:
    return "color: #48bb78" if val == "AUTHORIZED" else "color: #fc8181"

# ─────────────────────────────────────────────────────────────
# 5G Metrics Simulation
# ─────────────────────────────────────────────────────────────
def render_5g_panel():
    """Render a simulated 5G URLLC telemetry panel."""
    # Simulate realistic URLLC values with slight jitter
    latency   = round(random.uniform(10, 28), 1)
    throughput = round(random.uniform(820, 980), 0)
    packet_loss = round(random.uniform(0.001, 0.009), 3)
    reliability = round(random.uniform(99.990, 99.999), 3)

    st.markdown("""
    <div class="fiveg-panel">
        <div style="color:#63b3ed; font-size:0.9rem; font-weight:700; margin-bottom:10px;">
            📡 5G URLLC — Network Slice #4 (Dedicated Security)
        </div>
    </div>
    """, unsafe_allow_html=True)

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("⚡ Latency",     f"{latency} ms",        delta=f"-{round(500-latency,0):.0f}ms vs 4G", delta_color="normal")
    c2.metric("🚀 Throughput",  f"{throughput:.0f} Mbps", delta="↑ vs 4G (50 Mbps)")
    c3.metric("📦 Packet Loss", f"{packet_loss:.3f}%",   delta="-2.491% vs 4G",     delta_color="normal")
    c4.metric("✅ Reliability", f"{reliability:.3f}%",   delta="+0.599% vs 4G")
    c5.metric("🔗 Slice",       "URLLC #4",              delta="Dedicated")


# ─────────────────────────────────────────────────────────────
# Lockdown Controls
# ─────────────────────────────────────────────────────────────
def render_lockdown_controls(state: dict):
    is_locked = state.get("lockdown", False)

    if is_locked:
        st.markdown("""
        <div class="lockdown-banner">
            🚨 EMERGENCY LOCKDOWN ACTIVE — All access DENIED 🚨
        </div>
        """, unsafe_allow_html=True)
        st.caption(f"Locked by: {state.get('lockdown_by','Warden')} at {state.get('lockdown_at','—')}")
        if st.button("🔓 Lift Lockdown", type="primary", use_container_width=True):
            state.update({"lockdown": False, "lockdown_by": None,
                          "lockdown_at": None, "gate_status": "ACTIVE"})
            write_system_state(state)
            st.success("Lockdown lifted — gate is now ACTIVE.")
            st.rerun()
    else:
        col1, col2 = st.columns(2)
        with col1:
            if st.button("🔒 Emergency Lockdown", type="secondary", use_container_width=True):
                now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                state.update({"lockdown": True, "lockdown_by": "Warden",
                               "lockdown_at": now_str, "gate_status": "LOCKED"})
                write_system_state(state)
                st.error("🚨 LOCKDOWN ACTIVATED")
                st.rerun()
        with col2:
            gstatus = state.get("gate_status", "ACTIVE")
            st.info(f"Gate Status: **{gstatus}**", icon="🚪")


# ─────────────────────────────────────────────────────────────
# Student Registry Panel
# ─────────────────────────────────────────────────────────────
def render_student_registry(logger: AccessLogger):
    students = logger.get_all_students()

    with st.expander("👥 Student Registry", expanded=False):
        if students:
            df = pd.DataFrame(students)
            st.dataframe(df, use_container_width=True, hide_index=True)
        else:
            st.info("No students registered yet.")

        st.divider()
        st.subheader("➕ Register Student Metadata")
        st.caption("The Name must exactly match the image filename in `data/known_faces/` (without extension)")

        with st.form("add_student"):
            col1, col2 = st.columns(2)
            with col1:
                s_name  = st.text_input("Name*",        placeholder="alice")
                s_roll  = st.text_input("Roll Number",  placeholder="2024CS001")
            with col2:
                s_room  = st.text_input("Room Number",  placeholder="B-204")
                s_block = st.text_input("Hostel Block",  value="A")
            s_curfew = st.text_input("Curfew Time (HH:MM)", value=DEFAULT_CURFEW_TIME)

            submitted = st.form_submit_button("Save Student", type="primary")
            if submitted:
                if not s_name.strip():
                    st.error("Name is required.")
                else:
                    ok = logger.register_student(
                        name=s_name.strip(),
                        roll_number=s_roll.strip(),
                        room_number=s_room.strip(),
                        hostel_block=s_block.strip() or "A",
                        curfew_time=s_curfew.strip() or DEFAULT_CURFEW_TIME,
                    )
                    if ok:
                        st.success(f"✅ Student '{s_name}' saved.")
                    else:
                        st.error("Failed to save student.")


# ─────────────────────────────────────────────────────────────
# Main Dashboard Layout
# ─────────────────────────────────────────────────────────────
def main():
    logger = get_logger()
    state  = read_system_state()
    stats  = logger.get_stats_today()
    now    = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # ── Header ────────────────────────────────────────────────
    st.markdown(f"""
    <div class="dash-header">
        <h2 style="color:white;margin:0;">🔒 Hostel Security — Warden Dashboard</h2>
        <div style="color:#90cdf4; margin-top:4px;">
            {HOSTEL_NAME} &nbsp;|&nbsp; Gate: {GATE_ID} &nbsp;|&nbsp;
            🕐 {now} &nbsp;|&nbsp;
            🔄 Auto-refresh every {DASHBOARD_REFRESH_SECS}s
        </div>
    </div>
    """, unsafe_allow_html=True)

    # ── 5G Panel ──────────────────────────────────────────────
    render_5g_panel()

    # ── Stats Row ─────────────────────────────────────────────
    st.subheader("📊 Today's Activity")
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("🚶 Entries",          stats["total_entries"])
    c2.metric("🏃 Exits",            stats["exits"])
    c3.metric("⚠️ Violations",       stats["violations"],
              delta=f"+{stats['violations']}" if stats["violations"] else None,
              delta_color="inverse")
    c4.metric("❌ Unknown Attempts",  stats["unknown_attempts"],
              delta=f"+{stats['unknown_attempts']}" if stats["unknown_attempts"] else None,
              delta_color="inverse")
    c5.metric("✅ Authorized Total",  stats["authorized_count"])

    st.divider()

    # ── Lockdown Controls ─────────────────────────────────────
    left_col, right_col = st.columns([3, 1])
    with right_col:
        st.subheader("🚨 Gate Control")
        render_lockdown_controls(state)

    # ── Live Access Log ───────────────────────────────────────
    with left_col:
        st.subheader("📋 Live Access Log")
        rows = logger.fetch_recent_as_dicts(DASHBOARD_LOG_ROWS)
        if rows:
            df = pd.DataFrame(rows)
            styled = df.style.map(color_event, subset=["Event"]) \
                             .map(color_status, subset=["Status"])
            st.dataframe(styled, use_container_width=True, hide_index=True,
                         height=420)
        else:
            st.info("No access events yet. Start the camera to begin logging.")

    st.divider()

    # ── Student Registry ──────────────────────────────────────
    render_student_registry(logger)

    # ── Sidebar ───────────────────────────────────────────────
    with st.sidebar:
        st.title("⚙️ Settings")
        st.caption(f"Dashboard v1.0 | Python 3.11")
        st.divider()
        st.info(
            "**How to use:**\n"
            "1. Run the camera:\n"
            "   `venv\\Scripts\\python.exe src\\main.py`\n\n"
            "2. Register students via the registry panel below or:\n"
            "   `python src\\main.py --register-cam --name alice`\n\n"
            "3. Use 🔒 **Emergency Lockdown** to instantly deny all access."
        )
        st.divider()
        st.caption("🟢 Dashboard connected to SQLite DB")
        st.caption(f"Refreshing every {DASHBOARD_REFRESH_SECS}s...")

    # ── Auto-refresh ──────────────────────────────────────────
    time.sleep(DASHBOARD_REFRESH_SECS)
    st.rerun()


if __name__ == "__main__":
    main()
