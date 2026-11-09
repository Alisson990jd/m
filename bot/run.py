"""Ponto de entrada do bot.

  python -m bot.run --config bot/config.yaml            # roda 24/7 (um passo por minuto)
  python -m bot.run --config bot/config.yaml --once     # um único passo (útil para cron/teste)
  python -m bot.run --config bot/config.yaml --status   # mostra patrimônio e posições

Modo real só liga com as TRÊS condições: `mode: live` no config, variável de ambiente
BOT_LIVE_CONFIRM=SIM e chaves BINANCE_API_KEY / BINANCE_API_SECRET definidas.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path

import yaml

from bot import market
from bot.broker import LiveBroker, PaperBroker
from bot.engine import Engine, notify


def setup_logging(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    for h in (logging.StreamHandler(sys.stdout), RotatingFileHandler(path, maxBytes=5_000_000, backupCount=5)):
        h.setFormatter(fmt)
        root.addHandler(h)


def build(cfg: dict):
    fees = cfg.get("fees", {})
    kw = dict(fee_spot=fees.get("spot", 0.001), fee_perp=fees.get("perp", 0.0005),
              slippage=fees.get("slippage", 0.0002))
    if cfg.get("mode") == "live":
        if os.environ.get("BOT_LIVE_CONFIRM") != "SIM":
            raise SystemExit("mode: live exige BOT_LIVE_CONFIRM=SIM no ambiente. Abortando por segurança.")
        broker = LiveBroker(cfg["state_file"], cfg["capital_usdt"], testnet=cfg.get("testnet", True), **kw)
        for s in cfg["carry"]["symbols"]:
            broker.set_leverage(s + "USDT", int(cfg["carry"].get("perp_leverage", 2)))
        logging.getLogger("bot").warning("MODO REAL %s", "(TESTNET)" if cfg.get("testnet", True) else "— DINHEIRO REAL")
    else:
        broker = PaperBroker(cfg["state_file"], cfg["capital_usdt"], **kw)
    return Engine(cfg, broker, market)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="bot/config.yaml")
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--status", action="store_true")
    a = ap.parse_args(argv)
    cfg = yaml.safe_load(Path(a.config).read_text())
    setup_logging(Path(cfg.get("log_file", "bot/logs/bot.log")))
    eng = build(cfg)
    if a.status:
        prices = eng._prices()
        print(json.dumps({"equity": eng.b.equity(prices), "sleeves": eng.b.state["sleeves"],
                          "meta": eng.meta}, indent=1, default=str))
        return
    if a.once:
        eng.step()
        return
    notify(f"Bot iniciado em modo {cfg.get('mode', 'paper')}")
    every = int(cfg.get("loop_seconds", 60))
    errors = 0
    while True:
        t0 = time.time()
        try:
            eng.step()
            errors = 0
        except Exception as e:  # rede instável não pode derrubar um bot 24/7
            errors += 1
            logging.getLogger("bot").exception("erro no passo: %s", e)
            if errors in (3, 30, 300):
                notify(f"Bot: {errors} erros seguidos. Último: {e}")
        time.sleep(max(1.0, every - (time.time() - t0)))


if __name__ == "__main__":
    main()
