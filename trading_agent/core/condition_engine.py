from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum

from data.base import DataFeed
from data.market_state import MarketState


class ComparisonOperator(str, Enum):
    GREATER_THAN = ">"
    LESS_THAN = "<"
    GREATER_OR_EQUAL = ">="
    LESS_OR_EQUAL = "<="
    EQUAL = "=="


class Condition(ABC):
    """Base interface - every condition (leaf or composite) knows how to
    evaluate and describe itself."""

    @abstractmethod
    def evaluate(self, market_state: MarketState) -> bool:
        """Pure function - no side effects, no dependency on prior calls."""
        ...

    @abstractmethod
    def describe(self) -> str:
        """Human-readable description, will be used later by a confirmation
        layer (not part of this project yet)."""
        ...


@dataclass
class NumericCondition(Condition):
    """
    Deterministic condition on a numeric value - raw (price/volume) or
    derived (computed feature). `field` is a string in "TICKER.metric"
    format, e.g. "AAPL.price" or "AAPL.RSI_14".
    """
    field: str
    operator: ComparisonOperator
    value: float

    def evaluate(self, market_state: MarketState) -> bool:
        ticker, metric = self.field.split(".", 1)

        if metric in ("price", "volume"):
            snapshot = market_state.current.get(ticker)
            if snapshot is None:
                return False
            actual = snapshot.price if metric == "price" else snapshot.volume
        else:
            if self.field not in market_state.computed_features:
                return False
            actual = market_state.computed_features[self.field]

        match self.operator:
            case ComparisonOperator.GREATER_THAN:
                return actual > self.value
            case ComparisonOperator.LESS_THAN:
                return actual < self.value
            case ComparisonOperator.GREATER_OR_EQUAL:
                return actual >= self.value
            case ComparisonOperator.LESS_OR_EQUAL:
                return actual <= self.value
            case ComparisonOperator.EQUAL:
                return actual == self.value

    def describe(self) -> str:
        return f"{self.field} {self.operator.value} {self.value}"


@dataclass
class AndCondition(Condition):
    children: list[Condition]

    def evaluate(self, market_state: MarketState) -> bool:
        return all(child.evaluate(market_state) for child in self.children)

    def describe(self) -> str:
        return "(" + " AND ".join(child.describe() for child in self.children) + ")"


@dataclass
class OrCondition(Condition):
    children: list[Condition]

    def evaluate(self, market_state: MarketState) -> bool:
        return any(child.evaluate(market_state) for child in self.children)

    def describe(self) -> str:
        return "(" + " OR ".join(child.describe() for child in self.children) + ")"


@dataclass
class NotCondition(Condition):
    child: Condition

    def evaluate(self, market_state: MarketState) -> bool:
        return not self.child.evaluate(market_state)

    def describe(self) -> str:
        return f"NOT ({self.child.describe()})"


class ConditionEngine:
    """
    Intentionally thin orchestration layer - no new logic, just coordination
    between DataFeed (Layer 1) and Condition.evaluate() (above).
    """

    def check(self, query: "TradingQuery", feed: DataFeed) -> bool:
        market_state = feed.get_market_state(query.required_tickers)
        return query.condition.evaluate(market_state)
