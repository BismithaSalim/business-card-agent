import streamlit as st
import base64
import json
from utils.database import (
    get_contacts, insert_contact, update_contact, soft_delete_contact,
    get_contact_by_id, match_contacts_vector
)
from utils.openai_helper import openai_client, research_company, generate_embedding, build_contact_text

def show_contact(c):
    contact_id = c.get("id")
    label = f"👤 {c.get('name','Unknown')} — {c.get('company','')} | {c.get('contact_type','')} | {c.get('category','')}"
    with st.expander(label):
        edit_key = f"edit_{contact_id}"
        if st.session_state.get(edit_key):
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
                    update_contact(contact_id, {
                        "name": e_name, "designation": e_designation, "company": e_company,
                        "email": e_email, "mobile": e_mobile, "telephone": e_telephone,
                        "website": e_website, "address": e_address,
                        "contact_type": e_type, "category": e_cat, "subcategory": e_sub,
                    })
                    st.success("✅ Contact updated!")
                    st.session_state[edit_key] = False
                    st.rerun()
            with col_cancel:
                if st.button("❌ Cancel", key=f"cancel_{contact_id}"):
                    st.session_state[edit_key] = False
                    st.rerun()
        else:
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

            col_edit, col_del = st.columns(2)
            with col_edit:
                if st.button("✏️ Edit", key=f"edit_btn_{contact_id}"):
                    st.session_state[edit_key] = True
                    st.rerun()
            with col_del:
                if st.button("🗑️ Delete", key=f"del_{contact_id}"):
                    soft_delete_contact(contact_id)
                    st.rerun()


def show_bizcard_agent(org_id, org_name, user_email, user_role):
    tab1, tab2, tab3 = st.tabs(["📷 Add Contact", "📋 All Contacts", "🔍 Search"])
    tab4 = None

    # ── TAB 1: ADD CONTACT ──
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
                mobile    = st.text_input("📱 Mobile",    value=c.get("mobile", ""))
                telephone = st.text_input("☎️ Telephone", value=c.get("telephone", ""))
                website   = st.text_input("🌐 Website",   value=c.get("website", ""))
                address   = st.text_area("📍 Address",    value=c.get("address", ""))

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
                        "org_id": org_id, "created_by": user_email,
                    }
                    contact_id = insert_contact(record)
                    st.success("✅ Contact saved!")

                research_url = website
                if not research_url and email and "@" in email:
                    research_url = email.split("@")[1]
                    st.info(f"🌐 Using email domain: {research_url}")

                if research_url:
                    with st.spinner("🔍 Researching company with AI..."):
                        intel = research_company(research_url, company)
                        update_contact(contact_id, {
                            "company_summary": intel.get("company_summary", ""),
                            "ai_tags": intel.get("ai_tags", []),
                            "keywords": intel.get("keywords", []),
                        })
                        st.success("🧠 Company research complete!")
                        st.subheader("🏢 Company Intelligence")
                        st.write(intel.get("company_summary", ""))
                        st.write("🏷️ **Tags:** " + " | ".join([f"`{t}`" for t in intel.get("ai_tags", [])]))
                        st.write("🔑 **Keywords:** " + " | ".join([f"`{k}`" for k in intel.get("keywords", [])]))

                        with st.spinner("⚡ Generating vector embedding..."):
                            full_record = get_contact_by_id(contact_id)
                            text_for_embedding = build_contact_text({**full_record, **intel})
                            embedding = generate_embedding(text_for_embedding)
                            update_contact(contact_id, {"embedding": embedding})
                            st.success("⚡ Vector embedding saved!")
                else:
                    st.warning("⚠️ No website or email — skipping company research.")
                del st.session_state["extracted"]

    # ── TAB 2: ALL CONTACTS ──
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
            st.session_state["contacts_list"] = get_contacts(
                org_id,
                contact_type=filter_type if filter_type != "All" else None,
                category=filter_category if filter_category != "All" else None,
            )
            st.session_state.pop("editing_contact", None)

        contacts = st.session_state.get("contacts_list", [])
        if contacts:
            st.markdown(f"**{len(contacts)} contact(s) found**")
            ec = st.session_state.get("editing_contact")
            if ec:
                st.markdown("---")
                st.subheader(f"✏️ Edit: {ec.get('name','')}")
                types = ["Supplier","Client","Networking","Personal","Other"]
                cats  = ["IT","Cybersecurity","Telecom","Construction","Healthcare","Manufacturing","Other"]
                subs  = ["Servers","Networking","CCTV","Access Control","Cloud","AI","Software","Other"]
                c1, c2 = st.columns(2)
                with c1:
                    en  = st.text_input("Name",        value=ec.get("name",""))
                    ed  = st.text_input("Designation", value=ec.get("designation",""))
                    eco = st.text_input("Company",     value=ec.get("company",""))
                    ee  = st.text_input("Email",       value=ec.get("email",""))
                with c2:
                    em = st.text_input("Mobile",    value=ec.get("mobile",""))
                    et = st.text_input("Telephone", value=ec.get("telephone",""))
                    ew = st.text_input("Website",   value=ec.get("website",""))
                    ea = st.text_area("Address",    value=ec.get("address",""))
                c3, c4, c5 = st.columns(3)
                with c3:
                    ety  = st.selectbox("Type", types, index=types.index(ec.get("contact_type","Supplier")) if ec.get("contact_type") in types else 0)
                with c4:
                    ecat = st.selectbox("Category", cats, index=cats.index(ec.get("category","IT")) if ec.get("category") in cats else 0)
                with c5:
                    esub = st.selectbox("Subcategory", subs, index=subs.index(ec.get("subcategory","Servers")) if ec.get("subcategory") in subs else 0)
                cs, cc = st.columns(2)
                with cs:
                    if st.button("💾 Save", type="primary"):
                        update_contact(ec["id"], {
                            "name": en, "designation": ed, "company": eco,
                            "email": ee, "mobile": em, "telephone": et,
                            "website": ew, "address": ea,
                            "contact_type": ety, "category": ecat, "subcategory": esub,
                        })
                        st.success("✅ Saved!")
                        st.session_state.pop("editing_contact", None)
                        st.session_state.pop("contacts_list", None)
                        st.rerun()
                with cc:
                    if st.button("❌ Cancel"):
                        st.session_state.pop("editing_contact", None)
                        st.rerun()
                st.markdown("---")

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
                            soft_delete_contact(c["id"])
                            st.session_state["contacts_list"] = [x for x in contacts if x["id"] != c["id"]]
                            st.rerun()
        elif "contacts_list" in st.session_state:
            st.info("No contacts found!")

    # ── TAB 3: SEARCH ──
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
                all_contacts = get_contacts(org_id)
                filtered = []
                for c in all_contacts:
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
                    all_contacts = get_contacts(org_id)
                    if not all_contacts:
                        st.warning("No contacts in database yet!")
                    else:
                        contacts_text = ""
                        for i, c in enumerate(all_contacts):
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
Example: [{{"id": "uuid-here"}}]
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
                        matched_contacts = [c for c in all_contacts if c["id"] in matched_id_list]
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
                    matches = match_contacts_vector(query_embedding, 5, org_id)
                    st.markdown(f"**⚡ Found {len(matches)} semantically similar contact(s)**")
                    if matches:
                        for c in matches:
                            show_contact(c)
                    else:
                        st.info("No similar contacts found.")

