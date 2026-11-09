"""Testes do motor em modo paper com um mercado falso (sem rede)."""
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest

from bot.broker import PaperBroker
from bot.engine import Engine


class FakeMarket:
    def __init__(self, n_days=260, trend=+1):
        idx = pd.date_range("2025-01-01", periods=n_days, freq="1D", tz="UTC")
        base = np.linspace(100, 200, n_days) if trend > 0 else np.linspace(200, 100, n_days)
        self.daily = pd.DataFrame({"open": base, "high": base * 1.02, "low": base * 0.98, "close": base}, index=idx)
        self.daily["close_time"] = [int((t + pd.Timedelta(days=1)).timestamp() * 1000) - 1 for t in idx]
        self.price = {"BTCUSDT": float(base[-1]), "ETHUSDT": float(base[-1]) / 10}
        self.hi = None
        self.funding = pd.Series(dtype=float)

    def last_price(self, p):
        return self.price[p]

    def daily_closed(self, p, now_ms=None, limit=400):
        scale = 1 if p == "BTCUSDT" else 0.1
        d = self.daily.copy()
        for c in ("open", "high", "low", "close"):
            d[c] = d[c] * scale
        return d, self.price[p]

    def max_high_since(self, p, start_ms):
        return self.hi

    def funding_history(self, p, start_ms):
        return self.funding


CFG = {"state_file": "", "capital_usdt": {"trend": 1000, "breakout": 1000, "carry": 2000},
       "trend": {"symbol": "BTC", "rebalance_band": 0.05},
       "breakout": {"symbols": ["BTC", "ETH"], "k": 0.5, "trend_n": 50},
       "carry": {"symbols": ["BTC", "ETH"], "perp_leverage": 2, "rebalance_move": 0.2},
       "risk": {"max_drawdown": 0.25}}


@pytest.fixture
def eng(tmp_path):
    cfg = dict(CFG, state_file=str(tmp_path / "s.json"), equity_csv=str(tmp_path / "eq.csv"))
    b = PaperBroker(cfg["state_file"], cfg["capital_usdt"], fee_spot=0.001, fee_perp=0.0005, slippage=0.0)
    return Engine(cfg, b, FakeMarket())


T0 = datetime(2025, 9, 18, 0, 1, tzinfo=timezone.utc)


def test_full_day_cycle(eng):
    m, b = eng.m, eng.b
    eng.step(T0)
    # A: mercado em alta => 100% em BTC (menos folga de taxa)
    assert b.spot_qty("trend", "BTC") * m.price["BTCUSDT"] == pytest.approx(1000 * 0.995, rel=0.01)
    # B: armado para os dois ativos, ainda não executado
    assert set(eng.meta["armed"]) == {"BTC", "ETH"} and not eng.meta["armed"]["BTC"]["filled"]
    # C: hedge aberto com pernas iguais e nocional = capital/(1+1/2) por ativo
    q = b.spot_qty("carry", "BTC")
    assert q == pytest.approx(-b.perp_qty("carry", "BTCUSDT"))
    assert q * m.price["BTCUSDT"] == pytest.approx(1000 / 1.5, rel=0.01)
    # dispara o rompimento do BTC
    lvl = eng.meta["armed"]["BTC"]["level"]
    m.hi = lvl + 1
    eng.step(T0 + timedelta(hours=3))
    assert eng.meta["armed"]["BTC"]["filled"] and b.perp_qty("breakout", "BTCUSDT") > 0
    # funding positivo de 0,01%: o vendido recebe
    before = b.sleeve("carry")["usdt"]
    m.funding = pd.Series([0.0001], index=[pd.Timestamp(T0 + timedelta(hours=8))])
    eng.step(T0 + timedelta(hours=8, minutes=1))
    got = b.sleeve("carry")["usdt"] - before
    assert got == pytest.approx(2 * 1000 / 1.5 * 0.0001, rel=0.02)   # BTC e ETH
    # dia seguinte: posição do rompimento é fechada
    m.hi = None
    eng.step(T0 + timedelta(days=1))
    assert b.perp_qty("breakout", "BTCUSDT") == 0
    # preço não mudou: perdeu só taxas + a diferença entre o gatilho (comprou acima) e o fechamento
    e = b.equity(m.price)
    breakout_loss = sum(500 / lvl * (lvl - px) for lvl, px in ((204.0, 200.0), (20.4, 20.0)))
    assert e["total"] == pytest.approx(4000 - breakout_loss, abs=6)   # ~6 USDT de taxas
    assert e["breakout"] == pytest.approx(1000 - breakout_loss, abs=1.5)


def test_kill_switch(eng):
    m, b = eng.m, eng.b
    # queda de 70% só afeta a gaveta de tendência (1000 de 4000) => -17,5% no total
    eng.cfg["risk"] = {"max_drawdown": 0.15}
    eng.step(T0)
    for p in m.price:
        m.price[p] *= 0.3          # queda de 70%
    eng.step(T0 + timedelta(hours=1))
    assert eng.meta["killed"]
    assert b.spot_qty("trend", "BTC") == 0
    # carry segue neutro: a perda do spot é compensada pelo perp
    e = b.equity(m.price)
    assert e["carry"] == pytest.approx(2000, rel=0.01)


def test_carry_rehedge_keeps_neutral(eng):
    m, b = eng.m, eng.b
    eng.step(T0)
    m.price["BTCUSDT"] *= 1.3      # alta de 30% => re-hedge
    eng.step(T0 + timedelta(hours=1))
    q = b.spot_qty("carry", "BTC")
    assert q == pytest.approx(-b.perp_qty("carry", "BTCUSDT"), rel=1e-9)
    assert b.equity(m.price)["carry"] == pytest.approx(2000, rel=0.01)


def test_perp_accounting(tmp_path):
    b = PaperBroker(tmp_path / "x.json", {"s": 1000}, fee_perp=0.0, slippage=0.0)
    b.perp_trade("s", "BTCUSDT", 1.0, 100)      # compra 1 @100
    b.perp_trade("s", "BTCUSDT", 1.0, 110)      # compra 1 @110 => médio 105
    assert b.perp_entry("s", "BTCUSDT") == pytest.approx(105)
    b.perp_trade("s", "BTCUSDT", -2.0, 120)     # vende 2 @120 => +30
    assert b.perp_qty("s", "BTCUSDT") == 0
    assert b.sleeve("s")["usdt"] == pytest.approx(1030)
    b.perp_trade("s", "BTCUSDT", -1.0, 100)     # vendido 1 @100
    assert b.equity({"BTCUSDT": 90})["s"] == pytest.approx(1040)
