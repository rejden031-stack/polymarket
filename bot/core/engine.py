import asyncio
import logging
from datetime import datetime
from decimal import Decimal

from bot.arbitrage.engine import ArbitrageEngine
from bot.clients.polymarket_client import PolymarketClient
from bot.config import BotConfig
from bot.core.paper_trader import PaperTrader
from bot.health.watchdog import Watchdog
from bot.market_making.engine import MarketMakingEngine
from bot.models import OrderBook, Portfolio, Signal, TradeSource
from bot.notifications.telegram import TelegramNotifier
from bot.reconciliation.engine import ReconciliationEngine
from bot.risk.manager import RiskManager

logger = logging.getLogger(__name__)


class TradingEngine:
    def __init__(self, config: BotConfig):
        self.config = config
        self.client = PolymarketClient(config)
        self.risk = RiskManager(config.risk)
        self.arbitrage = ArbitrageEngine(config.arbitrage)
        self.market_making = MarketMakingEngine(config.market_making)
        self.paper_trader = PaperTrader(data_dir=config.logging.file.rsplit("/", 1)[0] if "/" in config.logging.file else "./data")
        self.recon = ReconciliationEngine(self.client)
        self.watchdog = Watchdog()
        self.tg = TelegramNotifier(config.telegram)
        self.running = False

    def _tg_status(self) -> dict:
        return {
            "mode": "paper" if self.config.dry_run else "live",
            "balance": str(self.paper_trader.balance),
            "daily_trades": self.paper_trader.daily_trades,
            "uptime": 0,
            "stopped": self.risk.is_stopped,
        }

    def _tg_trades(self) -> list:
        return self.paper_trader.trades

    def _tg_pnl(self) -> dict:
        dd = 0.0
        if self.paper_trader.peak_balance > 0:
            dd = float((self.paper_trader.peak_balance - self.paper_trader.balance) / self.paper_trader.peak_balance * 100)
        return {
            "daily_pnl": str(self.paper_trader.daily_pnl),
            "total_pnl": str(self.paper_trader.total_pnl),
            "drawdown": f"{dd:.2f}",
            "peak": str(self.paper_trader.peak_balance),
        }

    def _tg_positions(self) -> list:
        return [
            {
                "token_id": p.token_id,
                "size": str(p.size),
                "entry": str(p.entry_price),
                "current": str(p.current_price),
            }
            for p in self.paper_trader.positions.values()
        ]

    async def start(self):
        logger.info("Starting trading engine (dry_run=%s)", self.config.dry_run)
        await self.client.start()
        self.running = True

        if self.config.dry_run:
            logger.info("Paper trading mode: initial balance = %s", self.paper_trader.balance)

        await self.tg.send_startup(
            mode="paper" if self.config.dry_run else "live",
            strategy="all",
            balance=str(self.paper_trader.balance) if self.config.dry_run else "?",
        )

        await self.tg.start_polling({
            "get_status": self._tg_status,
            "get_trades": self._tg_trades,
            "get_pnl": self._tg_pnl,
            "get_positions": self._tg_positions,
        })

    async def stop(self):
        self.running = False
        await self.client.stop()
        await self.tg.send_shutdown()
        await self.tg.close()
        logger.info("Trading engine stopped")

    async def run_forever(self):
        await self.start()

        while self.running:
            try:
                await self.scan_cycle()
                self.watchdog.record_success()
            except Exception as e:
                self.watchdog.record_error(str(e))
                logger.exception("Scan cycle failed")
                await self.tg.send_error(f"Scan cycle failed: {e}")

            if not self.watchdog.status.is_healthy:
                logger.critical("Too many errors, stopping engine")
                await self.tg.send_error("Too many errors — engine stopping")
                break

            await asyncio.sleep(self.config.scan.interval_seconds)

        await self.stop()

    async def scan_cycle(self):
        if self.risk.is_stopped:
            logger.warning("Engine stopped by circuit breaker")
            await self.tg.send_circuit_breaker("Circuit breaker activated")
            return

        if self.config.dry_run:
            portfolio = Portfolio(
                balance=self.paper_trader.balance,
                total_pnl=self.paper_trader.total_pnl,
                day_pnl=self.paper_trader.daily_pnl,
                peak_balance=self.paper_trader.peak_balance,
                daily_trades=self.paper_trader.daily_trades,
            )
        else:
            balance = await self.client.get_balance()
            positions = await self.client.get_positions()
            portfolio = Portfolio(
                balance=balance,
                open_positions=positions,
            )

        markets = await self.client.list_markets(
            closed=False,
            page_size=self.config.scan.top_n_markets,
        )
        logger.info("Fetched %d active markets", len(markets))

        scanned = 0
        for market in markets[:self.config.scan.top_n_markets]:
            try:
                await self._process_market(market, portfolio)
                scanned += 1
            except Exception as e:
                logger.warning("Error processing market %s: %s", getattr(market, "id", "?"), e)

        if self.config.dry_run:
            books = {}
            for pos_token_id in list(self.paper_trader.positions.keys()):
                try:
                    books[pos_token_id] = await self.client.get_order_book(pos_token_id)
                except Exception:
                    pass
            if books:
                self.paper_trader.update_portfolio_value(books)

        logger.info("Scan cycle complete: processed %d/%d markets, portfolio=%s",
                     scanned, len(markets), portfolio.balance)

    async def _process_market(self, market, portfolio: Portfolio):
        outcomes = getattr(market, "outcomes", None)
        if outcomes is None:
            return

        yes_token_id = getattr(outcomes, "yes", None)
        no_token_id = getattr(outcomes, "no", None)

        token_id = None
        if hasattr(yes_token_id, "token_id"):
            token_id = yes_token_id.token_id
        elif isinstance(yes_token_id, str):
            token_id = yes_token_id
        else:
            try:
                token_id = str(yes_token_id)
            except Exception:
                pass

        if not token_id:
            return

        try:
            yes_book = await self.client.get_order_book(token_id)

            metrics = getattr(market, "metrics", None)
            volume_24h = 0.0
            if metrics:
                volume_24h = float(getattr(metrics, "volume_24hr", 0) or 0)

            if volume_24h < self.config.scan.min_market_volume:
                return

            no_book = None
            if no_token_id is not None:
                no_tid = None
                if hasattr(no_token_id, "token_id"):
                    no_tid = no_token_id.token_id
                elif isinstance(no_token_id, str):
                    no_tid = no_token_id
                else:
                    no_tid = str(no_token_id)
                try:
                    no_book = await self.client.get_order_book(no_tid)
                except Exception:
                    no_book = None

            signals: list[Signal] = []

            if self.config.arbitrage.enabled:
                arb_signal = self.arbitrage.find_complete_set_arb(yes_book, no_book, portfolio)
                if arb_signal:
                    signals.append(arb_signal)

            if self.config.market_making.enabled:
                if self.market_making.is_market_eligible(yes_book, volume_24h):
                    mm_signals = self.market_making.generate_quotes(yes_book, portfolio)
                    signals.extend(mm_signals)

            for signal in signals:
                checks = self.risk.check_all(signal, yes_book, portfolio)
                if not all(c.passed for c in checks):
                    failed = [c.reason for c in checks if not c.passed]
                    logger.info("Signal rejected: %s", failed)
                    continue

                if self.config.dry_run:
                    result = await self.paper_trader.execute(signal, yes_book)
                else:
                    side = "BUY" if signal.action.value == "BUY" else "SELL"
                    result = await self.client.place_limit_order(
                        token_id=signal.token_id,
                        side=side,
                        price=str(signal.price),
                        size=str(signal.size),
                    )

                if result.success:
                    self.risk.record_trade()
                    logger.info("Order executed: strategy=%s, signal=%s, order=%s",
                                signal.strategy.value, signal.action.value, result.order_id)

                await self.tg.send_trade(result, signal.strategy.value)

        except Exception as e:
            logger.warning("Error processing market token %s: %s", token_id[:16] if len(str(token_id)) > 16 else token_id, e)
            await self.tg.send_error(f"Market processing failed: {e}")
