"""
LangGraph workflow definition - state, nodes, and edges.

Graph architecture:
  START -> classify_input -> agent_process -> (tool_node -> agent_process)* -> END

The agent loop continues until the LLM produces a response without tool calls.

State persists across nodes:
  - messages:    Full conversation history (auto-merged by LangGraph)
  - persona:     "consultant" (parent mode) or "tutor" (student mode)
  - child_id:    ID of the student being discussed (if any)
  - parent_id:   ID of the authenticated parent user (if any)
  - input_type:  Classified intent (report/recommend/consult/explain/chat)
  - tool_results: Raw string results from the last tool call batch
"""

from __future__ import annotations

from typing import Annotated, Any, Literal, Optional, TypedDict

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode

from agents.prompts import (
    CLASSIFIER_PROMPT,
    CONSULTANT_SYSTEM_PROMPT,
    TUTOR_SYSTEM_PROMPT,
)
from agents.tools import ALL_TOOLS
from config import get_settings


# ─────────────────────────────────────────────────────────────────
# Graph state definition
# ─────────────────────────────────────────────────────────────────


class AgentState(TypedDict):
    """Shared state object passed between all graph nodes."""

    # Conversation messages - managed automatically by LangGraph (add_messages reducer)
    messages: Annotated[list, add_messages]

    # Context metadata
    persona: str                   # "consultant" or "tutor"
    child_id: Optional[str]        # Student UUID currently in focus
    parent_id: Optional[str]       # Parent user UUID
    input_type: Optional[str]      # Classified intent: report|recommend|consult|explain|chat
    tool_results: Optional[str]    # Accumulated tool output (for context injection)


# ─────────────────────────────────────────────────────────────────
# LLM factory functions
# ─────────────────────────────────────────────────────────────────


def _get_fast_llm() -> ChatGoogleGenerativeAI:
    """Return a fast, low-cost LLM instance for classification tasks."""
    settings = get_settings()
    return ChatGoogleGenerativeAI(
        model=settings.MODEL_FAST,
        google_api_key=settings.GOOGLE_API_KEY,
        max_output_tokens=256,
        temperature=0,
    )


def _get_smart_llm() -> ChatGoogleGenerativeAI:
    """Return a more capable LLM instance for analysis and generation."""
    settings = get_settings()
    return ChatGoogleGenerativeAI(
        model=settings.MODEL_SMART,
        google_api_key=settings.GOOGLE_API_KEY,
        max_output_tokens=2048,
        temperature=0.3,
    )


def _get_tool_llm() -> ChatGoogleGenerativeAI:
    """Return an LLM instance bound to all available tools.

    The LLM will automatically decide which tools to call based on context.
    """
    settings = get_settings()
    llm = ChatGoogleGenerativeAI(
        model=settings.MODEL_SMART,
        google_api_key=settings.GOOGLE_API_KEY,
        max_output_tokens=2048,
        temperature=0.1,
    )
    return llm.bind_tools(ALL_TOOLS)


# ─────────────────────────────────────────────────────────────────
# Node 1: classify_input
# ─────────────────────────────────────────────────────────────────


async def classify_input(state: AgentState) -> dict[str, Any]:
    """Classify the user's intent to determine which processing path to follow.

    Reads the last user message and uses a fast LLM to classify it into one of:
    report, recommend, consult, import, explain, or chat.

    Returns:
        dict with 'input_type' key set to the classified intent string.
    """
    llm = _get_fast_llm()

    # Find the most recent human message
    last_msg = ""
    for msg in reversed(state["messages"]):
        if isinstance(msg, HumanMessage):
            last_msg = msg.content
            break

    prompt = CLASSIFIER_PROMPT.format(message=last_msg)
    response = await llm.ainvoke([HumanMessage(content=prompt)])

    input_type = response.content.strip().lower()
    valid_types = {"report", "recommend", "consult", "import", "explain", "chat"}
    if input_type not in valid_types:
        input_type = "chat"

    return {"input_type": input_type}


# ─────────────────────────────────────────────────────────────────
# Node 2: agent_process
# ─────────────────────────────────────────────────────────────────


