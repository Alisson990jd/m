"""Biblioteca de sinais. Cada função recebe um DataFrame OHLC e devolve o peso-alvo
decidido no fechamento de cada barra (sem olhar o futuro: só usa dados até t)."""
from __future__ import annotations

import numpy as np
import pandas as pd

from bt import atr, ema, hold_until, realized_vol, rsi, sma


# ------------------------------------------------------------------ seguimento de tendência
def sma_cross(df, fast, slow, short=False):
    f, s = sma(df.close, fast), sma(df.close, slow)
    pos = (f > s).astype(float)
    if short:
        pos = pos - (f < s).astype(float)
    return pos.where(s.notna(), 0.0)


def above_sma(df, n, short=False):
    s = sma(df.close, n)
    pos = (df.close > s).astype(float)
    if short:
        pos = pos - (df.close < s).astype(float)
    return pos.where(s.notna(), 0.0)


def donchian(df, n_entry, n_exit, short=False):
    hi = df.high.rolling(n_entry).max().shift(1)
    lo = df.low.rolling(n_exit).min().shift(1)
    long_ = hold_until(df.close > hi, df.close < lo)
    if not short:
        return long_
    lo_e = df.low.rolling(n_entry).min().shift(1)
    hi_x = df.high.rolling(n_exit).max().shift(1)
    short_ = hold_until(df.close < lo_e, df.close > hi_x)
    return long_ - short_


def tsmom(df, lookback, short=False):
    r = df.close / df.close.shift(lookback) - 1
    pos = (r > 0).astype(float)
    if short:
        pos = pos - (r < 0).astype(float)
    return pos.where(r.notna(), 0.0)


def vol_target(df, pos, target, n, ppy, cap=1.0):
    """Escala a posição para mirar uma volatilidade anual `target`."""
    v = realized_vol(df.close, n, ppy)
    w = (target / v).clip(upper=cap)
    return (pos * w).fillna(0.0)


# ------------------------------------------------------------------ reversão à média
def rsi_revert(df, n, lo, hi, trend_n=None):
    r = rsi(df.close, n)
    entry = r < lo
    if trend_n:
        entry = entry & (df.close > sma(df.close, trend_n))
    return hold_until(entry, r > hi)


def zscore_revert(df, n, k_in, k_out=0.0, trend_n=None):
    m = sma(df.close, n)
    sd = df.close.rolling(n).std()
    z = (df.close - m) / sd
    entry = z < -k_in
    if trend_n:
        entry = entry & (df.close > sma(df.close, trend_n))
    return hold_until(entry, z > -k_out)


def ibs_revert(df, lo=0.2, hi=0.8, trend_n=None):
    """Internal Bar Strength: (C-L)/(H-L). Compra fechamento fraco, vende fechamento forte."""
    ibs = (df.close - df.low) / (df.high - df.low).replace(0, np.nan)
    entry = ibs < lo
    if trend_n:
        entry = entry & (df.close > sma(df.close, trend_n))
    return hold_until(entry, ibs > hi)


def rsi2_connors(df, lo=10, exit_n=5, trend_n=200):
    """Connors: compra RSI(2) < lo acima da SMA200, sai quando fecha acima da SMA(exit_n)."""
    r = rsi(df.close, 2)
    entry = r < lo
    if trend_n:
        entry = entry & (df.close > sma(df.close, trend_n))
    return hold_until(entry, df.close > sma(df.close, exit_n))


# ------------------------------------------------------------------ versões comprado/vendido
def zscore_revert_ls(df, n, k_in, k_out=0.0):
    m = sma(df.close, n)
    sd = df.close.rolling(n).std()
    z = (df.close - m) / sd
    return hold_until(z < -k_in, z > -k_out) - hold_until(z > k_in, z < k_out)


def rsi_revert_ls(df, n, lo, hi, mid=50):
    r = rsi(df.close, n)
    return hold_until(r < lo, r > mid) - hold_until(r > hi, r < mid)
