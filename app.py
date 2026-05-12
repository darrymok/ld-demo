import os
import time
import streamlit as st
import ldclient
from ldclient.config import Config
from ldclient import Context

# ── Optional AI SDK ──────────────────────────────────────────────────────────
try:
    from ldai.client import LDAIClient
    import openai
    AI_AVAILABLE = True
except ImportError:
    AI_AVAILABLE = False

# ─────────────────────────────────────────────────────────────────────────────
# CONFIG — replace with your LD SDK key or set env var LD_SDK_KEY
# ─────────────────────────────────────────────────────────────────────────────
LD_SDK_KEY = os.environ.get("LD_SDK_KEY", "YOUR_SDK_KEY_HERE")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")

# Flag keys — create these in your LD project
FLAG_NEW_DASHBOARD   = "new-dashboard-ui"      # Boolean flag
FLAG_DARK_MODE       = "dark-mode"             # Boolean flag
FLAG_CHECKOUT_FLOW   = "new-checkout-flow"     # Boolean flag
FLAG_BANNER_TEXT     = "promotional-banner"    # String flag
AI_CONFIG_KEY        = "support-assistant"     # AI Config key (optional)

# ─────────────────────────────────────────────────────────────────────────────
# INITIALISE LAUNCHDARKLY CLIENT (singleton)
# ─────────────────────────────────────────────────────────────────────────────
@st.cache_resource
def init_ld_client():
    ldclient.set_config(Config(LD_SDK_KEY))
    client = ldclient.get()
    return client

ld = init_ld_client()
ld_connected = ld.is_initialized()

@st.cache_resource
def init_ai_client(_ld_client):
    if AI_AVAILABLE and OPENAI_API_KEY:
        return LDAIClient(_ld_client)
    return None

ld = init_ld_client()
ai_client = init_ai_client(ld)

# ─────────────────────────────────────────────────────────────────────────────
# PAGE CONFIG
# ─────────────────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Acme Corp — Feature Control Demo",
    page_icon="🚀",
    layout="wide"
)

# ─────────────────────────────────────────────────────────────────────────────
# SIDEBAR — User Simulator
# ─────────────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 👤 Simulate a User")
    st.caption("Change the user to see how targeting rules affect their experience")

    user_name = st.selectbox(
        "Select user",
        ["alice", "bob", "carol", "dave", "guest-001"],
        help="Each user can be targeted differently in LaunchDarkly"
    )

    user_tier = st.radio(
        "Subscription tier",
        ["free", "pro", "enterprise"],
        help="Used as a targeting attribute in LD"
    )

    user_country = st.selectbox(
        "Country",
        ["SG", "AU", "JP", "IN", "US"],
        help="Useful for regional rollouts and compliance targeting"
    )

    user_beta = st.checkbox(
        "Beta tester",
        help="Members of the 'beta-testers' segment see features first"
    )

    st.divider()

    # LD connection status
    if ld_connected:
        st.success("✅ LaunchDarkly connected")
    else:
        st.error("❌ LD not connected — check SDK key")

    st.caption(f"SDK Key: `{LD_SDK_KEY[:12]}...`")

# ─────────────────────────────────────────────────────────────────────────────
# BUILD LAUNCHDARKLY CONTEXT
# ─────────────────────────────────────────────────────────────────────────────
context = (
    Context.builder(user_name)
    .kind("user")
    .name(user_name.capitalize())
    .set("tier", user_tier)
    .set("country", user_country)
    .set("betaTester", user_beta)
    .build()
)

# ─────────────────────────────────────────────────────────────────────────────
# EVALUATE ALL FLAGS
# ─────────────────────────────────────────────────────────────────────────────
show_new_dashboard = ld.variation(FLAG_NEW_DASHBOARD, context, False)
show_dark_mode     = ld.variation(FLAG_DARK_MODE, context, False)
show_new_checkout  = ld.variation(FLAG_CHECKOUT_FLOW, context, False)
banner_text        = ld.variation(FLAG_BANNER_TEXT, context, "")

# ─────────────────────────────────────────────────────────────────────────────
# HEADER
# ─────────────────────────────────────────────────────────────────────────────
st.title("🚀 Acme Corp — Product Dashboard")
st.caption(
    f"Logged in as **{user_name}** · Tier: **{user_tier}** · "
    f"Country: **{user_country}** · Beta: **{user_beta}**"
)

# Promotional banner (String flag demo)
if banner_text:
    st.info(f"📣 {banner_text}")

