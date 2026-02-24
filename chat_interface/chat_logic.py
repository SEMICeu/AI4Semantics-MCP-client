from os import (
    environ,
)
import streamlit as st
from json import (
    loads,
)
from openai.types.chat import (
    ChatCompletion,
    ChatCompletionMessage,
    ChatCompletionMessageToolCallParam,
    ChatCompletionUserMessageParam,
)
from openai.resources.chat.completions import (
    AsyncCompletions,
)
from clients import (
    MCPClient,
)
from chat_history import (
    ChatHistory,
)
from .model_utils.chat_data_structure import (
    shorten_json,
)



def set_chatbox_layout() -> None:
    # Create title and initiate chat
    st.title("Model Bot")
    for msg in st.session_state['history'].messages:
        if msg["role"] == "user" and msg["content"]:
            st.chat_message("human").write(msg["content"])

        elif msg["role"] == "assistant" and msg["content"]:
            st.chat_message("ai").write(msg["content"])

        elif msg["role"] == "tool" and msg["content"]:
            st.json(loads(msg["content"]), expanded=False)

    # Set up markdown to fix chat_input and layer UI issues
    st.markdown(
        """
    <style>
        .stChatInput {
            position: fixed;
            bottom: 50px;
            width: 65%;
            z-index: 3;
        }
        .fixed-square {
            position: fixed;
            bottom: 0;
            left: 28%;
            width: 67%;
            height: 100px;
            background-color: white;
            z-index: 2;
        }
        main {
            z-index 1;
        }
    </style>
    <div class="fixed-square"></div>
    """,
        unsafe_allow_html=True,
    )


async def process_user_input(
    user_input: str | None,
) -> None:
    """
    Handles user input, generates response, processes tool calls.

    """
    if user_input is None:
        return

    st.chat_message("human").write(user_input)

    model = st.session_state["model"]

    # If there is a model, pre-append this to the prompt
    # so that the LLM is aware of the model.
    model_prompt = ""
    if model and "elements" in model.keys():
        model_prompt = "\n".join([
            "[USER.MODEL]",
            str(shorten_json(model)),
            "[USER.INPUT]",
            "",
        ])
    elif model and "ttl" in model.keys():
        model_prompt = "\n".join([
            "[USER.MODEL]",
            str(model["ttl"]),
            "[USER.INPUT]",
            "",
        ])

    # Gather tools
    mcp_client: MCPClient
    async with st.session_state["mcp_client"] as mcp_client:
        tools = await mcp_client.tools()

    # Injects the model if any, in a way that allows us to remove it later
    user_message = ChatCompletionUserMessageParam(
        role="user",
        content=f"{model_prompt}{user_input}"
    )
    history: ChatHistory = st.session_state["history"]
    history.messages.append(user_message)

    # Completion client
    completions: AsyncCompletions = st.session_state["completions"]

    # Chat loop: generate a response, call tools, and repeat
    # until the LLM does not call any tool.
    loop: bool = True
    while loop:
        response: ChatCompletion = await completions.create(
            messages=history.messages,
            tools=tools,
            tool_choice="auto",
            model=str(environ["LLM_MODEL"]),
            temperature=0,
            stream=False,
        )

        message: ChatCompletionMessage = response.choices[0].message
        #DEBUG
        print("\n[DEBUG] Received assistant message:")
        print(message)
        content = message.content or ""
        if content:
            st.chat_message("ai").write(content)

        if message.tool_calls:
            print("\n[DEBUG] Processing tool calls:")
            tool_calls = [
                ChatCompletionMessageToolCallParam(
                    id=tool_call.id,
                    type="function",
                    function={
                        "name": tool_call.function.name,
                        "arguments": tool_call.function.arguments,
                    },
                )
                for tool_call
                in message.tool_calls
            ]
            history.add_assistant_message(
                content=content,
                tool_calls=tool_calls,
            )
            for tool_call in tool_calls:
                # For now OpenAI only supports the type 'function' in tool call
                function = tool_call["function"]
                async with mcp_client:
                    tool_message = await mcp_client.call_tool(
                        function["name"],
                        loads(function["arguments"]),
                    )
                st.json(
                    loads(tool_message),
                    expanded=2,
                )
                history.add_tool_message(
                    content=tool_message,
                    tool_call_id=tool_call["id"],
                )

        else:
            history.add_assistant_message(content)
            loop = False

    # Removes the model from the conversation and save the latter
    user_message["content"] = user_input
    history.save()
    return


