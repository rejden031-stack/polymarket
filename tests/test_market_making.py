from decimal import Decimal

from bot.config import MarketMakingConfig
from bot.market_making.engine import MarketMakingEngine
from bot.models import OrderBook, OrderBookLevel, Portfolio, SignalAction


def make_book(bid_price="0.48", bid_size="100", ask_price="0.52", ask_size="100",
              market_id="m1", token_id="t1") -> OrderBook:
    return OrderBook(
        market_id=market_id,
        token_id=token_id,
        bids=[OrderBookLevel(Decimal(bid_price), Decimal(bid_size))],
        asks=[OrderBookLevel(Decimal(ask_price), Decimal(ask_size))],
    )


def test_market_eligible():
    config = MarketMakingConfig(min_volume_24h=10_000, max_spread=0.05)
    engine = MarketMakingEngine(config)

    book = make_book()
    assert engine.is_market_eligible(book, 50_000) is True
    assert engine.is_market_eligible(book, 5_000) is False

    wide_book = make_book(bid_price="0.40", ask_price="0.60")
    assert engine.is_market_eligible(wide_book, 50_000) is False


def test_generate_quotes():
    config = MarketMakingConfig(max_inventory_pct=0.5, max_spread=0.05)
    engine = MarketMakingEngine(config)

    book = make_book()
    portfolio = Portfolio(balance=Decimal("1000"))

    signals = engine.generate_quotes(book, portfolio)
    assert len(signals) == 2

    assert signals[0].action == SignalAction.BUY
    assert signals[1].action == SignalAction.SELL
    assert signals[0].token_id == "t1"
    assert signals[1].token_id == "t1"


def test_skip_wide_spread():
    config = MarketMakingConfig(max_spread=0.03)
    engine = MarketMakingEngine(config)

    book = make_book(bid_price="0.40", ask_price="0.60")
    portfolio = Portfolio(balance=Decimal("1000"))

    signals = engine.generate_quotes(book, portfolio)
    assert len(signals) == 0


def test_stop_loss_buy():
    config = MarketMakingConfig(stop_loss_spread_mult=2.0)
    engine = MarketMakingEngine(config)

    book = make_book(market_id="m1", token_id="t1",
                     bid_price="0.40", ask_price="0.50")

    from bot.models import Side
    triggered = engine.check_stop_loss(book, Side.BUY, Decimal("0.70"))
    assert triggered is True

    not_triggered = engine.check_stop_loss(book, Side.BUY, Decimal("0.48"))
    assert not_triggered is False


def test_position_tracking():
    config = MarketMakingConfig()
    engine = MarketMakingEngine(config)

    engine.update_position("t1", Decimal("10"))
    assert engine._active_positions.get("t1") == Decimal("10")

    engine.update_position("t1", Decimal("-5"))
    assert engine._active_positions.get("t1") == Decimal("5")
