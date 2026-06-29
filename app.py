import streamlit as st
from supabase import create_client
from openai import OpenAI
import os
import json
import base64
import requests
import pandas as pd
from dotenv import load_dotenv
from streamlit_oauth import OAuth2Component

load_dotenv()

# Support both local .env and Streamlit Cloud secrets
def get_secret(key):
    try:
        return st.secrets[key]
    except:
        return os.getenv(key)

# Initialize clients
supabase = create_client(get_secret("SUPABASE_URL"), get_secret("SUPABASE_KEY"))
openai_client = OpenAI(api_key=get_secret("OPENAI_API_KEY"))

st.set_page_config(page_title="Business Card Intelligence Agent", page_icon="💼", layout="wide")

# PWA Support
st.markdown("""
    <link rel="manifest" href="app/static/manifest.json">
    <meta name="mobile-web-app-capable" content="yes">
    <meta name="apple-mobile-web-app-capable" content="yes">
    <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
    <meta name="apple-mobile-web-app-title" content="BizCard">
    <meta name="theme-color" content="#38bdf8">
""", unsafe_allow_html=True)

# ────────────────────────────────────────────────────────────
# GOOGLE AUTHENTICATION
# ────────────────────────────────────────────────────────────
GOOGLE_CLIENT_ID     = get_secret("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = get_secret("GOOGLE_CLIENT_SECRET")
AUTHORIZE_URL  = "https://accounts.google.com/o/oauth2/auth"
TOKEN_URL      = "https://oauth2.googleapis.com/token"
REDIRECT_URI   = "http://localhost:8501"

oauth2 = OAuth2Component(
    client_id=GOOGLE_CLIENT_ID,
    client_secret=GOOGLE_CLIENT_SECRET,
    authorize_endpoint=AUTHORIZE_URL,
    token_endpoint=TOKEN_URL,
)

if "token" not in st.session_state:
    st.markdown("""
    <style>
    [data-testid="stAppViewContainer"] { background: #0f172a; }
    .login-box {
        background: #1e293b;
        border: 1px solid #334155;
        border-radius: 16px;
        padding: 48px 40px;
        text-align: center;
        max-width: 420px;
        margin: 60px auto 24px auto;
    }
    .login-icon  { font-size: 3.5rem; margin-bottom: 12px; }
    .login-title { font-size: 1.8rem; font-weight: 700; color: #f1f5f9; margin-bottom: 6px; }
    .login-badge { background: #1e40af; color: #bfdbfe; padding: 4px 14px; border-radius: 20px; font-size: 0.78rem; display: inline-block; margin-bottom: 16px; }
    .login-sub   { color: #94a3b8; font-size: 0.9rem; line-height: 1.6; }
    </style>
    <div class="login-box">
        <div class="login-icon">🤖</div>
        <div class="login-title">Agent Portal</div>
        <div class="login-badge">🔐 Secure Access</div>
        <div class="login-sub">Sign in with your company Google account<br>to access your organisation's AI agents</div>
    </div>
    """, unsafe_allow_html=True)

    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        result = oauth2.authorize_button(
            name="Sign in with Google",
            redirect_uri=REDIRECT_URI,
            scope="openid email profile",
            icon="https://www.google.com/favicon.ico",
            use_container_width=True,
            extras_params={"prompt": "select_account"},
        )
        if result and "token" in result:
            st.session_state["token"] = result["token"]
            st.rerun()
    st.stop()

# ── Decode user info from token ────────────────────────────────
import base64 as _b64
import json as _json

def _decode_id_token(token_dict):
    id_token = token_dict.get("id_token", "")
    if not id_token:
        return {}
    parts = id_token.split(".")
    if len(parts) < 2:
        return {}
    payload = parts[1]
    payload += "=" * (4 - len(payload) % 4)
    decoded = _b64.urlsafe_b64decode(payload)
    return _json.loads(decoded)

user_info = _decode_id_token(st.session_state["token"])
user_email = user_info.get("email", "")
user_name  = user_info.get("name", "")

# ── Get or create user organisation ───────────────────────────
def get_user_org(email):
    result = supabase.table("users").select("*, organisations(*)").eq("email", email).execute()
    if result.data:
        return result.data[0]
    return None

def get_organisations():
    result = supabase.table("organisations").select("*").eq("is_deleted", False).order("name").execute()
    return result.data or []

user_data = get_user_org(user_email)

# ── If user not in any org → show waiting screen ──────────────
if not user_data or not user_data.get("org_id"):
    st.title("💼 Business Card Intelligence Agent")
    st.warning(f"👋 Welcome **{user_name}** ({user_email})")
    st.error("⚠️ Your account is not assigned to any organisation yet.")
    st.info("Please contact your administrator to assign you to an organisation.")
    col_back2, col_out2 = st.columns(2)
    with col_back2:
        if st.button("🏠 Portal"):
            st.session_state["current_agent"] = None
            st.rerun()
    with col_out2:
        if st.button("🚪 Logout"):
            st.session_state.clear()
            st.rerun()
    st.stop()

org_id       = user_data["org_id"]
org_name     = user_data.get("organisations", {}).get("name", "Unknown Org")
user_role    = user_data.get("role", "user")
org_data       = user_data.get("organisations", {}) or {}
portal_access  = org_data.get("portal_access", False)
access_bizcard     = org_data.get("access_bizcard", False)
access_email       = org_data.get("access_email", False)
access_compliance  = org_data.get("access_compliance", False)
# super_admin always has full access
if user_role == "super_admin":
    access_bizcard = access_email = access_compliance = True

# ── Check portal access ───────────────────────────────────────
has_any_access = access_bizcard or access_email or access_compliance
if not has_any_access and user_role not in ["super_admin"]:
    st.title("🚫 Access Denied")
    st.error(f"Your organisation **{org_name}** does not have portal access yet.")
    st.info("Please contact your administrator to request access.")
    if st.button("🚪 Logout"):
        st.session_state.clear()
        st.rerun()
    st.stop()

# ── Portal Home Page ──────────────────────────────────────────
if "current_agent" not in st.session_state:
    st.session_state["current_agent"] = None

if st.session_state["current_agent"] is None:
    # Header
    col1, col2 = st.columns([3, 1])
    with col1:
        st.title("🤖 Agent Portal")
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

    # Agent cards
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

    st.stop()

# ────────────────────────────────────────────────────────────
# MAIN APP
# ────────────────────────────────────────────────────────────
col1, col2, col3 = st.columns([2, 2, 1])
with col1:
    st.title("💼 Business Card Agent")
with col2:
    st.write("")
    st.markdown(f"👤 **{user_name}** | 🏢 **{org_name}**")
with col3:
    st.write("")
    col_back, col_logout = st.columns(2)
    with col_back:
        if st.button("🏠 Portal"):
            st.session_state["current_agent"] = None
            st.rerun()
    with col_logout:
        if st.button("🚪 Logout"):
            st.session_state.clear()
            st.rerun()

# ── HELPER: Get website text ──────────────────────────────────
def get_website_text(url):
    try:
        if not url.startswith("http"):
            url = "https://" + url
        resp = requests.get(url, timeout=8)
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(resp.text, "html.parser")
        for tag in soup(["script", "style", "nav", "footer"]):
            tag.decompose()
        text = soup.get_text(separator=" ", strip=True)
        return text[:4000]
    except:
        return ""

# ── HELPER: Generate Embedding ───────────────────────────────
def generate_embedding(text):
    response = openai_client.embeddings.create(
        model="text-embedding-3-small",
        input=text
    )
    return response.data[0].embedding

# ── HELPER: Build searchable text from contact ────────────────
def build_contact_text(contact):
    parts = [
        contact.get("name", ""),
        contact.get("designation", ""),
        contact.get("company", ""),
        contact.get("email", ""),
        contact.get("contact_type", ""),
        contact.get("category", ""),
        contact.get("subcategory", ""),
        contact.get("company_summary", ""),
        " ".join(contact.get("ai_tags") or []),
        " ".join(contact.get("keywords") or []),
    ]
    return " ".join([p for p in parts if p])

# ── HELPER: AI Company Research ───────────────────────────────
def research_company(website, company_name):
    website_text = get_website_text(website)
    if website_text:
        prompt = f"""You are a business intelligence analyst.
Based on the following website content from {company_name}, generate:
1. A company summary (2-5 paragraphs) covering nature of business, products, services, industries served.
2. A list of AI tags (e.g. HP Partner, Dell Partner, Cisco Partner, Cybersecurity, Cloud Services, Networking, Servers, Data Center)
3. Keywords for search

Website content:
{website_text}

Return ONLY a JSON with keys:
- "company_summary": string
- "ai_tags": list of strings
- "keywords": list of strings
No extra text."""
    else:
        prompt = f"""You are a business intelligence analyst.
Based on the company name "{company_name}" and website "{website}", generate your best guess:
1. A company summary (2-3 paragraphs)
2. Likely AI tags
3. Keywords

Return ONLY a JSON with keys:
- "company_summary": string
- "ai_tags": list of strings
- "keywords": list of strings
No extra text."""

    response = openai_client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}]
    )
    text = response.choices[0].message.content
    text = text.replace("```json", "").replace("```", "").strip()
    return json.loads(text)

