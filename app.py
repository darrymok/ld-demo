
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
    import requests
    from types import SimpleNamespace
    AI_AVAILABLE = True
except ImportError:
    AI_AVAILABLE = False

# ══════════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ← Set LD_SDK_KEY as an env var or replace the string below directly
# ══════════════════════════════════════════════════════════════════════════
LD_SDK_KEY          = os.environ.get("LD_SDK_KEY", "YOUR_SDK_KEY_HERE")  # ← REPLACE
PLURALSIGHT_API_KEY = os.environ.get("PLURALSIGHT_API_KEY", "")          # ← Pluralsight Sandbox token

# ─── Pluralsight AI Sandbox — model slug → endpoint URL ────────────────────
# In your LD AI Config, set the `model` field to one of the keys below.
# Swapping a user from Claude → GPT-4o → Gemini is then a one-click change
# in the LD dashboard, no code redeploy.
PLURALSIGHT_ENDPOINTS = {
    # Anthropic family (via Bedrock)
    "claude-45-opus":      "https://labs.pluralsight.com/labs-ai-proxy/rest/bedrock/anthropic/claude-45-opus",
    "claude-45-sonnet":    "https://labs.pluralsight.com/labs-ai-proxy/rest/bedrock/anthropic/claude-45-sonnet",
    "claude-4-sonnet":     "https://labs.pluralsight.com/labs-ai-proxy/rest/bedrock/anthropic/claude-4-sonnet",
    "claude-45-haiku":     "https://labs.pluralsight.com/labs-ai-proxy/rest/bedrock/anthropic/claude-45-haiku",
    # OpenAI family (via Azure)
    "chatgpt-4o":          "https://labs.pluralsight.com/labs-ai-proxy/rest/openai/chatgpt-4o/v1/chat/completions",
    "chatgpt-5-mini":      "https://labs.pluralsight.com/labs-ai-proxy/rest/openai/chatgpt-5/v1/chat/completions",
    # Google family
    "gemini-25-flash":     "https://labs.pluralsight.com/labs-ai-proxy/rest/gemini/Flash-25",
    "gemini-25-flash-lite":"https://labs.pluralsight.com/labs-ai-proxy/rest/gemini/Flash-Lite-25",
    # Others (Bedrock-routed)
    "cohere-command-r":    "https://labs.pluralsight.com/labs-ai-proxy/rest/bedrock/cohere/command-text-r",
    "jamba-mini":          "https://labs.pluralsight.com/labs-ai-proxy/rest/bedrock/ai21/jamba-mini",
    "llama-3-8b":          "https://labs.pluralsight.com/labs-ai-proxy/rest/bedrock/meta/llama2-13b-chat-v1",
    "llama-33-70b":        "https://labs.pluralsight.com/labs-ai-proxy/rest/bedrock/meta/llama-33",
    "mistral-large-3":     "https://labs.pluralsight.com/labs-ai-proxy/rest/bedrock/mistral-ai/mistral-large-3",
    "mistral-small":       "https://labs.pluralsight.com/labs-ai-proxy/rest/bedrock/mistral-ai/mistral-small",
    "amazon-nova-2-lite":  "https://labs.pluralsight.com/labs-ai-proxy/rest/bedrock/amazon/nova-2-lite",
}
PLURALSIGHT_DEFAULT_SLUG = "claude-4-sonnet"   # only slug with a verified working example in the docs

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
    if AI_AVAILABLE and PLURALSIGHT_API_KEY:
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

/* ── Architecture tab — topology diagrams + comparison tables ── */
.topology       { display:flex;flex-direction:column;align-items:center;
                  background:#070710;border:1px solid #1a1a30;border-radius:14px;
                  padding:24px;margin:12px 0; }
.topology-row   { display:flex;gap:10px;justify-content:center;flex-wrap:wrap;width:100%; }
.topology-node  { background:#0f0f24;border:1px solid #2d2d50;border-radius:10px;
                  padding:12px 18px;font-size:12px;color:#c7d2fe;
                  font-family:'JetBrains Mono',monospace;text-align:center;min-width:90px; }
