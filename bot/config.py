from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict
import os

import yaml


class ArbitrageConfig(BaseSettings):
    enabled: bool = True
    min_profit_pct: float = 0.3
    max_slippage_pct: float = 0.1
    max_position_size_pct: float = 2.0


class MarketMakingConfig(BaseSettings):
    enabled: bool = True
    min_volume_24h: float = 50_000
    max_spread: float = 0.03
    tick_offset: int = 1
    max_inventory_pct: float = 0.5
    stop_loss_spread_mult: float = 2.0
    post_only: bool = True


class RiskConfig(BaseSettings):
    max_position_size_pct: float = 2.0
    daily_loss_limit_pct: float = 0.5
    portfolio_drawdown_limit_pct: float = 3.0
    max_daily_trades: int = 20
    kill_switch_file: str = "./STOP"


class ScanConfig(BaseSettings):
    interval_seconds: int = 300
    min_market_volume: float = 10_000
    min_market_liquidity: float = 5_000
    top_n_markets: int = 20


class TelegramConfig(BaseSettings):
    token: str = ""
    chat_id: str = ""
    notify_on: dict = {
        "startup": True,
        "trade": True,
        "error": True,
        "daily_summary": True,
    }


class LoggingConfig(BaseSettings):
    level: str = "INFO"
    format: str = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    file: str = "./data/bot.log"


class BotConfig(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    polymarket_private_key: str = ""
    polymarket_wallet_address: str | None = None
    polymarket_signature_type: int = 0

    dry_run: bool = True

    telegram: TelegramConfig = TelegramConfig()

    arbitrage: ArbitrageConfig = ArbitrageConfig()
    market_making: MarketMakingConfig = MarketMakingConfig()
    risk: RiskConfig = RiskConfig()
    scan: ScanConfig = ScanConfig()
    logging: LoggingConfig = LoggingConfig()

    @classmethod
    def load(cls, config_path: str | Path = "config/config.yaml") -> "BotConfig":
        cfg = cls()
        path = Path(config_path)
        if path.exists():
            with open(path) as f:
                raw = yaml.safe_load(f) or {}
            if "arbitrage" in raw:
                cfg.arbitrage = ArbitrageConfig(**raw["arbitrage"])
            if "market_making" in raw:
                cfg.market_making = MarketMakingConfig(**raw["market_making"])
            if "risk" in raw:
                cfg.risk = RiskConfig(**raw["risk"])
            if "scan" in raw:
                cfg.scan = ScanConfig(**raw["scan"])
            if "logging" in raw:
                cfg.logging = LoggingConfig(**raw["logging"])

        tg_kwargs = {}
        if "telegram" in raw:
            tg_kwargs.update(raw["telegram"])
        for env_key, field in [("TELEGRAM_TOKEN", "token"), ("TELEGRAM_CHAT_ID", "chat_id")]:
            val = os.environ.get(env_key)
            if val:
                tg_kwargs[field] = val
        cfg.telegram = TelegramConfig(**tg_kwargs)
        return cfg
