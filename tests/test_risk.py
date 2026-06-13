from decimal import Decimal
from pathlib import Path
import tempfile

from bot.config import RiskConfig
from bot.risk.manager import RiskManager
from bot.models import OrderBook, OrderBookLevel, Portfolio, Position, Side, Signal, SignalAction, TradeSource


def make_book(bid_price="0.45", bid_size="100", ask_price="0.55", ask_size="100") -> OrderBook:
    return OrderBook(
        market_id="m1",
        token_id="t1",
        bids=[OrderBookLevel(Decimal(bid_price), Decimal(bid_size))],
        asks=[OrderBookLevel(Decimal(ask_price), Decimal(ask_size))],
    )


def make_signal(price="0.50", size="10", strategy=TradeSource.ARBITRAGE) -> Signal:
    return Signal(
        market_id="m1",
        token_id="t1",
        action=SignalAction.BUY,
        price=Decimal(price),
        size=Decimal(size),
        confidence=1.0,
        expected_value=1.0,
        strategy=strategy,
    )


def test_kill_switch():
    with tempfile.TemporaryDirectory() as tmpdir:
        kill_path = Path(tmpdir) / "STOP"
        config = RiskConfig(kill_switch_file=str(kill_path))
        manager = RiskManager(config)

        result = manager.check_kill_switch()
        assert result.passed is True

        kill_path.write_text("")
        result = manager.check_kill_switch()
        assert result.passed is False
        assert "Kill switch" in result.reason


def test_daily_trade_limit():
    config = RiskConfig(max_daily_trades=3)
    manager = RiskManager(config)

    for _ in range(3):
        result = manager.check_daily_trades()
        assert result.passed is True
        manager.record_trade()

    result = manager.check_daily_trades()
    assert result.passed is False


def test_trade_size_limit():
    config = RiskConfig(max_position_size_pct=2.0)
    manager = RiskManager(config)

    signal = make_signal(size="30")
    portfolio = Portfolio(balance=Decimal("1000"))

    result = manager.check_trade_size(signal, portfolio.balance)
    assert result.passed is False

    signal.size = Decimal("15")
    result = manager.check_trade_size(signal, portfolio.balance)
    assert result.passed is True


def test_liquidity_check():
    config = RiskConfig()
    manager = RiskManager(config)

    book = make_book(bid_size="10", ask_size="10")
    result = manager.check_liquidity(book)
    assert result.passed is True

    book = make_book(bid_size="0.5", ask_size="0.5")
    result = manager.check_liquidity(book)
    assert result.passed is False


def test_daily_loss_limit():
    config = RiskConfig(daily_loss_limit_pct=0.5)
    manager = RiskManager(config)

    portfolio = Portfolio(balance=Decimal("1000"))
    manager.check_daily_loss(portfolio)

    portfolio.balance = Decimal("995")
    result = manager.check_daily_loss(portfolio)
    assert result.passed is True

    portfolio.balance = Decimal("993")
    result = manager.check_daily_loss(portfolio)
    assert result.passed is False
    assert manager.is_stopped is True


def test_all_checks_pass():
    config = RiskConfig(daily_loss_limit_pct=5.0)
    manager = RiskManager(config)

    signal = make_signal(price="0.50", size="10")
    book = make_book()
    portfolio = Portfolio(balance=Decimal("1000"))

    results = manager.check_all(signal, book, portfolio)
    assert all(r.passed for r in results)


def test_all_checks_fail_on_empty_book():
    config = RiskConfig()
    manager = RiskManager(config)

    signal = make_signal(price="0.50", size="100")
    book = make_book(bid_size="0.1", ask_size="0.1")
    portfolio = Portfolio(balance=Decimal("10"))

    results = manager.check_all(signal, book, portfolio)
    failed = [r for r in results if not r.passed]
    assert len(failed) > 0
