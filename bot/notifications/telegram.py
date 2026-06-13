import asyncio
import json
import logging

import httpx

from bot.config import TelegramConfig
from bot.models import TradeResult

logger = logging.getLogger(__name__)

_MAIN_KEYBOARD = {
    "keyboard": [
        [{"text": "📊 Статус"}, {"text": "📈 PnL"}],
        [{"text": "📋 Сделки"}, {"text": "📍 Позиции"}],
        [{"text": "▶️ Старт"}, {"text": "⏹️ Стоп"}],
        [{"text": "❓ Помощь"}],
    ],
    "resize_keyboard": True,
    "one_time_keyboard": False,
}

_BUTTON_CMDS = {
    "📊 Статус": "/status",
    "📈 PnL": "/pnl",
    "📋 Сделки": "/trades",
    "📍 Позиции": "/positions",
    "▶️ Старт": "/start_trading",
    "⏹️ Стоп": "/stop_trading",
    "❓ Помощь": "/help",
}


class TelegramNotifier:
    def __init__(self, config: TelegramConfig):
        self._token = config.token
        self._chat_id = config.chat_id
        self._enabled = bool(self._token and self._chat_id)
        self._notify_on = config.notify_on
        self._poll_offset = 0
        self._poll_task: asyncio.Task | None = None

        if self._enabled:
            self._base_url = f"https://api.telegram.org/bot{self._token}"
            self._client = httpx.AsyncClient(timeout=10)
            self._poll_client = httpx.AsyncClient(timeout=35)

    async def _send(self, text: str, keyboard: dict | None = None) -> bool:
        if not self._enabled:
            return False
        try:
            payload = {"chat_id": self._chat_id, "text": text, "parse_mode": "HTML"}
            if keyboard:
                payload["reply_markup"] = keyboard
            resp = await self._client.post(
                f"{self._base_url}/sendMessage",
                json=payload,
            )
            resp.raise_for_status()
            return True
        except Exception as e:
            logger.warning("Failed to send Telegram message: %s", e)
            return False

    async def send_startup(self, mode: str, strategy: str, balance: str):
        if not self._notify_on.get("startup", True):
            return
        mode_label = "бумага" if mode == "paper" else "реал"
        text = (
            f"<b>Бот запущен</b>\n"
            f"Режим: {mode_label}\n"
            f"Стратегия: {strategy}\n"
            f"Баланс: {balance} USDC"
        )
        await self._send(text)
        await self._send("Кнопки управления:", keyboard=_MAIN_KEYBOARD)

    async def send_shutdown(self):
        if not self._notify_on.get("startup", True):
            return
        await self._send("<b>Бот остановлен</b>")

    async def send_trade(self, result: TradeResult, strategy: str):
        if not self._notify_on.get("trade", True):
            return
        emoji = "✅" if result.success else "❌"
        status = "Исполнена" if result.success else "Отклонена"
        text = f"{emoji} <b>Сделка {status}</b>\nСтратегия: {strategy}\n"
        if result.order_id:
            text += f"Ордер: <code>{result.order_id[:20]}</code>\n"
        if result.success and result.filled_price:
            text += f"Цена: {result.filled_price}\nРазмер: {result.filled_size}"
        if not result.success and result.message:
            text += f"Причина: {result.message}"
        await self._send(text)

    async def send_error(self, error_msg: str):
        if not self._notify_on.get("error", True):
            return
        text = f"<b>Ошибка</b>\n<code>{error_msg[:200]}</code>"
        await self._send(text)

    async def send_daily_summary(self, pnl: str, trades: int, balance: str, drawdown: str):
        if not self._notify_on.get("daily_summary", True):
            return
        pnl_num = float(pnl)
        emoji = "📈" if pnl_num >= 0 else "📉"
        text = (
            f"{emoji} <b>Дневной итог</b>\n"
            f"PnL: {pnl} USDC\n"
            f"Сделок: {trades}\n"
            f"Баланс: {balance} USDC\n"
            f"Просадка: {drawdown}%"
        )
        await self._send(text)

    async def send_circuit_breaker(self, reason: str):
        text = f"🚨 <b>Circuit Breaker Сработал</b>\n<code>{reason}</code>"
        await self._send(text)

    async def start_polling(self, ctx: dict):
        self._poll_task = asyncio.create_task(self._poll_loop(ctx))

    async def stop_polling(self):
        if self._poll_task:
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass
            self._poll_task = None

    async def _poll_loop(self, ctx: dict):
        url = f"{self._base_url}/getUpdates"
        while True:
            try:
                resp = await self._poll_client.get(
                    url, params={"offset": self._poll_offset, "timeout": 30}
                )
                resp.raise_for_status()
                data = resp.json()
                for update in data.get("result", []):
                    self._poll_offset = update["update_id"] + 1
                    msg = update.get("message") or update.get("callback_query", {}).get("message")
                    if not msg:
                        continue
                    text = msg.get("text", "").strip()
                    chat_id = msg["chat"]["id"]
                    if str(chat_id) != str(self._chat_id):
                        continue
                    await self._handle_command(text, ctx)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning("Telegram poll error: %s", e)
                await asyncio.sleep(10)

    async def _handle_command(self, text: str, ctx: dict):
        cmd = _BUTTON_CMDS.get(text.strip(), text.split()[0].lower())
        cmd_map = {
            "/start": self._cmd_start,
            "/help": self._cmd_help,
            "/status": self._cmd_status,
            "/trades": self._cmd_trades,
            "/pnl": self._cmd_pnl,
            "/positions": self._cmd_positions,
            "/start_trading": self._cmd_start_trading,
            "/stop_trading": self._cmd_stop_trading,
        }
        handler = cmd_map.get(cmd)
        if handler:
            reply = await handler(ctx)
        else:
            reply = "Неизвестная команда. Используйте кнопки."
        await self._send(reply, keyboard=_MAIN_KEYBOARD)

    async def _cmd_start_trading(self, ctx: dict) -> str:
        toggle = ctx.get("toggle_trading")
        if not toggle:
            return "Управление недоступно"
        status = toggle()
        if status == "started":
            return "▶️ Торговля запущена"
        else:
            return "Торговля уже работает."

    async def _cmd_stop_trading(self, ctx: dict) -> str:
        toggle = ctx.get("toggle_trading")
        if not toggle:
            return "Управление недоступно"
        status = toggle()
        if status == "stopped":
            return "⏹️ Торговля остановлена"
        else:
            return "Торговля уже остановлена."

    async def _cmd_start(self, ctx: dict) -> str:
        return "<b>Polymarket Bot</b>\nКнопки управления внизу экрана."

    async def _cmd_help(self, ctx: dict) -> str:
        return (
            "<b>Команды:</b>\n"
            "📊 Статус — режим, баланс, состояние\n"
            "📈 PnL — прибыль и просадка\n"
            "📋 Сделки — последние 10 сделок\n"
            "📍 Позиции — открытые позиции\n"
            "▶️ Старт — запустить торговлю\n"
            "⏹️ Стоп — остановить торговлю"
        )

    async def _cmd_status(self, ctx: dict) -> str:
        get_status = ctx.get("get_status")
        if not get_status:
            return "Статус недоступен"
        s = get_status()
        return (
            f"<b>Статус бота</b>\n"
            f"Режим: {s.get('mode', '?')}\n"
            f"Баланс: {s.get('balance', '?')} USDC\n"
            f"Сделок сегодня: {s.get('daily_trades', 0)}\n"
            f"Аптайм: {s.get('uptime', 0)}с\n"
            f"Circuit breaker: {'🚨 ОСТАНОВЛЕН' if s.get('stopped') else '✅ ОК'}\n"
            f"Торговля: {'▶️ Активна' if s.get('trading') else '⏹️ На паузе'}"
        )

    async def _cmd_trades(self, ctx: dict) -> str:
        get_trades = ctx.get("get_trades")
        if not get_trades:
            return "Сделки недоступны"
        trades = get_trades()
        if not trades:
            return "Сделок пока нет"
        lines = ["<b>Последние 10 сделок:</b>"]
        for t in trades[-10:]:
            lines.append(
                f"{t['timestamp'][:19]} | {t['action']:4s} | "
                f"{t['price']:>6s} | x{t['size']:>4s} | {t['strategy']}"
            )
        return "\n".join(lines)

    async def _cmd_pnl(self, ctx: dict) -> str:
        get_pnl = ctx.get("get_pnl")
        if not get_pnl:
            return "PnL недоступен"
        p = get_pnl()
        return (
            f"<b>Отчёт PnL</b>\n"
            f"Дневной PnL: {p.get('daily_pnl', '?')} USDC\n"
            f"Общий PnL: {p.get('total_pnl', '?')} USDC\n"
            f"Просадка: {p.get('drawdown', '?')}%\n"
            f"Пик баланса: {p.get('peak', '?')} USDC"
        )

    async def _cmd_positions(self, ctx: dict) -> str:
        get_positions = ctx.get("get_positions")
        if not get_positions:
            return "Позиции недоступны"
        positions = get_positions()
        if not positions:
            return "Нет открытых позиций"
        lines = ["<b>Открытые позиции:</b>"]
        for p in positions:
            lines.append(
                f"<code>{p['token_id'][:16]}...</code> | "
                f"размер {p['size']} | вход {p['entry']} | "
                f"сейчас {p['current']}"
            )
        return "\n".join(lines)

    async def close(self):
        await self.stop_polling()
        if self._enabled:
            await self._client.aclose()
            await self._poll_client.aclose()
