import streamlit as st
from utils.config import get_secret
from utils.database import get_user_org
from components.auth import show_login_page, decode_token

st.set_page_config(page_title="AI Agent Portal", page_icon="🤖", layout="wide")

# PWA Support
st.markdown("""
    <link rel="manifest" href="app/static/manifest.json">
    <meta name="mobile-web-app-capable" content="yes">
    <meta name="apple-mobile-web-app-capable" content="yes">
    <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
    <meta name="apple-mobile-web-app-title" content="AI Agent Portal">
    <meta name="theme-color" content="#38bdf8">
""", unsafe_allow_html=True)

# ── Authentication ────────────────────────────────────────────
if "token" not in st.session_state:
    show_login_page()

if "user_info" not in st.session_state:
    st.session_state["user_info"] = decode_token(st.session_state["token"])
user_info  = st.session_state["user_info"]
user_email = user_info.get("email", "")
user_name  = user_info.get("name", "")

# ── User & Org lookup (cached in session to avoid DB hit on every rerun) ──
if "user_data" not in st.session_state:
    st.session_state["user_data"] = get_user_org(user_email)
user_data = st.session_state["user_data"]

if not user_data or not user_data.get("org_id"):
    st.title("🤖 AI Agent Portal")
    st.warning(f"👋 Welcome **{user_name}** ({user_email})")
    st.error("⚠️ Your account is not assigned to any organisation yet.")
    st.info("Please contact your administrator to assign you to an organisation.")
    if st.button("🚪 Logout"):
        st.session_state.clear()
        st.rerun()
    st.stop()

org_id    = user_data["org_id"]
org_name  = user_data.get("organisations", {}).get("name", "Unknown Org")
user_role = user_data.get("role", "user")
org_data  = user_data.get("organisations", {}) or {}

access_bizcard    = org_data.get("access_bizcard", False)
access_email      = org_data.get("access_email", False)
access_compliance = org_data.get("access_compliance", False)

if user_role == "super_admin":
    access_bizcard = access_email = access_compliance = True

# ── Portal access check ───────────────────────────────────────
has_any_access = access_bizcard or access_email or access_compliance
if not has_any_access and user_role not in ["super_admin"]:
    st.title("🚫 Access Denied")
    st.error(f"Your organisation **{org_name}** does not have portal access yet.")
    st.info("Please contact your administrator to request access.")
    if st.button("🚪 Logout"):
        st.session_state.clear()
        st.rerun()
    st.stop()

# ── Session routing ───────────────────────────────────────────
if "current_agent" not in st.session_state:
    st.session_state["current_agent"] = None

