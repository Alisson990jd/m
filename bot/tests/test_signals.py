"""Testes de paridade: os sinais do bot devem ser IDÊNTICOS às posições do backtest.

Rodar a partir da raiz do repositório:  python -m pytest bot/tests -q
(precisa dos dados em research/data — gere com  python research/fetch_data.py crypto)
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "research"))
sys.path.insert(0, str(ROOT))

DATA = ROOT / "research" / "data" / "crypto_spot_BTC_1h.parquet"
pytestmark = pytest.mark.skipif(not DATA.exists(), reason="dados de pesquisa não baixados")


def _daily(sym="BTC"):
    from bt import load_crypto
    d = load_crypto(sym, "1D")
    return d[d.index >= "2018-01-01"]


def test_trend_parity():
    from robustness import trend_ensemble_pos
    from bot.signals import trend_target
    d = _daily()
    ref = trend_ensemble_pos(d)
    for i in range(0, len(d), 7):  # amostra de dias ao longo de todo o histórico
        got = trend_target(d["close"].iloc[: i + 1])
        assert got == pytest.approx(ref.iloc[i]), d.index[i]


def test_breakout_parity():
    from bt import sma
    from bot.signals import breakout_plan
    d = _daily("ETH")
    rng = (d.high - d.low).shift(1)
    ref_level = d.open + 0.5 * rng
    ref_active = d.open > sma(d.close, 50).shift(1)
    for i in range(1, len(d), 5):
        p = breakout_plan(d.iloc[:i], day_open=float(d.open.iloc[i]), k=0.5, trend_n=50)
        assert p.level == pytest.approx(ref_level.iloc[i])
        assert p.active == bool(ref_active.iloc[i]), d.index[i]


def test_trend_bounds():
    from bot.signals import trend_target
    up = pd.Series(np.linspace(1, 2, 300))
    down = pd.Series(np.linspace(2, 1, 300))
    assert trend_target(up) == 1.0
    assert trend_target(down) == 0.0
    assert trend_target(up.iloc[:10]) == 0.0   # histórico insuficiente => fora