# ── HELPER: Display contact card ──────────────────────────────
def show_contact(c):
    contact_id = c.get("id")
    label = f"👤 {c.get('name','Unknown')} — {c.get('company','')} | {c.get('contact_type','')} | {c.get('category','')}"
    with st.expander(label):
        # Edit mode toggle
        edit_key = f"edit_{contact_id}"
        if st.session_state.get(edit_key):
            # ── EDIT MODE ──
            col1, col2 = st.columns(2)
            with col1:
                e_name        = st.text_input("👤 Name",        value=c.get("name",""),        key=f"e_name_{contact_id}")
                e_designation = st.text_input("🏷️ Designation", value=c.get("designation",""), key=f"e_desig_{contact_id}")
                e_company     = st.text_input("🏢 Company",     value=c.get("company",""),     key=f"e_comp_{contact_id}")
                e_email       = st.text_input("📧 Email",       value=c.get("email",""),       key=f"e_email_{contact_id}")
            with col2:
                e_mobile    = st.text_input("📱 Mobile",    value=c.get("mobile",""),    key=f"e_mob_{contact_id}")
                e_telephone = st.text_input("☎️ Telephone", value=c.get("telephone",""), key=f"e_tel_{contact_id}")
                e_website   = st.text_input("🌐 Website",   value=c.get("website",""),   key=f"e_web_{contact_id}")
                e_address   = st.text_area("📍 Address",    value=c.get("address",""),   key=f"e_addr_{contact_id}")

            types = ["Supplier", "Client", "Networking", "Personal", "Other"]
            cats  = ["IT", "Cybersecurity", "Telecom", "Construction", "Healthcare", "Manufacturing", "Other"]
            subs  = ["Servers", "Networking", "CCTV", "Access Control", "Cloud", "AI", "Software", "Other"]
            col3, col4, col5 = st.columns(3)
            with col3:
                e_type = st.selectbox("Contact Type", types, index=types.index(c.get("contact_type","Other")) if c.get("contact_type") in types else 0, key=f"e_type_{contact_id}")
            with col4:
                e_cat = st.selectbox("Category", cats, index=cats.index(c.get("category","Other")) if c.get("category") in cats else 0, key=f"e_cat_{contact_id}")
            with col5:
                e_sub = st.selectbox("Subcategory", subs, index=subs.index(c.get("subcategory","Other")) if c.get("subcategory") in subs else 0, key=f"e_sub_{contact_id}")

            col_save, col_cancel = st.columns(2)
            with col_save:
                if st.button("💾 Save Changes", key=f"save_{contact_id}"):
                    supabase.table("contacts").update({
                        "name": e_name, "designation": e_designation, "company": e_company,
                        "email": e_email, "mobile": e_mobile, "telephone": e_telephone,
                        "website": e_website, "address": e_address,
                        "contact_type": e_type, "category": e_cat, "subcategory": e_sub,
                    }).eq("id", contact_id).execute()
                    st.success("✅ Contact updated!")
                    st.session_state[edit_key] = False
                    st.rerun()
            with col_cancel:
                if st.button("❌ Cancel", key=f"cancel_{contact_id}"):
                    st.session_state[edit_key] = False
                    st.rerun()
        else:
            # ── VIEW MODE ──
            col1, col2 = st.columns(2)
            with col1:
                st.write(f"🏷️ **Designation:** {c.get('designation','')}")
                st.write(f"📧 **Email:** {c.get('email','')}")
                st.write(f"📱 **Mobile:** {c.get('mobile','')}")
                st.write(f"☎️ **Telephone:** {c.get('telephone','')}")
            with col2:
                st.write(f"🌐 **Website:** {c.get('website','')}")
                st.write(f"📍 **Address:** {c.get('address','')}")
                st.write(f"🗂️ **Subcategory:** {c.get('subcategory','')}")
                st.write(f"👤 **Added by:** {c.get('created_by','')}")
            if c.get("company_summary"):
                st.subheader("🧠 Company Intelligence")
                st.write(c.get("company_summary", ""))
                st.write("🏷️ **Tags:** " + " | ".join([f"`{t}`" for t in (c.get("ai_tags") or [])]))
                st.write("🔑 **Keywords:** " + " | ".join([f"`{k}`" for k in (c.get("keywords") or [])]))

            # ── Edit & Delete buttons ──
            col_edit, col_del = st.columns(2)
            with col_edit:
                if st.button("✏️ Edit", key=f"edit_btn_{contact_id}"):
                    st.session_state[edit_key] = True
                    st.rerun()
            with col_del:
                if st.button("🗑️ Delete", key=f"del_{contact_id}"):
                    supabase.table("contacts").update({"is_deleted": True}).eq("id", contact_id).execute()
                    st.rerun()

