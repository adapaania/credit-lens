"""LangGraph agent: chooses between filing retrieval and Tavily search.

Uses a MemorySaver checkpointer keyed by the frontend-generated thread_id,
so follow-up questions in the same thread carry conversation history. The
frontend's filing_id is independent of thread_id (a user can switch filings
mid-thread), so it travels inline with each new message rather than being
baked into a one-time system prompt.
"""

import json
import re
from typing import Annotated, TypedDict

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition

from app.agent.prompts import AGENT_SYSTEM_PROMPT
from app.agent.tools import retrieve_filing, tavily_search
from app.config import get_settings

TOOLS = [retrieve_filing, tavily_search]


class AgentState(TypedDict):
    messages: Annotated[list, add_messages]


class Citation(TypedDict):
    page: int
    section: str
    snippet: str


class Answer(TypedDict):
    answer: str
    citations: list[Citation]


_model: ChatOpenAI | None = None


def _get_model() -> ChatOpenAI:
    global _model
    if _model is None:
        settings = get_settings()
        _model = ChatOpenAI(
            model=settings.chat_model,
            api_key=settings.openrouter_api_key,
            base_url=settings.openrouter_base_url,
            temperature=0,
        ).bind_tools(TOOLS)
    return _model


def _agent_node(state: AgentState) -> dict:
    messages = state["messages"]
    if not any(isinstance(m, SystemMessage) for m in messages):
        messages = [SystemMessage(content=AGENT_SYSTEM_PROMPT), *messages]
    response = _get_model().invoke(messages)
    return {"messages": [response]}


_graph = None


def _build_graph():
    graph = StateGraph(AgentState)
    graph.add_node("agent", _agent_node)
    graph.add_node("tools", ToolNode(TOOLS))
    graph.set_entry_point("agent")
    graph.add_conditional_edges("agent", tools_condition, {"tools": "tools", END: END})
    graph.add_edge("tools", "agent")
    return graph.compile(checkpointer=MemorySaver())


def get_graph():
    global _graph
    if _graph is None:
        _graph = _build_graph()
    return _graph


_PAGE_MENTION_RE = re.compile(r"pages?\s+(\d[\d,\-\s]*\d|\d+)", re.IGNORECASE)
_NUMBER_RE = re.compile(r"\d+")


def _mentioned_pages(text: str) -> set[int]:
    """Page numbers actually mentioned in the answer text.

    Handles "page 36", "pages 26, 60, 136", and ranges like "pages 59, 126-127".
    """
    pages: set[int] = set()
    for match in _PAGE_MENTION_RE.finditer(text):
        pages.update(int(n) for n in _NUMBER_RE.findall(match.group(1)))
    return pages


def _citations_by_filing_and_page(messages: list) -> dict[tuple[str, int], Citation]:
    """Every retrieve_filing chunk seen anywhere in the conversation so far.

    Keyed by (filing_id, page) rather than just page, since a thread can
    query more than one filing if the user switches the filing selector.
    """
    seen: dict[tuple[str, int], Citation] = {}
    for message in messages:
        if not isinstance(message, ToolMessage) or message.name != "retrieve_filing":
            continue
        try:
            payload = json.loads(message.content)
        except (TypeError, json.JSONDecodeError):
            continue
        for chunk in payload.get("chunks", []):
            key = (chunk["filing_id"], chunk["page"])
            if key not in seen:
                seen[key] = {
                    "page": chunk["page"],
                    "section": chunk["section"],
                    "snippet": chunk["text"][:300],
                }
    return seen


def run_agent(message: str, filing_id: str, thread_id: str) -> Answer:
    graph = get_graph()
    config = {"configurable": {"thread_id": thread_id}}

    prior_state = graph.get_state(config)
    prior_count = len(prior_state.values.get("messages", [])) if prior_state.values else 0

    augmented_message = f"[Selected filing_id: {filing_id}]\n\n{message}"
    result = graph.invoke({"messages": [HumanMessage(content=augmented_message)]}, config=config)

    new_messages = result["messages"][prior_count:]
    final_answers = [m for m in new_messages if isinstance(m, AIMessage) and m.content]
    answer_text = final_answers[-1].content if final_answers else ""

    # Citations are matched by page number actually mentioned in the final
    # answer, searched across the whole conversation's retrieve_filing
    # results - not just this turn's - since a memory-grounded follow-up
    # may not call the tool again but still cites a page from earlier.
    available = _citations_by_filing_and_page(result["messages"])
    mentioned_pages = _mentioned_pages(answer_text)
    citations = [
        citation for (fid, page), citation in available.items() if fid == filing_id and page in mentioned_pages
    ]

    return {"answer": answer_text, "citations": citations}
