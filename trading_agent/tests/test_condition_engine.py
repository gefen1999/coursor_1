import unittest

from core.condition_engine import (
    AndCondition,
    ComparisonOperator,
    ConditionEngine,
    NotCondition,
    NumericCondition,
    OrCondition,
)
from core.trading_query import ActionType, TradingQuery
from data.base import DataFeed
from data.market_state import MarketState, TickerSnapshot


def make_market_state(
    *,
    prices: dict[str, float] | None = None,
    volumes: dict[str, float] | None = None,
    computed_features: dict[str, float] | None = None,
) -> MarketState:
    prices = prices or {}
    volumes = volumes or {}
    tickers = set(prices) | set(volumes)
    current = {
        ticker: TickerSnapshot(
            price=prices.get(ticker, 0.0),
            volume=volumes.get(ticker, 0.0),
        )
        for ticker in tickers
    }
    return MarketState(
        current=current,
        computed_features=computed_features or {},
    )


class FakeDataFeed(DataFeed):
    def __init__(self, market_state: MarketState) -> None:
        self._market_state = market_state
        self.last_tickers: list[str] | None = None

    def get_market_state(self, tickers: list[str]) -> MarketState:
        self.last_tickers = tickers
        return self._market_state


class TestNumericCondition(unittest.TestCase):
    def test_evaluate_price_true(self) -> None:
        condition = NumericCondition(
            field="AAPL.price",
            operator=ComparisonOperator.GREATER_THAN,
            value=100.0,
        )
        market_state = make_market_state(prices={"AAPL": 150.0})

        self.assertTrue(condition.evaluate(market_state))

    def test_evaluate_price_false(self) -> None:
        condition = NumericCondition(
            field="AAPL.price",
            operator=ComparisonOperator.GREATER_THAN,
            value=200.0,
        )
        market_state = make_market_state(prices={"AAPL": 150.0})

        self.assertFalse(condition.evaluate(market_state))

    def test_evaluate_computed_feature(self) -> None:
        condition = NumericCondition(
            field="AAPL.RSI_14",
            operator=ComparisonOperator.LESS_THAN,
            value=30.0,
        )
        market_state = make_market_state(
            computed_features={"AAPL.RSI_14": 25.0},
        )

        self.assertTrue(condition.evaluate(market_state))

        market_state_high_rsi = make_market_state(
            computed_features={"AAPL.RSI_14": 45.0},
        )
        self.assertFalse(condition.evaluate(market_state_high_rsi))

    def test_evaluate_missing_field_returns_false(self) -> None:
        condition = NumericCondition(
            field="MSFT.price",
            operator=ComparisonOperator.EQUAL,
            value=300.0,
        )
        market_state = make_market_state(prices={"AAPL": 150.0})

        self.assertFalse(condition.evaluate(market_state))

        missing_feature = NumericCondition(
            field="AAPL.RSI_14",
            operator=ComparisonOperator.EQUAL,
            value=50.0,
        )
        self.assertFalse(missing_feature.evaluate(market_state))


class TestCompositeConditions(unittest.TestCase):
    def test_and_condition(self) -> None:
        true_child = NumericCondition(
            field="AAPL.price",
            operator=ComparisonOperator.GREATER_THAN,
            value=100.0,
        )
        false_child = NumericCondition(
            field="AAPL.price",
            operator=ComparisonOperator.GREATER_THAN,
            value=200.0,
        )
        market_state = make_market_state(prices={"AAPL": 150.0})

        self.assertTrue(
            AndCondition(children=[true_child, true_child]).evaluate(market_state)
        )
        self.assertFalse(
            AndCondition(children=[true_child, false_child]).evaluate(market_state)
        )

    def test_or_condition(self) -> None:
        true_child = NumericCondition(
            field="AAPL.price",
            operator=ComparisonOperator.GREATER_THAN,
            value=100.0,
        )
        false_child = NumericCondition(
            field="AAPL.price",
            operator=ComparisonOperator.GREATER_THAN,
            value=200.0,
        )
        market_state = make_market_state(prices={"AAPL": 150.0})

        self.assertTrue(
            OrCondition(children=[false_child, true_child]).evaluate(market_state)
        )
        self.assertFalse(
            OrCondition(children=[false_child, false_child]).evaluate(market_state)
        )

    def test_not_condition(self) -> None:
        child = NumericCondition(
            field="AAPL.price",
            operator=ComparisonOperator.GREATER_THAN,
            value=100.0,
        )
        market_state = make_market_state(prices={"AAPL": 150.0})

        self.assertFalse(NotCondition(child=child).evaluate(market_state))
        self.assertTrue(
            NotCondition(
                child=NumericCondition(
                    field="AAPL.price",
                    operator=ComparisonOperator.GREATER_THAN,
                    value=200.0,
                )
            ).evaluate(market_state)
        )

    def test_nested_or_and(self) -> None:
        market_state = make_market_state(prices={"AAPL": 150.0, "MSFT": 80.0})

        condition = OrCondition(
            children=[
                AndCondition(
                    children=[
                        NumericCondition(
                            field="AAPL.price",
                            operator=ComparisonOperator.GREATER_THAN,
                            value=200.0,
                        ),
                        NumericCondition(
                            field="MSFT.price",
                            operator=ComparisonOperator.GREATER_THAN,
                            value=100.0,
                        ),
                    ]
                ),
                NumericCondition(
                    field="AAPL.price",
                    operator=ComparisonOperator.GREATER_THAN,
                    value=100.0,
                ),
            ]
        )

        self.assertTrue(condition.evaluate(market_state))


