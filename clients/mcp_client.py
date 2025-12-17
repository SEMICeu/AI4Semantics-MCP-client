from __future__ import annotations

from contextlib import AsyncExitStack
from json import loads, dumps
from os import environ
from typing import Any, Callable, Dict, List, Mapping, Set

import streamlit as st
from openai.resources.chat.completions import AsyncCompletions
from openai.types.chat import ChatCompletionToolParam
from openai.types.shared_params import FunctionDefinition
from uuid import uuid4

# ✅ Prefect FastMCP client
from fastmcp import Client

# ----------------------------------------------------------------------
# Sampling handler (server -> client LLM request)
# Prefect FastMCP: the server calls ctx.sample(), your client handles it here.
# ----------------------------------------------------------------------
async def sampling_handler(messages, params, context) -> str:
    """
    Bridges MCP sampling -> OpenAI Chat Completions.
    This is called automatically when the server triggers ctx.sample(...).
    """
    # Build OpenAI message list
    openai_messages: List[Dict[str, str]] = []
    if params.systemPrompt:
        openai_messages.append({"role": "system", "content": params.systemPrompt})

    for m in messages:
        # Messages can be text/image/audio; here we handle text
        text = getattr(m.content, "text", str(m.content))
        openai_messages.append({"role": m.role, "content": text})

    # Use the AsyncCompletions client already stored in Streamlit session
    completions: AsyncCompletions = st.session_state["completions"]

    resp = await completions.create(
        model=str(environ["LLM_MODEL"]),
        messages=openai_messages,
        temperature=params.temperature or 0.0,
        max_tokens=params.maxTokens or 512,
        stop=params.stopSequences or None,
        stream=False,
    )
    return resp.choices[0].message.content or ""


