import pytest
from bot.notifications.telegram import TelegramNotifier
from bot.config import TelegramConfig
from bot.models import TradeResult


@pytest.fixture
def notifier():
    cfg = TelegramConfig()
    return TelegramNotifier(cfg)


@pytest.mark.asyncio
async def test_disabled_by_default(notifier):
    result = await notifier._send("test")
    assert result is False


@pytest.mark.asyncio
async def test_enabled_with_token():
    cfg = TelegramConfig(token="fake:token", chat_id="123")
    tg = TelegramNotifier(cfg)
    assert tg._enabled is True
    await tg.close()


@pytest.mark.asyncio
async def test_send_trade_success(notifier):
    result = TradeResult(success=True, order_id="paper_1", filled_price="0.50", filled_size="10")
    await notifier.send_trade(result, "arbitrage")


@pytest.mark.asyncio
async def test_send_trade_fail(notifier):
    result = TradeResult(success=False, message="Insufficient balance")
    await notifier.send_trade(result, "arbitrage")


@pytest.mark.asyncio
async def test_send_error(notifier):
    await notifier.send_error("Test error message")


@pytest.mark.asyncio
async def test_send_startup(notifier):
    await notifier.send_startup("paper", "all", "1000")


@pytest.mark.asyncio
async def test_send_shutdown(notifier):
    await notifier.send_shutdown()


@pytest.mark.asyncio
async def test_send_daily_summary(notifier):
    await notifier.send_daily_summary("5.50", 10, "1005", "0.5")


@pytest.mark.asyncio
async def test_send_circuit_breaker(notifier):
    await notifier.send_circuit_breaker("Daily loss limit exceeded")
