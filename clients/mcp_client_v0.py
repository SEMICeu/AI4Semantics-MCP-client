from types import (
    TracebackType,
)
from typing import (
    Any,
    Dict,
    List,
    Set,
    Mapping,
    Callable,
)
from pydantic import (
    AnyUrl,
)
from os import (
    getenv,
)
from uuid import (
    uuid4,
)
from contextlib import (
    AsyncExitStack
)
from json import (
    loads,
    dumps,
)
from mcp import (
    ClientSession,
    # StdioServerParameters,
)
# from mcp.client.stdio import (
#     stdio_client,
# )
from mcp.client.streamable_http import (
    streamablehttp_client,
)
from mcp.types import (
    TextResourceContents,
)
from openai.types.chat import (
    ChatCompletionToolParam,
)
from openai.types.shared_params import (
    FunctionDefinition,
)
import streamlit as st
# from fastmcp.client.sampling import (
#     SamplingMessage, 
#     SamplingParams, 
#     RequestContext,
# )
from openai.types.chat import (
    ChatCompletion,
    ChatCompletionMessage,
    ChatCompletionMessageToolCallParam,
    ChatCompletionUserMessageParam,
)
from openai.resources.chat.completions import (
    AsyncCompletions,
)
from os import (
    environ,
)
from mcp import StdioServerParameters
from mcp.client.stdio import stdio_client

# Add these imports
import mcp.types as types  # official MCP types
from mcp.shared.context import RequestContext  # official RequestContext

# Replace your current sampling_handler with this sampling_callback
async def sampling_callback(
    context: RequestContext["ClientSession", Any],
    params: types.CreateMessageRequestParams,
) -> types.CreateMessageResult | types.ErrorData:
    """
    Handle server-initiated sampling by calling your OpenAI client and
    returning a proper MCP CreateMessageResult.
    """
    # Build OpenAI messages
    openai_messages = []
    if params.systemPrompt:
        openai_messages.append({"role": "system", "content": params.systemPrompt})

    # params.messages is a list of MCP "sampling messages"
    # Each item has .role and .content (Text/Image/Audio); we only use text here
    for msg in params.messages:
        # msg.content may be a TextContent or a list of content items; be defensive
        content_text = ""
        try:
            # TextContent case
            content_text = getattr(msg.content, "text", "")
        except Exception:
            # List case (rare): concatenate any text parts
            parts = []
            for c in (msg.content or []):
                if getattr(c, "type", None) == "text":
                    parts.append(getattr(c, "text", ""))
            content_text = "\n".join(parts)

        openai_messages.append({"role": msg.role, "content": content_text})

    # Use your existing OpenAI client (you kept it in Streamlit session state)
    completions = st.session_state["completions"]  # AsyncCompletions
    resp = await completions.create(
        model=str(environ["LLM_MODEL"]),
        messages=openai_messages,
        temperature=params.temperature or 0.0,
        max_tokens=params.maxTokens or 512,
        stop=params.stopSequences or None,
        stream=False,
    )
    text = resp.choices[0].message.content or ""

    # IMPORTANT: Return a CreateMessageResult, not a string
    return types.CreateMessageResult(
        role="assistant",
        content=types.TextContent(type="text", text=text),
        model=str(environ["LLM_MODEL"]),
        stopReason="endTurn",
    )



