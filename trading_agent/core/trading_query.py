from dataclasses import dataclass
from enum import Enum

from core.condition_engine import Condition


class ActionType(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


@dataclass
class TradingQuery:
    """
    The output of the NL Parser (Layer 3, built later). Does not "execute"
    anything itself - just a structural description of what the user wants.
    """
    action: ActionType
    ticker: str
    condition: Condition
    required_tickers: list[str]
    raw_text: str
