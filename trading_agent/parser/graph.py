from collections.abc import Callable
from dataclasses import dataclass

from langgraph.graph import END, START, StateGraph

from core import TradingQuery
from parser.graph_state import ParserState
from parser.nodes import parse_node, validate_node


def build_parser_graph():
    """
    Builds and returns the compiled graph:
    START -> parse_node -> validate_node -> END

    Clarification looping is handled by parse_trading_query outside the graph.
    """
    graph = StateGraph(ParserState)
    graph.add_node("parse", parse_node)
    graph.add_node("validate", validate_node)
    graph.add_edge(START, "parse")
    graph.add_edge("parse", "validate")
    graph.add_edge("validate", END)
    return graph.compile()


@dataclass
class ParseOutcome:
    query: TradingQuery | None
    needs_clarification: bool
    clarification_question: str | None
    errors: list[str]


def _build_clarified_text(
    raw_text: str,
    history: list[tuple[str, str]],
    latest_question: str,
    latest_answer: str,
) -> str:
    history = history + [(latest_question, latest_answer)]
    lines = [raw_text, "", "Clarifications:"]
    for question, answer in history:
        lines.append(f"Q: {question}")
        lines.append(f"A: {answer}")
    return "\n".join(lines)


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


def parse_trading_query(
    raw_text: str,
    *,
    ask_user: Callable[[str], str] | None = None,
    max_rounds: int = 3,
) -> TradingQuery:
    """
    Runs the parser graph on raw_text, optionally looping to collect user
    clarifications when validate_node sets needs_clarification.
    """
    graph = build_parser_graph()
    history: list[tuple[str, str]] = []
    current_text = raw_text

    for _ in range(max_rounds):
        result = graph.invoke(_initial_state(current_text, history))

        if result["trading_query"] is not None:
            return result["trading_query"]

        if result["needs_clarification"]:
            question = result.get("clarification_question")
            if not question:
                raise ValueError("Clarification needed but no question was provided")
            if ask_user is None:
                raise ValueError(question)
            answer = ask_user(question)
            history.append((question, answer))
            current_text = _build_clarified_text(raw_text, history[:-1], question, answer)
            continue

        if result["validation_errors"]:
            raise ValueError("; ".join(result["validation_errors"]))

        raise ValueError("Failed to produce a TradingQuery")

    raise ValueError("Too many clarification rounds")