class MCPClient():
    # Tools that are exposed from the server to the LLM
    EXPOSED_TOOLS: Set[str] = {
        "retrieve_documents",
        "add_class",
        "plan_workflow_with_tools",
    }
    # Arguments that must not be provided by the LLM
    RESERVED_ARGUMENTS: Set[str] = {
        "user",
        "name",
        "package",
        "ID",
    }

    def __init__(
        self,
        state: Mapping = {},
        server_url: str = "http://localhost:8080/mcp", #"https://ai4sem-mcp-server.azurewebsites.net/mcp",
    ) -> None:
        self.session: ClientSession
        # The AsyncExitStack allows us to stack contexts.
        # This removes the need for nested `with` statements.
        self.exit_stack = AsyncExitStack()
        # The session's state
        self.state = state
        self.server_url = server_url
        # self.server_params = StdioServerParameters(
        #     command=executable,
        #     args=["./mcp_server.py"],
        # )
        return

    async def __aenter__(self):
        """
        Called at the start of an `async with` block.
        Initializes a session with the server.
        """
        # transport = await self.exit_stack.enter_async_context(
        #     streamablehttp_client(self.server_url)
        #     # stdio_client(self.server_params)
        # )
        # read, write, _ = transport
        # self.session = await self.exit_stack.enter_async_context(
        #     ClientSession(read, write, sampling_callback=sampling_callback,)
        # )
        # await self.session.initialize()
        
        server_params = StdioServerParameters(command="python", args=[r"C:\Users\ecaudron001\Documents\GitHub\AI4Semantics-MCP-Server\server.py"], env=None)
        transport = await self.exit_stack.enter_async_context(stdio_client(server_params))
        read, write = transport  # stdio returns (read, write)
        self.session = await self.exit_stack.enter_async_context(
            ClientSession(read, write, sampling_callback=sampling_callback)
        )
        await self.session.initialize()

        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        """
        Called at the end of an `async with` block.
        Closes the current server session.
        """
        for o in (exc_type, exc, tb):
            if o is not None:
                print(o, sep=' ')

        await self.exit_stack.aclose()
        return

    async def tools(self) -> List[ChatCompletionToolParam]:
        """
        Tools exposed to the LLM.
        Formatted in a suitable way for the OpenAI API.
        """
        tools = (await self.session.list_tools()).tools
        
        return [
            ChatCompletionToolParam(
                type="function",
                function=FunctionDefinition(
                    name=tool.name,
                    description=tool.description or "",
                    parameters=tool.inputSchema,
                ),
            )
            for tool
            in tools
            if tool.name in MCPClient.EXPOSED_TOOLS
        ]

    async def call_tool(
        self,
        name: str,
        arguments: Dict[str, Any],
    ) -> str:
        """
        Interface between the LLM and the server's tools.
        The LLM provides `name` and `arguments`, and this
        function handles the call to the server's tool.\n
        Each exposed server's tool has a dedicated
        client's method with its name prefixed with an _.
        These methods should validate the arguments,
        call the server's tool and process the results.
        Their results should evaluate to `False` if anything
        went wrong during this process.\n

        :Returns: (str) The response to the LLM's tool call,
        so that is has information about what happened as a
        result of it calling the tool.
        """
        #DEBUG
        print(f"[CLIENT] call_tool triggered for tool: {name}")
        print(f"[CLIENT] Arguments received: {arguments}")
        #END DEBUG
        content = {
            "tool_name": name,
            "tool_arguments": arguments,
            "tool_resulst": ...
        }
        if name not in (tools := MCPClient.EXPOSED_TOOLS):
            content["tool_resulst"] = f"ERROR! Name must be in {tools}"
            return dumps(content)

        tool: Callable[[Dict[str, Any]], Any] = getattr(self, f"_{name}")
        tool_results = await tool(arguments)

        if not tool_results:
            tool_results = "Something wrong happened."

        content["tool_resulst"] = tool_results,
        return dumps(content)

    async def _retrieve_documents(
        self,
        arguments: Dict[str, Any],
    ) -> Dict[str, Dict[str, str]]:
        # Verify arguments
        if "search_terms" not in arguments:
            return {}

        # Call the tool
        result = await self.session.call_tool(
            "retrieve_documents",
            {
                "search_terms": arguments["search_terms"],
                "vocabularies": arguments.get("vocabularies", []),
                "number_of_documents": arguments.get("number_of_documents", 5),
            },
        )

        # Process the result
        content = result.content[0]
        documents: Dict[str, Dict[str, Any]] = {}
        if content.type == "text" and content.text:
            try:
                documents = loads(content.text)
            except (ValueError, TypeError) as e:
                # Log the error and return an empty dictionary
                print(f"Error parsing content.text: {e}")
                documents = {}

        return documents

    async def upload_model(
        self,
        arguments: Dict[str, Any],
    ) -> Dict[str, Any]:
        if not arguments.get("model", {}):
            return {}

        result = await self.session.call_tool(
            "upload_model",
            {
                "user": self.state["user"],
                "name": self.state["name"],
                "model": arguments["model"],
            }
        )

        content = result.content[0]
        model: Dict[str, Any] = {}
        if content.type == "text" and content.text:
            model = loads(content.text)

        return model

    async def _add_class(
        self,
        arguments: Dict[str, Any],
    ) -> Dict[str, Any]:
        required = {
            "title",
            "definition",
            "usage_note",
        }
        if any(
            arg not in arguments
            for arg
            in required
        ):
            return {}

        result = await self.session.call_tool(
            "add_class",
            {
                "user": self.state["user"],
                "name": self.state["name"],
                "package": self.state["package"],
                "ID": self._generate_id(),
            } | {
                k: arguments[k]
                for k
                in required
            }
        )

        content = result.content[0]
        cls: Dict[str, Any] = {}
        if content.type == "text" and content.text:
            cls = loads(content.text)

        return cls

    async def read_model(
        self,
    ) -> Dict[str, Any]:
        user = self.state["user"]
        name = self.state["name"]
        if not user or not name:
            return {}

        result = await self.session.read_resource(
            AnyUrl(f"resource://model/{user}/{name}")
        )

        content = result.contents[0]
        model: Dict[str, Any] = {}
        if isinstance(content, TextResourceContents) and content.text:
            model = loads(content.text)

        return model

    async def _plan_workflow_with_tools(
        self,
        arguments: Dict[str, Any],
    ) -> Dict[str, Dict[str, str]]:

        # Call the tool
        result = await self.session.call_tool(
            "plan_workflow_with_tools",
            {
                "user_question": arguments["user_question"],
                "allowed_executor_tools": arguments["allowed_executor_tools"],
                "observations": arguments.get("observations", None),
                "max_steps": arguments.get("max_steps", 5),
            },
        )

        # Process the result
        content = result.content[0]
        plan: Dict[str, Any] = {}
        if content.type == "text" and content.text:
            try:
                plan = loads(content.text)
            except (ValueError, TypeError) as e:
                # Log the error and return an empty dictionary
                print(f"Error parsing content.text: {e}")
                plan = {}

        return plan

    @staticmethod
    def _generate_id() -> str:
        random_uuid = str(uuid4()).upper().replace("-", "_")
        return f"EAID_{random_uuid}"