# ────────────────────────────────────────────────────────────
# TABS
# ────────────────────────────────────────────────────────────
tabs = ["📷 Add Contact", "📋 All Contacts", "🔍 Search"]
if user_role in ["admin", "super_admin"]:
    tabs.append("⚙️ Admin")

tab_objects = st.tabs(tabs)
tab1 = tab_objects[0]
tab2 = tab_objects[1]
tab3 = tab_objects[2]
tab4 = tab_objects[3] if len(tab_objects) > 3 else None

# ────────────────────────────────────────────────────────────
# TAB 1 — ADD CONTACT
# ────────────────────────────────────────────────────────────
with tab1:
    st.header("📷 Add Business Card")

    input_method = st.radio("Choose Input Method:", ["📁 Upload Image", "📸 Use Camera"], horizontal=True)

    image_bytes = None

    if input_method == "📁 Upload Image":
        uploaded_file = st.file_uploader("Upload a business card image", type=["jpg", "jpeg", "png"])
        if uploaded_file:
            st.image(uploaded_file, caption="Uploaded Card", width=400)
            image_bytes = uploaded_file.read()
    else:
        st.info("📱 On mobile: this will open your phone camera directly!")
        camera_photo = st.camera_input("Point camera at business card")
        if camera_photo:
            st.image(camera_photo, caption="Captured Card", width=400)
            image_bytes = camera_photo.read()

    if image_bytes:
        if st.button("🔍 Extract Information"):
            with st.spinner("Reading business card with AI..."):
                image_data = base64.b64encode(image_bytes).decode("utf-8")
                response = openai_client.chat.completions.create(
                    model="gpt-4o",
                    messages=[{
                        "role": "user",
                        "content": [
                            {"type": "text", "text": """Extract contact info from this business card.
Return ONLY a JSON with these exact keys:
name, designation, company, email, mobile, telephone, website, address
If a field is not found, use empty string "". No extra text."""},
                            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_data}"}}
                        ]
                    }]
                )
                text = response.choices[0].message.content
                text = text.replace("```json", "").replace("```", "").strip()
                contact = json.loads(text)
                st.session_state["extracted"] = contact
                st.success("✅ Extraction complete! Review below.")

    if "extracted" in st.session_state:
        st.header("📝 Review & Edit Contact")
        c = st.session_state["extracted"]

        col1, col2 = st.columns(2)
        with col1:
            name        = st.text_input("👤 Name",        value=c.get("name", ""))
            designation = st.text_input("🏷️ Designation", value=c.get("designation", ""))
            company     = st.text_input("🏢 Company",     value=c.get("company", ""))
            email       = st.text_input("📧 Email",       value=c.get("email", ""))
        with col2:
            mobile      = st.text_input("📱 Mobile",      value=c.get("mobile", ""))
            telephone   = st.text_input("☎️ Telephone",   value=c.get("telephone", ""))
            website     = st.text_input("🌐 Website",     value=c.get("website", ""))
            address     = st.text_area("📍 Address",      value=c.get("address", ""))

        st.subheader("🗂️ Classify Contact")
        col3, col4, col5 = st.columns(3)
        with col3:
            contact_type = st.selectbox("Contact Type", ["Supplier", "Client", "Networking", "Personal", "Other"])
        with col4:
            category = st.selectbox("Business Category", ["IT", "Cybersecurity", "Telecom", "Construction", "Healthcare", "Manufacturing", "Other"])
        with col5:
            subcategory = st.selectbox("Subcategory", ["Servers", "Networking", "CCTV", "Access Control", "Cloud", "AI", "Software", "Other"])

        if st.button("💾 Save & Research Company"):
            with st.spinner("Saving contact..."):
                record = {
                    "name": name, "designation": designation, "company": company,
                    "email": email, "mobile": mobile, "telephone": telephone,
                    "website": website, "address": address,
                    "contact_type": contact_type, "category": category, "subcategory": subcategory,
                    "org_id": org_id,
                    "created_by": user_email,
                }
                result = supabase.table("contacts").insert(record).execute()
                contact_id = result.data[0]["id"]
                st.success("✅ Contact saved!")

            research_url = website
            if not research_url and email and "@" in email:
                research_url = email.split("@")[1]
                st.info(f"🌐 Using email domain: {research_url}")

            if research_url:
                with st.spinner("🔍 Researching company with AI..."):
                    intel = research_company(research_url, company)
                    supabase.table("contacts").update({
                        "company_summary": intel.get("company_summary", ""),
                        "ai_tags": intel.get("ai_tags", []),
                        "keywords": intel.get("keywords", []),
                    }).eq("id", contact_id).execute()

                    st.success("🧠 Company research complete!")
                    st.subheader("🏢 Company Intelligence")
                    st.write(intel.get("company_summary", ""))
                    st.write("🏷️ **Tags:** " + " | ".join([f"`{t}`" for t in intel.get("ai_tags", [])]))
                    st.write("🔑 **Keywords:** " + " | ".join([f"`{k}`" for k in intel.get("keywords", [])]))

                    with st.spinner("⚡ Generating vector embedding..."):
                        full_record = supabase.table("contacts").select("*").eq("id", contact_id).execute().data[0]
                        text_for_embedding = build_contact_text({**full_record, **intel})
                        embedding = generate_embedding(text_for_embedding)
                        supabase.table("contacts").update({
                            "embedding": embedding
                        }).eq("id", contact_id).execute()
                        st.success("⚡ Vector embedding saved!")
            else:
                st.warning("⚠️ No website or email — skipping company research.")

            del st.session_state["extracted"]

