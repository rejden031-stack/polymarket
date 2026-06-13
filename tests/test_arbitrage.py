from decimal import Decimal
from bot.config import ArbitrageConfig
from bot.arbitrage.engine import ArbitrageEngine
from bot.models import OrderBook, OrderBookLevel, Portfolio, Position, SignalAction, Side


def make_book(market_id: str, token_id: str, bid_price: str, bid_size: str,
              ask_price: str, ask_size: str) -> OrderBook:
    return OrderBook(
        market_id=market_id,
        token_id=token_id,
        bids=[OrderBookLevel(Decimal(bid_price), Decimal(bid_size))],
        asks=[OrderBookLevel(Decimal(ask_price), Decimal(ask_size))],
    )


def test_complete_set_arb_profitable():
    config = ArbitrageConfig(min_profit_pct=0.3)
    engine = ArbitrageEngine(config)

    yes_book = make_book("m1", "token_yes", "0.30", "100", "0.40", "100")
    no_book = make_book("m1", "token_no", "0.30", "100", "0.40", "100")
    portfolio = Portfolio(balance=Decimal("1000"))

    signal = engine.find_complete_set_arb(yes_book, no_book, portfolio)

    assert signal is not None
    assert signal.action == SignalAction.BUY
    assert signal.strategy.value == "arbitrage"
    assert signal.confidence == 1.0
    assert signal.expected_value >= 0.3
    assert signal.metadata["no_token_id"] == "token_no"


def test_complete_set_arb_not_profitable():
    config = ArbitrageConfig(min_profit_pct=0.3)
    engine = ArbitrageEngine(config)

    yes_book = make_book("m1", "token_yes", "0.45", "100", "0.52", "100")
    no_book = make_book("m1", "token_no", "0.45", "100", "0.47", "100")
    portfolio = Portfolio(balance=Decimal("1000"))

    signal = engine.find_complete_set_arb(yes_book, no_book, portfolio)

    assert signal is None


def test_complete_set_arb_insufficient_depth():
    config = ArbitrageConfig(min_profit_pct=0.3, max_position_size_pct=2.0)
    engine = ArbitrageEngine(config)

    yes_book = make_book("m1", "token_yes", "0.40", "0.5", "0.41", "0.5")
    no_book = make_book("m1", "token_no", "0.40", "0.5", "0.41", "0.5")
    portfolio = Portfolio(balance=Decimal("1000"))

    signal = engine.find_complete_set_arb(yes_book, no_book, portfolio)

    assert signal is None or signal.size < yes_book.min_order_size


def test_neg_risk_arbitrage():
    config = ArbitrageConfig(min_profit_pct=0.3)
    engine = ArbitrageEngine(config)

    books = {
        "a": make_book("m1", "a", "0.30", "100", "0.31", "100"),
        "b": make_book("m1", "b", "0.30", "100", "0.31", "100"),
        "c": make_book("m1", "c", "0.30", "100", "0.31", "100"),
    }
    portfolio = Portfolio(balance=Decimal("1000"))

    signal = engine.find_neg_risk_arb(books, portfolio)

    assert signal is not None
    assert "outcomes" in signal.metadata


def test_neg_risk_no_arb():
    config = ArbitrageConfig(min_profit_pct=0.3)
    engine = ArbitrageEngine(config)

    books = {
        "a": make_book("m1", "a", "0.30", "100", "0.50", "100"),
        "b": make_book("m1", "b", "0.30", "100", "0.50", "100"),
    }
    portfolio = Portfolio(balance=Decimal("1000"))

    signal = engine.find_neg_risk_arb(books, portfolio)

    assert signal is None