# ── Portal Home ───────────────────────────────────────────────
if st.session_state["current_agent"] is None:
    col1, col2 = st.columns([3, 1])
    with col1:
        st.title("🤖 AI Agent Portal")
        st.markdown(f"Welcome, **{user_name}** | 🏢 {org_name}")
    with col2:
        st.write("")
        if st.button("🚪 Logout"):
            st.session_state.clear()
            st.rerun()

    st.markdown("---")
    st.subheader("🤖 Available Agents")
    st.markdown("Select an agent to get started:")
    st.write("")

    # ── Row 1: Agent cards ─────────────────────────────────────
    col1, col2, col3 = st.columns(3)

    with col1:
        opacity = "1" if access_bizcard else "0.4"
        st.markdown(f"""
        <div style="background:#1e293b;border:1px solid #334155;border-radius:12px;padding:24px;text-align:center;opacity:{opacity};">
            <div style="font-size:2.5rem">💼</div>
            <div style="font-size:1.1rem;font-weight:700;color:#f1f5f9;margin:8px 0;">Business Card Agent</div>
            <div style="color:#94a3b8;font-size:0.85rem;">Scan, extract & manage business cards with AI</div>
        </div>
        """, unsafe_allow_html=True)
        st.write("")
        if access_bizcard:
            if st.button("Open →", key="open_bizcard", use_container_width=True):
                st.session_state["current_agent"] = "bizcard"
                st.rerun()
        else:
            st.button("No Access", key="open_bizcard", use_container_width=True, disabled=True)

    with col2:
        opacity = "1" if access_email else "0.4"
        st.markdown(f"""
        <div style="background:#1e293b;border:1px solid #334155;border-radius:12px;padding:24px;text-align:center;opacity:{opacity};">
            <div style="font-size:2.5rem">📧</div>
            <div style="font-size:1.1rem;font-weight:700;color:#f1f5f9;margin:8px 0;">Email & Tender Agent</div>
            <div style="color:#94a3b8;font-size:0.85rem;">Extract tenders & intelligence from emails</div>
        </div>
        """, unsafe_allow_html=True)
        st.write("")
        if access_email:
            if st.button("Open →", key="open_email", use_container_width=True):
                st.session_state["current_agent"] = "email"
                st.rerun()
        else:
            st.button("No Access", key="open_email", use_container_width=True, disabled=True)

    with col3:
        opacity = "1" if access_compliance else "0.4"
        st.markdown(f"""
        <div style="background:#1e293b;border:1px solid #334155;border-radius:12px;padding:24px;text-align:center;opacity:{opacity};">
            <div style="font-size:2.5rem">📋</div>
            <div style="font-size:1.1rem;font-weight:700;color:#f1f5f9;margin:8px 0;">Compliance Bidding Agent</div>
            <div style="color:#94a3b8;font-size:0.85rem;">Verify bid compliance before submission</div>
        </div>
        """, unsafe_allow_html=True)
        st.write("")
        if access_compliance:
            if st.button("Open →", key="open_compliance", use_container_width=True):
                st.session_state["current_agent"] = "compliance"
                st.rerun()
        else:
            st.button("No Access", key="open_compliance", use_container_width=True, disabled=True)

    # ── Row 2: Admin card (admin/super_admin only) ─────────────
    if user_role in ["admin", "super_admin"]:
        st.write("")
        col1, col2, col3 = st.columns(3)
        with col1:
            st.markdown("""
            <div style="background:#1e293b;border:1px solid #334155;border-radius:12px;padding:24px;text-align:center;">
                <div style="font-size:2.5rem">⚙️</div>
                <div style="font-size:1.1rem;font-weight:700;color:#f1f5f9;margin:8px 0;">Admin Panel</div>
                <div style="color:#94a3b8;font-size:0.85rem;">Manage organisations and users</div>
            </div>
            """, unsafe_allow_html=True)
            st.write("")
            if st.button("Open →", key="open_admin", use_container_width=True):
                st.session_state["current_agent"] = "admin"
                st.rerun()

    st.stop()

# ── Agent Header (shared across all agents) ───────────────────
agent_titles = {
    "bizcard":    "💼 Business Card Agent",
    "email":      "📧 Email & Tender Agent",
    "compliance": "📋 Compliance Bidding Agent",
    "admin":      "⚙️ Admin Panel",
}
col1, col2, col3 = st.columns([2, 2, 1])
with col1:
    st.title(agent_titles.get(st.session_state["current_agent"], "🤖 AI Agent Portal"))
with col2:
    st.write("")
    st.markdown(f"👤 **{user_name}** | 🏢 **{org_name}**")
with col3:
    st.write("")
    cb, cl = st.columns(2)
    with cb:
        if st.button("🏠 Portal"):
            st.session_state["current_agent"] = None
            st.rerun()
    with cl:
        if st.button("🚪 Logout"):
            st.session_state.clear()
            st.rerun()

# ── Route to Agent ────────────────────────────────────────────
if st.session_state["current_agent"] == "bizcard":
    from agents.bizcard import show_bizcard_agent
    show_bizcard_agent(org_id, org_name, user_email, user_role)

elif st.session_state["current_agent"] == "email":
    st.info("📧 Email & Tender Agent — Coming Soon!")

elif st.session_state["current_agent"] == "compliance":
    from agents.compliance import show_compliance_agent
    show_compliance_agent(org_id, user_email, user_role)

elif st.session_state["current_agent"] == "admin":
    from components.admin import show_admin_panel
    show_admin_panel(user_role, org_id)
