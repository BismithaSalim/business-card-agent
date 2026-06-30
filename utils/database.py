import psycopg2
import psycopg2.extras
import psycopg2.pool
import streamlit as st
from utils.config import get_secret

@st.cache_resource
def _get_pool():
    return psycopg2.pool.SimpleConnectionPool(
        minconn=1, maxconn=10,
        dsn=get_secret("DATABASE_URL")
    )

def execute_query(query, params=None, fetch=None):
    pool = _get_pool()
    conn = pool.getconn()
    try:
        with conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(query, params)
                if fetch == "one":
                    return cur.fetchone()
                elif fetch == "all":
                    return cur.fetchall()
    finally:
        pool.putconn(conn)

def get_user_org(email):
    row = execute_query("""
        SELECT u.*,
               o.id AS org__id,
               o.name AS org__name,
               o.portal_access AS org__portal_access,
               o.access_bizcard AS org__access_bizcard,
               o.access_email AS org__access_email,
               o.access_compliance AS org__access_compliance
        FROM users u
        LEFT JOIN organisations o ON u.org_id = o.id
        WHERE u.email = %s AND u.is_deleted = FALSE
    """, (email,), fetch="one")

    if not row:
        return None

    row = dict(row)
    row["organisations"] = {
        "id":                row.pop("org__id", None),
        "name":              row.pop("org__name", None),
        "portal_access":     row.pop("org__portal_access", False),
        "access_bizcard":    row.pop("org__access_bizcard", False),
        "access_email":      row.pop("org__access_email", False),
        "access_compliance": row.pop("org__access_compliance", False),
    }
    return row

def get_organisations():
    rows = execute_query("""
        SELECT * FROM organisations WHERE is_deleted = FALSE ORDER BY name
    """, fetch="all")
    return [dict(r) for r in rows] if rows else []

# ── Contacts ──────────────────────────────────────────────────

def insert_contact(record):
    cols = ", ".join(record.keys())
    placeholders = ", ".join(["%s"] * len(record))
    vals = list(record.values())
    row = execute_query(
        f"INSERT INTO contacts ({cols}) VALUES ({placeholders}) RETURNING id",
        vals, fetch="one"
    )
    return dict(row)["id"] if row else None

def update_contact(contact_id, fields):
    sets = ", ".join([f"{k} = %s" for k in fields.keys()])
    vals = list(fields.values()) + [contact_id]
    execute_query(f"UPDATE contacts SET {sets} WHERE id = %s", vals)

def get_contacts(org_id, contact_type=None, category=None):
    query = "SELECT * FROM contacts WHERE org_id = %s AND is_deleted = FALSE"
    params = [org_id]
    if contact_type:
        query += " AND contact_type = %s"
        params.append(contact_type)
    if category:
        query += " AND category = %s"
        params.append(category)
    query += " ORDER BY created_at DESC"
    rows = execute_query(query, params, fetch="all")
    return [dict(r) for r in rows] if rows else []

def soft_delete_contact(contact_id):
    execute_query("UPDATE contacts SET is_deleted = TRUE WHERE id = %s", (contact_id,))

def get_contact_by_id(contact_id):
    row = execute_query("SELECT * FROM contacts WHERE id = %s", (contact_id,), fetch="one")
    return dict(row) if row else None

def match_contacts_vector(query_embedding, match_count, org_id):
    rows = execute_query("""
        SELECT id, name, designation, company, email, mobile, telephone,
               website, address, contact_type, category, subcategory,
               company_summary, ai_tags, keywords, created_by,
               1 - (embedding <=> %s::vector) AS similarity
        FROM contacts
        WHERE org_id = %s AND is_deleted = FALSE AND embedding IS NOT NULL
        ORDER BY embedding <=> %s::vector
        LIMIT %s
    """, (str(query_embedding), org_id, str(query_embedding), match_count), fetch="all")
    return [dict(r) for r in rows] if rows else []

# ── Users ─────────────────────────────────────────────────────

def get_users(org_id=None):
    if org_id:
        rows = execute_query("""
            SELECT u.*, o.name AS org_name FROM users u
            LEFT JOIN organisations o ON u.org_id = o.id
            WHERE u.is_deleted = FALSE AND u.org_id = %s ORDER BY u.name
        """, (org_id,), fetch="all")
    else:
        rows = execute_query("""
            SELECT u.*, o.name AS org_name FROM users u
            LEFT JOIN organisations o ON u.org_id = o.id
            WHERE u.is_deleted = FALSE ORDER BY u.name
        """, fetch="all")
    if not rows:
        return []
    result = []
    for r in rows:
        d = dict(r)
        d["organisations"] = {"name": d.pop("org_name", None)}
        result.append(d)
    return result

def upsert_user(email, name, org_id, role):
    existing = execute_query("SELECT id FROM users WHERE email = %s", (email,), fetch="one")
    if existing:
        execute_query("""
            UPDATE users SET name=%s, org_id=%s, role=%s, is_deleted=FALSE WHERE email=%s
        """, (name, org_id, role, email))
    else:
        execute_query("""
            INSERT INTO users (email, name, org_id, role) VALUES (%s, %s, %s, %s)
        """, (email, name, org_id, role))

def update_user(user_id, fields):
    sets = ", ".join([f"{k} = %s" for k in fields.keys()])
    vals = list(fields.values()) + [user_id]
    execute_query(f"UPDATE users SET {sets} WHERE id = %s", vals)

def soft_delete_user(user_id):
    execute_query("UPDATE users SET is_deleted = TRUE WHERE id = %s", (user_id,))

# ── Organisations ─────────────────────────────────────────────

def insert_organisation(name):
    execute_query("INSERT INTO organisations (name) VALUES (%s)", (name,))

def update_organisation(org_id, fields):
    sets = ", ".join([f"{k} = %s" for k in fields.keys()])
    vals = list(fields.values()) + [org_id]
    execute_query(f"UPDATE organisations SET {sets} WHERE id = %s", vals)

def soft_delete_organisation(org_id):
    execute_query("UPDATE organisations SET is_deleted = TRUE WHERE id = %s", (org_id,))

# ── Bid Analyses ──────────────────────────────────────────────

def insert_bid_analysis(record):
    cols = ", ".join(record.keys())
    placeholders = ", ".join(["%s"] * len(record))
    execute_query(
        f"INSERT INTO bid_analyses ({cols}) VALUES ({placeholders})",
        list(record.values())
    )

def get_bid_analyses(org_id):
    rows = execute_query("""
        SELECT * FROM bid_analyses WHERE org_id = %s ORDER BY created_at DESC
    """, (org_id,), fetch="all")
    return [dict(r) for r in rows] if rows else []

def delete_bid_analysis(analysis_id):
    execute_query("DELETE FROM bid_analyses WHERE id = %s", (analysis_id,))
