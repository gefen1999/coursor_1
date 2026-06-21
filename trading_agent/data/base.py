from abc import ABC, abstractmethod

from data.market_state import MarketState


class DataFeed(ABC):
    @abstractmethod
    def get_market_state(self, tickers: list[str]) -> MarketState:
        ...
