import asyncio
import logging
import sys
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI

from bot.config import BotConfig
from bot.core.engine import TradingEngine

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

engine: TradingEngine | None = None
_start_time: datetime | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global engine, _start_time
    _start_time = datetime.utcnow()
    config = BotConfig.load("config/config.yaml")
    engine = TradingEngine(config)
    task = asyncio.create_task(engine.run_forever())
    yield
    task.cancel()
    await engine.stop()


app = FastAPI(lifespan=lifespan)


@app.get("/health")
async def health():
    global engine, _start_time
    uptime = (datetime.utcnow() - _start_time).seconds if _start_time else 0
    status = "running" if engine and engine.running else "stopped"
    return {
        "status": status,
        "uptime_seconds": uptime,
        "portfolio": str(engine.paper_trader.balance) if engine else "n/a",
        "trades": engine.paper_trader.daily_trades if engine else 0,
        "last_scan_ok": engine.watchdog.status.is_healthy if engine else False,
    }