.topology-node.ld    { background:linear-gradient(135deg,#1a1060,#3730a3);
                       border-color:#6366f1;color:white;font-weight:700;
                       padding:14px 28px;font-size:14px; }
.topology-node.relay { background:#0d2918;border-color:#22c55e;color:#86efac;font-weight:700; }
.topology-label { color:#64748b;font-size:11px;font-family:'JetBrains Mono',monospace;margin:8px 0; }

.compare-table        { width:100%;border-collapse:separate;border-spacing:0;
                        background:#0a0a18;border:1px solid #1a1a30;border-radius:10px;
                        overflow:hidden;font-size:13px;margin-top:6px; }
.compare-table th     { background:#0c0c1e;color:#a5b4fc;font-family:'JetBrains Mono',monospace;
                        font-size:11px;text-transform:uppercase;letter-spacing:.08em;
                        padding:10px 14px;text-align:left;border-bottom:1px solid #1a1a30; }
.compare-table td     { padding:10px 14px;color:#cbd5e1;border-bottom:1px solid #1a1a30; }
.compare-table tr:last-child td { border-bottom:none; }
.compare-table td.attr{ color:#94a3b8;font-family:'JetBrains Mono',monospace;
                        font-size:12px;width:30%; }
</style>
""", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════
# SESSION STATE — for change detection & experiment counters
# ══════════════════════════════════════════════════════════════════════════
ss = st.session_state
ss.setdefault("prev_flags",   {})
ss.setdefault("flash_until",  0.0)
ss.setdefault("conv_events",  0)
ss.setdefault("kill_until",   0.0)
ss.setdefault("session_id",   str(uuid.uuid4())[:8])

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
    if auto_refresh and HAS_AUTOREFRESH:
        st_autorefresh(interval=1500, key="ld_autorefresh")
        st.markdown(
            '<div style="font-size:11px;color:#4ade80;font-family:\'JetBrains Mono\',monospace;'
            'line-height:1.7;">'
            '<span class="dot-live"></span>&nbsp;Listening for flag changes<br/>'
            'SDK stream + 1.5s poll<br/>'
            'Toggle a flag in LD →<br/>watch the UI react.</div>',
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
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "⚡ Part 1 — Release & Remediate",
    "🎯 Part 2 — Target",
    "🧪 Part 3 — Bonus",
    "🔍 Flag Inspector",
    "🏗️ Architecture",
])

# ──────────────────────────────────────────────────────────────────────────
# PART 1 — RELEASE & REMEDIATE
# ──────────────────────────────────────────────────────────────────────────
with tab1:
    st.markdown('<div class="chip">⚡ PART 1 · RELEASE & REMEDIATE · Flag: new-hero-banner</div>', unsafe_allow_html=True)

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

    # ── REMEDIATE via TRIGGER ─────────────────────────────────────────────
    st.divider()
    st.markdown('<div class="chip">🔧 REMEDIATE · Trigger — disable without code change or redeploy</div>', unsafe_allow_html=True)
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
    st.markdown('<div class="chip">🎯 PART 2 · TARGET · Flag: checkout-redesign</div>', unsafe_allow_html=True)

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
# PART 3 — BONUS (Experimentation · AI Configs · Integrations)
# ──────────────────────────────────────────────────────────────────────────
with tab3:
    exp_tab, ai_tab, int_tab = st.tabs([
        "Option A — Experimentation",
        "Option B — AI Configs",
        "Integrations",
    ])

    # ── EXPERIMENTATION ──────────────────────────────────────────────────
    with exp_tab:
        st.markdown('<div class="chip">🧪 EXPERIMENTATION · Measure conversion impact with statistical significance</div>', unsafe_allow_html=True)
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
        st.markdown('<div class="chip">🤖 AI CONFIGS · LLM governance — swap models and prompts without redeploying</div>', unsafe_allow_html=True)
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
                    {"<strong style='color:#4ade80;'>claude-4-sonnet (enterprise variation)</strong>" if user_tier == "enterprise"
                     else "<strong style='color:#64748b;'>chatgpt-4o (standard variation)</strong>"}
                </div>
            </div>
            """, unsafe_allow_html=True)

            if not AI_AVAILABLE:
                st.warning("AI SDK not installed. Run: `pip install launchdarkly-server-sdk-ai requests`")
            elif not PLURALSIGHT_API_KEY:
                st.warning("Set `PLURALSIGHT_API_KEY` environment variable to enable the live AI demo.")
            else:
                user_q = st.text_input("Ask the assistant:", placeholder="e.g. How do I add a team member?")
                if st.button("Send →") and user_q:
                    with st.spinner("Calling AI via LD AI Config → Pluralsight Sandbox..."):
                        try:
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
                                # Build a model object — try kwarg, fall back to positional
                                _model_obj = None
                                for _make in (
                                    lambda: _ModelConfig(name=PLURALSIGHT_DEFAULT_SLUG),
                                    lambda: _ModelConfig(PLURALSIGHT_DEFAULT_SLUG),
                                ):
                                    try:
                                        _model_obj = _make()
                                        break
                                    except TypeError:
                                        continue

                                if _model_obj is not None:
                                    # Try a handful of known AIConfig signatures.
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
                                    model=_AIDict(name=PLURALSIGHT_DEFAULT_SLUG),
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
                            model_field = _get(ai_config, "model", "model", PLURALSIGHT_DEFAULT_SLUG)
                            ld_messages = _get(ai_config, "messages", "messages", []) or []

                            # `model` may be a ModelConfig object, a dict, or a plain string.
                            if hasattr(model_field, "name"):
                                model_slug = model_field.name
                            elif isinstance(model_field, dict):
                                model_slug = model_field.get("name", PLURALSIGHT_DEFAULT_SLUG)
                            else:
                                model_slug = model_field

                            # Resolve the Pluralsight endpoint URL for this slug.
                            endpoint = PLURALSIGHT_ENDPOINTS.get(
                                model_slug, PLURALSIGHT_ENDPOINTS[PLURALSIGHT_DEFAULT_SLUG]
                            )

                            # Each message may be an LDMessage object or a dict — normalise.
                            def _msg(m):
                                if isinstance(m, dict):
                                    return m.get("role"), m.get("content")
                                return getattr(m, "role", None), getattr(m, "content", None)

                            # ── Flatten LD-managed messages into a single prompt string
                            # (Pluralsight Sandbox takes `{"prompt": "..."}`, not a
                            # structured messages array).
                            if enabled:
                                system_prompt = "You are a helpful support assistant."
                                prior_turns = []
                                for m in ld_messages:
                                    role, content = _msg(m)
                                    if role == "system":
                                        system_prompt = content or system_prompt
                                    elif role in ("user","assistant"):
                                        prior_turns.append(f"{role.capitalize()}: {content}")
                                blocks = [f"[System]\n{system_prompt}"]
                                if prior_turns:
                                    blocks.append("[Prior conversation]\n" + "\n".join(prior_turns))
                                blocks.append(f"[User question]\n{user_q}")
                                prompt_text = "\n\n".join(blocks)
                            else:
                                system_prompt = "You are a concise support assistant. Keep answers under 3 sentences."
                                prompt_text = f"[System]\n{system_prompt}\n\n[User question]\n{user_q}"

                            # ── The actual HTTP call to the Pluralsight Sandbox.
                            t0 = time.time()
                            r = requests.post(
                                endpoint,
                                headers={
                                    "Authorization": f"Bearer {PLURALSIGHT_API_KEY}",
                                    "Content-Type":  "application/json",
                                },
                                json={"prompt": prompt_text},
                                timeout=60,
                            )
                            lat = int((time.time() - t0) * 1000)
                            r.raise_for_status()
                            data = r.json()

                            # ── Parse — Pluralsight returns two possible shapes:
                            #   OpenAI-routed:  {"message": {"role":"assistant","content":"..."}, "inputTokens": N, ...}
                            #   Claude-routed:  {"message": "...string..."}
                            msg_field = data.get("message")
                            if isinstance(msg_field, dict):
                                answer_text = msg_field.get("content", "") or ""
                            elif isinstance(msg_field, str):
                                answer_text = msg_field
                            else:
                                answer_text = str(msg_field) if msg_field is not None else "(empty response)"

                            in_tok  = int(data.get("inputTokens", 0)  or 0)
                            out_tok = int(data.get("outputTokens", 0) or 0)
                            cost    = float(data.get("cost", 0)       or 0)
                            total_tokens = in_tok + out_tok

                            # ── Feed metrics back to LD for AI experimentation.
                            # LD AI tracker expects OpenAI-shaped token fields — shim it.
                            try:
                                usage_shim = SimpleNamespace(
                                    prompt_tokens     = in_tok,
                                    completion_tokens = out_tok,
                                    total_tokens      = total_tokens,
                                )
                                tracker.track_duration(lat)
                                tracker.track_tokens(usage_shim)
                                tracker.track_success()
                            except Exception:
                                pass

                            st.markdown(f"""
                            <div class="card" style='margin-bottom:10px;'>
                                <div style='font-size:10px;color:#64748b;font-family:"JetBrains Mono",monospace;margin-bottom:8px;'>
                                    model: {model_slug} · via Pluralsight Sandbox · metrics → LD</div>
                                <div style='font-size:14px;color:#c7d2fe;line-height:1.7;white-space:pre-wrap;'>{answer_text}</div>
                            </div>
                            """, unsafe_allow_html=True)
                            m1,m2,m3,m4 = st.columns(4)
                            m1.metric("Model",   model_slug)
                            m2.metric("Tokens",  total_tokens if total_tokens else "—")
                            m3.metric("Latency", f"{lat}ms")
                            m4.metric("Cost",    f"${cost:.4f}" if cost else "—")
                        except requests.HTTPError as e:
                            code = e.response.status_code
                            if code == 404:
                                st.error(
                                    f"HTTP 404 — the Pluralsight endpoint for `{model_slug}` "
                                    f"isn't mounted in your sandbox. Try a different model slug in "
                                    f"the LD AI Config. **`claude-4-sonnet` is the only slug with "
                                    f"a verified working example in the docs.** Other safe bets: "
                                    f"`chatgpt-4o`, `gemini-25-flash`."
                                )
                                st.caption(f"Endpoint that returned 404: `{endpoint}`")
                            elif code in (401, 403):
                                st.error(f"HTTP {code} — `PLURALSIGHT_API_KEY` is missing, expired, or unauthorized for this model.")
                            else:
                                st.error(f"HTTP {code} from Pluralsight: {e.response.text[:300]}")
                        except Exception as e:
                            st.error(f"AI error: {e}")

            st.markdown("""
            <div class="mono" style='margin-top:14px;'>
<span style='color:#94a3b8;'># AI Config — LD returns the model slug; we map → Pluralsight URL:</span><br/>
ai_config, tracker = ai.config(<br/>
&nbsp;&nbsp;<span style='color:#fbbf24;'>"support-assistant"</span>, context, fallback,<br/>
&nbsp;&nbsp;{<span style='color:#fbbf24;'>"user_question"</span>: user_q}<br/>
)<br/>
model_slug = ai_config.model.name                <span style='color:#94a3b8;'># e.g. "claude-45-sonnet"</span><br/>
endpoint   = PLURALSIGHT_ENDPOINTS[model_slug]<br/>
<br/>
<span style='color:#94a3b8;'># Single HTTP POST — Pluralsight handles the provider routing:</span><br/>
r = requests.post(endpoint,<br/>
&nbsp;&nbsp;headers={<span style='color:#fbbf24;'>"Authorization"</span>: <span style='color:#fbbf24;'>f"Bearer {PLURALSIGHT_API_KEY}"</span>},<br/>
&nbsp;&nbsp;json={<span style='color:#fbbf24;'>"prompt"</span>: prompt_text})<br/>
<br/>
<span style='color:#94a3b8;'># Metrics flow back to LD per variation:</span><br/>
tracker.track_duration(latency_ms)<br/>
tracker.track_tokens(usage_shim)<br/>
tracker.track_success()
            </div>
            """, unsafe_allow_html=True)

        with col_a2:
            st.markdown("""<div class="card"><div style='font-size:10px;font-weight:700;color:#94a3b8;letter-spacing:.1em;text-transform:uppercase;font-family:"JetBrains Mono",monospace;margin-bottom:14px;'>What AI Configs control</div>""", unsafe_allow_html=True)
            for icon, title, desc in [
                ("🧠","Model selection",  "Cross-provider routing — Claude for one tier, GPT-4o or Gemini for another — one click in LD"),
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
                        Enterprise: <code>claude-4-sonnet</code>, detailed prompt<br/>
                        Free: <code>chatgpt-4o</code>, concise prompt<br/>
                        Rule: IF tier = enterprise → enterprise variation<br/>
                        <em style='color:#64748b;'>404? That slug isn't provisioned in your sandbox — try another.</em>
                    </div>
                </div>
            </div>
            """, unsafe_allow_html=True)

    # ── INTEGRATIONS ─────────────────────────────────────────────────────
    with int_tab:
        st.markdown('<div class="chip">🔌 INTEGRATIONS · Where LaunchDarkly fits in your existing stack</div>', unsafe_allow_html=True)
        st.markdown("""
        <div class="card-accent" style='margin-bottom:14px;'>
            <div style='font-size:14px;color:#94a3b8;line-height:1.7;'>
                LaunchDarkly doesn't live in a silo — every flag change can fan out to
                the tools your team already runs in. The result: release decisions and
                incident response stay inside the workflows engineers already trust.
            </div>
        </div>
        """, unsafe_allow_html=True)

        i1, i2, i3 = st.columns(3)
        for col, icon, name, items in [
            (i1, "💬", "Slack", [
                "Flag-change notifications → #releases channel",
                "Slash-command approvals for risky flags",
                "On-call ping the moment a kill-switch fires",
            ]),
            (i2, "🎫", "Jira", [
                "Auto-create rollback tickets when a flag is killed",
                "Link experiment results to the originating story",
                "Cleanup workflow for stale / archived flags",
            ]),
            (i3, "📈", "Datadog / New Relic", [
                "Annotate dashboards on every release",
                "Auto-fire flag-off when SLO breaches",
                "Correlate error spikes to specific variations",
            ]),
        ]:
            with col:
                items_html = "".join(
                    f"<div style='font-size:12px;color:#64748b;line-height:1.7;margin-bottom:6px;'>"
                    f"<span style='color:#4ade80;'>•</span>&nbsp;{x}</div>"
                    for x in items
                )
                st.markdown(f"""
                <div class="card" style='height:100%;'>
                    <div style='font-size:24px;margin-bottom:8px;'>{icon}</div>
                    <div style='font-size:14px;font-weight:700;color:#c7d2fe;margin-bottom:10px;'>{name}</div>
                    {items_html}
                </div>
                """, unsafe_allow_html=True)

        st.markdown('<div class="chip" style="margin-top:18px;">🔄 THE COMPLETE LOOP · Release-and-remediate without leaving Slack</div>', unsafe_allow_html=True)
        for n, color, title, desc in [
            ("1","#818cf8","Engineer ships code",      "Flag still OFF — zero customer impact."),
            ("2","#4ade80","Engineer toggles flag ON", "Slack #releases auto-announces with audit trail."),
            ("3","#f59e0b","Datadog detects error spike", "Webhook fires the LD trigger URL automatically."),
            ("4","#ef4444","Flag flips OFF instantly",   "Jira ticket auto-opens. Customers unaffected."),
            ("5","#a78bfa","Engineer iterates + ships fix", "Toggles flag ON again. Zero incident time recorded."),
        ]:
            st.markdown(f"""
            <div class="tl-item" style='margin-bottom:10px;'>
                <div class="tl-num" style='background:{color}18;border:1px solid {color}44;color:{color};'>{n}</div>
                <div>
                    <div class="tl-title">{title}</div>
                    <div class="tl-desc">{desc}</div>
                </div>
            </div>
            """, unsafe_allow_html=True)


# ──────────────────────────────────────────────────────────────────────────
# FLAG INSPECTOR
# ──────────────────────────────────────────────────────────────────────────
with tab4:
    st.markdown('<div class="chip">🔍 FLAG INSPECTOR · Live evaluation state + SDK change log</div>', unsafe_allow_html=True)
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


# ──────────────────────────────────────────────────────────────────────────
# ARCHITECTURE — Client vs Server SDKs · Microservices · Relay Proxy
# Conceptual tab that pre-answers the "but what about at scale?" question
# every VP of Engineering asks within 90 seconds of seeing the demo.
# ──────────────────────────────────────────────────────────────────────────
with tab5:
    st.markdown('<div class="chip">🏗️ ARCHITECTURE · How this scales beyond a single app</div>', unsafe_allow_html=True)

    arch_a, arch_b, arch_c = st.tabs([
        "SDKs · Client vs Server",
        "Microservices fan-out",
        "Relay Proxy",
    ])

    # ── Sub-tab A: Client-side vs Server-side SDKs ────────────────────
    with arch_a:
        st.markdown("""
        <div class="card-accent" style='margin-bottom:14px;'>
            <div style='font-size:13px;color:#cbd5e1;line-height:1.7;'>
                Same LaunchDarkly project, same flag definitions — but the SDK pattern
                changes depending on where the flag is evaluated.
                <strong>Server-side</strong> pulls all rules into process memory and
                evaluates locally; fast and secure, but rule definitions sit on the box.
                <strong>Client-side</strong> requests a single user's evaluated values
                from LD's edge — the browser bundle never sees rule names like
                <code style='color:#818cf8;'>"enterprise-pricing-rule"</code>.
            </div>
        </div>
        """, unsafe_allow_html=True)

        c1, c2 = st.columns(2)
        with c1:
            st.markdown("""
            <div class="card" style='height:100%;'>
                <div style='font-size:11px;color:#a5b4fc;letter-spacing:.1em;
                            text-transform:uppercase;font-family:"JetBrains Mono",monospace;
                            margin-bottom:8px;'>Server-side SDK</div>
                <div style='font-size:18px;font-weight:700;color:#e2e8f0;margin-bottom:8px;'>Backend services</div>
                <div style='font-size:12px;color:#cbd5e1;line-height:1.6;margin-bottom:12px;'>
                    Python, Java, Go, Node, .NET, Ruby. <strong>What this demo uses.</strong><br/><br/>
                    <strong>Auth:</strong> SDK Key — treated like a database password<br/>
                    <strong>Rules:</strong> all rules cached in process memory<br/>
                    <strong>Latency:</strong> &lt;5 ms per evaluation (in-memory)
                </div>
            </div>
            """, unsafe_allow_html=True)
            st.markdown("""
            <div class="mono" style='font-size:11px;margin-top:10px;'>
<span style='color:#94a3b8;'># Python — what this demo uses</span><br/>
ldclient.set_config(Config(<span style='color:#fbbf24;'>LD_SDK_KEY</span>))<br/>
ld = ldclient.get()<br/>
<br/>
context = Context.builder(<span style='color:#fbbf24;'>"alice"</span>)<br/>
&nbsp;&nbsp;.set(<span style='color:#a5b4fc;'>"tier"</span>, <span style='color:#fbbf24;'>"free"</span>).build()<br/>
<br/>
show = ld.variation(<br/>
&nbsp;&nbsp;<span style='color:#a5b4fc;'>"new-hero-banner"</span>, context, <span style='color:#f87171;'>False</span>)
            </div>
            """, unsafe_allow_html=True)

        with c2:
            st.markdown("""
            <div class="card" style='height:100%;'>
                <div style='font-size:11px;color:#a5b4fc;letter-spacing:.1em;
                            text-transform:uppercase;font-family:"JetBrains Mono",monospace;
                            margin-bottom:8px;'>Client-side SDK</div>
                <div style='font-size:18px;font-weight:700;color:#e2e8f0;margin-bottom:8px;'>Browsers &amp; mobile apps</div>
                <div style='font-size:12px;color:#cbd5e1;line-height:1.6;margin-bottom:12px;'>
                    JavaScript, React, iOS, Android, Flutter, React Native.<br/><br/>
                    <strong>Auth:</strong> Client-side ID — safe to expose in a JS bundle<br/>
                    <strong>Rules:</strong> only this user's evaluated values, never rule definitions<br/>
                    <strong>Latency:</strong> &lt;30 ms cold; instant after init
                </div>
            </div>
            """, unsafe_allow_html=True)
            st.markdown("""
            <div class="mono" style='font-size:11px;margin-top:10px;'>
<span style='color:#94a3b8;'>// JavaScript — what a browser app uses</span><br/>
const ld = LDClient.initialize(<br/>
&nbsp;&nbsp;<span style='color:#fbbf24;'>"CLIENT_SIDE_ID"</span>,<br/>
&nbsp;&nbsp;{ kind:<span style='color:#fbbf24;'>"user"</span>, key:<span style='color:#fbbf24;'>"alice"</span>,<br/>
&nbsp;&nbsp;&nbsp;&nbsp;tier:<span style='color:#fbbf24;'>"free"</span> });<br/>
<br/>
ld.on(<span style='color:#fbbf24;'>"ready"</span>, () =&gt; {<br/>
&nbsp;&nbsp;const show = ld.variation(<br/>
&nbsp;&nbsp;&nbsp;&nbsp;<span style='color:#a5b4fc;'>"new-hero-banner"</span>, <span style='color:#f87171;'>false</span>);<br/>
});
            </div>
            """, unsafe_allow_html=True)

        st.markdown("**Side-by-side comparison**")
        st.markdown("""
        <table class="compare-table">
            <tr><th>Attribute</th><th>Server-side SDK</th><th>Client-side SDK</th></tr>
            <tr><td class="attr">Auth credential</td><td>SDK Key (secret)</td><td>Client-side ID (public)</td></tr>
            <tr><td class="attr">Rule data on device</td><td>All rules in memory</td><td>Only this user's evaluated values</td></tr>
            <tr><td class="attr">Why the distinction</td><td>Backend is trusted; bandwidth is fine</td><td>Don't leak rule names; keep bundle small</td></tr>
            <tr><td class="attr">Connection</td><td>Streaming SSE</td><td>Streaming SSE (or polling on cellular)</td></tr>
            <tr><td class="attr">When to use</td><td>Backend services, batch jobs, cron</td><td>Browser, mobile, IoT, edge</td></tr>
        </table>
        """, unsafe_allow_html=True)

    # ── Sub-tab B: Microservices fan-out ──────────────────────────────
    with arch_b:
        st.markdown("""
        <div class="card-accent" style='margin-bottom:14px;'>
            <div style='font-size:13px;color:#cbd5e1;line-height:1.7;'>
                Pulse runs 50+ microservices in production: auth, billing, checkout,
                workout generation, email, notifications, search. Each one runs its own
                LaunchDarkly SDK instance — same flag keys, same context shape, same
                one-line evaluation. Toggle a flag once in LD and
                <strong>every service receives the update via streaming SSE in under
                200 ms.</strong> No redeploy, no cascade, no service-by-service rollout.
            </div>
        </div>
        """, unsafe_allow_html=True)

        st.markdown("""
        <div class="topology">
            <div class="topology-row">
                <div class="topology-node">Auth</div>
                <div class="topology-node">Billing</div>
                <div class="topology-node">Checkout</div>
                <div class="topology-node">Workouts</div>
                <div class="topology-node">Notifications</div>
            </div>
            <div class="topology-label">↓ &nbsp;each service holds its own streaming SDK connection &nbsp;↓</div>
            <div class="topology-node ld">LaunchDarkly · single source of truth</div>
        </div>
        """, unsafe_allow_html=True)

        c1, c2 = st.columns([3, 2])
        with c1:
            st.markdown("**The code in every one of those services is identical:**")
            st.markdown("""
            <div class="mono">
ldclient.set_config(Config(<span style='color:#fbbf24;'>LD_SDK_KEY</span>))<br/>
context = Context.builder(user_id)<br/>
&nbsp;&nbsp;.set(<span style='color:#a5b4fc;'>"tier"</span>, tier).build()<br/>
<br/>
<span style='color:#94a3b8;'># Same flag, same answer, in every service —</span><br/>
<span style='color:#94a3b8;'># LD guarantees consistency across the fleet.</span><br/>
show = ld.variation(<span style='color:#a5b4fc;'>"new-hero-banner"</span>, context, <span style='color:#f87171;'>False</span>)
            </div>
            """, unsafe_allow_html=True)
        with c2:
            st.markdown("""
            <div class="card" style='height:100%;'>
                <div style='font-size:11px;color:#a5b4fc;letter-spacing:.1em;
                            text-transform:uppercase;font-family:"JetBrains Mono",monospace;
                            margin-bottom:8px;'>Demo talking points</div>
                <ul style='font-size:12px;color:#cbd5e1;line-height:1.7;padding-left:18px;margin:0;'>
                    <li>Same SDK pattern in every language we use</li>
                    <li>Consistency: one flag value across 50 services</li>
                    <li>Propagation: ≤200 ms via SSE streaming</li>
                    <li>Resilience: each service caches rules locally; LD outage = features freeze, never break</li>
                    <li>Audit: every flag change attributes to a user across the whole estate</li>
                </ul>
            </div>
            """, unsafe_allow_html=True)

    # ── Sub-tab C: Relay Proxy ────────────────────────────────────────
    with arch_c:
        st.markdown("""
        <div class="card-accent" style='margin-bottom:14px;'>
            <div style='font-size:13px;color:#cbd5e1;line-height:1.7;'>
                The <strong>LaunchDarkly Relay Proxy</strong> is a small Go service you
                run inside your own infrastructure. It aggregates the streaming connection
                to LD so your N microservice instances all talk to the Relay instead of
                the LD edge. Optional — but worth deploying once you hit one of three
                triggers below.
            </div>
        </div>
        """, unsafe_allow_html=True)

        st.markdown("**Three reasons teams deploy the Relay Proxy:**")
        r1, r2, r3 = st.columns(3)
        for col, icon, title, body in [
            (r1, "📉", "Egress reduction",
             "500 services × 1 connection each = 500 outbound connections. With Relay it's 1. Significant cost saver at scale."),
            (r2, "🔒", "Data residency",
             "Some regulators require flag-evaluation traffic to stay inside your VPC. Relay sits in your network; your services never call app.launchdarkly.com directly."),
            (r3, "⚡", "Cold-start speed",
             "New service pods initialise from a hot in-network Relay in &lt;100 ms instead of pulling the full ruleset from LD's edge."),
        ]:
            with col:
                st.markdown(f"""
                <div class="card" style='height:100%;'>
                    <div style='font-size:24px;margin-bottom:6px;'>{icon}</div>
                    <div style='font-size:13px;font-weight:700;color:#c7d2fe;margin-bottom:6px;'>{title}</div>
                    <div style='font-size:12px;color:#cbd5e1;line-height:1.6;'>{body}</div>
                </div>
                """, unsafe_allow_html=True)

        st.markdown("**Before vs after:**")
        b1, b2 = st.columns(2)
        with b1:
            st.markdown("""
            <div class="topology">
                <div style='font-size:11px;color:#f87171;font-family:"JetBrains Mono",monospace;
                            letter-spacing:.1em;text-transform:uppercase;margin-bottom:8px;'>
                    Direct · N outbound connections
                </div>
                <div class="topology-row">
                    <div class="topology-node">Svc 1</div>
                    <div class="topology-node">Svc 2</div>
                    <div class="topology-node">Svc 3</div>
                    <div class="topology-node">...</div>
                    <div class="topology-node">Svc N</div>
                </div>
                <div class="topology-label">↓ &nbsp;N independent streaming connections &nbsp;↓</div>
                <div class="topology-node ld">LaunchDarkly (external)</div>
            </div>
            """, unsafe_allow_html=True)
        with b2:
            st.markdown("""
            <div class="topology">
                <div style='font-size:11px;color:#4ade80;font-family:"JetBrains Mono",monospace;
                            letter-spacing:.1em;text-transform:uppercase;margin-bottom:8px;'>
                    Via Relay · 1 outbound connection
                </div>
                <div class="topology-row">
                    <div class="topology-node">Svc 1</div>
                    <div class="topology-node">Svc 2</div>
                    <div class="topology-node">Svc 3</div>
                    <div class="topology-node">...</div>
                    <div class="topology-node">Svc N</div>
                </div>
                <div class="topology-label">↓ &nbsp;internal traffic only &nbsp;↓</div>
                <div class="topology-node relay">LD Relay Proxy<br/><span style='font-size:10px;font-weight:400;'>in your VPC</span></div>
                <div class="topology-label">↓ &nbsp;1 outbound connection &nbsp;↓</div>
                <div class="topology-node ld">LaunchDarkly (external)</div>
            </div>
            """, unsafe_allow_html=True)

        st.markdown("**The code change to point services at the Relay — one line:**")
        st.markdown("""
        <div class="mono">
<span style='color:#94a3b8;'># Before — direct to LD's edge</span><br/>
ldclient.set_config(Config(LD_SDK_KEY))<br/>
<br/>
<span style='color:#94a3b8;'># After — through the Relay in your VPC</span><br/>
ldclient.set_config(Config(<br/>
&nbsp;&nbsp;LD_SDK_KEY,<br/>
&nbsp;&nbsp;stream_uri=<span style='color:#fbbf24;'>"https://relay.internal.pulse-prod"</span>,<br/>
&nbsp;&nbsp;events_uri=<span style='color:#fbbf24;'>"https://relay.internal.pulse-prod"</span><br/>
))
        </div>
        """, unsafe_allow_html=True)

        st.markdown("""
        <div class="card" style='margin-top:18px;border-color:#f59e0b44;'>
            <div style='font-size:11px;color:#fbbf24;letter-spacing:.1em;
                        text-transform:uppercase;font-family:"JetBrains Mono",monospace;
                        margin-bottom:8px;'>When you don't need the Relay</div>
            <div style='font-size:12px;color:#cbd5e1;line-height:1.6;'>
                If you run fewer than ~50 SDK instances total, you don't have data
                residency requirements, and cold-start latency isn't a pain point —
                <strong>just connect direct.</strong> Don't add operational complexity
                you don't need.
            </div>
        </div>
        """, unsafe_allow_html=True)
