"""Baixa dados históricos dos três mercados e salva em research/data/*.parquet.

Fontes:
  - Cripto: arquivos mensais públicos da Binance (data.binance.vision) + API
    pública de dados (data-api.binance.vision) para o mês corrente.
    Spot 1h para um universo amplo (inclui moedas que "morreram", ex. LUNA/FTT,
    para reduzir viés de sobrevivência), futuros perpétuos 1h e funding rates.
  - B3, EUA e Forex: Yahoo Finance (diário desde o início + 1h dos últimos 730 dias).

Uso:  python research/fetch_data.py [crypto|futures|yahoo|all]
"""
from __future__ import annotations

import io
import sys
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

DATA = Path(__file__).resolve().parent / "data"
DATA.mkdir(exist_ok=True)
UA = {"User-Agent": "Mozilla/5.0 (research-backtest)"}
SESSION = requests.Session()
SESSION.headers.update(UA)

SPOT_SYMBOLS = [
    "BTC", "ETH", "BNB", "XRP", "ADA", "SOL", "DOGE", "TRX", "LTC", "LINK",
    "AVAX", "DOT", "BCH", "XLM", "ATOM", "ETC", "UNI", "FIL", "NEAR", "AAVE",
    "ALGO", "VET", "EOS", "NEO", "XTZ", "MATIC", "LUNA", "FTT", "ICP", "SAND",
    "MANA", "AXS", "THETA", "HBAR", "ZEC", "DASH", "IOTA", "ONT", "QTUM", "WAVES",
]
FUT_SYMBOLS = ["BTC", "ETH", "BNB", "SOL", "XRP", "DOGE", "ADA", "LTC", "LINK", "AVAX",
               "DOT", "BCH", "TRX", "ETC", "XLM", "ATOM"]

KLINE_COLS = ["open_time", "open", "high", "low", "close", "volume", "close_time",
              "quote_volume", "trades", "taker_buy_base", "taker_buy_quote", "ignore"]

YAHOO = {
    # B3
    "b3": ["^BVSP", "BOVA11.SA", "SMAL11.SA", "PETR4.SA", "PETR3.SA", "VALE3.SA", "ITUB4.SA",
           "BBDC4.SA", "BBAS3.SA", "ABEV3.SA", "WEGE3.SA", "B3SA3.SA", "ITSA4.SA", "SUZB3.SA",
           "GGBR4.SA", "RENT3.SA", "AXIA3.SA", "VIVT3.SA", "PRIO3.SA", "LREN3.SA", "RADL3.SA",
           "BBSE3.SA", "CSNA3.SA", "USIM5.SA", "CMIG4.SA", "EMBJ3.SA", "HYPE3.SA", "TOTS3.SA",
           "EQTL3.SA", "SBSP3.SA"],
    # EUA
    "us": ["^GSPC", "SPY", "QQQ", "IWM", "DIA", "TLT", "IEF", "GLD", "SLV", "USO", "UUP",
           "EFA", "EEM", "XLK", "XLF", "XLE", "XLV", "XLY", "XLP", "XLI", "XLU", "XLB"],
    # Forex + metais/commodities
    "fx": ["EURUSD=X", "GBPUSD=X", "USDJPY=X", "AUDUSD=X", "USDCAD=X", "USDCHF=X", "NZDUSD=X",
           "EURJPY=X", "GBPJPY=X", "EURGBP=X", "AUDJPY=X", "USDBRL=X", "USDMXN=X", "GC=F",
           "SI=F", "CL=F"],
}


def _get(url: str, tries: int = 4, timeout: int = 60) -> requests.Response | None:
    for i in range(tries):
        try:
            r = SESSION.get(url, timeout=timeout)
            if r.status_code == 404:
                return None
            if r.status_code == 200:
                return r
        except requests.RequestException:
            pass
        time.sleep(2 ** i)
    return None


def _months(start: str, end: str) -> list[str]:
    return [p.strftime("%Y-%m") for p in pd.period_range(start, end, freq="M")]