# ────────────────────────────────────────────────────────────
# TAB 2 — ALL CONTACTS
# ────────────────────────────────────────────────────────────
with tab2:
    st.header("📋 All Saved Contacts")

    col1, col2, col3 = st.columns(3)
    with col1:
        filter_type = st.selectbox("Filter by Type", ["All", "Supplier", "Client", "Networking", "Personal", "Other"], key="tab2_type")
    with col2:
        filter_category = st.selectbox("Filter by Category", ["All", "IT", "Cybersecurity", "Telecom", "Construction", "Healthcare", "Manufacturing", "Other"], key="tab2_category")
    with col3:
        st.write("")
        st.write("")
        load_btn = st.button("🔄 Load Contacts")

    if load_btn:
        query = supabase.table("contacts").select("*").eq("org_id", org_id).eq("is_deleted", False).order("created_at", desc=True)
        if filter_type != "All":
            query = query.eq("contact_type", filter_type)
        if filter_category != "All":
            query = query.eq("category", filter_category)
        st.session_state["contacts_list"] = query.execute().data
        st.session_state.pop("editing_contact", None)

    contacts = st.session_state.get("contacts_list", [])

    if contacts:
        st.markdown(f"**{len(contacts)} contact(s) found**")

        # ── Edit form at top ──
        ec = st.session_state.get("editing_contact")
        if ec:
            st.markdown("---")
            st.subheader(f"✏️ Edit: {ec.get('name','')}")
            types = ["Supplier","Client","Networking","Personal","Other"]
            cats  = ["IT","Cybersecurity","Telecom","Construction","Healthcare","Manufacturing","Other"]
            subs  = ["Servers","Networking","CCTV","Access Control","Cloud","AI","Software","Other"]
            c1, c2 = st.columns(2)
            with c1:
                en = st.text_input("Name",        value=ec.get("name",""))
                ed = st.text_input("Designation", value=ec.get("designation",""))
                eco = st.text_input("Company",    value=ec.get("company",""))
                ee = st.text_input("Email",       value=ec.get("email",""))
            with c2:
                em = st.text_input("Mobile",    value=ec.get("mobile",""))
                et = st.text_input("Telephone", value=ec.get("telephone",""))
                ew = st.text_input("Website",   value=ec.get("website",""))
                ea = st.text_area("Address",    value=ec.get("address",""))
            c3, c4, c5 = st.columns(3)
            with c3:
                ety = st.selectbox("Type", types, index=types.index(ec.get("contact_type","Supplier")) if ec.get("contact_type") in types else 0)
            with c4:
                ecat = st.selectbox("Category", cats, index=cats.index(ec.get("category","IT")) if ec.get("category") in cats else 0)
            with c5:
                esub = st.selectbox("Subcategory", subs, index=subs.index(ec.get("subcategory","Servers")) if ec.get("subcategory") in subs else 0)

            cs, cc = st.columns(2)
            with cs:
                if st.button("💾 Save", type="primary"):
                    supabase.table("contacts").update({
                        "name": en, "designation": ed, "company": eco,
                        "email": ee, "mobile": em, "telephone": et,
                        "website": ew, "address": ea,
                        "contact_type": ety, "category": ecat, "subcategory": esub,
                    }).eq("id", ec["id"]).execute()
                    st.success("✅ Saved!")
                    st.session_state.pop("editing_contact", None)
                    st.session_state.pop("contacts_list", None)
                    st.rerun()
            with cc:
                if st.button("❌ Cancel"):
                    st.session_state.pop("editing_contact", None)
                    st.rerun()
            st.markdown("---")

        # ── Contact list ──
        for c in contacts:
            with st.expander(f"👤 {c.get('name','Unknown')} — {c.get('company','')}"):
                st.write(f"🏷️ {c.get('designation','')} | 📧 {c.get('email','')} | 📱 {c.get('mobile','')}")
                st.write(f"🌐 {c.get('website','')} | 📍 {c.get('address','')}")
                st.write(f"🗂️ **{c.get('contact_type','')}** → {c.get('category','')} → {c.get('subcategory','')}")
                if c.get("company_summary"):
                    st.caption(c.get("company_summary","")[:200] + "...")
                ce, cd = st.columns(2)
                with ce:
                    if st.button("✏️ Edit", key=f"e_{c['id']}"):
                        st.session_state["editing_contact"] = c
                        st.rerun()
                with cd:
                    if st.button("🗑️ Delete", key=f"d_{c['id']}"):
                        supabase.table("contacts").update({"is_deleted": True}).eq("id", c["id"]).execute()
                        st.session_state["contacts_list"] = [x for x in contacts if x["id"] != c["id"]]
                        st.rerun()
    elif "contacts_list" in st.session_state:
        st.info("No contacts found!")