st.divider()

# ─────────────────────────────────────────────────────────────────────────────
# TABS
# ─────────────────────────────────────────────────────────────────────────────
tab1, tab2, tab3, tab4 = st.tabs([
    "🏠 Dashboard",
    "🛒 Checkout",
    "🧪 Flag Inspector",
    "🤖 AI Assistant"
])

# ── TAB 1: DASHBOARD ──────────────────────────────────────────────────────────
with tab1:
    if show_new_dashboard:
        # NEW DASHBOARD EXPERIENCE
        st.success("✨ **New Dashboard** — Feature flag `new-dashboard-ui` is **ON**")
        st.markdown("### Welcome to the redesigned dashboard!")

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Revenue", "$128,430", "+12%")
        col2.metric("Active Users", "4,821", "+8%")
        col3.metric("Deployments Today", "23", "+5")
        col4.metric("Incidents", "0", "-3")

        st.markdown("#### 📊 Feature Adoption (New UI)")
        import random
        data = {"Week 1": 12, "Week 2": 28, "Week 3": 45, "Week 4": 67}
        st.bar_chart(data)

        if user_tier == "enterprise":
            st.markdown("#### 🏢 Enterprise Analytics Panel")
            st.info("Advanced analytics available for your enterprise plan")

    else:
        # OLD DASHBOARD EXPERIENCE
        st.warning("📊 **Classic Dashboard** — Feature flag `new-dashboard-ui` is **OFF**")
        st.markdown("### Dashboard")
        st.markdown("- Revenue: $128,430")
        st.markdown("- Users: 4,821")
        st.markdown("- Status: Operational")

    if show_dark_mode:
        st.markdown("---")
        st.markdown("🌙 *Dark mode is enabled for this user (flag: `dark-mode`)*")

# ── TAB 2: CHECKOUT ───────────────────────────────────────────────────────────
with tab2:
    st.markdown("### 🛒 Checkout Experience")

    # Show which bucket this user landed in
    if show_new_checkout:
        st.success(
            f"✨ **{user_name.capitalize()}** is in the **NEW checkout** group "
            f"(50% rollout)"
        )
        st.caption(
            "This user's key was hashed into the 'true' bucket. "
            "They will consistently see this experience."
        )
        with st.form("checkout_new"):
            st.text_input("Email")
            col1, col2 = st.columns(2)
            col1.text_input("Card number")
            col2.text_input("CVV", type="password")
            st.checkbox("Save card for future purchases")
            submitted = st.form_submit_button("Pay Now →")
            if submitted:
                st.success("✅ Payment processed! (Demo)")
    else:
        st.warning(
            f"📊 **{user_name.capitalize()}** is in the **CLASSIC checkout** group "
            f"(50% rollout)"
        )
        st.caption(
            "This user's key was hashed into the 'false' bucket. "
            "They will consistently see this experience."
        )
        st.text_input("Email address")
        st.text_input("Card details")
        st.button("Submit Payment")

    # Visual rollout explainer
    st.divider()
    st.markdown("#### 📊 How percentage rollout works")
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**New Checkout** (50%)")
        users_new = ["alice", "carol", "guest-001"]
        for u in users_new:
            icon = "👤" if u == user_name else "👥"
            st.markdown(f"{icon} {u}")
    with col2:
        st.markdown("**Classic Checkout** (50%)")
        users_old = ["bob", "dave"]
        for u in users_old:
            icon = "👤" if u == user_name else "👥"
            st.markdown(f"{icon} {u}")

    st.caption(
        "💡 LD uses a deterministic hash of the user key — "
        "the same user always lands in the same bucket. "
        "Change the user in the sidebar to see different experiences."
    )

