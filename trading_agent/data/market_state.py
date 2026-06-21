from dataclasses import dataclass


@dataclass
class TickerSnapshot:
    price: float
    volume: float


@dataclass
class MarketState:
    current: dict[str, TickerSnapshot]
    computed_features: dict[str, float]
