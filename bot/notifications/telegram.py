import logging

import httpx

from bot.config import TelegramConfig
from bot.models import TradeResult

logger = logging.getLogger(__name__)


class TelegramNotifier:
    def __init__(self, config: TelegramConfig):
        self._token = config.token
        self._chat_id = config.chat_id
        self._enabled = bool(self._token and self._chat_id)
        self._notify_on = config.notify_on

        if self._enabled:
            self._base_url = f"https://api.telegram.org/bot{self._token}"
            self._client = httpx.AsyncClient(timeout=10)

    async def _send(self, text: str) -> bool:
        if not self._enabled:
            return False
        try:
            resp = await self._client.post(
                f"{self._base_url}/sendMessage",
                json={"chat_id": self._chat_id, "text": text, "parse_mode": "HTML"},
            )
            resp.raise_for_status()
            return True
        except Exception as e:
            logger.warning("Failed to send Telegram message: %s", e)
            return False

    async def send_startup(self, mode: str, strategy: str, balance: str):
        if not self._notify_on.get("startup", True):
            return
        text = (
            f"<b>Bot started</b>\n"
            f"Mode: {mode}\n"
            f"Strategy: {strategy}\n"
            f"Balance: {balance} USDC"
        )
        await self._send(text)

    async def send_shutdown(self):
        if not self._notify_on.get("startup", True):
            return
        await self._send("<b>Bot stopped</b>")

    async def send_trade(self, result: TradeResult, strategy: str):
        if not self._notify_on.get("trade", True):
            return
        emoji = "✅" if result.success else "❌"
        status = "Executed" if result.success else "Failed"
        text = f"{emoji} <b>Trade {status}</b>\nStrategy: {strategy}\n"
        if result.order_id:
            text += f"Order: <code>{result.order_id[:20]}</code>\n"
        if result.success and result.filled_price:
            text += f"Price: {result.filled_price}\nSize: {result.filled_size}"
        if not result.success and result.message:
            text += f"Reason: {result.message}"
        await self._send(text)

    async def send_error(self, error_msg: str):
        if not self._notify_on.get("error", True):
            return
        text = f"<b>Error</b>\n<code>{error_msg[:200]}</code>"
        await self._send(text)

    async def send_daily_summary(self, pnl: str, trades: int, balance: str, drawdown: str):
        if not self._notify_on.get("daily_summary", True):
            return
        pnl_num = float(pnl)
        emoji = "📈" if pnl_num >= 0 else "📉"
        text = (
            f"{emoji} <b>Daily Summary</b>\n"
            f"PnL: {pnl} USDC\n"
            f"Trades: {trades}\n"
            f"Balance: {balance} USDC\n"
            f"Drawdown: {drawdown}%"
        )
        await self._send(text)

    async def send_circuit_breaker(self, reason: str):
        text = f"🚨 <b>Circuit Breaker Activated</b>\n<code>{reason}</code>"
        await self._send(text)

    async def close(self):
        if self._enabled:
            await self._client.aclose()