# ── TAB 3: FLAG INSPECTOR ────────────────────────────────────────────────────
with tab3:
    st.markdown("### 🔍 Live Flag Evaluation")
    st.caption(
        "This is what makes LaunchDarkly powerful for demos — "
        "you can see exactly which flags are evaluated and their values "
        "in real time for the current user context."
    )

    st.markdown("#### Current User Context")
    st.json({
        "key": user_name,
        "kind": "user",
        "tier": user_tier,
        "country": user_country,
        "betaTester": user_beta
    })

    st.markdown("#### Flag Evaluation Results")
    flags_data = {
        FLAG_NEW_DASHBOARD:  {"value": show_new_dashboard,  "type": "Boolean", "default": False},
        FLAG_DARK_MODE:      {"value": show_dark_mode,      "type": "Boolean", "default": False},
        FLAG_CHECKOUT_FLOW:  {"value": show_new_checkout,   "type": "Boolean", "default": False},
        FLAG_BANNER_TEXT:    {"value": banner_text or "(empty)", "type": "String", "default": ""},
    }

    for flag_key, info in flags_data.items():
        col1, col2, col3 = st.columns([3, 1, 2])
        col1.markdown(f"`{flag_key}`")
        col2.markdown(f"*{info['type']}*")
        val = info["value"]
        if isinstance(val, bool):
            if val:
                col3.success("✅ TRUE")
            else:
                col3.error("❌ FALSE")
        else:
            col3.info(f"📝 {val}")

    st.divider()
    st.markdown("#### 💡 Demo Talking Points")
    st.markdown("""
- **Change the user in the sidebar** — watch flags re-evaluate instantly
- **Enterprise users** see additional UI panels that free users don't
- **Beta testers** can be targeted separately from tier
- **Country targeting** enables regional rollouts and compliance rules
- **All evaluation happens server-side** — flags resolve in <5ms
- **Go to your LD dashboard** and toggle a flag — this page updates on refresh
    """)

# ── TAB 4: AI ASSISTANT ───────────────────────────────────────────────────────
with tab4:
    st.markdown("### 🤖 AI Support Assistant")
    st.caption(
        "Powered by LaunchDarkly AI Configs — the prompt and model are controlled "
        "from the LD dashboard, not from code."
    )

    if not AI_AVAILABLE:
        st.warning(
            "AI SDK not installed. Run: `pip install launchdarkly-ai-sdk openai`"
        )
    elif not OPENAI_API_KEY:
        st.warning(
            "Set `OPENAI_API_KEY` environment variable to enable AI features."
        )
    elif not ai_client:
        st.warning("AI client could not be initialised.")
    else:
        st.info(
            f"**Current user tier: {user_tier}** — "
            f"{'Premium model (GPT-4o)' if user_tier == 'enterprise' else 'Standard model (GPT-4o-mini)'} "
            f"will be served based on your AI Config targeting rules."
        )

        user_question = st.text_input(
            "Ask the support assistant:",
            placeholder="e.g. How do I reset my password?"
        )

        if st.button("Send") and user_question:
            with st.spinner("Thinking..."):
                try:
                    oai = openai.OpenAI(api_key=OPENAI_API_KEY)
                    fallback = {
                        "model": "gpt-4o-mini",
                        "_ldMeta": {"enabled": False}
                    }

                    ai_config, tracker = ai_client.config(
                        key=AI_CONFIG_KEY,
                        context=context,
                        default_value=fallback,
                        variables={"user_question": user_question}
                    )

                    if ai_config.get("_ldMeta", {}).get("enabled", False):
                        messages = ai_config.get("messages", [
                            {"role": "system", "content": "You are a helpful support assistant."},
                            {"role": "user", "content": user_question}
                        ])
                        model = ai_config.get("model", "gpt-4o-mini")
                    else:
                        messages = [
                            {"role": "system", "content": "You are a helpful support assistant. Keep responses brief."},
                            {"role": "user", "content": user_question}
                        ]
                        model = "gpt-4o-mini"

                    start = time.time()
                    response = oai.chat.completions.create(
                        model=model,
                        messages=messages,
                        max_tokens=300
                    )
                    latency_ms = int((time.time() - start) * 1000)

                    answer = response.choices[0].message.content
                    st.markdown(f"**Assistant:** {answer}")

                    st.markdown("---")
                    col1, col2, col3 = st.columns(3)
                    col1.metric("Model used", model)
                    col2.metric("Tokens", response.usage.total_tokens)
                    col3.metric("Latency", f"{latency_ms}ms")

                    st.caption(
                        "💡 **Demo point**: Change the AI Config variation in LaunchDarkly "
                        "to swap the model or rewrite the prompt — no redeployment needed."
                    )

                except Exception as e:
                    st.error(f"AI error: {e}")

    st.divider()
    st.markdown("#### How AI Configs work (even without API key)")
    st.markdown("""
1. **Prompt & model live in LaunchDarkly** — not in this code
2. **Targeting rules** route enterprise users to GPT-4o, free users to GPT-4o-mini
3. **Metrics** (tokens, latency, cost) flow back to LD automatically
4. **To change the AI behaviour**: update the config in LD UI → takes effect instantly
5. **To roll back**: toggle the variation percentage in LD → no redeploy
    """)
