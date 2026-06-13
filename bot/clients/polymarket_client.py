import logging
from decimal import Decimal
from typing import Any

from polymarket import AsyncPublicClient, AsyncSecureClient, ApiKeyCreds

from bot.config import BotConfig
from bot.models import OrderBook, OrderBookLevel, Position, Side

logger = logging.getLogger(__name__)


class PolymarketClient:
    def __init__(self, config: BotConfig):
        self.config = config
        self._public: AsyncPublicClient | None = None
        self._secure: AsyncSecureClient | None = None
        self._credentials: ApiKeyCreds | None = None

    async def start(self):
        self._public = AsyncPublicClient()
        logger.info("Public client initialized")

        if not self.config.dry_run:
            self._secure = await AsyncSecureClient.create(
                private_key=self.config.polymarket_private_key,
                wallet=self.config.polymarket_wallet_address,
                credentials=self._credentials,
            )
            await self._secure.setup_trading_approvals()
            logger.info("Secure client initialized with trading approvals")

    async def stop(self):
        if self._public:
            await self._public.close()
        if self._secure:
            await self._secure.close()

    async def list_markets(self, page_size: int = 50, **filters) -> list[dict[str, Any]]:
        paginator = self._public.list_markets(page_size=page_size, **filters)
        page = await paginator.first_page()
        return list(page.items)

    async def get_order_book(self, token_id: str) -> OrderBook:
        book = await self._public.get_order_book(token_id=token_id)
        bids = [OrderBookLevel(price=Decimal(b.price), size=Decimal(b.size)) for b in (book.bids or [])]
        asks = [OrderBookLevel(price=Decimal(a.price), size=Decimal(a.size)) for a in (book.asks or [])]
        return OrderBook(
            market_id=book.market,
            token_id=str(book.token_id),
            bids=bids,
            asks=asks,
            last_trade_price=Decimal(book.last_trade_price) if book.last_trade_price else None,
            tick_size=Decimal(book.tick_size),
            min_order_size=Decimal(book.min_order_size),
        )

    async def get_midpoint(self, token_id: str) -> Decimal:
        result = await self._public.get_midpoint(token_id=token_id)
        return Decimal(result)

    async def get_spread(self, token_id: str) -> Decimal:
        result = await self._public.get_spread(token_id=token_id)
        return Decimal(result)

    async def get_price(self, token_id: str, side: str) -> Decimal:
        result = await self._public.get_price(token_id=token_id, side=side)
        return Decimal(result)

    async def get_balance(self) -> Decimal:
        if self._secure is None:
            return Decimal("0")
        value = await self._secure.get_portfolio_values()
        if value:
            return Decimal(str(value[0].value)) if hasattr(value[0], "value") else Decimal("0")
        return Decimal("0")

    async def get_positions(self) -> list[Position]:
        if self._secure is None:
            return []
        positions = self._secure.list_positions(page_size=50)
        result = []
        async for page in positions:
            for p in page.items:
                result.append(Position(
                    token_id=str(p.token_id) if hasattr(p, "token_id") else "",
                    market_id=str(p.market_id) if hasattr(p, "market_id") else "",
                    side=Side.BUY,
                    size=Decimal(str(p.size)) if hasattr(p, "size") else Decimal("0"),
                    entry_price=Decimal(str(p.entry_price)) if hasattr(p, "entry_price") else Decimal("0"),
                ))
        return result

    async def place_limit_order(self, token_id: str, side: str, price: str, size: str) -> dict[str, Any]:
        if self._secure is None:
            return {"success": False, "message": "Secure client not initialized"}
        response = await self._secure.place_limit_order(
            token_id=token_id,
            side=side,
            price=price,
            size=size,
        )
        if response.ok:
            logger.info("Order placed: id=%s", response.order_id)
            return {"success": True, "order_id": response.order_id}
        logger.warning("Order failed: %s - %s", response.code, response.message)
        return {"success": False, "message": f"{response.code}: {response.message}"}

    async def cancel_order(self, order_id: str) -> bool:
        if self._secure is None:
            return False
        response = await self._secure.cancel_order(order_id=order_id)
        return len(response.canceled) > 0

    async def cancel_all_orders(self, market_id: str | None = None):
        if self._secure is None:
            return
        if market_id:
            orders = self._secure.list_open_orders(market=market_id)
            async for page in orders:
                for o in page.items:
                    await self.cancel_order(o.id)
        else:
            response = await self._secure.cancel_market_orders()
            logger.info("Canceled %d orders", len(response.canceled))
