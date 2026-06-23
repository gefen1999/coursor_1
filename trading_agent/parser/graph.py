from dataclasses import dataclass
from typing import Callable

from langgraph.graph import END, START, StateGraph

from core import TradingQuery
from parser.graph_state import ParserState
from parser.nodes import parse_node, validate_node


@dataclass
class ParseOutcome:
    query: TradingQuery | None
    needs_clarification: bool
    clarification_question: str | None
    errors: list[str]


def build_parser_graph():
    """
    Builds and returns the compiled graph:
    START -> parse_node -> validate_node -> END

    Clarification looping lives in parse_trading_query, not inside the graph.
    """
    graph = StateGraph(ParserState)
    graph.add_node("parse", parse_node)
    graph.add_node("validate", validate_node)
    graph.add_edge(START, "parse")
    graph.add_edge("parse", "validate")
    graph.add_edge("validate", END)
    return graph.compile()


def _merge_clarifications(raw_text: str, history: list[tuple[str, str]]) -> str:
    if not history:
        return raw_text
    parts = [raw_text]
    for question, answer in history:
        parts.append(f"Clarification Q: {question}\nClarification A: {answer}")
    return "\n\n".join(parts)


def _initial_state(raw_text: str, history: list[tuple[str, str]]) -> ParserState:
    return {
        "raw_text": raw_text,
        "parsed_query": None,
        "validation_errors": [],
        "needs_clarification": False,
        "clarification_question": None,
        "clarification_reason": None,
        "clarification_history": history,
        "trading_query": None,
    }


def parse_trading_query_once(
    raw_text: str,
    *,
    history: list[tuple[str, str]] | None = None,
) -> ParseOutcome:
    """Run a single parse+validate pass and return structured outcome."""
    graph = build_parser_graph()
    clarification_history = history or []
    current_text = _merge_clarifications(raw_text, clarification_history)
    result = graph.invoke(_initial_state(current_text, clarification_history))

    return ParseOutcome(
        query=result["trading_query"],
        needs_clarification=result["needs_clarification"],
        clarification_question=result.get("clarification_question"),
        errors=list(result["validation_errors"]),
    )


def parse_trading_query(
    raw_text: str,
    *,
    ask_user: Callable[[str], str] | None = None,
    max_rounds: int = 3,
) -> TradingQuery:
    """
    Entry point — runs the graph on raw_text, optionally looping to collect
    clarifications when validate_node sets needs_clarification.
    """
    if ask_user is None:
        ask_user = input

    graph = build_parser_graph()
    history: list[tuple[str, str]] = []

    for _ in range(max_rounds):
        current_text = _merge_clarifications(raw_text, history)
        result = graph.invoke(_initial_state(current_text, history))

        if result["trading_query"] is not None:
            return result["trading_query"]

        if result["needs_clarification"]:
            question = result.get("clarification_question") or "Please clarify your query."
            answer = ask_user(question)
            history.append((question, answer))
            continue

        if result["validation_errors"]:
            raise ValueError("; ".join(result["validation_errors"]))
        raise ValueError("Failed to produce a TradingQuery")

    raise ValueError("Too many clarification rounds")
