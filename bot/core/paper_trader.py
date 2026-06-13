import json
import logging
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from bot.models import OrderBook, Portfolio, Position, Side, Signal, TradeResult

logger = logging.getLogger(__name__)


class PaperTrader:
    def __init__(self, data_dir: str = "./data"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

        self.balance = Decimal("1000")
        self.peak_balance = self.balance
        self.day_start_balance = self.balance
        self.daily_pnl = Decimal("0")
        self.total_pnl = Decimal("0")
        self.positions: dict[str, Position] = {}
        self.trades: list[dict] = []
        self.daily_trades = 0
        self._current_date = datetime.utcnow().date()

    def _check_day_rollover(self):
        today = datetime.utcnow().date()
        if today != self._current_date:
            self._save_snapshot()
            self._current_date = today
            self.day_start_balance = self.balance
            self.daily_pnl = Decimal("0")
            self.daily_trades = 0
            logger.info("Day rollover: balance=%s, daily_pnl=%s", self.balance, self.total_pnl)

    def update_portfolio_value(self, books: dict[str, OrderBook]):
        self._check_day_rollover()
        total_value = self.balance
        for token_id, pos in list(self.positions.items()):
            book = books.get(token_id)
            if book:
                current_price = book.mid_price if book.mid_price > 0 else book.last_trade_price or pos.entry_price
                current_value = pos.size * current_price
                pos.current_price = current_price
                pos.unrealized_pnl = current_value - (pos.size * pos.entry_price)
                total_value += current_value

        if total_value > self.peak_balance:
            self.peak_balance = total_value

        self.daily_pnl = total_value - self.day_start_balance
        return total_value

    async def execute(self, signal: Signal, book: OrderBook | None = None) -> TradeResult:
        self._check_day_rollover()

        fill_price = signal.price
        if book and book.asks:
            if signal.action.value == "BUY" and book.asks:
                fill_price = min(signal.price, book.asks[0].price)
            elif signal.action.value == "SELL" and book.bids:
                fill_price = max(signal.price, book.bids[0].price)

        cost = fill_price * signal.size

        if signal.action.value == "BUY":
            if cost > self.balance:
                return TradeResult(success=False, message=f"Insufficient balance: need {cost}, have {self.balance}")
            self.balance -= cost
            self.positions[signal.token_id] = Position(
                token_id=signal.token_id,
                market_id=signal.market_id,
                side=Side.BUY,
                size=signal.size,
                entry_price=fill_price,
                current_price=fill_price,
            )
        else:
            pos = self.positions.get(signal.token_id)
            if pos is None or pos.size < signal.size:
                return TradeResult(success=False, message=f"Insufficient position to sell")
            self.balance += cost
            pos.size -= signal.size
            realized_pnl = (fill_price - pos.entry_price) * signal.size
            self.total_pnl += realized_pnl
            if pos.size <= 0:
                del self.positions[signal.token_id]

        self.daily_trades += 1
        trade_record = {
            "timestamp": datetime.utcnow().isoformat(),
            "market_id": signal.market_id,
            "token_id": signal.token_id,
            "action": signal.action.value,
            "price": str(fill_price),
            "size": str(signal.size),
            "cost": str(cost),
            "strategy": signal.strategy.value,
            "balance_after": str(self.balance),
        }
        self.trades.append(trade_record)
        self._log_trade(trade_record)

        logger.info("Paper trade executed: %s %s @ %s (size=%s, cost=%s, balance=%s)",
                     signal.action.value, signal.token_id[:12], fill_price, signal.size, cost, self.balance)

        return TradeResult(
            success=True,
            order_id=f"paper_{len(self.trades)}",
            filled_price=fill_price,
            filled_size=signal.size,
        )

    def _log_trade(self, trade: dict):
        filepath = self.data_dir / "trades.jsonl"
        with open(filepath, "a") as f:
            f.write(json.dumps(trade) + "\n")

    def _save_snapshot(self):
        snapshot = {
            "timestamp": datetime.utcnow().isoformat(),
            "balance": str(self.balance),
            "total_pnl": str(self.total_pnl),
            "daily_pnl": str(self.daily_pnl),
            "peak_balance": str(self.peak_balance),
            "open_positions": len(self.positions),
            "daily_trades": self.daily_trades,
        }
        filepath = self.data_dir / f"snapshot_{self._current_date.isoformat()}.json"
        with open(filepath, "w") as f:
            json.dump(snapshot, f, indent=2)