# ────────────────────────────────────────────────────────────
# TAB 3 — SEARCH
# ────────────────────────────────────────────────────────────
with tab3:
    st.header("🔍 Search Contacts")
    st.info(f"Searching contacts for **{org_name}** only")

    search_mode = st.radio("Search Mode", ["🔎 Traditional Search", "🤖 AI Natural Language Search", "⚡ Vector Semantic Search"], horizontal=True)

    if search_mode == "🔎 Traditional Search":
        st.subheader("🔎 Traditional Search")
        col1, col2 = st.columns(2)
        with col1:
            search_name    = st.text_input("Search by Name", key="search_name")
            search_company = st.text_input("Search by Company", key="search_company")
            search_email   = st.text_input("Search by Email", key="search_email")
        with col2:
            search_type     = st.selectbox("Filter by Contact Type", ["All", "Supplier", "Client", "Networking", "Personal", "Other"], key="tab3_type")
            search_category = st.selectbox("Filter by Category", ["All", "IT", "Cybersecurity", "Telecom", "Construction", "Healthcare", "Manufacturing", "Other"], key="tab3_category")

        if st.button("🔎 Search"):
            result = supabase.table("contacts").select("*").eq("org_id", org_id).eq("is_deleted", False).execute()
            contacts = result.data

            filtered = []
            for c in contacts:
                if search_name    and search_name.lower()    not in (c.get("name","") or "").lower(): continue
                if search_company and search_company.lower() not in (c.get("company","") or "").lower(): continue
                if search_email   and search_email.lower()   not in (c.get("email","") or "").lower(): continue
                if search_type != "All"     and c.get("contact_type","") != search_type: continue
                if search_category != "All" and c.get("category","")     != search_category: continue
                filtered.append(c)

            st.markdown(f"**{len(filtered)} result(s) found**")
            for c in filtered:
                show_contact(c)

    elif search_mode == "🤖 AI Natural Language Search":
        st.subheader("🤖 AI Natural Language Search")
        st.info('💡 Try: "Find suppliers dealing in CCTV cameras" or "Show cybersecurity companies"')

        ai_query = st.text_input("Ask anything about your contacts...")

        if st.button("🤖 Search with AI") and ai_query:
            with st.spinner("🤖 AI is searching your contacts..."):
                result = supabase.table("contacts").select("*").eq("org_id", org_id).eq("is_deleted", False).execute()
                contacts = result.data

                if not contacts:
                    st.warning("No contacts in database yet!")
                else:
                    contacts_text = ""
                    for i, c in enumerate(contacts):
                        contacts_text += f"""
Contact {i+1}:
- ID: {c.get('id')}
- Name: {c.get('name','')}
- Designation: {c.get('designation','')}
- Company: {c.get('company','')}
- Email: {c.get('email','')}
- Contact Type: {c.get('contact_type','')}
- Category: {c.get('category','')}
- Subcategory: {c.get('subcategory','')}
- AI Tags: {', '.join(c.get('ai_tags') or [])}
- Keywords: {', '.join(c.get('keywords') or [])}
- Company Summary: {(c.get('company_summary') or '')[:300]}
"""

                    prompt = f"""You are a smart contact search assistant.
User query: "{ai_query}"

Here are all the contacts:
{contacts_text}

Return ONLY a JSON array of contact IDs that match the query.
Example: [{{"id": "uuid-here"}}, {{"id": "uuid-here2"}}]
If no matches, return empty array: []
No extra text."""

                    response = openai_client.chat.completions.create(
                        model="gpt-4o",
                        messages=[{"role": "user", "content": prompt}]
                    )
                    text = response.choices[0].message.content
                    text = text.replace("```json", "").replace("```", "").strip()
                    matched_ids = json.loads(text)
                    matched_id_list = [m["id"] for m in matched_ids]

                    matched_contacts = [c for c in contacts if c["id"] in matched_id_list]

                    st.markdown(f"**🤖 AI found {len(matched_contacts)} matching contact(s)**")
                    if matched_contacts:
                        for c in matched_contacts:
                            show_contact(c)
                    else:
                        st.info("No matching contacts found for your query.")

    else:
        st.subheader("⚡ Vector Semantic Search")
        st.info('💡 Finds contacts by meaning! Try: "cloud infrastructure" or "security cameras"')

        vector_query = st.text_input("Search by meaning...", key="vector_query")

        if st.button("⚡ Semantic Search") and vector_query:
            with st.spinner("⚡ Searching by meaning..."):
                query_embedding = generate_embedding(vector_query)

                result = supabase.rpc("match_contacts", {
                    "query_embedding": query_embedding,
                    "match_count": 5,
                    "org_id": org_id
                }).execute()

                matches = result.data
                st.markdown(f"**⚡ Found {len(matches)} semantically similar contact(s)**")
                if matches:
                    for c in matches:
                        show_contact(c)
                else:
                    st.info("No similar contacts found.")

