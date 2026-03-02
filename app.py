from phoenix.otel import register
from openinference.instrumentation.mcp import MCPInstrumentor
from openinference.instrumentation.openai import OpenAIInstrumentor
from config import load_config

config = load_config()
SERVER_URL = config["MCP-server"]["local"]
PHOENIX_URL = config["Phoenix"]["local"]

tracer_provider = register(
    project_name="default",
    endpoint=PHOENIX_URL,
    auto_instrument=True,
)
MCPInstrumentor().instrument(tracer_provider=tracer_provider)
OpenAIInstrumentor().instrument(tracer_provider=tracer_provider)

from opentelemetry import trace
tracer = trace.get_tracer(__name__)
with tracer.start_as_current_span("client-startup-test") as span:
    span.set_attribute("server.status", "started")

import os
import base64
from asyncio import run as asyncio_run
import streamlit as st


from chat_interface import data_modelling_chat_tab


# --- Helper ---
def get_image_base64(image_path: str) -> str:
    try:
        with open(image_path, "rb") as f:
            return base64.b64encode(f.read()).decode()
    except FileNotFoundError:
        return ""


# --- Secrets → env ---
try:
    st.session_state.setdefault('add_env', True)
    if st.session_state['add_env']:
        st.session_state['add_env'] = False
        os.environ.update(st.secrets)
except Exception as e:
    st.warning(f"Could not apply secrets to environment: {e}")


# --- Page config ---
st.set_page_config(
    layout="wide",
    page_title="Data Modelling Assistant",
    page_icon=".streamlit/images/logo.png",
)

# --- Login gate: require username and session ID (for Phoenix trace grouping) ---
# Values are sent to Phoenix via OTLP: chat_logic uses using_attributes(session_id, user_id)
# so every span gets session.id and user.id; in Phoenix you can filter/group by these.
def is_authenticated() -> bool:
    return bool(
        st.session_state.get("user_name", "").strip()
        and st.session_state.get("session_id", "").strip()
    )

if not is_authenticated():
    st.markdown("### Sign in")
    st.caption("Enter your user name and session ID to continue. These are used to group traces in Phoenix Arise.")
    with st.form("login_form"):
        user_name = st.text_input("User name", placeholder="e.g. john.doe", key="login_username")
        session_id = st.text_input("Session ID", placeholder="e.g. session-abc-123", key="login_session_id")
        submitted = st.form_submit_button("Continue")
    if submitted:
        if (user_name or "").strip() and (session_id or "").strip():
            st.session_state["user_name"] = (user_name or "").strip()
            st.session_state["session_id"] = (session_id or "").strip()
            st.rerun()
        else:
            st.warning("Please fill in both User name and Session ID.")
    st.stop()

# --- Load images ---
bg_b64     = get_image_base64(".streamlit/images/background.png")
logo_b64   = get_image_base64(".streamlit/images/logo.png")


# --- Full-page background ---
if bg_b64:
    st.markdown(f"""
        <style>
            .stApp {{
                background-image: url("data:image/png;base64,{bg_b64}");
                background-size: cover;
                background-position: center;
                background-repeat: no-repeat;
                background-attachment: fixed;
            }}
        </style>
    """, unsafe_allow_html=True)


# --- Header banner with logo ---
if logo_b64:
    st.markdown(f"""
        <div style="
            display: flex;
            align-items: center;
            padding: 12px 24px;
            background-color: rgba(0, 0, 0, 0.55);
            border-radius: 10px;
            margin-bottom: 16px;
            backdrop-filter: blur(6px);
        ">
            <img src="data:image/png;base64,{logo_b64}" height="50" style="margin-right: 20px;"/>
            <h2 style="color: white; margin: 0; font-family: sans-serif;">Data Modelling Assistant</h2>
        </div>
    """, unsafe_allow_html=True)
else:
    st.markdown("""
        <div style="
            padding: 12px 24px;
            background-color: rgba(0, 0, 0, 0.55);
            border-radius: 10px;
            margin-bottom: 16px;
        ">
            <h2 style="color: white; margin: 0;">Data Modelling Assistant</h2>
        </div>
    """, unsafe_allow_html=True)

# --- Logged-in user and logout ---
col_title, col_user = st.columns([4, 1])
with col_user:
    if st.button("Log out", key="logout_btn"):
        for key in ("user_name", "session_id"):
            st.session_state.pop(key, None)
        st.rerun()
    st.caption(f"**{st.session_state.get('user_name', '')}** · Session: `{st.session_state.get('session_id', '')}`")

# --- Tabs ---
tab1, *_ = st.tabs(["Data Model chat"])

with tab1:
    try:
        asyncio_run(data_modelling_chat_tab(server=SERVER_URL))
    except Exception as e:
        try:
            with st.status("The UI encountered an unexpected error.", expanded=True, state="error") as status:
                st.write(str(e))
                st.write(
                    "**What you can do now:**\n"
                    "1) Review your inputs and correct the bug if possible.\n"
                    "2) Re-launch the UI.\n"
                    "3) If the error keeps happening, contact the tech team at **emilien.caudron@pwc.com**."
                )
                status.update(label="Action required", state="error")
        except Exception:
            st.error("The UI encountered an unexpected error.")
            st.write(str(e))