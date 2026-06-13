import logging
from decimal import Decimal
from typing import Callable

from bot.config import MarketMakingConfig
from bot.models import OrderBook, Portfolio, Signal, SignalAction, Side, TradeSource

logger = logging.getLogger(__name__)


class MarketMakingEngine:
    def __init__(self, config: MarketMakingConfig):
        self.config = config
        self._active_positions: dict[str, Decimal] = {}

    def is_market_eligible(self, book: OrderBook, volume_24h: float) -> bool:
        if volume_24h < self.config.min_volume_24h:
            return False
        if book.spread > Decimal(str(self.config.max_spread)):
            return False
        return True

    def generate_quotes(self, book: OrderBook, portfolio: Portfolio) -> list[Signal]:
        if not book.bids or not book.asks:
            return []

        if book.spread > Decimal(str(self.config.max_spread)):
            return []

        tick = Decimal(str(book.tick_size))
        mid = book.mid_price
        offset = tick * Decimal(str(self.config.tick_offset))

        bid_price = mid - offset
        ask_price = mid + offset

        position = self._active_positions.get(book.token_id, Decimal("0"))
        max_inv = portfolio.balance * Decimal(str(self.config.max_inventory_pct / 100))

        signals = []

        if position <= max_inv:
            bid_size = min(
                Decimal("10"),
                portfolio.balance * Decimal("0.01"),
                book.bids[0].size if book.bids else Decimal("10"),
            )
            if bid_size >= book.min_order_size:
                signals.append(Signal(
                    market_id=book.market_id,
                    token_id=book.token_id,
                    action=SignalAction.BUY,
                    price=bid_price,
                    size=bid_size,
                    confidence=0.7,
                    expected_value=float(book.spread),
                    strategy=TradeSource.MARKET_MAKING,
                    metadata={"type": "bid", "mid": str(mid), "spread": str(book.spread)},
                ))

        if position >= -max_inv:
            ask_size = min(
                Decimal("10"),
                portfolio.balance * Decimal("0.01"),
                book.asks[0].size if book.asks else Decimal("10"),
            )
            if ask_size >= book.min_order_size:
                signals.append(Signal(
                    market_id=book.market_id,
                    token_id=book.token_id,
                    action=SignalAction.SELL,
                    price=ask_price,
                    size=ask_size,
                    confidence=0.7,
                    expected_value=float(book.spread),
                    strategy=TradeSource.MARKET_MAKING,
                    metadata={"type": "ask", "mid": str(mid), "spread": str(book.spread)},
                ))

        return signals

    def check_stop_loss(self, book: OrderBook, position_side: Side | None,
                        entry_price: Decimal | None) -> bool:
        if position_side is None or entry_price is None:
            return False

        stop_distance = book.spread * Decimal(str(self.config.stop_loss_spread_mult))

        if position_side == Side.BUY:
            loss = entry_price - book.mid_price
            if loss > stop_distance:
                logger.warning("Stop loss triggered for BUY: entry=%s, mid=%s, loss=%s, threshold=%s",
                               entry_price, book.mid_price, loss, stop_distance)
                return True
        else:
            loss = book.mid_price - entry_price
            if loss > stop_distance:
                logger.warning("Stop loss triggered for SELL: entry=%s, mid=%s, loss=%s, threshold=%s",
                               entry_price, book.mid_price, loss, stop_distance)
                return True

        return False

    def update_position(self, token_id: str, delta: Decimal):
        current = self._active_positions.get(token_id, Decimal("0"))
        self._active_positions[token_id] = current + delta
