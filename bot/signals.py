"""Sinais das estratégias aprovadas na pesquisa (research/). Funções puras, sem rede.

Todas recebem candles DIÁRIOS (UTC) já FECHADOS — a última linha é o último dia completo.
A paridade com o backtest é verificada em bot/tests/test_signals.py.
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

TREND_SMA = (50, 100, 150, 200)
TREND_MOM = (30, 60, 90, 180)


def trend_target(close: pd.Series) -> float:
    """Estratégia A — fração do capital da estratégia a manter em BTC (0 a 1, em passos de 1/8).

    8 votos: preço > média móvel de 50/100/150/200 dias e retorno positivo em 30/60/90/180 dias.
    """
    c = close.dropna()
    votes = []
    for n in TREND_SMA:
        votes.append(float(len(c) >= n and c.iloc[-1] > c.iloc[-n:].mean()))
    for lb in TREND_MOM:
        votes.append(float(len(c) > lb and c.iloc[-1] > c.iloc[-1 - lb]))
    return sum(votes) / len(votes)


@dataclass
class BreakoutPlan:
    active: bool        # filtro de tendência permite operar hoje?
    level: float        # preço de gatilho (ordem stop de compra)
    day_open: float
    k: float


def breakout_plan(daily: pd.DataFrame, day_open: float, k: float = 0.5, trend_n: int = 50) -> BreakoutPlan:
    """Estratégia B — compra se o preço de hoje atingir  abertura + k × (máxima − mínima de ontem),
    somente se a abertura estiver acima da média dos últimos `trend_n` fechamentos. Sai no fim do dia UTC.
    """
    d = daily.dropna(subset=["high", "low", "close"])
    rng = float(d["high"].iloc[-1] - d["low"].iloc[-1])
    level = day_open + k * rng
    active = len(d) >= trend_n and day_open > float(d["close"].iloc[-trend_n:].mean())
    return BreakoutPlan(active=bool(active), level=level, day_open=day_open, k=k)


def carry_target() -> float:
    """Estratégia C — hedge spot comprado + perpétuo vendido, sempre ligado (1 = 100% do nocional).

    Na pesquisa, ligar/desligar pelo funding recente com limiares baixos piorou o resultado
    (custo do vai-e-vem). O bot só desliga por regra de risco (ver engine).
    """
    return 1.0
