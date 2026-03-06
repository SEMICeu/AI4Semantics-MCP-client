from __future__ import annotations

import csv
import logging
import random
import time
from datetime import datetime
from io import BytesIO
from json import loads as json_loads, dumps as json_dumps
from os import environ, listdir, makedirs
from os.path import exists, join
from typing import Any, Dict, List

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from openinference.instrumentation import using_attributes
from openinference.instrumentation.mcp import MCPInstrumentor
from openinference.instrumentation.openai import OpenAIInstrumentor
from opentelemetry import trace
from phoenix.otel import register
from pydantic import BaseModel

from chat_history import ChatHistory
from chat_history.chat_history import PATH_HISTORIES
from chat_interface.data_model_utils.chat_data_structure import shorten_json
from chat_interface.data_model_utils.export_ttl import jsonld_to_ttl_bytes
from chat_interface.data_model_utils.export_xml import json_to_xml
from chat_interface.data_model_utils.import_ttl import ttl_to_json
from chat_interface.data_model_utils.import_xml import xml_to_json
from chat_interface.data_model_utils.visualisation import get_image_bytes
from clients.openai_client import OpenAIClient
from config import load_config
from fastmcp import Client
from openai.types.chat import (
    ChatCompletionMessageToolCallParam,
    ChatCompletionToolParam,
    ChatCompletionUserMessageParam,
)
from openai.types.shared_params import FunctionDefinition

load_dotenv()

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

tracer = trace.get_tracer(__name__)
with tracer.start_as_current_span("client-startup-test") as span:
    span.set_attribute("server.status", "started")

logger = logging.getLogger("app")
logger.setLevel(logging.INFO)
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setLevel(logging.INFO)
    handler.setFormatter(logging.Formatter("[%(asctime)s] %(levelname)s %(name)s: %(message)s"))
    logger.addHandler(handler)


class RequestDurationMiddleware(BaseHTTPMiddleware):
    """Add X-Request-Duration-Ms header so the frontend can show how long the request took."""

    async def dispatch(self, request, call_next):
        start = time.perf_counter()
        response = await call_next(request)
        duration_ms = round((time.perf_counter() - start) * 1000)
        response.headers["X-Request-Duration-Ms"] = str(duration_ms)
        return response


