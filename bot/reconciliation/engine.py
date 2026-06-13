import logging

from bot.clients.polymarket_client import PolymarketClient

logger = logging.getLogger(__name__)


class ReconciliationEngine:
    def __init__(self, client: PolymarketClient):
        self.client = client

    async def reconcile_orders(self, expected_order_ids: set[str]) -> list[str]:
        if not expected_order_ids:
            return []

        open_orders = self.client._secure.list_open_orders()
        active_ids: set[str] = set()
        async for page in open_orders:
            for o in page.items:
                active_ids.add(o.id)

        stale = expected_order_ids - active_ids
        if stale:
            logger.warning("Stale orders detected: %s", stale)

        return list(stale)
