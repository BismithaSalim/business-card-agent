import streamlit as st
from utils.database import (
    get_organisations, insert_organisation, update_organisation, soft_delete_organisation,
    get_users, upsert_user, update_user, soft_delete_user
)

def show_admin_panel(user_role, org_id):
    st.header("⚙️ Admin Panel")

    if user_role == "super_admin":
        admin_tab1, admin_tab2 = st.tabs(["🏢 Organisations", "👥 Users"])
    else:
        admin_tab1 = None
        admin_tab2 = st.container()

    # ── Organisations (super_admin only) ──
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
                                update_organisation(oid, {"name": new_name})
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
                            soft_delete_organisation(oid)
                            st.rerun()

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
                                        update_organisation(oid, {field: not current})
                                        st.rerun()
                            st.markdown("---")
            else:
                st.info("No organisations yet.")

            st.markdown("---")
            st.subheader("➕ Add Organisation")
            new_org_name = st.text_input("Organisation Name")
            if st.button("➕ Create Organisation") and new_org_name:
                insert_organisation(new_org_name)
                st.success(f"✅ Organisation '{new_org_name}' created!")
                st.rerun()

    # ── Users ──
    with admin_tab2:
        st.subheader("👥 Manage Users")

        all_users = get_users(org_id=None if user_role == "super_admin" else org_id)

        if all_users:
            for u in all_users:
                uid = u.get("id")
                org_label = u.get("organisations", {}).get("name", "No Org") or "No Org"
                col1, col2, col3 = st.columns([4, 1, 1])
                with col1:
                    st.write(f"👤 **{u.get('name','Unknown')}** ({u.get('email')}) — 🏢 {org_label} — `{u.get('role','user')}`")
                with col2:
                    if st.button("✏️ Edit", key=f"edit_user_{uid}"):
                        st.session_state["editing_user"] = uid
                        st.rerun()
                with col3:
                    if st.button("🗑️ Delete", key=f"del_user_{uid}"):
                        soft_delete_user(uid)
                        st.rerun()

            if st.session_state.get("editing_user"):
                uid = st.session_state["editing_user"]
                u = next((x for x in all_users if x["id"] == uid), None)
                if u:
                    st.markdown("---")
                    st.subheader(f"✏️ Edit User: {u.get('email')}")
                    e_name = st.text_input("Name", value=u.get("name", ""), key="eu_name")
                    if user_role == "super_admin":
                        orgs = get_organisations()
                        org_options = {org["name"]: org["id"] for org in orgs}
                        e_org = st.selectbox("Organisation", list(org_options.keys()), key="eu_org")
                        new_org_id = org_options[e_org]
                        role_options = ["user", "admin", "super_admin"]
                    else:
                        new_org_id = org_id
                        role_options = ["user", "admin"]
                    e_role = st.selectbox("Role", role_options, index=role_options.index(u.get("role", "user")) if u.get("role") in role_options else 0, key="eu_role")
                    if st.button("💾 Save User"):
                        update_user(uid, {"name": e_name, "org_id": new_org_id, "role": e_role})
                        st.success("✅ User updated!")
                        del st.session_state["editing_user"]
                        st.rerun()
        else:
            st.info("No users yet.")

        st.markdown("---")
        with st.expander("➕ Add New User", expanded=False):
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
                upsert_user(new_user_email, new_user_name, new_org_id, selected_role)
                st.success(f"✅ User '{new_user_email}' added!")
                st.rerun()