class MCPClient:
    """
    Prefect FastMCP-compatible client wrapper for your app.

    - Keeps your app's API the same: `async with mcp_client: ...`
    - Exposes OpenAI-compatible 'tools()'
    - Executes server tools via 'call_tool(...)'
    - Implements helper methods (_retrieve_documents, _add_class, read_model, etc.)
    """

    # Tools that are exposed to the LLM (as OpenAI function tools)
    EXPOSED_TOOLS: Set[str] = {
        "retrieve_documents",
        "add_class",
        "plan_workflow_with_tools",
        # "metadata_checker",
        # "reuse_check",
        # "interoperability_check",
    }

    # Arguments that must not be provided by the LLM
    RESERVED_ARGUMENTS: Set[str] = {
        "user", "name", "package", "ID",
    }

    def __init__(
        self,
        state: Mapping[str, Any] = {},
        server: str | Any = "http://localhost:8080/mcp",  # URL *without* trailing slash
    ) -> None:
        """
        :param state: per-session state (user, name, package, etc.)
        :param server: Either the MCP HTTP endpoint (e.g., 'http://host:port/mcp')
                       OR a FastMCP server instance (for in-memory use).
                       The Prefect client infers the right transport automatically.
        """
        self.state = state
        self.server = server
        self.exit_stack = AsyncExitStack()
        self.client: Client | None = None

    # -------------------------
    # Async context management
    # -------------------------
    async def __aenter__(self) -> "MCPClient":
        """
        Opens an MCP client session (re-entrant).
        Prefect Client supports multiple concurrent `async with` blocks.
        """
        # Create the Prefect client with sampling enabled
        if self.client is None:
            self.client = Client(
                self.server,
                sampling_handler=sampling_handler,  # <-- enables ctx.sample(...)
            )
        await self.exit_stack.enter_async_context(self.client)  # open a session
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        """
        Closes the session when leaving the outermost context.
        """
        await self.exit_stack.aclose()
        return

    # -------------------------
    # Tool exposure for OpenAI
    # -------------------------
    async def tools(self) -> List[ChatCompletionToolParam]:
        """
        Convert MCP tools into OpenAI Chat Completions "function" tools.
        Only expose tools listed in EXPOSED_TOOLS.
        """
        assert self.client is not None, "MCP client not initialized"
        tools = await self.client.list_tools()  # -> List[Tool]
        return [
            ChatCompletionToolParam(
                type="function",
                function=FunctionDefinition(
                    name=t.name,
                    description=t.description or "",
                    parameters=t.inputSchema,
                ),
            )
            for t in tools
            if t.name in MCPClient.EXPOSED_TOOLS
        ]

    # -------------------------
    # Generic tool dispatcher
    # -------------------------
    async def call_tool(self, name: str, arguments: Dict[str, Any]) -> str:
        """
        Interface between the LLM and the server tools.
        Returns a JSON string for your Streamlit UI.
        """
        print(f"[CLIENT] call_tool triggered for tool: {name}")
        print(f"[CLIENT] Arguments received: {arguments}")

        payload = {"tool_name": name, "tool_arguments": arguments, "tool_resulst": ""}

        print(f"[CLIENT] Payload: {payload}")

        if name not in (tools := MCPClient.EXPOSED_TOOLS):
            payload["tool_resulst"] = f"ERROR! Name must be in {tools}"
            return dumps(payload)

        # Each server tool has a matching method `_name`
        tool_func: Callable[[Dict[str, Any]], Any] = getattr(self, f"_{name}")
        result = await tool_func(arguments)
        payload["tool_resulst"] = result if result else "Something wrong happened."
        print(f"[CLIENT] Payload: {payload}")

        return dumps(payload)

    # -------------------------
    # Tool wrappers (validate args, call server tool, parse results)
    # -------------------------
    async def _retrieve_documents(
        self,
        arguments: Dict[str, Any],
    ) -> Dict[str, Dict[str, str]]:
        # Verify arguments
        if "search_terms" not in arguments:
            return {}

        # Call the tool
        result = await self.client.call_tool(
            "retrieve_documents",
            {
                "search_terms": arguments["search_terms"]
                # "vocabularies": arguments.get("vocabularies", []),
                # "number_of_documents": arguments.get("number_of_documents", 10),
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
    
    async def _add_class(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        assert self.client is not None, "MCP client not initialized"

        required = {"title", "definition", "usage_note"}
        if any(arg not in arguments for arg in required):
            return {}

        res = await self.client.call_tool(
            "add_class",
            {
                "user": self.state.get("user"),
                "name": self.state.get("name"),
                "package": self.state.get("package"),
                "ID": self._generate_id(),
                **{k: arguments[k] for k in required},
            },
        )

        if getattr(res, "data", None) is not None:
            return res.data if isinstance(res.data, dict) else {}

        text = "".join(getattr(b, "text", "") for b in (res.content or []))
        try:
            return loads(text) if text else {}
        except Exception:
            return {}

    async def _plan_workflow_with_tools(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        assert self.client is not None, "MCP client not initialized"

        res = await self.client.call_tool(
            "plan_workflow_with_tools",
            {
                "user_question": arguments["user_question"],
                "allowed_executor_tools": self.EXPOSED_TOOLS,
                "observations": arguments.get("observations", None),
                "max_steps": arguments.get("max_steps", 5),
            },
        )

        if getattr(res, "data", None) is not None:
            return res.data if isinstance(res.data, dict) else {}

        text = "".join(getattr(b, "text", "") for b in (res.content or []))
        try:
            return loads(text) if text else {}
        except Exception:
            return {}
        
    async def _metadata_checker(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        assert self.client is not None, "MCP client not initialized"

        res = await self.client.call_tool(
            "metadata_checker",
            {
                "user": self.state.get("user"),
                "name": self.state.get("name"),
                "target_names": arguments.get("target_names", None), 
                "check_instruction": arguments.get("check_instruction", None)
            },
        )

        if getattr(res, "data", None) is not None:
            return res.data if isinstance(res.data, dict) else {}

        text = "".join(getattr(b, "text", "") for b in (res.content or []))
        try:
            return loads(text) if text else {}
        except Exception:
            return {}

    async def _reuse_check(self, arguments: Dict[str, Any]):
        assert self.client is not None, "MCP client not initialized"

        res = await self.client.call_tool(
            "reuse_check",
            {
                "user": self.state.get("user"),
                "name": self.state.get("name"),
                "vocabularies": arguments.get("vocabularies", None), 
                "n_documents": arguments.get("n_documents", 10)
            },
        )

        if getattr(res, "data", None) is not None:
            return res.data if isinstance(res.data, dict) else {}

        text = "".join(getattr(b, "text", "") for b in (res.content or []))
        try:
            return loads(text) if text else {}
        except Exception:
            return {}
        
    async def _interoperability_check(self, arguments: Dict[str, Any]):
        assert self.client is not None, "MCP client not initialized"

        # res = await self.client.call_tool(
        #     "metadata_checker",
        #     {
        #         "user": self.state.get("user"),
        #         "name": self.state.get("name"),
        #         "target_names": arguments.get("target_names", None), 
        #         "check_instruction": arguments.get("check_instruction", None)
        #     },
        # )

        # if getattr(res, "data", None) is not None:
        #     metadata_checks = res.data if isinstance(res.data, dict) else {}

        # text = "".join(getattr(b, "text", "") for b in (res.content or []))
        # try:
        #     metadata_checks = loads(text) if text else {}
        # except Exception:
        #     metadata_checks = {}

        # res = await self.client.call_tool(
        #     "reuse_check",
        #     {
        #         "user": self.state.get("user"),
        #         "name": self.state.get("name"),
        #         "vocabularies": arguments.get("vocabularies", None), 
        #         "n_documents": arguments.get("n_documents", 10)
        #     },
        # )

        # if getattr(res, "data", None) is not None:
        #     reuse_checks = res.data if isinstance(res.data, dict) else {}

        # text = "".join(getattr(b, "text", "") for b in (res.content or []))
        # try:
        #     reuse_checks = loads(text) if text else {}
        # except Exception:
        #     reuse_checks = {}
        
        res = await self.client.call_tool(
            "interoperability_check",
            {
                "user": self.state.get("user"),
                "name": self.state.get("name"),
                "target_names": arguments.get("target_names", None), 
                "check_instruction": arguments.get("check_instruction", None),
                "vocabularies": arguments.get("vocabularies", None), 
                "n_documents": arguments.get("n_documents", 10), 
                "metadata_checks": arguments.get("metadata_checks", None), #metadata_checks,
                "reuse_checks": arguments.get("reuse_checks", None), #reuse_checks,
            },
        )

        if getattr(res, "data", None) is not None:
            return res.data if isinstance(res.data, dict) else {}

        text = "".join(getattr(b, "text", "") for b in (res.content or []))
        try:
            return loads(text) if text else {}
        except Exception:
            return {}

    # -------------------------
    # Other helpers your UI calls directly
    # -------------------------
    async def upload_model(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        Not exposed to the LLM (no leading underscore in EXPOSED_TOOLS).
        Your UI can call this directly to persist a model on the server.
        """
        assert self.client is not None, "MCP client not initialized"

        if not arguments.get("model", {}):
            return {}

        res = await self.client.call_tool(
            "upload_model",
            {
                "user": self.state.get("user"),
                "name": self.state.get("name"),
                "model": arguments["model"],
            },
        )

        if getattr(res, "data", None) is not None:
            return res.data if isinstance(res.data, dict) else {}

        text = "".join(getattr(b, "text", "") for b in (res.content or []))
        try:
            return loads(text) if text else {}
        except Exception:
            return {}

    async def read_model(self) -> Dict[str, Any]:
        """
        Read a model resource from the MCP server.
        """
        assert self.client is not None, "MCP client not initialized"
        user = self.state.get("user")
        name = self.state.get("name")
        if not user or not name:
            return {}

        contents = await self.client.read_resource(f"resource://model/{user}/{name}")
        if not contents:
            return {}

        # Prefer text content
        text = getattr(contents[0], "text", None)
        if text:
            try:
                return loads(text)
            except Exception:
                return {}

        return {}

    # -------------------------
    # Utilities
    # -------------------------
    @staticmethod
    def _generate_id() -> str:
        random_uuid = str(uuid4()).upper().replace("-", "_")
        return f"EAID_{random_uuid}"
