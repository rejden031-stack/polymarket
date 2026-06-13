import logging
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

from bot.config import RiskConfig
from bot.models import OrderBook, Portfolio, Signal

logger = logging.getLogger(__name__)


@dataclass
class CheckResult:
    passed: bool
    reason: str = ""
    details: dict = field(default_factory=dict)


class RiskManager:
    def __init__(self, config: RiskConfig):
        self.config = config
        self._daily_trades = 0
        self._daily_start_balance: Decimal | None = None
        self._peak_balance: Decimal | None = None
        self._stopped = False

    def reset_daily(self):
        self._daily_trades = 0

    @property
    def is_stopped(self) -> bool:
        return self._stopped

    def check_kill_switch(self) -> CheckResult:
        path = Path(self.config.kill_switch_file)
        if path.exists():
            logger.warning("Kill switch file found at %s", path)
            return CheckResult(passed=False, reason="Kill switch activated")
        return CheckResult(passed=True)

    def check_daily_trades(self) -> CheckResult:
        if self._daily_trades >= self.config.max_daily_trades:
            return CheckResult(passed=False, reason=f"Daily trade limit reached ({self._daily_trades}/{self.config.max_daily_trades})")
        return CheckResult(passed=True)

    def check_trade_size(self, signal: Signal, balance: Decimal) -> CheckResult:
        max_size = balance * Decimal(str(self.config.max_position_size_pct / 100))
        if signal.size > max_size:
            return CheckResult(
                passed=False,
                reason=f"Trade size {signal.size} exceeds max {max_size} ({self.config.max_position_size_pct}% of {balance})",
            )
        return CheckResult(passed=True)

    def check_daily_loss(self, portfolio: Portfolio) -> CheckResult:
        if self._daily_start_balance is None:
            self._daily_start_balance = portfolio.balance
            self._peak_balance = portfolio.balance
            return CheckResult(passed=True)

        if portfolio.balance > self._peak_balance:
            self._peak_balance = portfolio.balance

        day_loss_pct = float((self._daily_start_balance - portfolio.balance) / self._daily_start_balance * 100)
        if day_loss_pct > self.config.daily_loss_limit_pct:
            self._stopped = True
            return CheckResult(
                passed=False,
                reason=f"Daily loss {day_loss_pct:.2f}% exceeds limit {self.config.daily_loss_limit_pct}%",
            )

        drawdown_pct = float((self._peak_balance - portfolio.balance) / self._peak_balance * 100)
        if drawdown_pct > self.config.portfolio_drawdown_limit_pct:
            self._stopped = True
            return CheckResult(
                passed=False,
                reason=f"Drawdown {drawdown_pct:.2f}% exceeds limit {self.config.portfolio_drawdown_limit_pct}%",
            )

        return CheckResult(passed=True)

    def check_liquidity(self, book: OrderBook) -> CheckResult:
        if not book.bids or not book.asks:
            return CheckResult(passed=False, reason="Empty order book")

        total_bid_depth = sum(b.size for b in book.bids[:5]) if book.bids else Decimal("0")
        total_ask_depth = sum(a.size for a in book.asks[:5]) if book.asks else Decimal("0")

        if total_bid_depth < Decimal("10") or total_ask_depth < Decimal("10"):
            return CheckResult(passed=False, reason=f"Insufficient depth: bids={total_bid_depth}, asks={total_ask_depth}")

        return CheckResult(passed=True)

    def check_exposure(self, market_id: str, positions: list) -> CheckResult:
        market_positions = [p for p in positions if p.market_id == market_id]
        if len(market_positions) >= self.config.max_position_size_pct / 2:
            return CheckResult(passed=False, reason=f"Already exposed to market {market_id}")
        return CheckResult(passed=True)

    def check_all(self, signal: Signal, book: OrderBook, portfolio: Portfolio) -> list[CheckResult]:
        results = [
            self.check_kill_switch(),
            self.check_daily_trades(),
            self.check_trade_size(signal, portfolio.balance),
            self.check_daily_loss(portfolio),
            self.check_liquidity(book),
            self.check_exposure(signal.market_id, portfolio.open_positions),
        ]
        failed = [r for r in results if not r.passed]
        if failed:
            logger.warning("Risk checks failed: %s", [r.reason for r in failed])
        return results

    def record_trade(self):
        self._daily_trades += 1