class TestDescribe(unittest.TestCase):
    def test_numeric_describe(self) -> None:
        condition = NumericCondition(
            field="AAPL.price",
            operator=ComparisonOperator.GREATER_THAN,
            value=100.0,
        )
        self.assertEqual(condition.describe(), "AAPL.price > 100.0")

    def test_and_describe(self) -> None:
        condition = AndCondition(
            children=[
                NumericCondition(
                    field="AAPL.price",
                    operator=ComparisonOperator.GREATER_THAN,
                    value=100.0,
                ),
                NumericCondition(
                    field="MSFT.volume",
                    operator=ComparisonOperator.LESS_THAN,
                    value=1_000_000.0,
                ),
            ]
        )
        self.assertEqual(
            condition.describe(),
            "(AAPL.price > 100.0 AND MSFT.volume < 1000000.0)",
        )

    def test_or_describe(self) -> None:
        condition = OrCondition(
            children=[
                NumericCondition(
                    field="AAPL.price",
                    operator=ComparisonOperator.EQUAL,
                    value=150.0,
                ),
                NumericCondition(
                    field="GOOG.price",
                    operator=ComparisonOperator.EQUAL,
                    value=140.0,
                ),
            ]
        )
        self.assertEqual(
            condition.describe(),
            "(AAPL.price == 150.0 OR GOOG.price == 140.0)",
        )

    def test_not_describe(self) -> None:
        condition = NotCondition(
            child=NumericCondition(
                field="AAPL.price",
                operator=ComparisonOperator.LESS_THAN,
                value=50.0,
            )
        )
        self.assertEqual(condition.describe(), "NOT (AAPL.price < 50.0)")

    def test_nested_describe(self) -> None:
        condition = OrCondition(
            children=[
                AndCondition(
                    children=[
                        NumericCondition(
                            field="AAPL.price",
                            operator=ComparisonOperator.GREATER_THAN,
                            value=100.0,
                        ),
                        NumericCondition(
                            field="MSFT.price",
                            operator=ComparisonOperator.LESS_THAN,
                            value=300.0,
                        ),
                    ]
                ),
                NotCondition(
                    child=NumericCondition(
                        field="GOOG.price",
                        operator=ComparisonOperator.EQUAL,
                        value=0.0,
                    )
                ),
            ]
        )
        self.assertEqual(
            condition.describe(),
            "((AAPL.price > 100.0 AND MSFT.price < 300.0) OR NOT (GOOG.price == 0.0))",
        )


class TestConditionEngine(unittest.TestCase):
    def test_check_end_to_end(self) -> None:
        market_state = make_market_state(
            prices={"AAPL": 150.0, "USO": 60.0},
            computed_features={"AAPL.RSI_14": 25.0},
        )
        feed = FakeDataFeed(market_state)
        engine = ConditionEngine()

        query = TradingQuery(
            action=ActionType.BUY,
            ticker="AAPL",
            condition=AndCondition(
                children=[
                    NumericCondition(
                        field="AAPL.price",
                        operator=ComparisonOperator.GREATER_THAN,
                        value=100.0,
                    ),
                    NumericCondition(
                        field="USO.price",
                        operator=ComparisonOperator.LESS_THAN,
                        value=70.0,
                    ),
                ]
            ),
            required_tickers=["AAPL", "USO"],
            raw_text="Buy AAPL when price > 100 and oil < 70",
        )

        self.assertTrue(engine.check(query, feed))
        self.assertEqual(feed.last_tickers, ["AAPL", "USO"])

    def test_check_returns_false_when_condition_fails(self) -> None:
        market_state = make_market_state(prices={"AAPL": 90.0})
        feed = FakeDataFeed(market_state)
        engine = ConditionEngine()

        query = TradingQuery(
            action=ActionType.SELL,
            ticker="AAPL",
            condition=NumericCondition(
                field="AAPL.price",
                operator=ComparisonOperator.GREATER_THAN,
                value=100.0,
            ),
            required_tickers=["AAPL"],
            raw_text="Sell AAPL when price > 100",
        )

        self.assertFalse(engine.check(query, feed))


if __name__ == "__main__":
    unittest.main()