def _parse_klines(raw: bytes) -> pd.DataFrame:
    df = pd.read_csv(io.BytesIO(raw), header=None)
    if not str(df.iloc[0, 0]).isdigit():  # alguns arquivos têm cabeçalho
        df = df.iloc[1:]
    df = df.iloc[:, :12]
    df.columns = KLINE_COLS
    t = df["open_time"].astype("int64")
    # A partir de 2025 a Binance passou a gravar timestamps em microssegundos.
    t = t.where(t < 10**14, t // 1000)
    df.index = pd.to_datetime(t, unit="ms", utc=True)
    df = df[["open", "high", "low", "close", "volume", "quote_volume", "trades",
             "taker_buy_quote"]].astype(float)
    return df


def _zip_bytes(r: requests.Response) -> bytes:
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        return z.read(z.namelist()[0])


def fetch_binance_klines(sym: str, market: str = "spot", interval: str = "1h",
                         start: str = "2017-08", end: str | None = None) -> pd.DataFrame | None:
    """market: 'spot' ou 'um' (futuros perpétuos USDT-M)."""
    end = end or (pd.Timestamp.now(tz="UTC") - pd.DateOffset(months=1)).strftime("%Y-%m")
    base = ("https://data.binance.vision/data/spot/monthly/klines" if market == "spot"
            else "https://data.binance.vision/data/futures/um/monthly/klines")
    pair = f"{sym}USDT"
    urls = [f"{base}/{pair}/{interval}/{pair}-{interval}-{m}.zip" for m in _months(start, end)]
    with ThreadPoolExecutor(12) as ex:
        parts = [r for r in ex.map(_get, urls) if r is not None]
    frames = [_parse_klines(_zip_bytes(r)) for r in parts]
    # mês corrente pela API pública de dados (somente spot está acessível daqui)
    if market == "spot":
        since = int((pd.Timestamp(end) + pd.offsets.MonthBegin(1)).timestamp() * 1000)
        while True:
            r = _get(f"https://data-api.binance.vision/api/v3/klines?symbol={pair}"
                     f"&interval={interval}&startTime={since}&limit=1000")
            if r is None or not r.json():
                break
            rows = r.json()
            df = pd.DataFrame([x[:12] for x in rows], columns=KLINE_COLS)
            buf = df.to_csv(index=False, header=False).encode()
            frames.append(_parse_klines(buf))
            since = rows[-1][0] + 1
            if len(rows) < 1000:
                break
    if not frames:
        return None
    out = pd.concat(frames).sort_index()
    return out[~out.index.duplicated(keep="last")]


def fetch_funding(sym: str, start: str = "2019-09", end: str | None = None) -> pd.DataFrame | None:
    end = end or (pd.Timestamp.now(tz="UTC") - pd.DateOffset(months=1)).strftime("%Y-%m")
    pair = f"{sym}USDT"
    base = "https://data.binance.vision/data/futures/um/monthly/fundingRate"
    urls = [f"{base}/{pair}/{pair}-fundingRate-{m}.zip" for m in _months(start, end)]
    with ThreadPoolExecutor(12) as ex:
        parts = [r for r in ex.map(_get, urls) if r is not None]
    frames = []
    for r in parts:
        df = pd.read_csv(io.BytesIO(_zip_bytes(r)))
        t = df["calc_time"].astype("int64")
        t = t.where(t < 10**14, t // 1000)
        frames.append(pd.DataFrame({"funding": df["last_funding_rate"].astype(float).values},
                                   index=pd.to_datetime(t, unit="ms", utc=True)))
    if not frames:
        return None
    out = pd.concat(frames).sort_index()
    return out[~out.index.duplicated(keep="last")]


def fetch_yahoo(ticker: str, interval: str = "1d", rng: str = "max") -> pd.DataFrame | None:
    # Com range=max o Yahoo devolve barras MENSAIS mesmo pedindo 1d; por isso o
    # histórico completo é pedido com period1/period2 explícitos.
    if rng == "max":
        span = f"period1=-1325635200&period2={int(time.time())}"
    else:
        span = f"range={rng}"
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{requests.utils.quote(ticker)}"
           f"?interval={interval}&{span}&includeAdjustedClose=true&events=div,splits")
    r = _get(url)
    if r is None:
        return None
    res = r.json()["chart"]["result"]
    if not res or "timestamp" not in res[0]:
        return None
    res = res[0]
    q = res["indicators"]["quote"][0]
    df = pd.DataFrame({k: q.get(k) for k in ["open", "high", "low", "close", "volume"]},
                      index=pd.to_datetime(res["timestamp"], unit="s", utc=True))
    if "adjclose" in res["indicators"]:
        df["adjclose"] = res["indicators"]["adjclose"][0]["adjclose"]
    else:
        df["adjclose"] = df["close"]
    df = df.dropna(subset=["close"]).astype(float)
    return df[~df.index.duplicated(keep="last")]


def run_crypto() -> None:
    for sym in SPOT_SYMBOLS:
        df = fetch_binance_klines(sym, "spot")
        if df is None:
            print("spot", sym, "sem dados", flush=True)
            continue
        df.to_parquet(DATA / f"crypto_spot_{sym}_1h.parquet")
        print("spot", sym, len(df), df.index[0].date(), "->", df.index[-1], flush=True)


def run_futures() -> None:
    for sym in FUT_SYMBOLS:
        df = fetch_binance_klines(sym, "um", start="2019-09")
        if df is not None:
            df.to_parquet(DATA / f"crypto_perp_{sym}_1h.parquet")
        fr = fetch_funding(sym)
        if fr is not None:
            fr.to_parquet(DATA / f"crypto_funding_{sym}.parquet")
        print("perp", sym, None if df is None else len(df),
              "funding", None if fr is None else len(fr), flush=True)


def run_yahoo() -> None:
    for group, tickers in YAHOO.items():
        for t in tickers:
            safe = t.replace("^", "IDX_").replace("=", "_").replace(".", "_")
            d = fetch_yahoo(t, "1d", "max")
            h = fetch_yahoo(t, "1h", "730d")
            if d is not None:
                d.to_parquet(DATA / f"{group}_{safe}_1d.parquet")
            if h is not None:
                h.to_parquet(DATA / f"{group}_{safe}_1h.parquet")
            print(group, t, "1d", None if d is None else (len(d), str(d.index[0].date())),
                  "1h", None if h is None else len(h), flush=True)
            time.sleep(0.3)


if __name__ == "__main__":
    what = sys.argv[1] if len(sys.argv) > 1 else "all"
    if what in ("yahoo", "all"):
        run_yahoo()
    if what in ("crypto", "all"):
        run_crypto()
    if what in ("futures", "all"):
        run_futures()
    print("FIM", datetime.now(timezone.utc).isoformat())
