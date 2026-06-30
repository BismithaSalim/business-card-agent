import streamlit as st
from utils.config import get_secret
import base64 as _b64
import json as _json
import urllib.parse
import requests as _requests

AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/auth"
TOKEN_URL     = "https://oauth2.googleapis.com/token"
REDIRECT_URI  = "http://localhost:8501"

def _get_auth_url():
    params = {
        "client_id": get_secret("GOOGLE_CLIENT_ID"),
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": "openid email profile",
        "prompt": "select_account",
        "access_type": "offline",
    }
    return AUTHORIZE_URL + "?" + urllib.parse.urlencode(params)

def _exchange_code(code):
    data = {
        "code": code,
        "client_id": get_secret("GOOGLE_CLIENT_ID"),
        "client_secret": get_secret("GOOGLE_CLIENT_SECRET"),
        "redirect_uri": REDIRECT_URI,
        "grant_type": "authorization_code",
    }
    resp = _requests.post(TOKEN_URL, data=data)
    return resp.json()

def show_login_page():
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
        <div class="login-title">AI Agent Portal</div>
        <div class="login-badge">🔐 Secure Access</div>
        <div class="login-sub">Sign in with your company Google account<br>to access your organisation's AI agents</div>
    </div>
    """, unsafe_allow_html=True)

    # Handle OAuth callback — code returned in query params
    params = st.query_params
    if "code" in params:
        code = params["code"]
        with st.spinner("Signing you in..."):
            token = _exchange_code(code)
        if "id_token" in token:
            st.session_state["token"] = token
            st.query_params.clear()
            st.rerun()
        else:
            st.error("Login failed. Please try again.")
            st.query_params.clear()
        st.stop()

    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        auth_url = _get_auth_url()
        st.markdown(
            f'''<a href="{auth_url}" target="_self" style="
                display:block; text-align:center; background:#4285F4; color:white;
                padding:10px 20px; border-radius:8px; text-decoration:none;
                font-size:1rem; font-weight:600; margin-top:16px;">
                🔐 Sign in with Google
            </a>''',
            unsafe_allow_html=True
        )
    st.stop()

def decode_token(token_dict):
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
