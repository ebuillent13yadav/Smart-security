"""
dashboard.py
------------
Streamlit Warden Dashboard — AI-Powered Smart Hostel Security System.

Run with:
    venv\\Scripts\\streamlit.exe run src/dashboard.py

Phase 3 additions:
  • 4G / 5G live toggle (writes to system_state.json, camera reads it)
  • Security alarm banner (flashing red when alarm_active=True)
  • Network mode pill shown in the 5G metrics panel header
  • Alarm reset button for the warden
"""

import os
import sys
import random
import time
from datetime import datetime

import pandas as pd
import streamlit as st

# Allow running from project root or src/
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from config import (
    HOSTEL_NAME,
    GATE_ID,
    DEFAULT_CURFEW_TIME,
    DASHBOARD_REFRESH_SECS,
    DASHBOARD_LOG_ROWS,
)
from database import AccessLogger
from hostel import read_system_state, write_system_state

# ─────────────────────────────────────────────────────────────
# Page Config
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
    .stApp { background-color: #0e1117; }

    [data-testid="metric-container"] {
        background: #1c2130;
        border: 1px solid #2d3748;
        border-radius: 10px;
        padding: 12px;
    }

    /* Alarm banner pulse */
    .alarm-banner {
        background: linear-gradient(90deg, #c53030, #9b2c2c);
        color: white;
        text-align: center;
        padding: 14px 20px;
        border-radius: 8px;
        font-size: 1.15rem;
        font-weight: 700;
        letter-spacing: 1px;
        margin-bottom: 16px;
        border: 2px solid #fc8181;
        animation: alarmpulse 1s infinite;
    }
    @keyframes alarmpulse { 0%,100%{opacity:1} 50%{opacity:0.75} }

    /* Lockdown banner */
    .lockdown-banner {
        background: linear-gradient(90deg, #742a2a, #c53030);
        color: white;
        text-align: center;
        padding: 12px;
        border-radius: 8px;
        font-size: 1.05rem;
        font-weight: 700;
        margin-bottom: 12px;
        animation: alarmpulse 1.5s infinite;
    }

    /* 5G panel */
    .fiveg-panel {
        background: linear-gradient(135deg, #0d1b2a 0%, #1a2a4a 100%);
        border: 1px solid #3182ce;
        border-radius: 10px;
        padding: 16px;
        margin-bottom: 16px;
    }

    /* 4G panel (warning colours) */
    .fourgpanel {
        background: linear-gradient(135deg, #1a0d00 0%, #3d1a00 100%);
        border: 1px solid #dd6b20;
        border-radius: 10px;
        padding: 16px;
        margin-bottom: 16px;
    }

    /* Network toggle buttons */
    .net-5g-active { background: #1a4731; border: 2px solid #48bb78; }
    .net-4g-active { background: #4a2008; border: 2px solid #ed8936; }
</style>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────
# Cached Resources
# ─────────────────────────────────────────────────────────────
@st.cache_resource
def get_logger():
    return AccessLogger()


# ─────────────────────────────────────────────────────────────
# Dataframe Styling
# ─────────────────────────────────────────────────────────────
def color_event(val: str) -> str:
    return {
        "ENTRY":     "color:#48bb78;font-weight:600",
        "EXIT":      "color:#63b3ed;font-weight:600",
        "VIOLATION": "color:#f6ad55;font-weight:700",
        "DENIED":    "color:#fc8181;font-weight:600",
    }.get(val, "")

def color_status(val: str) -> str:
    return "color:#48bb78" if val == "AUTHORIZED" else "color:#fc8181"


# ─────────────────────────────────────────────────────────────
# Phase 3 — 5G/4G Metrics Panel
# ─────────────────────────────────────────────────────────────
def render_network_panel(network_mode: str):
    """
    Renders the 5G URLLC / 4G metrics panel.
    Values are simulated with realistic jitter to demonstrate network performance.
    The 4G vs 5G toggle lets judges see the difference live.
    """
    is_5g = (network_mode == "5G")

    # Simulated KPI values
    if is_5g:
        latency     = round(random.uniform(10, 28), 1)
        throughput  = round(random.uniform(820, 980), 0)
        packet_loss = round(random.uniform(0.001, 0.009), 3)
        reliability = round(random.uniform(99.990, 99.999), 3)
        slice_label = "URLLC Slice #4 — Dedicated Security"
        panel_class = "fiveg-panel"
        mode_emoji  = "⚡"
        mode_color  = "#63b3ed"
    else:
        latency     = round(random.uniform(380, 620), 0)
        throughput  = round(random.uniform(20, 55), 0)
        packet_loss = round(random.uniform(1.5, 3.5), 2)
        reliability = round(random.uniform(98.5, 99.2), 2)
        slice_label = "4G LTE — Shared Public Network (Congested)"
        panel_class = "fourgpanel"
        mode_emoji  = "🐌"
        mode_color  = "#ed8936"

    st.markdown(f"""
    <div class="{panel_class}">
        <div style="color:{mode_color}; font-size:0.9rem; font-weight:700; margin-bottom:10px;">
            📡 {mode_emoji} {network_mode} Network — {slice_label}
        </div>
    </div>
    """, unsafe_allow_html=True)

    c1, c2, c3, c4, c5 = st.columns(5)
    if is_5g:
        c1.metric("⚡ Latency",      f"{latency} ms",       delta=f"-{round(500-latency,0):.0f}ms vs 4G")
        c2.metric("🚀 Throughput",   f"{throughput:.0f} Mbps", delta="↑ vs 4G (45 Mbps)")
        c3.metric("📦 Packet Loss",  f"{packet_loss:.3f}%",  delta="-2.5% vs 4G", delta_color="normal")
        c4.metric("✅ Reliability",  f"{reliability:.3f}%",  delta="+0.7% vs 4G")
        c5.metric("🔗 Slice Type",   "URLLC",               delta="Dedicated")
    else:
        c1.metric("🐌 Latency",      f"{latency:.0f} ms",   delta=f"+{round(latency-20,0):.0f}ms vs 5G", delta_color="inverse")
        c2.metric("📶 Throughput",   f"{throughput:.0f} Mbps", delta="↓ vs 5G (900 Mbps)", delta_color="inverse")
        c3.metric("📦 Packet Loss",  f"{packet_loss:.2f}%", delta=f"+{round(packet_loss-0.005,2):.2f}% vs 5G", delta_color="inverse")
        c4.metric("⚠️ Reliability",  f"{reliability:.2f}%", delta=f"-{round(99.995-reliability,2):.2f}% vs 5G", delta_color="inverse")
        c5.metric("🔗 Slice Type",   "Shared",              delta="No guarantee")


# ─────────────────────────────────────────────────────────────
# Phase 3 — 4G / 5G Toggle
# ─────────────────────────────────────────────────────────────
def render_network_toggle(state: dict):
    """Network mode toggle — writes to system_state.json which main.py reads."""
    st.subheader("📡 Network Mode Demo")
    st.caption("Switch to 4G to simulate congested network — watch the camera lag!")

    current = state.get("network_mode", "5G")
    col1, col2 = st.columns(2)

    with col1:
        btn_type_5g = "primary" if current == "5G" else "secondary"
        if st.button("⚡ Switch to 5G  (URLLC ~18ms)", type=btn_type_5g,
                     use_container_width=True):
            state["network_mode"] = "5G"
            write_system_state(state)
            st.success("Switched to **5G URLLC** mode — ultra-low latency active.")
            st.rerun()

    with col2:
        btn_type_4g = "primary" if current == "4G" else "secondary"
        if st.button("🐌 Switch to 4G  (LTE ~500ms)", type=btn_type_4g,
                     use_container_width=True):
            state["network_mode"] = "4G"
            write_system_state(state)
            st.warning("Switched to **4G LTE** mode — artificial 500ms delay injected.")
            st.rerun()

    # Status pill
    if current == "5G":
        st.markdown("**Active:** <span style='color:#48bb78;font-weight:700'>⚡ 5G URLLC</span>",
                    unsafe_allow_html=True)
    else:
        st.markdown("**Active:** <span style='color:#ed8936;font-weight:700'>🐌 4G LTE (degraded)</span>",
                    unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────
# Phase 3 — Alarm Banner + Reset
# ─────────────────────────────────────────────────────────────
def render_alarm_section(state: dict):
    """Show flashing alarm banner if alarm is active; allow warden to reset it."""
    alarm_active = state.get("alarm_active", False)
    alarm_at     = state.get("alarm_at", "—")
    alarm_reason = state.get("alarm_reason", "Security event detected")

    if alarm_active:
        st.markdown(f"""
        <div class="alarm-banner">
            🚨 SECURITY ALARM ACTIVE 🚨<br>
            <span style="font-size:0.9rem;font-weight:400">
                {alarm_reason} &nbsp;|&nbsp; Triggered at: {alarm_at}
            </span>
        </div>
        """, unsafe_allow_html=True)

        if st.button("✅ Reset Alarm", type="primary"):
            state["alarm_active"] = False
            state["alarm_at"]     = None
            state["alarm_reason"] = None
            write_system_state(state)
            st.success("Alarm cleared by warden.")
            st.rerun()


# ─────────────────────────────────────────────────────────────
# Gate Lockdown Controls
# ─────────────────────────────────────────────────────────────
def render_lockdown_controls(state: dict):
    is_locked = state.get("lockdown", False)

    if is_locked:
        st.markdown("""
        <div class="lockdown-banner">
            🔒 EMERGENCY LOCKDOWN ACTIVE — All access DENIED
        </div>
        """, unsafe_allow_html=True)
        st.caption(f"Locked by: {state.get('lockdown_by','Warden')} at {state.get('lockdown_at','—')}")
        if st.button("🔓 Lift Lockdown", type="primary", use_container_width=True):
            state.update({"lockdown": False, "lockdown_by": None,
                          "lockdown_at": None, "gate_status": "ACTIVE"})
            write_system_state(state)
            st.success("Lockdown lifted — gate ACTIVE.")
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
            color   = "#48bb78" if gstatus == "ACTIVE" else "#fc8181"
            st.markdown(
                f"Gate: <span style='color:{color};font-weight:700'>{gstatus}</span>",
                unsafe_allow_html=True,
            )


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
        st.subheader("➕ Register / Update Student")
        st.caption("Name must match the image filename stem in `data/known_faces/`")
        with st.form("add_student"):
            col1, col2 = st.columns(2)
            with col1:
                s_name  = st.text_input("Name*",       placeholder="alice")
                s_roll  = st.text_input("Roll Number", placeholder="2024CS001")
            with col2:
                s_room  = st.text_input("Room Number", placeholder="B-204")
                s_block = st.text_input("Hostel Block", value="A")
            s_curfew = st.text_input("Curfew Time (HH:MM)", value=DEFAULT_CURFEW_TIME)
            if st.form_submit_button("Save Student", type="primary"):
                if not s_name.strip():
                    st.error("Name is required.")
                else:
                    ok = logger.register_student(
                        name=s_name.strip(), roll_number=s_roll.strip(),
                        room_number=s_room.strip(),
                        hostel_block=s_block.strip() or "A",
                        curfew_time=s_curfew.strip() or DEFAULT_CURFEW_TIME,
                    )
                    st.success(f"✅ '{s_name}' saved.") if ok else st.error("Failed.")


# ─────────────────────────────────────────────────────────────
# Main Dashboard Layout
# ─────────────────────────────────────────────────────────────
def main():
    logger = get_logger()
    state  = read_system_state()
    stats  = logger.get_stats_today()
    now    = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    net    = state.get("network_mode", "5G")

    # ── 1. Alarm Banner (top priority — shows above everything) ──
    render_alarm_section(state)

    # ── 2. Header ─────────────────────────────────────────────
    net_badge = (
        "<span style='color:#48bb78;font-weight:700'>⚡ 5G URLLC</span>"
        if net == "5G" else
        "<span style='color:#ed8936;font-weight:700'>🐌 4G LTE</span>"
    )
    st.markdown(f"""
    <div style="background:linear-gradient(90deg,#1a365d,#2c5282);
                border-radius:10px;padding:16px 20px;margin-bottom:20px;">
        <h2 style="color:white;margin:0;">🔒 Hostel Warden Dashboard</h2>
        <div style="color:#90cdf4;margin-top:4px;">
            {HOSTEL_NAME} &nbsp;|&nbsp; Gate: {GATE_ID} &nbsp;|&nbsp;
            🕐 {now} &nbsp;|&nbsp; Network: {net_badge} &nbsp;|&nbsp;
            🔄 Refreshing every {DASHBOARD_REFRESH_SECS}s
        </div>
    </div>
    """, unsafe_allow_html=True)

    # ── 3. Network Metrics Panel ───────────────────────────────
    render_network_panel(net)

    # ── 4. Today's Stats ──────────────────────────────────────
    st.subheader("📊 Today's Activity")
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("🚶 Entries",         stats["total_entries"])
    c2.metric("🏃 Exits",           stats["exits"])
    c3.metric("⚠️ Violations",      stats["violations"],
              delta=f"+{stats['violations']}" if stats["violations"] else None,
              delta_color="inverse")
    c4.metric("❌ Unknown Attempts", stats["unknown_attempts"],
              delta=f"+{stats['unknown_attempts']}" if stats["unknown_attempts"] else None,
              delta_color="inverse")
    c5.metric("✅ Authorized Total", stats["authorized_count"])

    st.divider()

    # ── 5. Main Content Row ───────────────────────────────────
    left_col, right_col = st.columns([3, 1])

    with right_col:
        # Gate Controls
        st.subheader("🚨 Gate Control")
        render_lockdown_controls(state)
        st.divider()

        # 4G / 5G Toggle
        render_network_toggle(state)

    with left_col:
        # Live Access Log
        st.subheader("📋 Live Access Log")
        rows = logger.fetch_recent_as_dicts(DASHBOARD_LOG_ROWS)
        if rows:
            df     = pd.DataFrame(rows)
            styled = (df.style
                        .map(color_event,  subset=["Event"])
                        .map(color_status, subset=["Status"]))
            st.dataframe(styled, use_container_width=True,
                         hide_index=True, height=420)
        else:
            st.info("No events yet — start the camera to begin logging.")

    st.divider()

    # ── 6. Student Registry ───────────────────────────────────
    render_student_registry(logger)

    # ── 7. Sidebar ────────────────────────────────────────────
    with st.sidebar:
        st.title("⚙️ Controls")

        # Quick alarm reset in sidebar too
        if state.get("alarm_active"):
            if st.button("🔕 Reset Alarm", type="primary", use_container_width=True):
                state.update({"alarm_active": False, "alarm_at": None, "alarm_reason": None})
                write_system_state(state)
                st.rerun()

        st.divider()

        # Network quick-toggle in sidebar
        st.subheader("📡 Quick Network Toggle")
        current_net = state.get("network_mode", "5G")
        toggle_label = "🐌 Simulate 4G" if current_net == "5G" else "⚡ Back to 5G"
        if st.button(toggle_label, use_container_width=True):
            state["network_mode"] = "4G" if current_net == "5G" else "5G"
            write_system_state(state)
            st.rerun()

        st.divider()
        st.info(
            "**Launch Commands:**\n\n"
            "Camera:\n"
            "```\nstart_camera.bat\n```\n\n"
            "Dashboard:\n"
            "```\nstart_dashboard.bat\n```\n\n"
            "**Camera Keys:**\n"
            "- `Q` Quit\n"
            "- `R` Reload gallery\n"
            "- `S` Snapshot\n"
            "- `N` Toggle 4G/5G\n"
            "- `A` Reset alarm\n"
        )
        st.divider()
        st.caption("🟢 Connected to SQLite DB")
        st.caption(f"Auto-refresh: {DASHBOARD_REFRESH_SECS}s")

    # ── 8. Auto-refresh ───────────────────────────────────────
    time.sleep(DASHBOARD_REFRESH_SECS)
    st.rerun()


if __name__ == "__main__":
    main()
