import streamlit as st
import psycopg2
import psycopg2.extras
from pgvector.psycopg2 import register_vector
from pgvector import Vector
from openai import OpenAI
import os
import json
import base64
import requests
from dotenv import load_dotenv

load_dotenv()

# Support both local .env and Streamlit Cloud secrets
def get_secret(key):
    try:
        return st.secrets[key]
    except:
        return os.getenv(key)

# ── Postgres (pgvector) connection ─────────────────────────────
# A fresh connection per script run mirrors how the Supabase client was
# (re-)instantiated on every Streamlit rerun. Closed explicitly via `with`.
def get_conn():
    conn = psycopg2.connect(get_secret("DATABASE_URL"), cursor_factory=psycopg2.extras.RealDictCursor)
    register_vector(conn)
    return conn

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

st.title("💼 Business Card Intelligence Agent")

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
    label = f"👤 {c.get('name','Unknown')} — {c.get('company','')} | {c.get('contact_type','')} | {c.get('category','')}"
    with st.expander(label):
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
        if c.get("company_summary"):
            st.subheader("🧠 Company Intelligence")
            st.write(c.get("company_summary", ""))
            st.write("🏷️ **Tags:** " + " | ".join([f"`{t}`" for t in (c.get("ai_tags") or [])]))
            st.write("🔑 **Keywords:** " + " | ".join([f"`{k}`" for k in (c.get("keywords") or [])]))

# ════════════════════════════════════════════════════════════════
# TABS
# ════════════════════════════════════════════════════════════════
tab1, tab2, tab3 = st.tabs(["📷 Add Contact", "📋 All Contacts", "🔍 Search"])

# ════════════════════════════════════════════════════════════════
# TAB 1 — ADD CONTACT (Phase 1 + 2 + 3)
# ════════════════════════════════════════════════════════════════
with tab1:
    st.header("📷 Add Business Card")

    # Input method selection
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
        st.header("✏️ Review & Edit Contact")
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
                }
                with get_conn() as conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            """INSERT INTO contacts
                               (name, designation, company, email, mobile, telephone, website, address, contact_type, category, subcategory)
                               VALUES (%(name)s, %(designation)s, %(company)s, %(email)s, %(mobile)s, %(telephone)s, %(website)s, %(address)s, %(contact_type)s, %(category)s, %(subcategory)s)
                               RETURNING id""",
                            record,
                        )
                        contact_id = cur.fetchone()["id"]
                    conn.commit()
                st.success("✅ Contact saved!")

            research_url = website
            if not research_url and email and "@" in email:
                research_url = email.split("@")[1]
                st.info(f"🌐 Using email domain: {research_url}")

            if research_url:
                with st.spinner("🔍 Researching company with AI..."):
                    intel = research_company(research_url, company)
                    with get_conn() as conn:
                        with conn.cursor() as cur:
                            cur.execute(
                                """UPDATE contacts SET company_summary=%s, ai_tags=%s, keywords=%s WHERE id=%s""",
                                (
                                    intel.get("company_summary", ""),
                                    psycopg2.extras.Json(intel.get("ai_tags", [])),
                                    psycopg2.extras.Json(intel.get("keywords", [])),
                                    contact_id,
                                ),
                            )
                        conn.commit()

                    st.success("🧠 Company research complete!")
                    st.subheader("🏢 Company Intelligence")
                    st.write(intel.get("company_summary", ""))
                    st.write("🏷️ **Tags:** " + " | ".join([f"`{t}`" for t in intel.get("ai_tags", [])]))
                    st.write("🔑 **Keywords:** " + " | ".join([f"`{k}`" for k in intel.get("keywords", [])]))

                    # Generate and save embedding
                    with st.spinner("⚡ Generating vector embedding..."):
                        with get_conn() as conn:
                            with conn.cursor() as cur:
                                cur.execute("SELECT * FROM contacts WHERE id=%s", (contact_id,))
                                full_record = dict(cur.fetchone())
                        text_for_embedding = build_contact_text({**full_record, **intel})
                        embedding = generate_embedding(text_for_embedding)
                        with get_conn() as conn:
                            with conn.cursor() as cur:
                                cur.execute(
                                    "UPDATE contacts SET embedding=%s WHERE id=%s",
                                    (Vector(embedding), contact_id),
                                )
                            conn.commit()
                        st.success("⚡ Vector embedding saved!")
            else:
                st.warning("⚠️ No website or email — skipping company research.")

            del st.session_state["extracted"]

