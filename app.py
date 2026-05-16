"""
╔══════════════════════════════════════════════════════════════════════╗
║   LaunchDarkly SE Technical Exercise — Darryl Mok · APJ FY27        ║
║   Pulse · Fitness Performance Platform                                ║
╠══════════════════════════════════════════════════════════════════════╣
║  SETUP:                                                              ║
║    pip install -r requirements.txt                                   ║
║    export LD_SDK_KEY="sdk-your-key-here"        ← REPLACE THIS       ║
║    export OPENAI_API_KEY="sk-..."               ← optional, Part 3   ║
║    streamlit run app.py                                              ║
╠══════════════════════════════════════════════════════════════════════╣
║  FLAGS TO CREATE IN YOUR LD PROJECT (Test environment):              ║
║    new-hero-banner     Boolean   Part 1 — Release & Remediate        ║
║    checkout-redesign   Boolean   Part 2 — Targeting + Part 3 Expt    ║
║    promotional-banner  String    Part 2 — String-flag demo           ║
║    support-assistant   AI Config Part 3 — AI Configs (optional)      ║
╠══════════════════════════════════════════════════════════════════════╣
║  TRIGGER SETUP (Part 1 Remediate):                                   ║
║    LD Dashboard → new-hero-banner → Triggers tab                     ║
║    → Add trigger → Generic trigger → copy URL → run:                 ║
║    curl -X POST "<your-trigger-url>"                                 ║
╠══════════════════════════════════════════════════════════════════════╣
║  TARGETING RULES (Part 2 — checkout-redesign):                       ║
║    Individual targets: alice, carol                                  ║
║    Rule 1: IF tier = "enterprise" → TRUE                             ║
║    Rule 2: IF betaTester = true → TRUE                               ║
║    Default rule: FALSE                                               ║
║  STRING FLAG (promotional-banner):                                   ║
║    Rule: IF tier = "free" → "Upgrade to Pro — ship 9x faster!"       ║
║    Default: "" (empty string)                                        ║
╠══════════════════════════════════════════════════════════════════════╣
║  EXPERIMENT METRIC (Part 3 bonus):                                   ║
║    Create custom metric "purchase-clicked" (numeric, sum)            ║
║    Create experiment on checkout-redesign with that metric           ║
║    This app emits ld.track("purchase-clicked", ctx, metric_value)    ║
╚══════════════════════════════════════════════════════════════════════╝
"""

from __future__ import annotations

import os
import time
import uuid
import threading
from collections import deque
from datetime import datetime

import streamlit as st
import ldclient
from ldclient.config import Config
from ldclient import Context

# ── Non-blocking auto-refresh (drives the "live" feel for SDK updates) ────
try:
    from streamlit_autorefresh import st_autorefresh
    HAS_AUTOREFRESH = True
except ImportError:
    HAS_AUTOREFRESH = False

# ── Optional AI SDK (Part 3 bonus) ────────────────────────────────────────
try:
    from ldai.client import LDAIClient
    import openai
    from types import SimpleNamespace
    AI_AVAILABLE = True
except ImportError:
    AI_AVAILABLE = False

# ══════════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ← Set LD_SDK_KEY as an env var or replace the string below directly
# ══════════════════════════════════════════════════════════════════════════
LD_SDK_KEY     = os.environ.get("LD_SDK_KEY", "YOUR_SDK_KEY_HERE")  # ← REPLACE
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")               # ← Optional, for Part 3 AI tab

# Flag keys — must match what you create in your LaunchDarkly project
FLAG_HERO      = "new-hero-banner"      # Part 1: Boolean
FLAG_CHECKOUT  = "checkout-redesign"    # Part 2 + experiment flag
FLAG_BANNER    = "promotional-banner"   # Part 2: String flag
AI_CONFIG_KEY  = "support-assistant"    # Part 3: AI Config

# Metric key for the experiment in Part 3 (must match LD UI metric name)
METRIC_PURCHASE = "purchase-clicked"

# ══════════════════════════════════════════════════════════════════════════
# LD CLIENT  +  SDK CHANGE LISTENER (the "instant rollback" mechanism)
# Server-side SDK: downloads all flag rules at startup, evaluates locally
# in memory — <5ms per call. Flag changes stream via a persistent SSE
# connection. We attach a flag_tracker listener that fires the instant a
# flag value changes for any context — captured in a thread-safe deque
# and surfaced in the UI (no page reload required).
# ══════════════════════════════════════════════════════════════════════════
@st.cache_resource
def init_ld():
    ldclient.set_config(Config(LD_SDK_KEY))
    return ldclient.get()

@st.cache_resource
def init_ai(_ld):
    if AI_AVAILABLE and OPENAI_API_KEY:
        return LDAIClient(_ld)
    return None

# Thread-safe change log fed by LD's SDK listener on a background thread.
_change_log: deque = deque(maxlen=25)
_change_lock = threading.Lock()
_listeners_registered = False

def _on_flag_change(change):
    """SDK listener — fires the moment any flag's rules change in LD."""
    with _change_lock:
        _change_log.appendleft({
            "ts":   datetime.now().strftime("%H:%M:%S"),
            "flag": getattr(change, "key", "?"),
        })

def register_listeners(client):
    """Attach the SDK change listener. Idempotent."""
    global _listeners_registered
    if _listeners_registered:
        return
    try:
        client.flag_tracker.add_listener(_on_flag_change)
        _listeners_registered = True
    except Exception:
        # Older SDK versions may not expose flag_tracker — degrade gracefully.
        pass

ld    = init_ld()
ai    = init_ai(ld)
ld_ok = ld.is_initialized()
if ld_ok:
    register_listeners(ld)