app = FastAPI(
    title="Data Modelling Assistant API",
    description=(
        "Chat, model upload/download, and diagram generation. "
        "Sessions persist by (user_name, session_id): use stable values after login "
        "so that chat history (on disk) and model (on MCP server) are restored. "
        "GET /sessions?user_name=... returns saved session_ids for that user."
    ),
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(RequestDurationMiddleware)


class ChatRequest(BaseModel):
    user_name: str
    session_id: str
    message: str


class Step(BaseModel):
    tool_name: str
    arguments: Dict[str, Any]
    result: Any | None = None


class ChatResponse(BaseModel):
    messages: List[Dict[str, Any]]
    steps: List[Step]


class UploadModelResponse(BaseModel):
    status: str
    model_filename: str | None = None


class SessionInfo(BaseModel):
    session_id: str
    model_uploaded: bool = False
    model_filename: str | None = None


class ChatHistoryResponse(BaseModel):
    messages: List[Dict[str, Any]]
    model_uploaded: bool = False
    model_filename: str | None = None


class CreateUserResponse(BaseModel):
    user_name: str


class LoginRequest(BaseModel):
    user_name: str


class LoginResponse(BaseModel):
    user_name: str


class FlagIssueRequest(BaseModel):
    user_name: str
    session_id: str
    user_question: str
    assistant_answer: str
    user_comment: str


def _generate_random_username() -> str:
    """Generate a random user name like 'curious-otter-7b3'.

    We don't guarantee global uniqueness, but we avoid obvious collisions with
    existing history directories.
    """
    adjectives = [
        "curious",
        "brave",
        "eager",
        "clever",
        "bright",
        "kind",
        "lively",
        "swift",
        "calm",
        "bold",
    ]
    nouns = [
        "otter",
        "falcon",
        "lynx",
        "heron",
        "sparrow",
        "fox",
        "whale",
        "badger",
        "owl",
        "panther",
    ]
    for _ in range(50):
        base = f"{random.choice(adjectives)}-{random.choice(nouns)}"
        # add a short suffix to reduce collision chance
        suffix = f"-{random.randrange(16**3):03x}"
        candidate = base + suffix
        user_dir = join(PATH_HISTORIES, candidate)
        if not exists(user_dir):
            return candidate
    # Fallback if everything somehow collides
    return f"user-{int(datetime.utcnow().timestamp())}"


def _read_model_filename_from_history(user_name: str, session_id: str) -> str | None:
    """Read model_filename from the session's history file (same file as chat messages)."""
    user_name = (user_name or "").strip() or "anonymous"
    session_id = (session_id or "").strip() or "default"
    fp = join(PATH_HISTORIES, user_name, f"{session_id}.json")
    if not exists(fp):
        return None
    try:
        with open(fp, "r", encoding="utf-8") as f:
            data = json_loads(f.read())
        name = data.get("model_filename") or ""
        return name if name else None
    except Exception:
        return None


def _write_model_filename_to_history(user_name: str, session_id: str, model_filename: str) -> None:
    """Store model filename in the session's history file so session details can return it."""
    user_name = (user_name or "").strip() or "anonymous"
    session_id = (session_id or "").strip() or "default"
    user_dir = join(PATH_HISTORIES, user_name)
    makedirs(user_dir, exist_ok=True)
    fp = join(user_dir, f"{session_id}.json")
    if exists(fp):
        with open(fp, "r", encoding="utf-8") as f:
            data = json_loads(f.read())
    else:
        data = {"messages": []}
    data["model_filename"] = model_filename or ""
    with open(fp, "w", encoding="utf-8") as f:
        f.write(json_dumps(data, ensure_ascii=False))


@app.get("/health")
async def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.post("/user/create", response_model=CreateUserResponse)
async def create_user() -> CreateUserResponse:
    """Create a new random user name to be used by the frontend.

    The frontend should call this once (e.g. on first visit), store the returned
    user_name, and then reuse it for all subsequent requests (chat, model, feedback).
    """
    user_name = _generate_random_username()
    # Ensure the directory exists so later history saves work without races.
    user_dir = join(PATH_HISTORIES, user_name)
    makedirs(user_dir, exist_ok=True)
    return CreateUserResponse(user_name=user_name)


@app.post("/user/login", response_model=LoginResponse)
async def login_user(payload: LoginRequest) -> LoginResponse:
    """Login with an existing user_name.

    We simply check whether a history folder already exists for this user.
    If it does, we return the user_name; otherwise, 404 is raised.
    """
    user_name = (payload.user_name or "").strip()
    if not user_name:
        raise HTTPException(status_code=400, detail="user_name must not be empty.")

    user_dir = join(PATH_HISTORIES, user_name)
    if not exists(user_dir):
        raise HTTPException(status_code=404, detail="User does not exist.")

    return LoginResponse(user_name=user_name)


@app.get("/sessions", response_model=List[SessionInfo])
async def list_sessions(user_name: str) -> List[SessionInfo]:
    """
    List persisted sessions for a user. Each item includes session_id and, if a model
    was uploaded, model_uploaded and model_filename (from the same history file, no extra folders).
    """
    user_name = (user_name or "").strip()
    if not user_name:
        return []
    user_dir = join(PATH_HISTORIES, user_name)
    if not exists(user_dir):
        return []
    result: List[SessionInfo] = []
    for name in sorted(listdir(user_dir)):
        if not name.endswith(".json"):
            continue
        sid = name[:-5]
        model_filename = _read_model_filename_from_history(user_name, sid)
        result.append(
            SessionInfo(
                session_id=sid,
                model_uploaded=bool(model_filename),
                model_filename=model_filename,
            )
        )
    return result


@app.get("/chat/history", response_model=ChatHistoryResponse)
async def get_chat_history(user_name: str, session_id: str) -> ChatHistoryResponse:
    """
    Return saved conversation messages for this user and session. Call this on
    page load or after login/refresh to restore the conversation without sending a message.
    """
    user_name = (user_name or "").strip() or "anonymous"
    session_id = (session_id or "").strip() or "default"
    history = ChatHistory(user=user_name, name=session_id)
    history.load(name=session_id)
    model_filename = (getattr(history, "model_filename", "") or "").strip() or None
    return ChatHistoryResponse(
        messages=history.messages,
        model_uploaded=bool(model_filename),
        model_filename=model_filename,
    )


@app.post("/chat/feedback/flag")
async def flag_issue(payload: FlagIssueRequest) -> Dict[str, str]:
    user_name = (payload.user_name or "").strip() or "anonymous"
    session_id = (payload.session_id or "").strip() or "default"
    timestamp = datetime.utcnow().isoformat(timespec="seconds") + "Z"

    # Per-user CSV in existing chat_history/histories/{username}/
    user_dir = join(PATH_HISTORIES, user_name)
    makedirs(user_dir, exist_ok=True)
    user_csv_path = join(user_dir, "flagged_issues.csv")
    user_row = (
        timestamp,
        session_id,
        payload.user_question.strip(),
        payload.assistant_answer.strip(),
        payload.user_comment.strip(),
    )
    write_header = not exists(user_csv_path)
    with open(user_csv_path, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if write_header:
            w.writerow(["timestamp", "session_id", "user_question", "assistant_answer", "user comment"])
        w.writerow(user_row)

    # Global index CSV: user_name, session_id for lookup
    logs_dir = join("chat_history", "logs")
    makedirs(logs_dir, exist_ok=True)
    index_path = join(logs_dir, "flagged_issues_user_list.csv")
    index_row = (timestamp, user_name, session_id)
    index_header = not exists(index_path)
    with open(index_path, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if index_header:
            w.writerow(["timestamp", "user_name", "session_id"])
        w.writerow(index_row)

    return {"status": "ok"}


@app.post("/model/upload", response_model=UploadModelResponse)
async def upload_model_endpoint(
    user_name: str = Form(...),
    session_id: str = Form(...),
    file: UploadFile = File(...),
) -> UploadModelResponse:
    filename = file.filename or ""
    ext = filename.rsplit(".", 1)[-1].lower()

    if ext not in {"xml", "xmi", "ttl"}:
        raise HTTPException(
            status_code=400,
            detail="Only .xml/.xmi and .ttl files are supported.",
        )

    if ext in {"xml", "xmi"}:
        model_payload = xml_to_json(file.file)
    else:
        content = await file.read()
        model_payload = ttl_to_json(BytesIO(content))

    async with Client(SERVER_URL, sampling_handler=sampling_handler) as client:
        await client.call_tool(
            "upload_model",
            {"user": user_name, "name": session_id, "model": model_payload},
        )

    _write_model_filename_to_history(user_name, session_id, filename)
    return UploadModelResponse(status="ok", model_filename=filename or None)


@app.get("/model", response_class=Response)
async def download_model(user_name: str, session_id: str) -> Response:
    async with Client(SERVER_URL, sampling_handler=sampling_handler) as client:
        contents = await client.read_resource(f"resource://model/{user_name}/{session_id}")

    if not contents:
        raise HTTPException(status_code=404, detail="No model found for this user/session.")

    text = getattr(contents[0], "text", None)
    if not text:
        raise HTTPException(status_code=500, detail="Stored model is empty or unreadable.")

    model = json_loads(text)

    if isinstance(model, dict) and "ttl" in model:
        ttl_bytes = jsonld_to_ttl_bytes(model["ttl"])
        return Response(
            content=ttl_bytes,
            media_type="text/turtle",
            headers={"Content-Disposition": f'attachment; filename="{session_id}.ttl"'},
        )
    
    if isinstance(model, dict) and "elements" in model and "connectors" in model:
        xml_bytes = json_to_xml(model)
        return Response(
            content=xml_bytes,
            media_type="application/xml",
            headers={"Content-Disposition": f'attachment; filename="{session_id}.xmi"'},
        )

    raise HTTPException(
        status_code=500,
        detail="Unknown model format on server; expected UML JSON or TTL JSON-LD.",
    )


@app.get("/model/diagram", response_class=Response)
async def model_diagram(user_name: str, session_id: str) -> Response:
    async with Client(SERVER_URL, sampling_handler=sampling_handler) as client:
        contents = await client.read_resource(f"resource://model/{user_name}/{session_id}")

    if not contents:
        raise HTTPException(status_code=404, detail="No model found for this user/session.")

    text = getattr(contents[0], "text", None)
    if not text:
        raise HTTPException(status_code=500, detail="Stored model is empty or unreadable.")

    model = json_loads(text)

    if isinstance(model, dict) and "xmi" in model:
        uml_json = model["xmi"]
    elif isinstance(model, dict) and "elements" in model and "connectors" in model:
        uml_json = model
    else:
        raise HTTPException(
            status_code=500,
            detail="Model format not supported for visualisation (expected UML JSON).",
        )

    try:
        image_stream = get_image_bytes(uml_json)
        image_bytes = image_stream.getvalue()
    except Exception as e:
        logger.exception("Diagram generation failed: %s", e)
        raise HTTPException(
            status_code=503,
            detail="Diagram generation failed (PlantUML server error or unreachable). Try again later.",
        ) from e

    return Response(
        content=image_bytes,
        media_type="image/png",
        headers={"Content-Disposition": f'inline; filename="{session_id}.png"'},
    )


async def sampling_handler(messages, params, context) -> str:
    try:
        openai_messages: list[dict[str, str]] = []
        if getattr(params, "systemPrompt", None):
            openai_messages.append({"role": "system", "content": params.systemPrompt})

        for m in messages:
            text = getattr(m.content, "text", str(m.content))
            openai_messages.append({"role": m.role, "content": text})

        llm_model = environ.get("LLM_MODEL")
        if not llm_model:
            raise RuntimeError("Missing LLM_MODEL environment variable.")

        completions = OpenAIClient().chat_completions
        resp = await completions.create(
            model=str(llm_model),
            messages=openai_messages,
            temperature=getattr(params, "temperature", 0.0) or 0.0,
            max_tokens=getattr(params, "maxTokens", 512) or 512,
            stop=getattr(params, "stopSequences", None) or None,
            stream=False,
        )
        return (resp.choices[0].message.content or "").strip()
    except Exception as exc:
        logger.exception("sampling_handler failed: %s", exc)
        return ""


async def list_mcp_tools() -> List[Dict[str, Any]]:
    async with Client(SERVER_URL, sampling_handler=sampling_handler) as client:
        tools = await client.list_tools()

    openai_tools: List[ChatCompletionToolParam] = []
    for t in tools:
        # Do not expose upload_model directly to the LLM; it is driven
        # via the /model/upload endpoint so that we always pass a proper
        # parsed model payload. If the LLM calls it without "model", the
        # MCP server raises a validation error.
        if t.name == "upload_model":
            continue
        openai_tools.append(
            ChatCompletionToolParam(
                type="function",
                function=FunctionDefinition(
                    name=t.name,
                    description=t.description or "",
                    parameters=t.inputSchema,
                ),
            )
        )
    return openai_tools  # type: ignore[return-value]


EXPOSED_TOOLS = [
    "retrieve_documents",
    "add_class",
    "add_attribute",
    "add_connector",
    "plan_workflow_with_tools",
    "metadata_checker",
    "reuse_check",
    "validator_check",
    "style_guide_check",
]


async def call_mcp_tool(name: str, arguments: Dict[str, Any]) -> str:
    tool_args = dict(arguments)

    if name == "retrieve_documents":
        tool_args = {
            "search_terms": arguments.get("search_terms"),
            "vocabularies": arguments.get("vocabularies", []),
            "number_of_documents": arguments.get("number_of_documents", arguments.get("n_documents", 10)),
        }

    if name == "get_style_guide":
        # This tool does not accept any parameters; always send an empty payload.
        tool_args = {}

    if name == "plan_workflow_with_tools":
        tool_args = {
            "user": arguments.get("user", ""),
            "name": arguments.get("name", ""),
            "user_question": arguments.get("user_question", ""),
            "allowed_executor_tools": sorted(EXPOSED_TOOLS),
            "observations": arguments.get("observations") or [],
            "max_steps": arguments.get("max_steps", 5),
        }

    if name == "metadata_checker":
        tool_args = {
            "user": arguments.get("user", ""),
            "name": arguments.get("name", ""),
            "target_names": arguments.get("target_names") or [],
            "check_instruction": arguments.get("check_instruction") or "",
        }

    if name == "reuse_check":
        tool_args = {
            "user": arguments.get("user", ""),
            "name": arguments.get("name", ""),
            "vocabularies": arguments.get("vocabularies") or [],
            "n_documents": arguments.get("n_documents", 5),
            "target_names": arguments.get("target_names") or [],
        }

    if name == "style_guide_check":
        tool_args = {
            "validator_check": arguments.get("validator_check") or {},
            "metadata_checks": arguments.get("metadata_checks") or {},
            "reuse_checks": arguments.get("reuse_checks") or {},
        }

    async with Client(SERVER_URL, sampling_handler=sampling_handler) as client:
        result = await client.call_tool(name, tool_args)

    if name == "retrieve_documents":
        content = getattr(result, "content", [])
        if content and getattr(content[0], "type", "") == "text":
            raw_text = getattr(content[0], "text", "") or ""
            try:
                return json_loads(raw_text)  # type: ignore[return-value]
            except Exception:
                return raw_text

    data = getattr(result, "data", None)
    if data is not None:
        return data  # type: ignore[return-value]

    content = getattr(result, "content", [])
    return "".join(getattr(block, "text", "") for block in (content or []))


@app.post("/chat", response_model=ChatResponse)
async def chat_endpoint(payload: ChatRequest) -> ChatResponse:
    user_name = (payload.user_name or "").strip() or "anonymous"
    session_id = (payload.session_id or "").strip() or "default"
    user_input = payload.message.strip()

    if not user_input:
        raise HTTPException(status_code=400, detail="Message must not be empty.")

    llm_model = environ.get("LLM_MODEL")
    if not llm_model:
        raise HTTPException(status_code=500, detail="Missing LLM_MODEL environment variable.")

    history = ChatHistory(user=user_name, name=session_id)
    history.load(name=session_id)

    model = {}
    try:
        async with Client(SERVER_URL) as client:
            contents = await client.read_resource(f"resource://model/{user_name}/{session_id}")
        if contents:
            text = getattr(contents[0], "text", None)
            if text:
                model = json_loads(text)
    except Exception as e:
        logger.info("Model context not available or failed to load: %s", e)

    model_prompt = ""
    if model and "ttl" in model:
        model_prompt = "\n".join(["[USER.MODEL]", str(model["ttl"]), "[USER.INPUT]", ""])
    elif model and "elements" in model:
        model_prompt = "\n".join(["[USER.MODEL]", str(shorten_json(model)), "[USER.INPUT]", ""])

    completions = OpenAIClient().chat_completions
    steps: List[Step] = []

    user_message = ChatCompletionUserMessageParam(role="user", content=f"{model_prompt}{user_input}")
    history.messages.append(user_message)

    tools = await list_mcp_tools()

    with using_attributes(
        session_id=session_id,
        user_id=user_name,
        metadata={"user.name": user_name, "session.name": session_id},
    ):
        loop = True
        while loop:
            try:
                response = await completions.create(
                    messages=history.messages,
                    tools=tools,
                    tool_choice="auto",
                    model=str(llm_model),
                    temperature=0,
                    stream=False,
                )
            except Exception as e:
                logger.exception("Assistant response generation failed: %s", e)
                raise HTTPException(
                    status_code=500,
                    detail=f"Assistant response generation failed: {e}",
                ) from e

            message = response.choices[0].message
            content = message.content or ""

            tool_calls: List[ChatCompletionMessageToolCallParam] = []
            if message.tool_calls:
                tool_calls = [
                    ChatCompletionMessageToolCallParam(
                        id=tool_call.id,
                        type="function",
                        function={
                            "name": tool_call.function.name,
                            "arguments": tool_call.function.arguments,
                        },
                    )
                    for tool_call in message.tool_calls
                ]

            history.add_assistant_message(content=content, tool_calls=tool_calls)

            if tool_calls:
                for tool_call in tool_calls:
                    function = tool_call["function"]
                    name = function["name"]
                    try:
                        args = json_loads(function["arguments"] or "{}")
                    except Exception:
                        args = {}

                    # Always use the current user/session for MCP tools,
                    # even if the LLM provided different placeholders.
                    args["user"] = user_name
                    args["name"] = session_id

                    try:
                        tool_result = await call_mcp_tool(name, args)
                    except Exception as e:
                        err_msg = str(e)
                        if "Unknown model format" in err_msg:
                            tool_result = {
                                "error": "Model format on server is not compatible with this tool.",
                                "hint": "Re-upload your model (XML/TTL) for this user/session and try again.",
                            }
                            logger.warning("Tool '%s': %s", name, err_msg)
                        else:
                            logger.exception("Tool '%s' failed: %s", name, e)
                            raise HTTPException(
                                status_code=500,
                                detail=f"Tool '{name}' failed: {e}",
                            ) from e

                    steps.append(Step(tool_name=name, arguments=args, result=tool_result))

                    try:
                        history_tool_content = (
                            json_dumps(tool_result, ensure_ascii=False)
                            if isinstance(tool_result, (dict, list))
                            else str(tool_result)
                        )
                    except TypeError:
                        history_tool_content = str(tool_result)

                    history.add_tool_message(
                        content=history_tool_content,
                        tool_call_id=tool_call["id"],
                    )

                continue

            loop = False

    user_message["content"] = user_input
    history.save()

    return ChatResponse(messages=history.messages, steps=steps)

