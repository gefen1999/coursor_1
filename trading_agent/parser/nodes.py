import os

from dotenv import load_dotenv

from core import ActionType, ComparisonOperator, LogicMode, NumericCondition, TradingQuery
from parser.graph_state import ParserState
from parser.prompts import SYSTEM_PROMPT, VALIDATION_PROMPT
from parser.schema import ParsedQuery, ValidationAssessment


def _call_ollama(raw_text: str) -> ParsedQuery:
    from ollama import Client

    host = os.getenv("OLLAMA_HOST", "http://localhost:11434")
    model = os.getenv("OLLAMA_MODEL", "llama3.1")

    client = Client(host=host)
    response = client.chat(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": raw_text},
        ],
        format=ParsedQuery.model_json_schema(),
    )
    content = response["message"]["content"]
    return ParsedQuery.model_validate_json(content)


def _call_ollama_validation(raw_text: str, parsed_query: ParsedQuery) -> ValidationAssessment:
    from ollama import Client

    host = os.getenv("OLLAMA_HOST", "http://localhost:11434")
    model = os.getenv("OLLAMA_MODEL", "llama3.1")

    user_content = (
        f"Original query:\n{raw_text}\n\n"
        f"Parsed JSON:\n{parsed_query.model_dump_json(indent=2)}"
    )

    client = Client(host=host)
    response = client.chat(
        model=model,
        messages=[
            {"role": "system", "content": VALIDATION_PROMPT},
            {"role": "user", "content": user_content},
        ],
        format=ValidationAssessment.model_json_schema(),
    )
    content = response["message"]["content"]
    return ValidationAssessment.model_validate_json(content)


def parse_node(state: ParserState) -> ParserState:
    """
    Sends state["raw_text"] + the system prompt (from prompts.py) to the
    local LLM (via Ollama), requesting structured output per the
    ParsedQuery schema. Updates and returns state with a fully populated
    parsed_query.
    """
    load_dotenv()
    raw_text = state["raw_text"]

    try:
        parsed_query = _call_ollama(raw_text)
    except Exception as exc:
        state["validation_errors"].append(f"LLM parse failed: {exc}")
        return state

    state["parsed_query"] = parsed_query
    return state


def _build_trading_query(state: ParserState, parsed: ParsedQuery) -> TradingQuery:
    conditions = [
        NumericCondition(
            ticker=cond.ticker.strip(),
            operator=ComparisonOperator(cond.operator),
            value=cond.value,
        )
        for cond in parsed.conditions
    ]

    return TradingQuery(
        action=ActionType(parsed.action),
        ticker=parsed.ticker.strip(),
        conditions=conditions,
        logic=LogicMode(parsed.logic),
        raw_text=state["raw_text"],
    )


def validate_node(state: ParserState) -> ParserState:
    """
    Phase A: fast structural checks on parsed_query.
    Phase B: semantic validation via LLM (ValidationAssessment).
    Phase C: map to TradingQuery or set clarification / error flags.
    """
    parsed = state.get("parsed_query")
    if parsed is None:
        if not state["validation_errors"]:
            state["validation_errors"].append("No parsed query to validate")
        return state

    errors: list[str] = []

    if not parsed.ticker or not parsed.ticker.strip():
        errors.append("ticker must be a non-empty string")

    if not parsed.conditions:
        errors.append("conditions list must not be empty")

    for i, cond in enumerate(parsed.conditions):
        if not cond.ticker or not cond.ticker.strip():
            errors.append(f"condition {i}: ticker must be a non-empty string")

    if errors:
        state["validation_errors"].extend(errors)
        return state

    try:
        assessment = _call_ollama_validation(state["raw_text"], parsed)
    except Exception as exc:
        state["validation_errors"].append(f"LLM validation failed: {exc}")
        return state

    if assessment.needs_clarification:
        state["needs_clarification"] = True
        state["clarification_question"] = assessment.clarification_question
        state["clarification_reason"] = assessment.reason
        return state

    if not assessment.is_valid:
        state["validation_errors"].extend(
            assessment.issues or ["Parsed query failed semantic validation"]
        )
        return state

    state["trading_query"] = _build_trading_query(state, parsed)
    state["needs_clarification"] = False
    state["clarification_question"] = None
    state["clarification_reason"] = None
    return state
