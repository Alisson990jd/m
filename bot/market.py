"""Dados públicos de mercado da Binance (sem chave de API).

Spot: data-api.binance.vision (espelho público só de dados) com fallback para api.binance.com.
Perpétuos (funding): fapi.binance.com — bloqueado em algumas regiões (ex.: EUA); nesse caso
as funções devolvem None e o bot registra um aviso em vez de quebrar.
"""
from __future__ import annotations

import logging
import time

import pandas as pd
import requests

log = logging.getLogger("bot.market")
SPOT_HOSTS = ["https://data-api.binance.vision", "https://api.binance.com"]
FAPI = "https://fapi.binance.com"
_S = requests.Session()
_S.headers.update({"User-Agent": "trading-bot/1.0"})


def _get(path: str, params: dict, hosts=SPOT_HOSTS, tries: int = 3):
    last = None
    for h in hosts:
        for i in range(tries):
            try:
                r = _S.get(h + path, params=params, timeout=15)
                if r.status_code == 200:
                    return r.json()
                last = f"{r.status_code} {r.text[:120]}"
                if r.status_code in (403, 451):   # bloqueio regional: tenta o próximo host
                    break
            except requests.RequestException as e:
                last = str(e)
            time.sleep(2 ** i)
    raise ConnectionError(f"falha em {path}: {last}")


def klines(symbol: str, interval: str, limit: int = 500, start_ms: int | None = None) -> pd.DataFrame:
    p = {"symbol": symbol, "interval": interval, "limit": limit}
    if start_ms is not None:
        p["startTime"] = start_ms
    rows = _get("/api/v3/klines", p)
    df = pd.DataFrame(rows, columns=["open_time", "open", "high", "low", "close", "volume", "close_time",
                                     "qv", "n", "tb", "tq", "x"])
    df.index = pd.to_datetime(df["open_time"], unit="ms", utc=True)
    out = df[["open", "high", "low", "close", "volume"]].astype(float)
    out["close_time"] = df["close_time"].astype("int64").values
    return out


def daily_closed(symbol: str, now_ms: int | None = None, limit: int = 400) -> tuple[pd.DataFrame, float]:
    """(candles diários FECHADOS, preço de abertura do dia UTC corrente)."""
    df = klines(symbol, "1d", limit=limit)
    now_ms = now_ms or int(time.time() * 1000)
    closed = df[df["close_time"] < now_ms]
    current = df[df["close_time"] >= now_ms]
    day_open = float(current["open"].iloc[0]) if len(current) else float(closed["close"].iloc[-1])
    return closed, day_open


def max_high_since(symbol: str, start_ms: int) -> float | None:
    """Máxima dos candles de 1 minuto desde start_ms (detecta se uma ordem stop teria disparado)."""
    hi, cursor = None, start_ms
    while True:
        df = klines(symbol, "1m", limit=1000, start_ms=cursor)
        if df.empty:
            break
        m = float(df["high"].max())
        hi = m if hi is None else max(hi, m)
        if len(df) < 1000:
            break
        cursor = int(df["close_time"].iloc[-1]) + 1
    return hi


def last_price(symbol: str) -> float:
    return float(_get("/api/v3/ticker/price", {"symbol": symbol})["price"])


def funding_history(symbol: str, start_ms: int) -> pd.Series | None:
    try:
        rows = _get("/fapi/v1/fundingRate", {"symbol": symbol, "startTime": start_ms, "limit": 1000},
                    hosts=[FAPI], tries=2)
    except ConnectionError as e:
        log.warning("funding indisponível (%s) — região bloqueada? %s", symbol, e)
        return None
    if not rows:
        return pd.Series(dtype=float)
    s = pd.Series([float(r["fundingRate"]) for r in rows],
                  index=pd.to_datetime([int(r["fundingTime"]) for r in rows], unit="ms", utc=True))
    return s