# ────────────────────────────────────────────────────────────
# TAB 4 — ADMIN (only for admin/super_admin)
# ────────────────────────────────────────────────────────────
if tab4 and user_role in ["admin", "super_admin"]:
    with tab4:
        st.header("⚙️ Admin Panel")

        if user_role == "super_admin":
            admin_tab1, admin_tab2 = st.tabs(["🏢 Organisations", "👥 Users"])
        else:
            admin_tab2 = st.container()
            admin_tab1 = None

        if admin_tab1:
          with admin_tab1:
            st.subheader("🏢 Manage Organisations")

            orgs = get_organisations()
            if orgs:
                for org in orgs:
                    oid = org["id"]
                    col1, col2, col3, col4 = st.columns([4, 1, 1, 1])
                    with col1:
                        if st.session_state.get(f"edit_org_{oid}"):
                            new_name = st.text_input("Edit Name", value=org["name"], key=f"org_name_{oid}")
                        else:
                            st.write(f"🏢 **{org['name']}**")
                    with col2:
                        if st.session_state.get(f"edit_org_{oid}"):
                            if st.button("💾 Save", key=f"save_org_{oid}", use_container_width=True):
                                supabase.table("organisations").update({"name": new_name}).eq("id", oid).execute()
                                st.session_state[f"edit_org_{oid}"] = False
                                st.rerun()
                        else:
                            if st.button("✏️ Edit", key=f"edit_org_btn_{oid}", use_container_width=True):
                                st.session_state[f"edit_org_{oid}"] = True
                                st.rerun()
                    with col3:
                        if st.button("🔑 Access", key=f"acc_btn_{oid}", use_container_width=True):
                            key = f"show_access_{oid}"
                            st.session_state[key] = not st.session_state.get(key, False)
                            st.rerun()
                    with col4:
                        if st.button("🗑️ Delete", key=f"del_org_{oid}", use_container_width=True):
                            supabase.table("organisations").update({"is_deleted": True}).eq("id", oid).execute()
                            st.rerun()

                    # Agent access panel (expands inline when clicked)
                    if st.session_state.get(f"show_access_{oid}", False):
                        with st.container():
                            st.markdown("---")
                            hc1, hc2 = st.columns([5, 1])
                            with hc1:
                                st.markdown(f"**🔑 Agent Access — {org['name']}**")
                            with hc2:
                                if st.button("✖ Close", key=f"close_acc_{oid}", use_container_width=True):
                                    st.session_state[f"show_access_{oid}"] = False
                                    st.rerun()
                            agents = [
                                ("access_bizcard",    "💼 Business Card Agent"),
                                ("access_email",      "📧 Email & Tender Agent"),
                                ("access_compliance", "📋 Compliance Bidding Agent"),
                            ]
                            for field, label in agents:
                                current = org.get(field, False)
                                c1, c2 = st.columns([5, 1])
                                with c1:
                                    if current:
                                        st.success(f"✅ {label}")
                                    else:
                                        st.warning(f"❌ {label} — No Access")
                                with c2:
                                    btn_label = "Revoke" if current else "Grant"
                                    btn_type = "secondary" if current else "primary"
                                    if st.button(btn_label, key=f"{field}_{oid}", use_container_width=True, type=btn_type):
                                        supabase.table("organisations").update({field: not current}).eq("id", oid).execute()
                                        st.rerun()
                            st.markdown("---")
            else:
                st.info("No organisations yet.")

            st.markdown("---")
            st.subheader("➕ Add Organisation")
            new_org_name = st.text_input("Organisation Name")
            if st.button("➕ Create Organisation") and new_org_name:
                supabase.table("organisations").insert({"name": new_org_name}).execute()
                st.success(f"✅ Organisation '{new_org_name}' created!")
                st.rerun()

        with admin_tab2:
            st.subheader("👥 Manage Users")

            # super_admin sees all users, admin sees only their org's users
            if user_role == "super_admin":
                all_users = supabase.table("users").select("*, organisations(name)").eq("is_deleted", False).order("name").execute().data or []
            else:
                all_users = supabase.table("users").select("*, organisations(name)").eq("is_deleted", False).eq("org_id", org_id).order("name").execute().data or []

            if all_users:
                for u in all_users:
                    uid = u.get("id")
                    org_label = u.get("organisations", {}).get("name", "No Org") if u.get("organisations") else "No Org"
                    col1, col2, col3 = st.columns([4, 1, 1])
                    with col1:
                        st.write(f"👤 **{u.get('name','Unknown')}** ({u.get('email')}) — 🏢 {org_label} — `{u.get('role','user')}`")
                    with col2:
                        if st.button("✏️ Edit", key=f"edit_user_{uid}"):
                            st.session_state["editing_user"] = uid
                            st.rerun()
                    with col3:
                        if st.button("🗑️ Delete", key=f"del_user_{uid}"):
                            supabase.table("users").update({"is_deleted": True}).eq("id", uid).execute()
                            st.rerun()

                if st.session_state.get("editing_user"):
                    uid = st.session_state["editing_user"]
                    u = next((x for x in all_users if x["id"] == uid), None)
                    if u:
                        st.markdown("---")
                        st.subheader(f"✏️ Edit User: {u.get('email')}")
                        e_name = st.text_input("Name", value=u.get("name",""), key="eu_name")
                        # super_admin can change org, admin cannot
                        if user_role == "super_admin":
                            orgs = get_organisations()
                            org_options = {org["name"]: org["id"] for org in orgs}
                            e_org = st.selectbox("Organisation", list(org_options.keys()), key="eu_org")
                            new_org_id = org_options[e_org]
                            role_options = ["user", "admin", "super_admin"]
                        else:
                            new_org_id = org_id
                            role_options = ["user", "admin"]
                        e_role = st.selectbox("Role", role_options, index=role_options.index(u.get("role","user")) if u.get("role") in role_options else 0, key="eu_role")
                        if st.button("💾 Save User"):
                            supabase.table("users").update({
                                "name": e_name,
                                "org_id": new_org_id,
                                "role": e_role
                            }).eq("id", uid).execute()
                            st.success("✅ User updated!")
                            del st.session_state["editing_user"]
                            st.rerun()
            else:
                st.info("No users yet.")

            st.markdown("---")
            with st.expander("➕ Add New User", expanded=False):

              # admin can only add to their own org
              if user_role == "super_admin":
                  orgs = get_organisations()
                  org_options = {org["name"]: org["id"] for org in orgs}
                  selected_org = st.selectbox("Assign to Organisation", list(org_options.keys()))
                  new_org_id = org_options[selected_org]
                  role_options = ["user", "admin"]
              else:
                  new_org_id = org_id
                  role_options = ["user"]

              new_user_email = st.text_input("User Email")
              new_user_name  = st.text_input("User Name")
              selected_role  = st.selectbox("Role", role_options)

              if st.button("➕ Add User") and new_user_email:
                existing = supabase.table("users").select("*").eq("email", new_user_email).execute()
                if existing.data:
                    supabase.table("users").update({
                        "org_id": new_org_id,
                        "role": selected_role,
                        "name": new_user_name,
                        "is_deleted": False
                    }).eq("email", new_user_email).execute()
                    st.success(f"✅ User '{new_user_email}' updated!")
                else:
                    supabase.table("users").insert({
                        "email": new_user_email,
                        "name": new_user_name,
                        "org_id": new_org_id,
                        "role": selected_role
                    }).execute()
                    st.success(f"✅ User '{new_user_email}' added!")
                st.rerun()