# ════════════════════════════════════════════════════════════════
# TAB 2 — ALL CONTACTS (Phase 4)
# ════════════════════════════════════════════════════════════════
with tab2:
    st.header("📋 All Saved Contacts")

    # Filter bar
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
        where_clauses = []
        params = []
        if filter_type != "All":
            where_clauses.append("contact_type = %s")
            params.append(filter_type)
        if filter_category != "All":
            where_clauses.append("category = %s")
            params.append(filter_category)
        where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(f"SELECT * FROM contacts {where_sql} ORDER BY created_at DESC", params)
                contacts = [dict(r) for r in cur.fetchall()]

        st.markdown(f"**{len(contacts)} contact(s) found**")
        if contacts:
            for c in contacts:
                show_contact(c)
        else:
            st.info("No contacts found!")

# ════════════════════════════════════════════════════════════════
# TAB 3 — SEARCH (Phase 5)
# ════════════════════════════════════════════════════════════════
with tab3:
    st.header("🔍 Search Contacts")

    search_mode = st.radio("Search Mode", ["🔎 Traditional Search", "🤖 AI Natural Language Search", "⚡ Vector Semantic Search"], horizontal=True)

    # ── TRADITIONAL SEARCH ────────────────────────────────────
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
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT * FROM contacts")
                    contacts = [dict(r) for r in cur.fetchall()]

            # Filter in Python
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

    # ── AI NATURAL LANGUAGE SEARCH ────────────────────────────
    elif search_mode == "🤖 AI Natural Language Search":
        st.subheader("🤖 AI Natural Language Search")
        st.info('💡 Try: "Find suppliers dealing in CCTV cameras" or "Show cybersecurity companies" or "Who deals with cloud infrastructure?"')

        ai_query = st.text_input("Ask anything about your contacts...")

        if st.button("🤖 Search with AI") and ai_query:
            with st.spinner("🤖 AI is searching your contacts..."):
                # Load all contacts
                with get_conn() as conn:
                    with conn.cursor() as cur:
                        cur.execute("SELECT * FROM contacts")
                        contacts = [dict(r) for r in cur.fetchall()]

                if not contacts:
                    st.warning("No contacts in database yet!")
                else:
                    # Build contact list for AI
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
The user is searching their business card contacts database.

User query: "{ai_query}"

Here are all the contacts:
{contacts_text}

Return ONLY a JSON array of contact IDs that match the query.
Be generous — include partial matches based on tags, keywords, category, summary.
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

                    # Filter contacts by matched IDs (id comes back as uuid.UUID from
                    # psycopg2, so compare as strings against the AI's JSON ids)
                    matched_contacts = [c for c in contacts if str(c["id"]) in matched_id_list]

                    st.markdown(f"**🤖 AI found {len(matched_contacts)} matching contact(s)**")
                    if matched_contacts:
                        for c in matched_contacts:
                            show_contact(c)
                    else:
                        st.info("No matching contacts found for your query.")

    # ── VECTOR SEMANTIC SEARCH ────────────────────────────────
    else:
        st.subheader("⚡ Vector Semantic Search")
        st.info('💡 Finds contacts by **meaning** not just keywords! Try: "cloud infrastructure" or "security cameras" or "network equipment"')

        vector_query = st.text_input("Search by meaning...", key="vector_query")

        if st.button("⚡ Semantic Search") and vector_query:
            with st.spinner("⚡ Searching by meaning..."):
                # Convert query to vector
                query_embedding = generate_embedding(vector_query)

                # Search using the match_contacts() pgvector similarity function
                with get_conn() as conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            "SELECT * FROM match_contacts(%s, %s)",
                            (Vector(query_embedding), 5),
                        )
                        matches = [dict(r) for r in cur.fetchall()]
                st.markdown(f"**⚡ Found {len(matches)} semantically similar contact(s)**")
                if matches:
                    for c in matches:
                        show_contact(c)
                else:
                    st.info("No similar contacts found.")
