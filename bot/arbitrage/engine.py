import logging
from decimal import Decimal

from bot.config import ArbitrageConfig
from bot.models import OrderBook, Portfolio, Signal, SignalAction, Side, TradeSource

logger = logging.getLogger(__name__)


class ArbitrageEngine:
    def __init__(self, config: ArbitrageConfig):
        self.config = config

    def find_complete_set_arb(self, yes_book: OrderBook, no_book: OrderBook | None,
                              portfolio: Portfolio) -> Signal | None:
        if not yes_book.bids or not yes_book.asks:
            return None

        if no_book is None:
            return None

        yes_best_ask = yes_book.asks[0].price if yes_book.asks else None
        no_best_ask = no_book.asks[0].price if no_book.asks else None

        if yes_best_ask is None or no_best_ask is None:
            return None

        total_cost = yes_best_ask + no_best_ask
        fee = total_cost * Decimal("0.01")
        profit = Decimal("1") - total_cost - fee
        profit_pct = float(profit / total_cost * 100) if total_cost > 0 else 0

        if profit_pct < self.config.min_profit_pct:
            return None

        max_size = portfolio.balance * Decimal(str(self.config.max_position_size_pct / 100))
        arb_quantity = total_cost * Decimal("1")
        size = max_size / arb_quantity if arb_quantity > 0 else Decimal("0")
        size = min(size, yes_book.asks[0].size, no_book.asks[0].size)

        if size < yes_book.min_order_size:
            return None

        logger.info("Arbitrage found: YES ask=%s, NO ask=%s, total=%s, profit=%s%%",
                     yes_best_ask, no_best_ask, total_cost, round(profit_pct, 2))

        return Signal(
            market_id=yes_book.market_id,
            token_id=yes_book.token_id,
            action=SignalAction.BUY,
            price=yes_best_ask,
            size=size,
            confidence=1.0,
            expected_value=profit_pct,
            strategy=TradeSource.ARBITRAGE,
            metadata={
                "no_token_id": no_book.token_id,
                "no_price": str(no_best_ask),
                "total_cost": str(total_cost),
                "fee": str(fee),
                "profit_pct": profit_pct,
            },
        )

    def find_neg_risk_arb(self, books: dict[str, OrderBook], portfolio: Portfolio) -> Signal | None:
        if len(books) < 2:
            return None

        best_asks = {}
        for token_id, book in books.items():
            if book.asks:
                best_asks[token_id] = book.asks[0].price

        if len(best_asks) < 2:
            return None

        total = sum(best_asks.values())
        fee = total * Decimal("0.01")
        profit = Decimal("1") - total - fee
        profit_pct = float(profit / total * 100) if total > 0 else 0

        if profit_pct < self.config.min_profit_pct:
            return None

        min_size = min(
            books[t].asks[0].size
            for t in best_asks
            if books[t].asks
        )

        if min_size < Decimal("1"):
            return None

        first_token = next(iter(best_asks.keys()))
        logger.info("Neg-risk arb: sum=%s, profit=%s%%", total, round(profit_pct, 2))

        return Signal(
            market_id=books[first_token].market_id,
            token_id=first_token,
            action=SignalAction.BUY,
            price=best_asks[first_token],
            size=min_size,
            confidence=1.0,
            expected_value=profit_pct,
            strategy=TradeSource.ARBITRAGE,
            metadata={
                "outcomes": {t: str(p) for t, p in best_asks.items()},
                "total_cost": str(total),
                "fee": str(fee),
                "profit_pct": profit_pct,
            },
        )
