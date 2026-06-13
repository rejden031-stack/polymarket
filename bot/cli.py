import asyncio
import logging
import sys
from pathlib import Path

import typer

app = typer.Typer()


def _setup_logging(config):
    root = logging.getLogger()
    root.setLevel(config.logging.level.upper())

    fmt = logging.Formatter(config.logging.format)

    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(fmt)
    root.addHandler(console)

    log_path = Path(config.logging.file)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    file_handler = logging.FileHandler(str(log_path))
    file_handler.setFormatter(fmt)
    root.addHandler(file_handler)


@app.command()
def run(
    paper: bool = typer.Option(True, "--paper", help="Paper trading mode"),
    live: bool = typer.Option(False, "--live", help="Live trading mode"),
    strategy: str = typer.Option("all", "--strategy", help="Strategy to use (arbitrage, market_making, all)"),
    scan_interval: int = typer.Option(300, "--scan-interval", help="Market scan interval in seconds"),
    config_path: str = typer.Option("config/config.yaml", "--config", help="Path to config file"),
):
    from bot.config import BotConfig
    from bot.core.engine import TradingEngine

    config = BotConfig.load(config_path)
    config.dry_run = not live
    if paper:
        config.dry_run = True
    config.scan.interval_seconds = scan_interval

    if strategy == "arbitrage":
        config.market_making.enabled = False
    elif strategy == "market_making":
        config.arbitrage.enabled = False

    _setup_logging(config)

    logger = logging.getLogger("bot")
    logger.info("Starting Polymarket bot (mode=%s, strategy=%s)",
                "paper" if config.dry_run else "live", strategy)

    engine = TradingEngine(config)
    asyncio.run(engine.run_forever())


@app.command()
def status(config_path: str = typer.Option("config/config.yaml", "--config")):
    from bot.config import BotConfig

    config = BotConfig.load(config_path)
    logger = logging.getLogger("bot")
    logger.setLevel(logging.INFO)

    print(f"Config loaded from {config_path}")
    print(f"  Dry run: {config.dry_run}")
    print(f"  Arbitrage enabled: {config.arbitrage.enabled}")
    print(f"  Market making enabled: {config.market_making.enabled}")
    print(f"  Scan interval: {config.scan.interval_seconds}s")
    print(f"  Daily loss limit: {config.risk.daily_loss_limit_pct}%")
    print(f"  Max drawdown: {config.risk.portfolio_drawdown_limit_pct}%")


@app.command()
def trades(
    n: int = typer.Option(20, "--n", help="Number of recent trades"),
    data_dir: str = typer.Option("./data", "--data-dir"),
):
    import json

    filepath = Path(data_dir) / "trades.jsonl"
    if not filepath.exists():
        print("No trades found")
        return

    with open(filepath) as f:
        lines = f.readlines()

    for line in lines[-n:]:
        trade = json.loads(line.strip())
        print(f"{trade['timestamp'][:19]} | {trade['action']:4s} | {trade['token_id'][:12]}... "
              f"| @ {trade['price']:>6s} | size {trade['size']:>4s} | balance {trade['balance_after']:>8s}")


def main():
    app()


if __name__ == "__main__":
    main()
