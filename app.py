import os
from asyncio import (
    run,
)
import streamlit as st
from chat_interface import (
    xmi_chat_tab,
)


# Setting up environment variables and kernel
# os.environ["OPENAI_API_VERSION"] = "2023-12-01-preview"
# os.environ["AZURE_OPENAI_ENDPOINT"] = st.secrets["ENDPOINT"]
# os.environ["AZURE_OPENAI_API_KEY"] = st.secrets["KEY"]


# load_dotenv(override=True)
st.session_state['add_env'] = True
if st.session_state['add_env']:
    st.session_state['add_env'] = False
    os.environ.update(st.secrets)


# set layout
st.set_page_config(layout="wide")

tab1, *_ = st.tabs(["XMI chat"])

with tab1:
    run(xmi_chat_tab())
