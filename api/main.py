"""
FastAPI server - HTTP interface between the Next.js frontend and the AI Agent.

Endpoints:
  POST /api/chat         - Send a message, receive the agent's response
  POST /api/chat/stream  - Same but streamed via Server-Sent Events (SSE)
  GET  /api/health       - Health check for monitoring / Docker
  GET  /api/tools        - List all available agent tools
"""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from agents.graph import get_graph, run_agent
from config import get_settings
from mcp_server.schema import AgentRequest, AgentResponse, ChatMessage


# ─────────────────────────────────────────────────────────────────
# Application lifespan (startup / shutdown hooks)
# ─────────────────────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Pre-compile the LangGraph agent on startup to avoid cold-start latency."""
    # Startup: compile graph and print config summary
    _ = get_graph()
    settings = get_settings()
    print("HocGioi Agent Service started")
    print(f"  Fast model  : {settings.MODEL_FAST}")
    print(f"  Smart model : {settings.MODEL_SMART}")
    print(f"  API running : http://{settings.API_HOST}:{settings.API_PORT}")
    yield
    # Shutdown
    print("HocGioi Agent Service stopped")


# ─────────────────────────────────────────────────────────────────
# FastAPI application
# ─────────────────────────────────────────────────────────────────

app = FastAPI(
    title="HocGioi Agent Service",
    description=(
        "AI Agent Service for the HocGioi learning platform (Math, Grades 1-3).\n\n"
        "Two personas are available:\n"
        "- **consultant**: Supports parents in tracking student progress\n"
        "- **tutor**: Helps students practice Math interactively\n\n"
        "Connects to Supabase via MCP tools to read real learning data."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

# Allow requests from the Next.js frontend
settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─────────────────────────────────────────────────────────────────
# Request / Response models
# ─────────────────────────────────────────────────────────────────


class ChatRequest(BaseModel):
    """Request body for POST /api/chat."""
    message: str = Field(..., min_length=1, description="User message text")
    child_id: Optional[str] = Field(None, description="Student UUID (optional)")
    parent_id: Optional[str] = Field(None, description="Parent user UUID (optional)")
    persona: str = Field(
        "consultant",
        pattern="^(consultant|tutor)$",
        description="Agent persona: 'consultant' (parent) or 'tutor' (student)",
    )
    conversation_history: list[ChatMessage] = Field(
        default_factory=list,
        description="Prior conversation messages in chronological order",
    )


class ChatResponse(BaseModel):
    """Response body for POST /api/chat."""
    message: str = Field(..., description="Agent response text")
    persona: str = Field(..., description="Persona used for this response")


class HealthResponse(BaseModel):
    """Response body for GET /api/health."""
    status: str = "ok"
    service: str = "hocgioi-agent"
    version: str = "0.1.0"


class ToolInfo(BaseModel):
    """Summary of one available agent tool."""
    name: str
    description: str


# ─────────────────────────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────────────────────────


@app.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """Send a message and receive the agent's complete response.

    Flow: Next.js -> POST /api/chat -> LangGraph Agent -> JSON response

    The agent will:
    1. Classify the request intent (report/recommend/consult/...)
    2. Call MCP tools if needed to fetch real data from Supabase
    3. Return a final response based on actual student data
    """
    try:
        history = [
            {"role": msg.role, "content": msg.content}
            for msg in request.conversation_history
        ]

        response_text = await run_agent(
            message=request.message,
            persona=request.persona,
            child_id=request.child_id,
            parent_id=request.parent_id,
            conversation_history=history,
        )

        return ChatResponse(
            message=response_text,
            persona=request.persona,
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Agent error: {str(e)}",
        )


@app.post("/api/chat/stream")
async def chat_stream(request: ChatRequest):
    """Send a message and stream the agent's response via Server-Sent Events.

    Provides better UX by displaying tokens as they are generated
    instead of waiting for the full response.

    Event types streamed:
    - {"type": "token", "content": "..."}     - text chunk from LLM
    - {"type": "tool_start", "tool": "..."}   - tool call started
    - {"type": "tool_end",   "tool": "..."}   - tool call finished
    - {"type": "done"}                        - stream complete
    - {"type": "error", "content": "..."}     - error occurred
    """
    async def event_generator():
        try:
            graph = get_graph()

            from langchain_core.messages import AIMessage, HumanMessage

            messages = []
            for msg in request.conversation_history:
                if msg.role == "user":
                    messages.append(HumanMessage(content=msg.content))
                elif msg.role == "assistant":
                    messages.append(AIMessage(content=msg.content))
            messages.append(HumanMessage(content=request.message))

            initial_state = {
                "messages": messages,
                "persona": request.persona,
                "child_id": request.child_id,
                "parent_id": request.parent_id,
                "input_type": None,
                "tool_results": None,
            }

            # Stream events from LangGraph
            async for event in graph.astream_events(initial_state, version="v2"):
                kind = event.get("event")

                if kind == "on_chat_model_stream":
                    content = event["data"]["chunk"].content
                    if content:
                        data = json.dumps(
                            {"type": "token", "content": content},
                            ensure_ascii=False,
                        )
                        yield f"data: {data}\n\n"

                elif kind == "on_tool_start":
                    tool_name = event.get("name", "unknown")
                    data = json.dumps(
                        {"type": "tool_start", "tool": tool_name},
                        ensure_ascii=False,
                    )
                    yield f"data: {data}\n\n"

                elif kind == "on_tool_end":
                    tool_name = event.get("name", "unknown")
                    data = json.dumps(
                        {"type": "tool_end", "tool": tool_name},
                        ensure_ascii=False,
                    )
                    yield f"data: {data}\n\n"

            yield f"data: {json.dumps({'type': 'done'})}\n\n"

        except Exception as e:
            error_data = json.dumps({"type": "error", "content": str(e)})
            yield f"data: {error_data}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/api/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint for monitoring and container orchestration."""
    return HealthResponse()


@app.get("/api/tools", response_model=list[ToolInfo])
async def list_tools():
    """List all tools available to the agent."""
    from agents.tools import ALL_TOOLS

    return [
        ToolInfo(
            name=tool.name,
            description=tool.description or "",
        )
        for tool in ALL_TOOLS
    ]


# ─────────────────────────────────────────────────────────────────
# Entry point (run directly with: python -m api.main)
# ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn

    cfg = get_settings()
    uvicorn.run(
        "api.main:app",
        host=cfg.API_HOST,
        port=cfg.API_PORT,
        reload=True,
    )