async def agent_process(state: AgentState) -> dict[str, Any]:
    """Main agent node: LLM reasons, decides which tools to call (if any).

    Selects system prompt based on persona (consultant vs tutor).
    Injects available context (child_id, parent_id, input_type) into the prompt.
    The LLM may emit tool_calls in its response, which triggers the tool node.

    Returns:
        dict with 'messages' key containing the LLM response.
    """
    # Choose system prompt based on current persona
    persona = state.get("persona", "consultant")
    system_prompt = (
        CONSULTANT_SYSTEM_PROMPT if persona == "consultant" else TUTOR_SYSTEM_PROMPT
    )

    # Append relevant context to the system prompt
    context_note = ""
    if state.get("child_id"):
        context_note += f"\n\n[Context: child_id = {state['child_id']}]"
    if state.get("parent_id"):
        context_note += f"\n[Context: parent_id = {state['parent_id']}]"
    if state.get("input_type"):
        context_note += f"\n[Request type: {state['input_type']}]"

    llm = _get_tool_llm()

    messages = [SystemMessage(content=system_prompt + context_note)] + state["messages"]
    response = await llm.ainvoke(messages)

    return {"messages": [response]}


# ─────────────────────────────────────────────────────────────────
# Node 3: tool_node (prebuilt)
# ─────────────────────────────────────────────────────────────────

# LangGraph's ToolNode automatically handles calling the tools requested by the LLM.
tool_node = ToolNode(ALL_TOOLS)


# ─────────────────────────────────────────────────────────────────
# Edge routing logic
# ─────────────────────────────────────────────────────────────────


def should_use_tools(state: AgentState) -> Literal["tools", "end"]:
    """Decide whether to route to tool execution or end the agent loop.

    If the last LLM response contains tool_calls, route to the tool node.
    Otherwise, the agent has produced a final answer - route to END.
    """
    last_message = state["messages"][-1]
    if isinstance(last_message, AIMessage) and last_message.tool_calls:
        return "tools"
    return "end"


# ─────────────────────────────────────────────────────────────────
# Graph construction
# ─────────────────────────────────────────────────────────────────


def build_graph() -> StateGraph:
    """Build and compile the LangGraph agent workflow.

    Flow:
      START -> classify -> agent -> (tools -> agent)* -> END

    The agent-tools loop continues until the LLM stops calling tools
    and returns a plain text response.
    """
    graph = StateGraph(AgentState)

    # Register nodes
    graph.add_node("classify", classify_input)
    graph.add_node("agent", agent_process)
    graph.add_node("tools", tool_node)

    # Static edges
    graph.add_edge(START, "classify")
    graph.add_edge("classify", "agent")

    # Conditional edge: agent -> tools OR end
    graph.add_conditional_edges(
        "agent",
        should_use_tools,
        {
            "tools": "tools",
            "end": END,
        },
    )

    # After tool execution, return to agent for processing results
    graph.add_edge("tools", "agent")

    return graph.compile()


# ─────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────

# Compiled graph singleton - initialized lazily on first request
_graph = None


def get_graph():
    """Return the compiled LangGraph instance (singleton)."""
    global _graph
    if _graph is None:
        _graph = build_graph()
    return _graph


async def run_agent(
    message: str,
    persona: str = "consultant",
    child_id: Optional[str] = None,
    parent_id: Optional[str] = None,
    conversation_history: Optional[list[dict]] = None,
) -> str:
    """Run the agent and return the final response text.

    Entry point called by the FastAPI endpoint.

    Args:
        message:              The current user message.
        persona:              "consultant" (parent) or "tutor" (student).
        child_id:             UUID of the student in context (optional).
        parent_id:            UUID of the parent user (optional).
        conversation_history: Previous turns as [{"role": ..., "content": ...}].

    Returns:
        The agent's final response as a plain string.
    """
    graph = get_graph()

    # Reconstruct message history from prior turns
    messages = []
    if conversation_history:
        for msg in conversation_history:
            if msg["role"] == "user":
                messages.append(HumanMessage(content=msg["content"]))
            elif msg["role"] == "assistant":
                messages.append(AIMessage(content=msg["content"]))

    # Append the current user message
    messages.append(HumanMessage(content=message))

    initial_state: AgentState = {
        "messages": messages,
        "persona": persona,
        "child_id": child_id,
        "parent_id": parent_id,
        "input_type": None,
        "tool_results": None,
    }

    result = await graph.ainvoke(initial_state)

    # Extract the final AI response
    last_message = result["messages"][-1]
    if isinstance(last_message, AIMessage):
        return last_message.content

    return "Sorry, an error occurred. Please try again."
