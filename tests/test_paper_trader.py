from decimal import Decimal
import tempfile
from pathlib import Path

import pytest

from bot.core.paper_trader import PaperTrader
from bot.models import OrderBook, OrderBookLevel, Signal, SignalAction, TradeSource


@pytest.mark.asyncio
async def test_paper_trade_buy():
    with tempfile.TemporaryDirectory() as tmpdir:
        trader = PaperTrader(data_dir=tmpdir)
        initial = trader.balance

        book = OrderBook(
            market_id="m1",
            token_id="t1",
            bids=[OrderBookLevel(Decimal("0.45"), Decimal("100"))],
            asks=[OrderBookLevel(Decimal("0.50"), Decimal("100"))],
        )

        signal = Signal(
            market_id="m1",
            token_id="t1",
            action=SignalAction.BUY,
            price=Decimal("0.50"),
            size=Decimal("10"),
            confidence=0.9,
            expected_value=1.0,
            strategy=TradeSource.ARBITRAGE,
        )

        result = await trader.execute(signal, book)
        assert result.success is True
        assert trader.balance == initial - Decimal("5.0")
        assert "t1" in trader.positions


@pytest.mark.asyncio
async def test_paper_trade_insufficient_balance():
    with tempfile.TemporaryDirectory() as tmpdir:
        trader = PaperTrader(data_dir=tmpdir)
        trader.balance = Decimal("1")

        signal = Signal(
            market_id="m1",
            token_id="t1",
            action=SignalAction.BUY,
            price=Decimal("0.50"),
            size=Decimal("100"),
            confidence=0.9,
            expected_value=1.0,
            strategy=TradeSource.ARBITRAGE,
        )

        result = await trader.execute(signal)
        assert result.success is False


@pytest.mark.asyncio
async def test_paper_trade_sell():
    with tempfile.TemporaryDirectory() as tmpdir:
        trader = PaperTrader(data_dir=tmpdir)

        buy_signal = Signal(
            market_id="m1", token_id="t1",
            action=SignalAction.BUY, price=Decimal("0.50"), size=Decimal("10"),
            confidence=0.9, expected_value=1.0, strategy=TradeSource.ARBITRAGE,
        )
        await trader.execute(buy_signal)

        sell_signal = Signal(
            market_id="m1", token_id="t1",
            action=SignalAction.SELL, price=Decimal("0.60"), size=Decimal("5"),
            confidence=0.9, expected_value=1.0, strategy=TradeSource.ARBITRAGE,
        )
        result = await trader.execute(sell_signal)
        assert result.success is True
        assert trader.total_pnl == Decimal("0.50")


@pytest.mark.asyncio
async def test_trade_logging():
    with tempfile.TemporaryDirectory() as tmpdir:
        trader = PaperTrader(data_dir=tmpdir)

        signal = Signal(
            market_id="m1", token_id="t1",
            action=SignalAction.BUY, price=Decimal("0.50"), size=Decimal("10"),
            confidence=0.9, expected_value=1.0, strategy=TradeSource.ARBITRAGE,
        )
        await trader.execute(signal)

        log_file = Path(tmpdir) / "trades.jsonl"
        assert log_file.exists()
        content = log_file.read_text()
        assert "t1" in content
        assert "BUY" in content


@pytest.mark.asyncio
async def test_portfolio_valuation():
    with tempfile.TemporaryDirectory() as tmpdir:
        trader = PaperTrader(data_dir=tmpdir)

        signal = Signal(
            market_id="m1", token_id="t1",
            action=SignalAction.BUY, price=Decimal("0.50"), size=Decimal("10"),
            confidence=0.9, expected_value=1.0, strategy=TradeSource.ARBITRAGE,
        )
        await trader.execute(signal)

        book = OrderBook(
            market_id="m1", token_id="t1",
            bids=[OrderBookLevel(Decimal("0.55"), Decimal("100"))],
            asks=[OrderBookLevel(Decimal("0.60"), Decimal("100"))],
        )

        total = trader.update_portfolio_value({"t1": book})
        assert total > trader.balance
