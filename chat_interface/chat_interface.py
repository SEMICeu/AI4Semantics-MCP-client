from typing import (
    Dict,
    Any,
)
from io import (
    BytesIO,
)
import streamlit as st
from clients import (
    OpenAIClient,
    MCPClient,
)
from chat_history import (
    ChatHistory,
)
from .scripts_xmi_chat.model_utils import (
    upload_xml,
    download_xml,
    visualise,
)
from .chat_logic import (
    set_chatbox_layout,
    process_user_input,
)


async def xmi_chat_tab() -> None:
    col1, col2, col3 = st.columns([0.15, 0.1, 0.75], gap="small")

    # Initialises/updates the session state
    st.session_state["visualise"] = False
    if "history" not in st.session_state:
        st.session_state['history'] = ChatHistory()

    chat_history: ChatHistory = st.session_state["history"]
    st.session_state["user"] = chat_history.user
    st.session_state["name"] = chat_history.name

    if "client" not in st.session_state:
        st.session_state["completions"] = OpenAIClient().chat_completions

    if "mcp_client" not in st.session_state:
        st.session_state["mcp_client"] = MCPClient(st.session_state)

    model: Dict[str, Any] = {}

    mcp_client: MCPClient
    if st.session_state["user"] and st.session_state["name"]:
        async with st.session_state["mcp_client"] as mcp_client:
            model = await mcp_client.read_model()

    st.session_state["model"] = model
    if model.get("elements", []):
        root: Dict[str, Any] = model["elements"][0]
        st.session_state["ID"] = root["ID"]
        st.session_state["package"] = root["package"]

    with col1:
        # Allows to "login" a user and a session name
        if chat_history.user:
            st.write(f'User: {chat_history.user}')
            if chat_history.name:
                st.write(f'Session: {chat_history.name}')

            else:
                chat_history.name = st.text_input(
                    label='Enter Session:',
                )
                if st.button(
                    label='Set Session',
                    disabled=not bool(chat_history.user),
                ):
                    chat_history.save()
                    st.rerun()

            reload_session = st.text_input(
                label='Session to load:',
                disabled=not bool(chat_history.user),
                placeholder="",
            )
            if st.button(
                label='Load Session',
                disabled=not bool(chat_history.user),
            ):
                chat_history.load(reload_session)
                st.rerun()

        else:
            chat_history.user = st.text_input(
                label='Enter User:',
            )
            if st.button('Set User'):
                st.rerun()

    with col3:
        # If a user and a session are available:
        #   - checks if the session does not have a model, allows to upload one
        #   - otherwise allows to visualise and download the session's model
        if all(
            bool(st.session_state[required])
            for required
            in {
                "user",
                "name",
            }
        ):
            model = st.session_state["model"]
            if not model:
                st.session_state["file"] = st.file_uploader(
                    "Upload an XML document",
                    type=["xml", "ttl"],
                    accept_multiple_files=False,
                    help="Upload your data model as an XML export from EA or a TTL file",
                )
                if st.session_state["file"] is not None:
                    uploaded_file: BytesIO = st.session_state["file"]
                    st.session_state["model"] = await upload_xml(uploaded_file)
                    st.rerun()

            else:
                try: 
                    download_xml(model)
                    st.session_state["visualise"] = st.checkbox(
                        "Visualise Model",
                        value=st.session_state.get("visualise", False),
                    )
                    if st.session_state.get("visualise", False):
                        visualise(model)
                except:
                    print("Error downloading or visualising the model.")

        set_chatbox_layout()

        if user_input := st.chat_input(key="xmi_chat_input"):
            await process_user_input(user_input)
            st.rerun()