# ══════════════════════════════════════════════════════════════════════════
# PAGE CONFIG
# ══════════════════════════════════════════════════════════════════════════
st.set_page_config(
    page_title="Pulse · LaunchDarkly Demo",
    page_icon="🏋️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ══════════════════════════════════════════════════════════════════════════
# GLOBAL CSS  (dark theme, LD-inspired, mono accents)
# ══════════════════════════════════════════════════════════════════════════
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600&family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap');

html, body, [class*="css"] { font-family: 'Plus Jakarta Sans', sans-serif; }
#MainMenu, footer, header { visibility: hidden; }
.block-container { padding-top: 1.2rem; padding-bottom: 2rem; }

/* ── Force dark mode globally — independent of .streamlit/config.toml ── */
html, body                                       { background-color:#0a0a14 !important; color:#e2e8f0; }
.stApp                                           { background-color:#0a0a14 !important; color:#e2e8f0; }
[data-testid="stAppViewContainer"]               { background-color:#0a0a14 !important; }
[data-testid="stHeader"]                         { background-color:rgba(10,10,20,0.7) !important; }
.main, .block-container, section.main            { background-color:transparent !important; color:#e2e8f0; }

/* Default body text on the dark page */
.main p, .main span, .main li, .main label,
.main h1, .main h2, .main h3, .main h4, .main h5, .main h6,
.stMarkdown, .stMarkdown p                       { color:#e2e8f0; }

/* Streamlit captions kept secondary but readable */
[data-testid="stCaptionContainer"] p,
.stCaption                                       { color:#94a3b8 !important; }

/* Streamlit form inputs — dark surfaces with light text */
.stTextInput input, .stTextArea textarea,
.stNumberInput input, .stDateInput input,
.stTimeInput input                               { background-color:#1a1a2e !important; color:#e2e8f0 !important;
                                                    border:1px solid #2d2d50 !important; }
.stTextInput input::placeholder,
.stTextArea textarea::placeholder                { color:#64748b !important; }
.stSelectbox > div > div                         { background-color:#1a1a2e !important; color:#e2e8f0 !important;
                                                    border-color:#2d2d50 !important; }
.stRadio label, .stCheckbox label,
.stTextInput label, .stSelectbox label,
.stForm label                                    { color:#cbd5e1 !important; }

/* Streamlit buttons */
.stButton > button, .stFormSubmitButton > button { background-color:#4f46e5 !important; color:white !important;
                                                    border:none !important; }
.stButton > button:hover,
.stFormSubmitButton > button:hover               { background-color:#4338ca !important; }

/* Streamlit metric component */
[data-testid="stMetricValue"]                    { color:#e2e8f0 !important; }
[data-testid="stMetricLabel"]                    { color:#94a3b8 !important; }
[data-testid="stMetricDelta"]                    { color:#4ade80 !important; }

/* Tabs */
button[data-baseweb="tab"]                       { color:#94a3b8 !important; }
button[data-baseweb="tab"][aria-selected="true"] { color:#e2e8f0 !important; }

/* Dividers */
hr                                               { border-color:#1a1a30 !important; }

/* Streamlit alert variants */
.stAlert                                         { background-color:#0e0e1c !important; border:1px solid #2d2d50 !important;
                                                    color:#e2e8f0 !important; }

[data-testid="stSidebar"] { background: #0c0c18 !important; border-right: 1px solid #1a1a30; }

.pill-on  { display:inline-flex;align-items:center;gap:6px;background:#0d2918;color:#4ade80;
            border:1px solid #166534;border-radius:6px;padding:5px 12px;font-size:12px;
            font-weight:600;font-family:'JetBrains Mono',monospace; }
.pill-off { display:inline-flex;align-items:center;gap:6px;background:#1f0d0d;color:#f87171;
            border:1px solid #7f1d1d;border-radius:6px;padding:5px 12px;font-size:12px;
            font-weight:600;font-family:'JetBrains Mono',monospace; }
.dot-on  { width:7px;height:7px;border-radius:50%;background:#4ade80;display:inline-block;
           box-shadow:0 0 8px #4ade80aa; }
.dot-off { width:7px;height:7px;border-radius:50%;background:#f87171;display:inline-block;
           animation:blink 1.2s ease-in-out infinite; }
.dot-live{ width:8px;height:8px;border-radius:50%;background:#4ade80;display:inline-block;
           animation:pulse 1.4s ease-in-out infinite; }
@keyframes blink { 0%,100%{opacity:1}50%{opacity:.2} }
@keyframes pulse { 0%,100%{box-shadow:0 0 0 0 #4ade8088}50%{box-shadow:0 0 0 8px transparent} }

.chip { display:inline-flex;align-items:center;gap:8px;background:#0c0c1e;
        border:1px solid #1e1e3f;border-radius:6px;padding:5px 13px;font-size:11px;
        font-weight:600;color:#6366f1;font-family:'JetBrains Mono',monospace;
        letter-spacing:.08em;text-transform:uppercase;margin-bottom:16px; }

.card       { background:#0e0e1c;border:1px solid #1a1a30;border-radius:14px;padding:22px 24px;margin-bottom:12px; }
.card-accent{ background:#0e0e1c;border:1px solid #2d2d60;border-radius:14px;padding:22px 24px;margin-bottom:12px; }

.hero-new { background:linear-gradient(135deg,#0f0f2e 0%,#151540 40%,#1a1060 100%);
            border:1px solid #3730a366;border-radius:16px;padding:36px 40px;
            margin-bottom:16px;position:relative;overflow:hidden; }
.hero-new::after { content:'';position:absolute;top:-80px;right:-80px;width:280px;height:280px;
                   border-radius:50%;background:radial-gradient(circle,#6366f133 0%,transparent 65%);
                   pointer-events:none; }
.hero-new .tag { font-family:'JetBrains Mono',monospace;font-size:11px;font-weight:600;
                 color:#818cf8;letter-spacing:.12em;text-transform:uppercase;margin-bottom:14px; }
.hero-new h2 { font-size:30px;font-weight:800;color:#e2e8f0;margin:0 0 10px;line-height:1.2; }
.hero-new p  { font-size:14px;color:#64748b;margin:0 0 22px;line-height:1.6; }

.hero-old { background:#09090f;border:1px dashed #1e1e2e;border-radius:16px;
            padding:36px 40px;margin-bottom:16px; }
.hero-old h2 { font-size:24px;font-weight:600;color:#e2e8f0;margin:0 0 8px; }
.hero-old p  { font-size:13px;color:#cbd5e1;margin:0 0 14px; }
.hero-old .tag { font-family:'JetBrains Mono',monospace;font-size:10px;color:#94a3b8;
                 letter-spacing:.1em;text-transform:uppercase;margin-bottom:12px; }

.metric-row { display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-top:18px; }
.metric-box { background:#0a0a18;border:1px solid #1a1a2e;border-radius:12px;padding:18px 20px; }
.metric-box.dim { opacity:.6; }
.m-val { font-size:26px;font-weight:700;color:#e2e8f0;font-family:'JetBrains Mono',monospace; }
.m-lbl { font-size:11px;color:#94a3b8;margin-top:4px;font-weight:500;text-transform:uppercase;letter-spacing:.05em; }
.m-pos { font-size:12px;color:#4ade80;font-weight:600;font-family:'JetBrains Mono',monospace; }

.mono { background:#060610;border:1px solid #1a1a2e;border-radius:10px;padding:14px 18px;
        font-family:'JetBrains Mono',monospace;font-size:12px;color:#a5b4fc;line-height:1.8; }

.rule { background:#0a0a18;border:1px solid #1a1a2e;border-radius:10px;padding:14px 18px;margin-bottom:8px; }
.rule.matched { border-color:#166534;background:#0a1f12; }
.rule-num { font-family:'JetBrains Mono',monospace;font-size:10px;color:#6366f1;font-weight:600;margin-bottom:5px; }
.rule-body { font-size:13px;color:#64748b;line-height:1.5; }
.rule-match { font-family:'JetBrains Mono',monospace;font-size:11px;color:#4ade80;font-weight:600;margin-top:7px; }
.rule-miss  { font-family:'JetBrains Mono',monospace;font-size:11px;color:#94a3b8;margin-top:7px; }

.checkout-new { background:linear-gradient(160deg,#0d0d28 0%,#111135 100%);
                border:1px solid #3730a333;border-radius:16px;padding:28px 32px; }
.checkout-old { background:#08080e;border:1px dashed #111120;border-radius:16px;padding:28px 32px; }

.trigger { background:#0e0820;border:1px solid #3730a333;border-radius:12px;padding:20px 24px;margin-top:12px; }

.tl-item  { display:flex;gap:14px;margin-bottom:16px;align-items:flex-start; }
.tl-num   { width:26px;height:26px;border-radius:50%;display:flex;align-items:center;
            justify-content:center;font-size:11px;font-weight:700;flex-shrink:0;
            font-family:'JetBrains Mono',monospace; }
.tl-title { font-size:13px;font-weight:600;color:#c7d2fe; }
.tl-desc  { font-size:12px;color:#94a3b8;line-height:1.5;margin-top:2px; }

.stream-on  { background:linear-gradient(90deg,#0d1f0d,#0f280f);border:1px solid #166534;
              border-radius:10px;padding:12px 18px;font-size:13px;color:#4ade80;
              font-family:'JetBrains Mono',monospace;margin-bottom:14px;
              display:flex;align-items:center;gap:10px; }
.stream-off { background:#0e0e1c;border:1px solid #1a1a2e;border-radius:10px;
              padding:12px 18px;font-size:12px;color:#94a3b8;
              font-family:'JetBrains Mono',monospace;margin-bottom:14px; }

/* Live change flash banner — fires the moment a flag value flips */
@keyframes flashIn { 0%{opacity:0;transform:translateY(-6px)} 100%{opacity:1;transform:translateY(0)} }
.flag-flash {
    animation:flashIn .35s ease-out;
    background:linear-gradient(90deg,#1a1305,#2c1d05);
    border:1px solid #f59e0b;
    color:#fbbf24;
    padding:13px 18px;border-radius:10px;font-size:13px;
    font-family:'JetBrains Mono',monospace;
    margin-bottom:14px;
    display:flex;align-items:center;gap:10px;
    box-shadow:0 0 30px #f59e0b22;
}
.kill-flash {
    animation:flashIn .35s ease-out;
    background:linear-gradient(90deg,#2c0a0a,#3d0f0f);
    border:1px solid #ef4444;
    color:#fca5a5;
    padding:14px 18px;border-radius:10px;font-size:13px;
    font-family:'JetBrains Mono',monospace;
    margin-bottom:14px;font-weight:600;
    box-shadow:0 0 30px #ef444433;
}
.changelog {
    background:#06060f;border:1px solid #1a1a2e;border-radius:8px;
    padding:10px 14px;font-family:'JetBrains Mono',monospace;
    font-size:11px;color:#64748b;margin-bottom:6px;
}
.changelog b { color:#a5b4fc; }

/* ── Chat bubbles for the AI Coach ───────────────────────────── */
.chat-row    { display:flex;gap:12px;margin:10px 0;align-items:flex-start; }
.chat-row.user-row  { flex-direction:row-reverse; }
.chat-avatar { width:36px;height:36px;border-radius:50%;display:flex;align-items:center;
               justify-content:center;font-size:20px;flex-shrink:0;
               box-shadow:0 2px 10px rgba(0,0,0,0.4); }
.chat-avatar.bot    { background:linear-gradient(135deg,#4f46e5,#7c3aed); }
.chat-avatar.user   { background:linear-gradient(135deg,#0ea5e9,#06b6d4); }
.chat-bubble { max-width:75%;padding:14px 18px;border-radius:16px;
               font-size:14px;line-height:1.65;white-space:pre-wrap; }
.chat-bubble.bot    { background:#0e0e1c;border:1px solid #2d2d50;color:#e2e8f0;
                      border-top-left-radius:4px; }
.chat-bubble.user   { background:linear-gradient(135deg,#1e1b4b,#312e81);
                      border:1px solid #4f46e5;color:#e2e8f0;
                      border-top-right-radius:4px; }
.chat-meta   { font-size:10px;color:#64748b;font-family:'JetBrains Mono',monospace;
               margin-top:8px;letter-spacing:.05em; }

/* ── Big, animated feature-state indicator ───────────────────── */
@keyframes statePulse {
  0%,100% { box-shadow:0 0 0 0    rgba(74,222,128,0.45); }
  50%     { box-shadow:0 0 0 14px rgba(74,222,128,0); }
}
@keyframes stateOff {
  0%,100% { box-shadow:0 0 0 0    rgba(248,113,113,0.45); }
  50%     { box-shadow:0 0 0 14px rgba(248,113,113,0); }
}
.feature-state {
  display:flex;align-items:center;gap:16px;
  padding:18px 24px;border-radius:14px;margin:0 0 16px 0;
  font-family:'JetBrains Mono',monospace;
}
.feature-state.on  {
  background:linear-gradient(135deg,#052e16,#14532d);
  border:1px solid #22c55e;
  animation:statePulse 2.4s ease-in-out infinite;
}
.feature-state.off {
  background:linear-gradient(135deg,#2c0a0a,#3f1414);
  border:1px solid #ef4444;
  animation:stateOff 2.4s ease-in-out infinite;
}
.feature-state .icon       { font-size:28px; }
.feature-state .label      { font-size:11px;letter-spacing:.12em;text-transform:uppercase;color:#94a3b8;display:block; }
.feature-state .value      { font-size:18px;font-weight:700;display:block;margin-top:2px; }
.feature-state.on  .value  { color:#86efac; }
.feature-state.off .value  { color:#fca5a5; }
.feature-state .flag-key   { font-size:11px;color:#94a3b8;margin-left:auto; }

/* Stronger flash banner */
.flag-flash {
    background:linear-gradient(90deg,#1a1305,#3a2208) !important;
    border:2px solid #f59e0b !important;
    border-left:6px solid #f59e0b !important;
    padding:18px 22px !important;
    font-size:14px !important;
    font-weight:600 !important;
    color:#fde68a !important;
    box-shadow:0 0 40px rgba(245,158,11,0.35) !important;
}

/* ── Streamlit expander — themed to match dark cards ── */
[data-testid="stExpander"] details {
    background: #0c0c1e !important;
    border: 1px solid #2d2d50 !important;
    border-radius: 10px !important;
    margin: 8px 0 !important;
}
[data-testid="stExpander"] summary {
    color: #c7d2fe !important;
    font-size: 14px !important;
    padding: 14px 18px !important;
    border-radius: 10px !important;
}
[data-testid="stExpander"] summary:hover {
    background: #11113a !important;
}
[data-testid="stExpander"] summary p { color: #c7d2fe !important; font-weight: 500 !important; }
[data-testid="stExpander"] [data-testid="stExpanderDetails"] { padding: 4px 14px 14px !important; }
</style>
""", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════
# SESSION STATE — for change detection & experiment counters
# ══════════════════════════════════════════════════════════════════════════
ss = st.session_state
ss.setdefault("prev_flags",       {})
ss.setdefault("flash_until",      0.0)
ss.setdefault("conv_events",      0)
ss.setdefault("kill_until",       0.0)
ss.setdefault("session_id",       str(uuid.uuid4())[:8])
ss.setdefault("last_ai_response", None)   # survives autorefresh reruns
ss.setdefault("last_ai_error",    None)
ss.setdefault("last_ai_status",   None)
ss.setdefault("last_ai_trace",    None)
ss.setdefault("disable_autorefresh", False)
ss.setdefault("last_ai_tracker_errors", [])

# ══════════════════════════════════════════════════════════════════════════
# SIDEBAR — User Simulator
# ══════════════════════════════════════════════════════════════════════════
with st.sidebar:
    st.markdown("""
    <div style='padding:12px 0 6px;'>
        <div style='font-size:10px;font-weight:700;color:#94a3b8;letter-spacing:.14em;
                    text-transform:uppercase;font-family:"JetBrains Mono",monospace;'>
            LaunchDarkly Demo
        </div>
        <div style='font-size:20px;font-weight:800;color:#a5b4fc;margin:6px 0 2px;'>
            User Simulator
        </div>
        <div style='font-size:12px;color:#94a3b8;'>
            Change attributes to see targeting live
        </div>
    </div>
    """, unsafe_allow_html=True)
    st.divider()

    st.markdown('<div style="font-size:10px;font-weight:700;color:#94a3b8;letter-spacing:.1em;text-transform:uppercase;font-family:\'JetBrains Mono\',monospace;margin-bottom:8px;">User Key</div>', unsafe_allow_html=True)
    user_key = st.selectbox(
        "User key", ["alice", "bob", "carol", "dave", "eve", "guest-9923"],
        label_visibility="collapsed",
        help="Individual targeting matches on this exact key. alice and carol are pre-targeted."
    )

    st.divider()
    st.markdown('<div style="font-size:10px;font-weight:700;color:#94a3b8;letter-spacing:.1em;text-transform:uppercase;font-family:\'JetBrains Mono\',monospace;margin-bottom:10px;">Context Attributes</div>', unsafe_allow_html=True)

    user_tier    = st.select_slider("tier", options=["free","pro","enterprise"], value="free")
    user_country = st.selectbox("country", ["SG","AU","JP","IN","US","UK"])
    user_beta    = st.toggle("betaTester", value=False)
    user_device  = st.radio("deviceType", ["desktop","mobile"], horizontal=True)

    st.divider()
    if ld_ok:
        st.markdown('<div class="pill-on"><span class="dot-on"></span>LD Connected</div>', unsafe_allow_html=True)
    else:
        st.markdown('<div class="pill-off"><span class="dot-off"></span>LD Disconnected</div>', unsafe_allow_html=True)
    st.markdown(f'<div style="margin-top:8px;font-size:11px;color:#64748b;font-family:\'JetBrains Mono\',monospace;">session · {ss.session_id}</div>', unsafe_allow_html=True)

    st.divider()
    # ── LIVE STREAMING (non-blocking, via streamlit-autorefresh) ─────────
    st.markdown('<div style="font-size:10px;font-weight:700;color:#94a3b8;letter-spacing:.1em;text-transform:uppercase;font-family:\'JetBrains Mono\',monospace;margin-bottom:8px;">⟳ Live Streaming</div>', unsafe_allow_html=True)
    auto_refresh = st.toggle(
        "Auto-refresh (1.5s)", value=True,
        help="Non-blocking poll that pairs with the SDK change listener. "
             "Toggle a flag in LD — watch this app react instantly."
    )
    # Skip autorefresh while an AI call is in flight — otherwise the rerun
    # cancels the in-progress OpenAI call and the response never lands.
    # Also respect a manual user override (set from the AI tab).
    _ai_in_flight    = ss.get("last_ai_status") == "calling"
    _user_paused     = ss.get("disable_autorefresh", False)
    _refresh_active  = auto_refresh and HAS_AUTOREFRESH and not _ai_in_flight and not _user_paused

    if _refresh_active:
        # 5-second interval (was 1.5s) gives OpenAI calls time to complete
        # before being interrupted. Flag-change detection is still fast
        # enough for the live demo — most toggles propagate well within 5s.
        st_autorefresh(interval=5000, key="ld_autorefresh")
        st.markdown(
            '<div style="font-size:11px;color:#4ade80;font-family:\'JetBrains Mono\',monospace;'
            'line-height:1.7;">'
            '<span class="dot-live"></span>&nbsp;Listening for flag changes<br/>'
            'SDK stream + 5s poll<br/>'
            'Toggle a flag in LD →<br/>watch the UI react.</div>',
            unsafe_allow_html=True
        )
    elif auto_refresh and _ai_in_flight:
        st.markdown(
            '<div style="font-size:11px;color:#fbbf24;font-family:\'JetBrains Mono\',monospace;'
            'line-height:1.7;">⏸ Autorefresh paused (AI call in flight)</div>',
            unsafe_allow_html=True
        )
    elif _user_paused:
        st.markdown(
            '<div style="font-size:11px;color:#fbbf24;font-family:\'JetBrains Mono\',monospace;'
            'line-height:1.7;">⏸ Autorefresh paused (manual override)</div>',
            unsafe_allow_html=True
        )
    elif auto_refresh and not HAS_AUTOREFRESH:
        st.warning("Install `streamlit-autorefresh` for non-blocking live updates.")

# ══════════════════════════════════════════════════════════════════════════
# BUILD LAUNCHDARKLY CONTEXT
# ══════════════════════════════════════════════════════════════════════════
context = (
    Context.builder(user_key)
    .kind("user")
    .name(user_key.capitalize())
    .set("tier",       user_tier)
    .set("country",    user_country)
    .set("betaTester", user_beta)
    .set("deviceType", user_device)
    .build()
)

# ══════════════════════════════════════════════════════════════════════════
# EVALUATE ALL FLAGS  (locally in-memory, <5ms)
# ══════════════════════════════════════════════════════════════════════════
show_hero     = ld.variation(FLAG_HERO,     context, False)

# For the checkout flag we want the *full evaluation detail* — not just the
# value — so the Part 2 rules panel can show LD's ACTUAL reason for serving
# what it served (target match, rule match, fallthrough, off, etc.) rather
# than re-deriving it from hardcoded conditions in this file.
_checkout_detail = ld.variation_detail(FLAG_CHECKOUT, context, False)
show_checkout    = _checkout_detail.value

def _reason_kind(d):
    r = getattr(d, "reason", None) or {}
    return r.get("kind") if isinstance(r, dict) else getattr(r, "kind", None)
def _reason_index(d):
    r = getattr(d, "reason", None) or {}
    return r.get("ruleIndex") if isinstance(r, dict) else getattr(r, "rule_index", None)

checkout_reason_kind  = _reason_kind(_checkout_detail)
checkout_reason_index = _reason_index(_checkout_detail)

banner_text   = ld.variation(FLAG_BANNER,   context, "")

current_flags = {
    FLAG_HERO:     show_hero,
    FLAG_CHECKOUT: show_checkout,
    FLAG_BANNER:   banner_text,
}

# Detect value changes vs. the previous rerun → fuels the flash banner.
just_changed = []
for k, v in current_flags.items():
    if k in ss.prev_flags and ss.prev_flags[k] != v:
        just_changed.append((k, ss.prev_flags[k], v))
ss.prev_flags = current_flags.copy()

if just_changed:
    ss.flash_until = time.time() + 6
    # If the hero feature was just killed → trigger the kill-switch banner
    for k, old, new in just_changed:
        if k == FLAG_HERO and old is True and new is False:
            ss.kill_until = time.time() + 8

# ══════════════════════════════════════════════════════════════════════════
# HEADER
# ══════════════════════════════════════════════════════════════════════════
col_logo, col_user = st.columns([3, 1])
with col_logo:
    st.markdown("""
    <div style='margin-bottom:2px;'>
        <span style='font-size:24px;font-weight:800;color:#e2e8f0;'>Pulse</span>
        <span style='font-size:13px;color:#94a3b8;margin-left:12px;
                     font-family:"JetBrains Mono",monospace;'>· Fitness Performance Platform</span>
    </div>
    """, unsafe_allow_html=True)
with col_user:
    tc = {"free":"#64748b","pro":"#818cf8","enterprise":"#a78bfa"}[user_tier]
    st.markdown(f"""
    <div style='text-align:right;padding-top:5px;'>
        <span style='font-size:12px;font-family:"JetBrains Mono",monospace;'>
            <span style='color:#6366f1;'>{user_key}</span>
            &nbsp;·&nbsp;<span style='color:{tc};'>{user_tier}</span>
            &nbsp;·&nbsp;<span style='color:#94a3b8;'>{user_country}</span>
        </span>
    </div>
    """, unsafe_allow_html=True)

# Promotional banner (string flag)
if banner_text:
    st.markdown(f"""
    <div style='background:linear-gradient(90deg,#0d0d28,#11113a);border:1px solid #3730a344;
                border-radius:8px;padding:9px 18px;margin:8px 0;font-size:13px;color:#818cf8;
                font-family:"JetBrains Mono",monospace;'>
        📣 &nbsp;{banner_text}
        <span style='font-size:10px;color:#a5b4fc;margin-left:12px;'>← string flag: {FLAG_BANNER}</span>
    </div>
    """, unsafe_allow_html=True)

# ── FLASH BANNER on live flag change (the "wow" moment) ──────────────────
if time.time() < ss.flash_until and just_changed:
    for k, old, new in just_changed:
        st.markdown(f"""
        <div class="flag-flash">
            <span class="dot-live"></span>
            <b>{k}</b> changed live · <code>{old}</code> → <code>{new}</code>
            &nbsp;·&nbsp; no reload, no redeploy
        </div>
        """, unsafe_allow_html=True)

if time.time() < ss.kill_until:
    st.markdown(f"""
    <div class="kill-flash">
        🛑 KILL-SWITCH FIRED · <b>{FLAG_HERO}</b> turned OFF · customer impact stopped
    </div>
    """, unsafe_allow_html=True)

st.divider()

# ══════════════════════════════════════════════════════════════════════════
# TABS
# ══════════════════════════════════════════════════════════════════════════
tab1, tab2, tab3, tab4 = st.tabs([
    "🏠  Home",
    "💳  Membership",
    "🤖  AI Coach",
    "📊  Admin",
])

# ──────────────────────────────────────────────────────────────────────────
# PART 1 — RELEASE & REMEDIATE
# ──────────────────────────────────────────────────────────────────────────
with tab1:
    st.markdown('<div class="chip">🏠 HOME · Flag: new-hero-banner</div>', unsafe_allow_html=True)

    # Big, pulsing state indicator — impossible to miss when the flag flips.
    _state_cls = "on" if show_hero else "off"
    _state_icon = "✦" if show_hero else "○"
    _state_value = "NEW EXPERIENCE LIVE" if show_hero else "LEGACY EXPERIENCE"
    st.markdown(f"""
    <div class="feature-state {_state_cls}">
        <div class="icon">{_state_icon}</div>
        <div>
            <span class="label">Feature state — live from LaunchDarkly</span>
            <span class="value">{_state_value}</span>
        </div>
        <div class="flag-key">flag · new-hero-banner = {str(show_hero).upper()}</div>
    </div>
    """, unsafe_allow_html=True)

    # Live streaming indicator — driven by the real SDK listener + autorefresh
    if auto_refresh and HAS_AUTOREFRESH:
        st.markdown(f"""
        <div class="stream-on">
            <span class="dot-live"></span>
            STREAMING ACTIVE · SDK listener attached · UI polls every 1.5s.
            Toggle <code>{FLAG_HERO}</code> in LD — UI reacts instantly.
        </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown("""
        <div class="stream-off">
            Auto-refresh OFF. Re-enable it in the sidebar to see live flag changes without reloading.
        </div>
        """, unsafe_allow_html=True)

    col_main, col_side = st.columns([3, 1])

    with col_main:
        # ── THE FEATURE FLAG GATE ─────────────────────────────────────────
        # This single if/else is the entire release mechanism.
        # Both code paths ship in the same binary. LD picks which one runs.
        if show_hero:
            st.markdown("""
            <div class="hero-new">
                <div class="tag">✦ NEW — AI Personal Trainer</div>
                <h2>Train smarter.<br/>Push harder. Recover better.</h2>
                <p>Workouts that adapt to your performance in real time.<br/>
                Built for athletes. Trusted by gyms. Loved by trainers.</p>
                <div style='display:flex;gap:12px;flex-wrap:wrap;'>
                    <div style='background:#4f46e5;color:#fff;border-radius:8px;
                                padding:9px 20px;font-size:13px;font-weight:600;'>Start Free Trial →</div>
                    <div style='border:1px solid #1e293b;color:#475569;border-radius:8px;
                                padding:9px 20px;font-size:13px;'>Watch Demo</div>
                </div>
            </div>
            """, unsafe_allow_html=True)
            st.markdown(f'<div class="pill-on"><span class="dot-on"></span>{FLAG_HERO} = TRUE — New experience LIVE</div>', unsafe_allow_html=True)
            st.caption("Toggle the flag OFF in LaunchDarkly → instant rollback, zero redeploy.")
            st.markdown("""
            <div class="metric-row">
                <div class="metric-box"><div class="m-val">184k</div><div class="m-lbl">Active Members</div><div class="m-pos">↑ 18%</div></div>
                <div class="metric-box"><div class="m-val">4.9★</div><div class="m-lbl">Avg. Plan Rating</div><div class="m-pos">↑ 0.3</div></div>
                <div class="metric-box"><div class="m-val">47k</div><div class="m-lbl">Workouts Today</div><div class="m-pos">↑ 12%</div></div>
                <div class="metric-box"><div class="m-val">+72</div><div class="m-lbl">Member NPS</div><div class="m-pos">↑ 4 vs last wk</div></div>
            </div>
            """, unsafe_allow_html=True)
        else:
            st.markdown("""
            <div class="hero-old">
                <div class="tag">Legacy · Pulse 2.x</div>
                <h2>Pulse Dashboard</h2>
                <p>Welcome back. Your workouts are ready.</p>
                <div style='background:#1a1a30;border:1px solid #2d2d50;border-radius:6px;
                            padding:8px 14px;display:inline-block;font-size:13px;color:#cbd5e1;'>
                    View Workouts
                </div>
            </div>
            """, unsafe_allow_html=True)
            st.markdown(f'<div class="pill-off"><span class="dot-off"></span>{FLAG_HERO} = FALSE — Legacy experience served</div>', unsafe_allow_html=True)
            st.caption("Toggle the flag ON in LaunchDarkly to release the new version instantly.")
            st.markdown("""
            <div class="metric-row">
                <div class="metric-box dim"><div class="m-val">184k</div><div class="m-lbl">Members</div></div>
                <div class="metric-box dim"><div class="m-val">4.9★</div><div class="m-lbl">Rating</div></div>
                <div class="metric-box dim"><div class="m-val">47k</div><div class="m-lbl">Workouts</div></div>
            </div>
            """, unsafe_allow_html=True)

    with col_side:
        st.markdown("""<div class="card-accent"><div style='font-size:10px;font-weight:700;color:#a5b4fc;letter-spacing:.1em;text-transform:uppercase;font-family:"JetBrains Mono",monospace;margin-bottom:14px;'>Release lifecycle</div>""", unsafe_allow_html=True)
        for num, color, title, desc in [
            ("1","#818cf8","Deploy",   "Code ships to prod — flag OFF. Zero user impact."),
            ("2","#4ade80","Release",  "Toggle ON in LD. New experience live in <2s."),
            ("3","#f87171","Rollback", "Bug detected? Toggle OFF. Restored instantly."),
            ("4","#a78bfa","Remediate","curl trigger auto-disables. No code, no redeploy."),
        ]:
            st.markdown(f"""
            <div class="tl-item">
                <div class="tl-num" style='background:{color}18;border:1px solid {color}44;color:{color};'>{num}</div>
                <div><div class="tl-title">{title}</div><div class="tl-desc">{desc}</div></div>
            </div>
            """, unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

    # ── REMEDIATE via TRIGGER  (collapsed by default — click to expand) ───
    st.divider()
    with st.expander("🔧  **Remediate · Trigger** — disable without code change or redeploy", expanded=False):
        col_t1, col_t2 = st.columns([3, 2])
        with col_t1:
            st.markdown(f"""
            <div class="trigger">
                <div style='font-size:13px;font-weight:600;color:#a78bfa;margin-bottom:10px;'>📡 Trigger setup</div>
                <div style='font-size:12px;color:#64748b;line-height:1.8;margin-bottom:12px;'>
                    1. LD Dashboard → Feature Flags → <code style='color:#a78bfa;'>{FLAG_HERO}</code><br/>
                    2. Triggers tab → Add trigger → Generic trigger<br/>
                    3. Copy the webhook URL → run the curl below
                </div>
            </div>
            """, unsafe_allow_html=True)
            st.markdown("""
            <div class="mono">
<span style='color:#94a3b8;'># Simulate automated incident response:</span><br/>
<span style='color:#4ade80;'>curl</span> -X POST <span style='color:#fbbf24;'>"https://app.launchdarkly.com/webhook/triggers/&lt;url&gt;"</span><br/><br/>
<span style='color:#94a3b8;'># Flag OFF instantly. No code. No redeploy.</span><br/>
<span style='color:#94a3b8;'># In prod: PagerDuty/Datadog fires this when error rate spikes.</span>
            </div>
            """, unsafe_allow_html=True)
        with col_t2:
            st.markdown("""
            <div class="card">
                <div style='font-size:13px;font-weight:600;color:#a78bfa;margin-bottom:10px;'>Impact comparison</div>
                <div style='font-size:13px;color:#94a3b8;line-height:1.8;margin-bottom:12px;'>
                    <strong style='color:#64748b;'>Traditional:</strong><br/>
                    detect → wake engineer → fix → deploy<br/>
                    <span style='color:#f87171;'>30–60 min user impact</span>
                </div>
                <div style='font-size:13px;color:#94a3b8;line-height:1.8;'>
                    <strong style='color:#64748b;'>With LD trigger:</strong><br/>
                    detect → webhook fires → flag OFF<br/>
                    <span style='color:#4ade80;'>2 seconds additional impact</span>
                </div>
            </div>
            """, unsafe_allow_html=True)

        st.markdown("""
        <div class="mono" style='margin-top:8px;'>
<span style='color:#94a3b8;'># The complete LD integration — 5 lines, including the listener:</span><br/>
ldclient.set_config(Config(<span style='color:#fbbf24;'>LD_SDK_KEY</span>))                             <span style='color:#94a3b8;'># 1. connect</span><br/>
ld.flag_tracker.add_listener(<span style='color:#a5b4fc;'>on_change</span>)                          <span style='color:#94a3b8;'># 2. listen</span><br/>
context = Context.builder(<span style='color:#fbbf24;'>user_key</span>).set(<span style='color:#a5b4fc;'>"tier"</span>, tier).build()   <span style='color:#94a3b8;'># 3. context</span><br/>
show = ld.variation(<span style='color:#a5b4fc;'>"new-hero-banner"</span>, context, <span style='color:#f87171;'>False</span>)            <span style='color:#94a3b8;'># 4. evaluate</span><br/>
<span style='color:#818cf8;'>if</span> show: render_new_experience()                                    <span style='color:#94a3b8;'># 5. react</span>
        </div>
        """, unsafe_allow_html=True)


# ──────────────────────────────────────────────────────────────────────────
# PART 2 — TARGET
# ──────────────────────────────────────────────────────────────────────────
with tab2:
    st.markdown('<div class="chip">💳 MEMBERSHIP · Flag: checkout-redesign</div>', unsafe_allow_html=True)

    col_cx, col_rules = st.columns([3, 2])

    with col_cx:
        if show_checkout:
            st.markdown(f"""
            <div class="checkout-new">
                <div style='font-size:10px;font-weight:700;color:#6366f1;letter-spacing:.12em;
                            text-transform:uppercase;font-family:"JetBrains Mono",monospace;margin-bottom:14px;'>
                    ✦ Redesigned Signup · {user_tier.upper()}
                </div>
                <div style='font-size:22px;font-weight:700;color:#e2e8f0;margin-bottom:6px;'>Activate Premium Membership</div>
                <div style='font-size:13px;color:#94a3b8;margin-bottom:22px;'>Unlimited AI-personalised workouts · Cancel anytime.</div>
            </div>
            """, unsafe_allow_html=True)
            st.markdown(f'<div class="pill-on"><span class="dot-on"></span>{FLAG_CHECKOUT} = TRUE · LD evaluated to new signup for {user_key}</div>', unsafe_allow_html=True)
            st.markdown("<br>", unsafe_allow_html=True)
            with st.form("checkout_new"):
                c1, c2 = st.columns(2)
                c1.text_input("First name", placeholder="Alex")
                c2.text_input("Last name",  placeholder="Chen")
                st.text_input("Email", placeholder="alex@pulsefit.com")
                c3, c4, c5 = st.columns([2,1,1])
                c3.text_input("Card number", placeholder="4242 4242 4242 4242")
                c4.text_input("Expiry",      placeholder="MM/YY")
                c5.text_input("CVV",         placeholder="•••", type="password")
                st.checkbox("Save card for monthly billing")
                if st.form_submit_button("Start Premium Membership →", use_container_width=True):
                    # ─── Experiment metric (Part 3): track the conversion ───
                    # This is what feeds an LD Experiment on `checkout-redesign`.
                    ld.track(METRIC_PURCHASE, context, metric_value=1.0)
                    ss.conv_events += 1
                    st.success(
                        f"✅ Membership activated (demo). Event `{METRIC_PURCHASE}` "
                        f"sent to LD — feeds the experiment in Part 3."
                    )
        else:
            st.markdown("""
            <div class="checkout-old">
                <div style='font-size:10px;font-weight:700;color:#1a1a2e;letter-spacing:.12em;
                            text-transform:uppercase;font-family:"JetBrains Mono",monospace;margin-bottom:14px;'>
                    Legacy Signup
                </div>
                <div style='font-size:20px;font-weight:600;color:#64748b;margin-bottom:18px;'>Sign Up</div>
            </div>
            """, unsafe_allow_html=True)
            st.markdown(f'<div class="pill-off"><span class="dot-off"></span>{FLAG_CHECKOUT} = FALSE · LD evaluated to legacy for {user_key}</div>', unsafe_allow_html=True)
            st.caption(f"User `{user_key}` got the legacy signup form.")
            st.markdown("<br>", unsafe_allow_html=True)
            with st.form("checkout_old"):
                st.text_input("Email address")
                st.text_input("Card number")
                st.text_input("CVV", type="password")
                if st.form_submit_button("Submit"):
                    # Track the conversion against the control variation too.
                    ld.track(METRIC_PURCHASE, context, metric_value=1.0)
                    ss.conv_events += 1
                    st.success(f"Submitted. Event `{METRIC_PURCHASE}` sent (control variation).")

    with col_rules:
        # ── Drive the highlighting from LD's *actual* evaluation reason ──
        # variation_detail returns reasons like:
        #   {kind: "TARGET_MATCH"}                 → individual targets matched
        #   {kind: "RULE_MATCH", ruleIndex: N}     → custom rule N matched
        #   {kind: "FALLTHROUGH"}                  → no rule matched, default served
        #   {kind: "OFF"}                          → targeting toggle is OFF
        #   {kind: "ERROR", errorKind: ...}        → SDK could not evaluate
        matched_card = None
        if checkout_reason_kind == "TARGET_MATCH":
            matched_card = "individual"
        elif checkout_reason_kind == "RULE_MATCH":
            matched_card = f"rule{checkout_reason_index}"
        elif checkout_reason_kind == "FALLTHROUGH":
            matched_card = "default"
        elif checkout_reason_kind == "OFF":
            matched_card = "off"

        st.markdown("""<div class="card-accent"><div style='font-size:10px;font-weight:700;color:#a5b4fc;letter-spacing:.1em;text-transform:uppercase;font-family:"JetBrains Mono",monospace;margin-bottom:14px;'>Targeting Rules · live from LD</div>""", unsafe_allow_html=True)

        if matched_card == "off":
            st.markdown(f"""
            <div class="rule" style='border-color:#f59e0b;background:#1a1305;'>
                <div class="rule-num" style='color:#fbbf24;'>⚠ Targeting OFF</div>
                <div class="rule-body" style='color:#fde68a;'>
                  The flag's targeting toggle is OFF in LD — none of the rules below
                  are evaluated. Currently serving the off-variation:
                  <code>{show_checkout}</code>.
                </div>
            </div>
            """, unsafe_allow_html=True)

        for slot, rnum, rtitle, rbody in [
            ("individual", "Individual", "Specific user keys",
             "Serve TRUE to: <code style='color:#818cf8;'>alice</code>, <code style='color:#818cf8;'>carol</code><br/>"
             "<span style='font-size:11px;color:#64748b;'>Internal QA / pilot users</span>"),
            ("rule0",      "Rule 1", "tier = enterprise",
             "IF <code style='color:#818cf8;'>tier</code> = <code style='color:#a78bfa;'>\"enterprise\"</code> → TRUE"),
            ("rule1",      "Rule 2", "betaTester = true",
             "IF <code style='color:#818cf8;'>betaTester</code> = <code style='color:#a78bfa;'>true</code> → TRUE"),
        ]:
            is_match = (slot == matched_card)
            cls    = "rule matched" if is_match else "rule"
            served = "TRUE" if show_checkout else "FALSE"
            result = (f'<div class="rule-match">✓ MATCHED — LD served {served}</div>'
                      if is_match else
                      '<div class="rule-miss">— not matched by LD</div>')
            st.markdown(f"""
            <div class="{cls}">
                <div class="rule-num">{rnum} · {rtitle}</div>
                <div class="rule-body">{rbody}</div>
                {result}
            </div>
            """, unsafe_allow_html=True)

        # Default rule card — also driven by LD's reason
        is_default = (matched_card == "default")
        default_served = "TRUE" if show_checkout else "FALSE"
        default_colour = "#4ade80" if show_checkout else "#f87171"
        def_result = (f'<div class="rule-match" style="color:{default_colour};">'
                      f'↓ FALLTHROUGH — LD served {default_served}</div>'
                      if is_default else
                      '<div class="rule-miss">skipped — a rule above matched</div>')
        def_cls = "rule matched" if is_default else "rule"
        st.markdown(f"""
        <div class="{def_cls}" style='border-color:#1f2937;'>
            <div class="rule-num" style='color:#94a3b8;'>Default Rule · Fallthrough</div>
            <div class="rule-body">Everyone else → whatever the default rule serves in LD</div>
            {def_result}
        </div>
        """, unsafe_allow_html=True)

        # Honest debug line — surfaces mismatches between what the panel
        # mirrors and what LD actually did (e.g. a percentage rollout, an
        # unexpected rule, or targeting being toggled off).
        st.caption(
            f"LD evaluation reason: `{checkout_reason_kind}`"
            + (f" · rule index `{checkout_reason_index}`" if checkout_reason_index is not None else "")
            + f" · value `{show_checkout}`"
        )

        st.markdown("</div>", unsafe_allow_html=True)

    st.divider()
    st.markdown('<div class="chip">📋 CONTEXT · Sent to LD on every flag evaluation</div>', unsafe_allow_html=True)
    col_j, col_n = st.columns([2, 3])
    with col_j:
        st.json({"kind":"user","key":user_key,"name":user_key.capitalize(),
                 "tier":user_tier,"country":user_country,
                 "betaTester":user_beta,"deviceType":user_device})
    with col_n:
        st.markdown("""
        <div style='padding-top:8px;font-size:13px;color:#94a3b8;line-height:1.9;'>
            Every flag evaluation passes this context to LaunchDarkly.<br/>
            The SDK evaluates targeting rules against these attributes
            <strong style='color:#c7d2fe;'>locally in memory</strong> —
            no network call per evaluation, results in
            <strong style='color:#4ade80;'>&lt;5ms</strong>.<br/><br/>
            Change any sidebar attribute — the targeting rules update live.
        </div>
        """, unsafe_allow_html=True)



# ──────────────────────────────────────────────────────────────────────────
# PART 3 — BONUS (Experimentation · AI Configs)
# ──────────────────────────────────────────────────────────────────────────
with tab3:
    exp_tab, ai_tab = st.tabs([
        "📊 Conversion Analytics",
        "💬 Chat",
    ])

    # ── EXPERIMENTATION ──────────────────────────────────────────────────
    with exp_tab:
        st.markdown('<div class="chip">📊 ANALYTICS · Measure conversion impact with statistical significance</div>', unsafe_allow_html=True)
        col_e1, col_e2 = st.columns([3,2])

        with col_e1:
            st.markdown(f"""
            <div class="card-accent" style='margin-bottom:16px;'>
                <div style='font-size:18px;font-weight:700;color:#e2e8f0;margin-bottom:6px;'>
                    Does the new checkout increase conversion?
                </div>
                <div style='font-size:13px;color:#94a3b8;line-height:1.6;'>
                    Reuse the <code style='color:#818cf8;'>checkout-redesign</code> flag as the
                    experiment flag. The "Complete Purchase" button in Part 2 emits a
                    <code style='color:#818cf8;'>{METRIC_PURCHASE}</code> metric via
                    <code style='color:#a78bfa;'>ld.track()</code>.
                    LD attributes each event to the variation the user saw and computes
                    significance automatically.
                </div>
            </div>
            """, unsafe_allow_html=True)

            # Real session-level counter (proves we're actually emitting events)
            st.markdown(f"""
            <div class="card" style='margin-bottom:18px;
                 background:linear-gradient(90deg,#0a1f12,#0d2918);
                 border-color:#16653488;'>
                <div style='display:flex;align-items:center;justify-content:space-between;'>
                    <div>
                        <div style='font-size:11px;color:#4ade80;font-family:"JetBrains Mono",monospace;
                                    letter-spacing:.1em;text-transform:uppercase;margin-bottom:4px;'>
                            Events emitted this session
                        </div>
                        <div style='font-size:13px;color:#86efac;'>Sent to LD as <code>{METRIC_PURCHASE}</code></div>
                    </div>
                    <div style='font-size:32px;font-weight:800;color:#4ade80;
                                font-family:"JetBrains Mono",monospace;'>{ss.conv_events}</div>
                </div>
            </div>
            """, unsafe_allow_html=True)

            # Representative results panel (what the LD UI would show post-collection)
            for var, rate, lift, sig, color in [
                ("Control (legacy checkout)",  "3.2%", "—",      "Baseline",              "#374151"),
                ("Variation A (new checkout)", "4.7%", "+46.9%", "✓ Significant p<0.05",  "#4ade80"),
            ]:
                st.markdown(f"""
                <div class="card" style='margin-bottom:8px;'>
                    <div style='display:flex;justify-content:space-between;align-items:center;'>
                        <div>
                            <div style='font-size:13px;font-weight:600;color:#c7d2fe;'>{var}</div>
                            <div style='font-size:12px;color:#94a3b8;margin-top:3px;'>{sig}</div>
                        </div>
                        <div style='text-align:right;'>
                            <div style='font-size:22px;font-weight:700;font-family:"JetBrains Mono",monospace;color:{color};'>{rate}</div>
                            <div style='font-size:12px;color:{color};font-family:"JetBrains Mono",monospace;'>{lift}</div>
                        </div>
                    </div>
                </div>
                """, unsafe_allow_html=True)

            st.markdown("<br>", unsafe_allow_html=True)
            for step, pct_old, pct_new in [
                ("Page view",61,68),("Add to cart",38,47),("Begin checkout",12,18),("Purchase",3,5)
            ]:
                bar_new = int(pct_new/pct_old*100) if pct_old else 0
                st.markdown(f"""
                <div style='margin-bottom:10px;'>
                    <div style='display:flex;justify-content:space-between;margin-bottom:4px;'>
                        <span style='font-size:12px;color:#94a3b8;'>{step}</span>
                        <span style='font-size:12px;font-family:"JetBrains Mono",monospace;'>
                            <span style='color:#94a3b8;'>{pct_old}%</span>&nbsp;→&nbsp;
                            <span style='color:#4ade80;'>{pct_new}%</span>
                        </span>
                    </div>
                    <div style='background:#0a0a18;border-radius:4px;height:8px;overflow:hidden;'>
                        <div style='height:100%;width:{pct_old}%;background:#1a1a2e;border-radius:4px;position:relative;'>
                            <div style='position:absolute;left:0;top:0;height:100%;width:{bar_new}%;
                                        background:linear-gradient(90deg,#4f46e5,#7c3aed);border-radius:4px;'></div>
                        </div>
                    </div>
                </div>
                """, unsafe_allow_html=True)

        with col_e2:
            st.markdown("""<div class="card"><div style='font-size:10px;font-weight:700;color:#94a3b8;letter-spacing:.1em;text-transform:uppercase;font-family:"JetBrains Mono",monospace;margin-bottom:14px;'>How to set up in LD</div>""", unsafe_allow_html=True)
            for sn, st_, sd in [
                ("1","Create metric",    f"Experiments → Metrics → Create → Custom event → name it {METRIC_PURCHASE}."),
                ("2","Create experiment",f"Experiments → Create → attach {FLAG_CHECKOUT} + {METRIC_PURCHASE}."),
                ("3","Set audience",     "Choose experiment %. Start at 20% — enough for signal without full exposure."),
                ("4","Start & observe",  "LD shows confidence intervals live. Wait for statistical significance."),
                ("5","Ship the winner",  "Roll winning variation to 100%. No code change needed."),
            ]:
                st.markdown(f"""
                <div style='display:flex;gap:10px;margin-bottom:12px;align-items:flex-start;'>
                    <div style='width:22px;height:22px;border-radius:50%;background:#1a1a30;border:1px solid #3730a3;
                                color:#818cf8;font-size:10px;font-weight:700;display:flex;align-items:center;
                                justify-content:center;flex-shrink:0;font-family:"JetBrains Mono",monospace;'>{sn}</div>
                    <div>
                        <div style='font-size:12px;font-weight:600;color:#c7d2fe;'>{st_}</div>
                        <div style='font-size:12px;color:#94a3b8;line-height:1.4;margin-top:2px;'>{sd}</div>
                    </div>
                </div>
                """, unsafe_allow_html=True)
            st.markdown("</div>", unsafe_allow_html=True)

            # The actual SDK call shown to the viewer
            st.markdown(f"""
            <div class="mono" style='margin-top:10px;'>
<span style='color:#94a3b8;'># Live in this app — Part 2 checkout form fires:</span><br/>
ld.track(<br/>
&nbsp;&nbsp;<span style='color:#fbbf24;'>"{METRIC_PURCHASE}"</span>,<br/>
&nbsp;&nbsp;context,<br/>
&nbsp;&nbsp;metric_value=<span style='color:#4ade80;'>1.0</span><br/>
)
            </div>
            """, unsafe_allow_html=True)

    # ── AI CONFIGS ───────────────────────────────────────────────────────
    with ai_tab:
        st.markdown('<div class="chip">🤖 AI COACH · Powered by LaunchDarkly AI Configs — swap models and prompts without redeploying</div>', unsafe_allow_html=True)
        col_a1, col_a2 = st.columns([3,2])

        with col_a1:
            st.markdown(f"""
            <div class="card-accent" style='margin-bottom:16px;'>
                <div style='font-size:16px;font-weight:700;color:#e2e8f0;margin-bottom:6px;'>AI Fitness Coach</div>
                <div style='font-size:13px;color:#94a3b8;line-height:1.6;'>
                    Model, system prompt, and temperature are controlled by an LD AI Config —
                    not hardcoded here. Change them in the LD dashboard → takes effect instantly.<br/><br/>
                    User <strong style='color:#818cf8;'>{user_key}</strong>
                    (tier: <strong style='color:#a78bfa;'>{user_tier}</strong>) →
                    {"<strong style='color:#4ade80;'>gpt-4o (enterprise variation)</strong>" if user_tier == "enterprise"
                     else "<strong style='color:#64748b;'>gpt-4o-mini (standard variation)</strong>"}
                </div>
            </div>
            """, unsafe_allow_html=True)

            if not AI_AVAILABLE:
                st.warning("AI SDK not installed. Run: `pip install launchdarkly-server-sdk-ai openai`")
            elif not OPENAI_API_KEY:
                st.warning("Set `OPENAI_API_KEY` environment variable to enable the live AI demo.")
            else:
                # ── Heads-up about the autorefresh / AI-call interaction.
                # OpenAI calls take 2-10 s. If autorefresh fires mid-call,
                # Streamlit kills the script and the response is lost.
                # Offer the user a one-click pause.
                if not ss.get("disable_autorefresh", False):
                    _c1, _c2 = st.columns([3, 1])
                    with _c1:
                        st.info(
                            "💡 **Tip:** if responses don't appear, pause autorefresh — "
                            "the 5-second poll can interrupt long OpenAI calls."
                        )
                    with _c2:
                        if st.button("⏸ Pause", key="pause_autorefresh"):
                            ss.disable_autorefresh = True
                            st.rerun()
                else:
                    _c1, _c2 = st.columns([3, 1])
                    with _c1:
                        st.success("✅ Autorefresh paused — AI calls won't be interrupted.")
                    with _c2:
                        if st.button("▶ Resume", key="resume_autorefresh"):
                            ss.disable_autorefresh = False
                            st.rerun()

                user_q = st.text_input("Ask the assistant:", placeholder="e.g. How do I add a team member?")
                _send_clicked = st.button("Send →")

                # Surface common silent-failure cases explicitly
                if _send_clicked and not user_q:
                    st.warning("Type a question above first, then click Send.")

                if _send_clicked and user_q:
                    ss.last_ai_status = "calling"
                    with st.spinner("Calling OpenAI via LD AI Config..."):
                        try:
                            # 30-second timeout so a hang doesn't leave us
                            # stuck in "calling" state forever.
                            oai = openai.OpenAI(api_key=OPENAI_API_KEY, timeout=30.0)

                            # ── Build the default config defensively. The LD AI SDK
                            # has reshuffled both the import path AND the
                            # AIConfig constructor signature across releases.
                            # Strategy: probe imports → try several constructor
                            # signatures → fall back to a dict shim that supports
                            # attribute access, item access, and to_dict().
                            _AIConfig = _ModelConfig = None
                            for _path in ("ldai.types", "ldai.client.types",
                                          "ldai", "ldai.client"):
                                try:
                                    _mod = __import__(_path, fromlist=["AIConfig","ModelConfig"])
                                    _a = getattr(_mod, "AIConfig", None)
                                    _m = getattr(_mod, "ModelConfig", None)
                                    if _a and _m:
                                        _AIConfig, _ModelConfig = _a, _m
                                        break
                                except ImportError:
                                    continue

                            fallback = None
                            if _AIConfig and _ModelConfig:
                                _model_obj = None
                                for _make in (
                                    lambda: _ModelConfig(name="gpt-4o-mini"),
                                    lambda: _ModelConfig("gpt-4o-mini"),
                                ):
                                    try:
                                        _model_obj = _make()
                                        break
                                    except TypeError:
                                        continue

                                if _model_obj is not None:
                                    for _make in (
                                        lambda: _AIConfig(enabled=False, model=_model_obj, messages=[]),
                                        lambda: _AIConfig(enabled=False, model=_model_obj, prompt=[]),
                                        lambda: _AIConfig(enabled=False, model=_model_obj),
                                        lambda: _AIConfig(model=_model_obj, enabled=False),
                                        lambda: _AIConfig(enabled=False),
                                    ):
                                        try:
                                            fallback = _make()
                                            break
                                        except TypeError:
                                            continue

                            if fallback is None:
                                # Could not import or construct the typed class —
                                # use a dict subclass that quacks like AIConfig.
                                class _AIDict(dict):
                                    def __getattr__(self, name):
                                        try:
                                            return self[name]
                                        except KeyError:
                                            raise AttributeError(name)
                                    def to_dict(self):
                                        def _conv(v):
                                            if hasattr(v, "to_dict"): return v.to_dict()
                                            if isinstance(v, list):    return [_conv(i) for i in v]
                                            if isinstance(v, dict):    return {k:_conv(x) for k,x in v.items()}
                                            return v
                                        return {k:_conv(v) for k,v in self.items()}

                                fallback = _AIDict(
                                    enabled=False,
                                    model=_AIDict(name="gpt-4o-mini"),
                                    messages=[],
                                    _ldMeta=_AIDict(enabled=False),
                                )

                            # Call positionally so we don't depend on the kwarg name
                            # (it has been `default_value` / `default_config` across versions).
                            _result = ai.config(
                                AI_CONFIG_KEY,
                                context,
                                fallback,
                                {"user_question": user_q},
                            )

                            # SDK return shape varies by version:
                            #   older → tuple (AIConfig, AIConfigTracker)
                            #   newer → single AICompletionConfig with .tracker attr
                            if isinstance(_result, tuple) and len(_result) == 2:
                                ai_config, tracker = _result
                            else:
                                ai_config = _result
                                tracker = (
                                    getattr(_result, "tracker", None)
                                    or getattr(_result, "_tracker", None)
                                )

                            # ── Normalise the response — supports both AIConfig object
                            # (newer SDK) and dict (older SDK) return shapes.
                            def _get(o, attr, key, default=None):
                                if hasattr(o, attr):
                                    return getattr(o, attr)
                                if isinstance(o, dict):
                                    return o.get(key, default)
                                return default

                            enabled = (
                                _get(ai_config, "enabled", "enabled", None)
                                if hasattr(ai_config, "enabled")
                                else (ai_config.get("_ldMeta", {}) or {}).get("enabled", False)
                                     if isinstance(ai_config, dict) else False
                            )
                            model_field = _get(ai_config, "model", "model", "gpt-4o-mini")
                            ld_messages = _get(ai_config, "messages", "messages", []) or []

                            # `model` may be a ModelConfig object, a dict, or a plain string.
                            if hasattr(model_field, "name"):
                                model_used = model_field.name
                            elif isinstance(model_field, dict):
                                model_used = model_field.get("name", "gpt-4o-mini")
                            else:
                                model_used = model_field

                            # Each message may be an LDMessage object or a dict — normalise.
                            def _msg(m):
                                if isinstance(m, dict):
                                    return m.get("role"), m.get("content")
                                return getattr(m, "role", None), getattr(m, "content", None)

                            # ── Build the OpenAI messages array.
                            # OpenAI takes system/user/assistant messages natively, so
                            # we keep the LD-managed messages as-is and append the new
                            # user turn at the end.
                            if enabled:
                                messages, has_system = [], False
                                for m in ld_messages:
                                    role, content = _msg(m)
                                    if role in ("system","user","assistant") and content:
                                        messages.append({"role": role, "content": content})
                                        if role == "system":
                                            has_system = True
                                if not has_system:
                                    messages.insert(0, {"role":"system","content":"You are a helpful support assistant."})
                                messages.append({"role":"user","content":user_q})
                            else:
                                messages = [
                                    {"role":"system","content":"You are a concise support assistant. Keep answers under 3 sentences."},
                                    {"role":"user","content":user_q},
                                ]

                            # ── Detect reasoning models (o1 / o3 / gpt-5 family).
                            # They spend tokens on internal reasoning BEFORE
                            # producing any output text. A 300-token budget
                            # gets entirely consumed by reasoning → empty
                            # response. Bump to 4000 for reasoning models.
                            _reasoning_prefixes = ("o1", "o3", "gpt-5")
                            _is_reasoning = any(
                                model_used.lower().startswith(p)
                                for p in _reasoning_prefixes
                            )
                            _token_budget = 4000 if _is_reasoning else 300

                            # ── The actual OpenAI call.
                            # OpenAI deprecated `max_tokens` in favour of
                            # `max_completion_tokens` for newer models
                            # (gpt-4o family, o1, gpt-5, etc.). Older models
                            # like gpt-3.5-turbo still expect `max_tokens`.
                            # Try the new name first; fall back if the model
                            # rejects it.
                            t0 = time.time()
                            try:
                                resp = oai.chat.completions.create(
                                    model=model_used,
                                    messages=messages,
                                    max_completion_tokens=_token_budget,
                                )
                            except Exception as _e:
                                if "max_completion_tokens" in str(_e).lower():
                                    resp = oai.chat.completions.create(
                                        model=model_used,
                                        messages=messages,
                                        max_tokens=_token_budget,
                                    )
                                else:
                                    raise
                            lat = int((time.time() - t0) * 1000)

                            # ── Feed metrics back to LD for AI experimentation.
                            # The LD AI tracker expects token usage in a
                            # different shape than what OpenAI returns:
                            #   OpenAI:  total_tokens / prompt_tokens / completion_tokens
                            #   LD AI:   total / input / output
                            # The shim below provides BOTH naming conventions
                            # so the tracker can pick whichever it needs.
                            # We also try the official LD TokenUsage type first
                            # in case the SDK does an isinstance check.
                            _usage_obj = None
                            try:
                                from ldai.types import TokenUsage as _TokenUsage
                                _usage_obj = _TokenUsage(
                                    total=resp.usage.total_tokens,
                                    input=resp.usage.prompt_tokens,
                                    output=resp.usage.completion_tokens,
                                )
                            except (ImportError, TypeError):
                                pass
                            if _usage_obj is None:
                                _usage_obj = SimpleNamespace(
                                    # LD AI shape
                                    total=resp.usage.total_tokens,
                                    input=resp.usage.prompt_tokens,
                                    output=resp.usage.completion_tokens,
                                    # OpenAI shape (kept for compatibility)
                                    total_tokens=resp.usage.total_tokens,
                                    prompt_tokens=resp.usage.prompt_tokens,
                                    completion_tokens=resp.usage.completion_tokens,
                                )

                            # Capture any tracker errors so we can see them in the
                            # diagnostic expander (otherwise they'd be invisible).
                            _tracker_errors = []
                            for _name, _fn in [
                                ("track_duration", lambda: tracker.track_duration(lat)),
                                ("track_tokens",   lambda: tracker.track_tokens(_usage_obj)),
                                ("track_success",  lambda: tracker.track_success()),
                            ]:
                                try:
                                    _fn()
                                except Exception as _te:
                                    _tracker_errors.append(f"{_name}: {type(_te).__name__}: {_te}")
                            # Force-flush so events reach LD immediately,
                            # not on the next 5-second batch interval.
                            try:
                                ld.flush()
                            except Exception as _fe:
                                _tracker_errors.append(f"flush: {type(_fe).__name__}: {_fe}")
                            ss.last_ai_tracker_errors = _tracker_errors

                            # ── Persist the response in session state so it
                            # survives the autorefresh-driven script reruns.
                            # Without this, the answer would render once and
                            # vanish on the next 1.5s rerun (when the button
                            # is no longer in its "just-clicked" state).
                            ss.last_ai_response = {
                                "model":   model_used,
                                "answer":  resp.choices[0].message.content or "(empty response from model)",
                                "tokens":  resp.usage.total_tokens,
                                "latency": lat,
                                "question": user_q,
                            }
                            ss.last_ai_error  = None
                            ss.last_ai_status = "success"
                        except BaseException as e:
                            # BaseException (vs Exception) catches things like
                            # KeyboardInterrupt / SystemExit / GeneratorExit
                            # that Streamlit's framework can sometimes raise
                            # when reruns are scheduled mid-call.
                            import traceback
                            ss.last_ai_error    = f"{type(e).__name__}: {e}"
                            ss.last_ai_trace    = traceback.format_exc()
                            ss.last_ai_response = None
                            ss.last_ai_status   = "error"

            # ── Render the latest response (or error) from session state,
            # so it stays visible across autorefresh-triggered reruns.
            if ss.last_ai_error:
                st.error(f"AI error: {ss.last_ai_error}")
                with st.expander("Show full traceback"):
                    st.code(ss.get("last_ai_trace", "(no traceback captured)"), language="python")
            elif ss.last_ai_response:
                r = ss.last_ai_response
                # Chat-style layout — user bubble + bot bubble with avatars
                st.markdown(f"""
                <div class="chat-row user-row">
                    <div class="chat-avatar user">👤</div>
                    <div class="chat-bubble user">{r['question']}</div>
                </div>
                <div class="chat-row">
                    <div class="chat-avatar bot">🤖</div>
                    <div>
                        <div class="chat-bubble bot">{r['answer']}</div>
                        <div class="chat-meta">
                            🤖 AI Coach · model <b>{r['model']}</b> · {r['tokens']} tokens · {r['latency']} ms · metrics → LD
                        </div>
                    </div>
                </div>
                """, unsafe_allow_html=True)
                st.markdown("<div style='margin-top:18px;'></div>", unsafe_allow_html=True)
                m1, m2, m3 = st.columns(3)
                m1.metric("Model",   r["model"])
                m2.metric("Tokens",  r["tokens"])
                m3.metric("Latency", f"{r['latency']}ms")

            # ── Diagnostic expander — collapsed by default; lets us see
            # exactly what's in session state without breaking the demo
            # flow if everything works.
            with st.expander("🔍 Diagnostic info", expanded=False):
                _tracker_errs = ss.get("last_ai_tracker_errors", [])
                st.write({
                    "status": ss.get("last_ai_status", "(no request made yet)"),
                    "has_response": ss.last_ai_response is not None,
                    "has_error":    ss.last_ai_error is not None,
                    "openai_key_present":     bool(OPENAI_API_KEY),
                    "ai_client_initialised":  ai is not None,
                    "user_question_in_box":   user_q or "(empty)",
                    "tracker_calls_ok":       len(_tracker_errs) == 0,
                    "tracker_errors":         _tracker_errs or "(none)",
                })
                st.caption(
                    "If `tracker_calls_ok` is true but you don't see metrics in "
                    "the LD AI Config dashboard, wait 1-2 minutes — LD batches "
                    "events. Look in the AI Config's **Monitoring** tab, not the "
                    "main flag page."
                )

            st.markdown("""
            <div class="mono" style='margin-top:14px;'>
<span style='color:#94a3b8;'># AI Config — same pattern as feature flags, plus metric tracking:</span><br/>
ai_config, tracker = ai.config(<br/>
&nbsp;&nbsp;<span style='color:#fbbf24;'>"support-assistant"</span>, context, fallback,<br/>
&nbsp;&nbsp;{<span style='color:#fbbf24;'>"user_question"</span>: user_q})<br/>
<br/>
<span style='color:#94a3b8;'># Model + prompt come from LD — not from this code:</span><br/>
resp = oai.chat.completions.create(<br/>
&nbsp;&nbsp;model=ai_config.model.name,<br/>
&nbsp;&nbsp;messages=ai_config.messages + [user_turn])<br/>
<br/>
<span style='color:#94a3b8;'># Metrics flow back to LD per variation:</span><br/>
tracker.track_duration(latency_ms)<br/>
tracker.track_tokens(resp.usage)<br/>
tracker.track_success()
            </div>
            """, unsafe_allow_html=True)

        with col_a2:
            st.markdown("""<div class="card"><div style='font-size:10px;font-weight:700;color:#94a3b8;letter-spacing:.1em;text-transform:uppercase;font-family:"JetBrains Mono",monospace;margin-bottom:14px;'>What AI Configs control</div>""", unsafe_allow_html=True)
            for icon, title, desc in [
                ("🧠","Model selection",  "GPT-4o for enterprise, GPT-4o-mini for free — targeting rule, no code"),
                ("📝","System prompt",    "Rewrite the assistant's persona from the LD dashboard instantly"),
                ("🌡️","Temperature",      "Adjust creativity per user segment, no deployment"),
                ("💰","Cost control",     "Route to cheaper models for non-paying users automatically"),
                ("⚡","Instant rollback", "Bad prompt in prod? Roll back the variation in the LD UI"),
                ("📊","Monitoring",       "Token usage, latency, cost tracked per variation in real time"),
            ]:
                st.markdown(f"""
                <div style='display:flex;gap:10px;margin-bottom:12px;align-items:flex-start;'>
                    <div style='font-size:16px;flex-shrink:0;'>{icon}</div>
                    <div>
                        <div style='font-size:12px;font-weight:600;color:#c7d2fe;'>{title}</div>
                        <div style='font-size:11px;color:#94a3b8;line-height:1.4;margin-top:2px;'>{desc}</div>
                    </div>
                </div>
                """, unsafe_allow_html=True)
            st.markdown(f"""
                <div style='background:#0e0820;border:1px solid #3730a322;border-radius:8px;padding:12px 14px;margin-top:6px;'>
                    <div style='font-size:12px;color:#818cf8;line-height:1.6;'>
                        <strong>Setup in LD:</strong> Create → AI Configs →
                        name it <code>{AI_CONFIG_KEY}</code> → two variations:<br/>
                        Enterprise: <code>gpt-4o</code>, detailed prompt<br/>
                        Free: <code>gpt-4o-mini</code>, concise prompt<br/>
                        Rule: IF tier = enterprise → enterprise variation
                    </div>
                </div>
            </div>
            """, unsafe_allow_html=True)


# ──────────────────────────────────────────────────────────────────────────
# FLAG INSPECTOR
# ──────────────────────────────────────────────────────────────────────────
with tab4:
    st.markdown('<div class="chip">📊 ADMIN · Flag evaluations · Live SDK change log</div>', unsafe_allow_html=True)
    col_f, col_c = st.columns(2)

    with col_f:
        st.markdown('<div style="font-size:12px;font-weight:600;color:#94a3b8;margin-bottom:12px;">Flag evaluation results</div>', unsafe_allow_html=True)
        for fkey, val, ftype, part in [
            (FLAG_HERO,     show_hero,         "Boolean","Part 1"),
            (FLAG_CHECKOUT, show_checkout,     "Boolean","Part 2 + Experiment"),
            (FLAG_BANNER,   bool(banner_text), "String", "Part 2"),
        ]:
            pill = "pill-on" if val else "pill-off"
            dot  = "dot-on"  if val else "dot-off"
            lbl  = "TRUE"    if val else "FALSE"
            st.markdown(f"""
            <div style='background:#0a0a18;border:1px solid #1a1a2e;border-radius:10px;
                        padding:14px 16px;margin-bottom:8px;
                        display:flex;align-items:center;justify-content:space-between;'>
                <div>
                    <div style='font-size:13px;font-family:"JetBrains Mono",monospace;color:#818cf8;margin-bottom:3px;'>{fkey}</div>
                    <div style='font-size:11px;color:#64748b;'>{ftype} · {part}</div>
                </div>
                <div class="{pill}"><span class="{dot}"></span>{lbl}</div>
            </div>
            """, unsafe_allow_html=True)
        if banner_text:
            st.markdown(f"""
            <div style='background:#0a0a18;border:1px solid #1a1a2e;border-radius:10px;padding:14px 16px;'>
                <div style='font-size:11px;color:#64748b;margin-bottom:4px;font-family:"JetBrains Mono",monospace;'>{FLAG_BANNER} value:</div>
                <div style='font-size:13px;color:#4ade80;font-family:"JetBrains Mono",monospace;'>"{banner_text}"</div>
            </div>
            """, unsafe_allow_html=True)

    with col_c:
        st.markdown('<div style="font-size:12px;font-weight:600;color:#94a3b8;margin-bottom:12px;">Context passed to LaunchDarkly</div>', unsafe_allow_html=True)
        st.json({"kind":"user","key":user_key,"name":user_key.capitalize(),
                 "tier":user_tier,"country":user_country,
                 "betaTester":user_beta,"deviceType":user_device})

    # ── Live SDK change log (from the flag_tracker listener) ─────────────
    st.divider()
    st.markdown('<div style="font-size:12px;font-weight:600;color:#94a3b8;margin-bottom:12px;">⚡ Live SDK change log · powered by ld.flag_tracker.add_listener()</div>', unsafe_allow_html=True)
    with _change_lock:
        events = list(_change_log)
    if not events:
        st.markdown(
            '<div class="changelog">No flag changes detected yet. '
            'Toggle a flag in LD — it appears here within milliseconds.</div>',
            unsafe_allow_html=True
        )
    else:
        for e in events:
            st.markdown(
                f'<div class="changelog">'
                f'<span style="color:#4ade80;">●</span>&nbsp; '
                f'<b>{e["ts"]}</b> &nbsp;·&nbsp; flag <b>{e["flag"]}</b> rules updated'
                f'</div>',
                unsafe_allow_html=True
            )

    st.divider()
    st.markdown("""
    <div class="mono">
<span style='color:#94a3b8;'># SDK mechanics — what happens under the hood:</span><br/>
<span style='color:#94a3b8;'># 1. SDK connects and downloads ALL flag rules into memory at startup</span><br/>
<span style='color:#94a3b8;'># 2. Each ld.variation() call evaluates rules locally — no network call, &lt;5ms</span><br/>
<span style='color:#94a3b8;'># 3. When a flag changes in LD dashboard, SDK receives the update via</span><br/>
<span style='color:#94a3b8;'>#    a persistent Server-Sent Events stream — instantly, no polling</span><br/>
<span style='color:#94a3b8;'># 4. flag_tracker.add_listener() callbacks fire on a background thread</span><br/>
<span style='color:#94a3b8;'># 5. Next evaluation immediately uses the new rule</span>
    </div>
    """, unsafe_allow_html=True)
