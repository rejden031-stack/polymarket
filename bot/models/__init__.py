from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any


class Side(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class SignalAction(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


class TradeSource(str, Enum):
    ARBITRAGE = "arbitrage"
    MARKET_MAKING = "market_making"


@dataclass
class Signal:
    market_id: str
    token_id: str
    action: SignalAction
    price: Decimal
    size: Decimal
    confidence: float
    expected_value: float
    strategy: TradeSource
    timestamp: datetime = field(default_factory=datetime.utcnow)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_log(self) -> dict:
        return {
            "market_id": self.market_id,
            "token_id": self.token_id,
            "action": self.action.value,
            "price": str(self.price),
            "size": str(self.size),
            "confidence": self.confidence,
            "expected_value": self.expected_value,
            "strategy": self.strategy.value,
            "timestamp": self.timestamp.isoformat(),
            **self.metadata,
        }


@dataclass
class TradeResult:
    success: bool
    order_id: str | None = None
    filled_price: Decimal | None = None
    filled_size: Decimal | None = None
    message: str = ""


@dataclass
class Position:
    token_id: str
    market_id: str
    side: Side
    size: Decimal
    entry_price: Decimal
    current_price: Decimal | None = None
    unrealized_pnl: Decimal = Decimal("0")
    timestamp: datetime = field(default_factory=datetime.utcnow)


@dataclass
class Portfolio:
    balance: Decimal = Decimal("0")
    total_pnl: Decimal = Decimal("0")
    day_pnl: Decimal = Decimal("0")
    peak_balance: Decimal = Decimal("0")
    open_positions: list[Position] = field(default_factory=list)
    daily_trades: int = 0
    last_updated: datetime = field(default_factory=datetime.utcnow)


@dataclass
class OrderBookLevel:
    price: Decimal
    size: Decimal


@dataclass
class OrderBook:
    market_id: str
    token_id: str
    bids: list[OrderBookLevel]
    asks: list[OrderBookLevel]
    mid_price: Decimal = Decimal("0")
    spread: Decimal = Decimal("0")
    last_trade_price: Decimal | None = None
    tick_size: Decimal = Decimal("0.01")
    min_order_size: Decimal = Decimal("1")

    def __post_init__(self):
        if self.bids and self.asks:
            best_bid = self.bids[0].price
            best_ask = self.asks[0].price
            self.mid_price = (best_bid + best_ask) / Decimal("2")
            self.spread = best_ask - best_bid
