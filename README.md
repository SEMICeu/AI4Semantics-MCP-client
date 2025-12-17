# **AIforSemantics**

## Requirements

- Ideally python 3.12. Should run with 3.10 and above.

## **Setup**

- Clone the github repository [AI4Semantics](https://github.com/pwc-be-adv-tc-cd/AI4semantics)
- Get access to the following folders/files ***.streamlit, .openai_client_config.yaml, .env***
- Make sure that the ***venv*** package is installed: `pip install venv`
- Create a virtual environment at the root of the project: `python -m venv .venv`
- Activate it: `./.venv/Scripts/activate`
- Install dependencies: `pip install -r requirement.txt`

## **Chat history** *./chat_history/*

- *chat_history.py* contains a class `ChatHistory` used to record the conversation, save it and load it later.

## **Clients** *./clients/*

### **MCP Client** */mcp_client.py*

- *mcp_client.py* implements an MCP client that interfaces LLMs with an MCP server. This exposes certain server's tools to the LLM which it can then use, resulting in a more agentic interaction.

### **OpenAI Client** */openai_client.py*

- *openai_client.py* contains a wrapper class for an `AsyncOpenAI` client
- *.openai_client_config.yaml* contains the configs to create an OpenAI client to use an LLM. Choose the config by setting the `API` environment variable.

## **Streamlit tabs** *./tabs/*

- contains the different tabs of the application

### **XMI Tab** */xmi_tab/*

- contains the tab dedicated to the interaction with the user's xml model

#### **XMI scripts** */scripts_xmi_chat/*

- *chatbox.py* contains the chat's layout and the chat loop.

##### **Model interaction** */model_utils/*

- contains all the functions that allow to upload an xml file, convert it to json and back to xml, visualise it and download it back (after modification by the agent).

---
---

## **Start**

- To launch the application, run `streamlit run app.py`. Make sure that the server is running. For deployment you can add the flags `--host 0.0.0.0` `--port 8000`.

## **Usage**

You can directly use the chat, but in order to unlock the other features, you need to:

- Enter a user name on the left, then click on the `Set user` button. This will enable the following:
  - Either you enter a session name and clik on the `Set session` button, so that the conversation as well as your model are automatically saved for later
  - Or you enter a the name of a previous session, and clik on the `Reload session` button to resume your session.
  - Upload an xml model if one was not already uploaded before; otherwise the model is fetched from the server

---
---

## **Tests** *./tests* (OUTDATED)

- The questions/answers pairs as well as the expected vocabulary are in *qa.xlsx*.

### **Run tests** *./run_tests.py*

- To run the tests, in a terminal at the root: python ./run_tests.py

### **Vocabularies** *./tests/vocabularies*

- The results are in *./tests/vocabularies/results*: contains the result for the current run in *voc_[datetime of call to run_tests].xlsx*.
- The error rate for each run is in *./tests/vo*

### **Rag** *./tests/rag*

- Baseline in *./tests/rag/baseline.py*. You only need to include in *./run_tests.py* if the *qa.xlsx* has been modified.
- Rag test in *./tests/rag/test.py*.
- The results are in *./tests/rag/results*:
