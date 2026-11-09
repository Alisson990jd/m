"""Motor de backtest vetorizado + métricas.

Convenções (evitam olhar o futuro):
  - `pos` é o peso-alvo decidido com informação até o FECHAMENTO da barra t.
  - exec="close": a ordem é executada no fechamento de t (ex.: ordem MOC ou cripto 24/7,
    onde o fechamento de t é praticamente a abertura de t+1). Retorno da barra t+1 = pos_t * r_{t+1}.
  - exec="open": a ordem é executada na ABERTURA de t+1. O gap noturno (C_t -> O_{t+1})
    pertence à posição antiga e o intradiário (O_{t+1} -> C_{t+1}) à posição nova.
  - Custo = cost_side * |Δpeso| a cada troca (taxa + slippage por lado).
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

DATA = Path(__file__).resolve().parent / "data"


# ----------------------------------------------------------------------------- dados
def load(name: str) -> pd.DataFrame:
    return pd.read_parquet(DATA / f"{name}.parquet")


def crypto_segments(sym: str, kind: str = "spot", max_gap: str = "3D") -> list[pd.DataFrame]:
    """Divide a série em lacunas longas. Ex.: LUNA antiga (colapso em mai/2022) e a 'LUNA 2.0'
    listada depois com o mesmo código; FTT ficou ~1 ano sem negociar. Emendar as séries
    criaria saltos falsos de milhares de vezes."""
    df = load(f"crypto_{kind}_{sym}_1h")
    gap = df.index.to_series().diff() > pd.Timedelta(max_gap)
    seg_id = gap.cumsum()
    return [g for _, g in df.groupby(seg_id)]


def load_crypto(sym: str, freq: str = "1h", kind: str = "spot", seg: int = 0) -> pd.DataFrame:
    """`sym` pode ter sufixo '#2' para o 2º segmento (ver crypto_segments)."""
    if "#" in sym:
        sym, s = sym.split("#")
        seg = int(s) - 1
    segs = crypto_segments(sym, kind)
    df = segs[seg]
    if freq != "1h":
        df = resample_ohlc(df, freq)
    return df


def crypto_universe(kind: str = "spot") -> list[str]:
    syms = sorted(p.name.split("_")[2] for p in DATA.glob(f"crypto_{kind}_*_1h.parquet"))
    out = []
    for s in syms:
        n = len(crypto_segments(s, kind))
        out += [s] + [f"{s}#{i + 1}" for i in range(1, n)]
    return out


def resample_ohlc(df: pd.DataFrame, freq: str) -> pd.DataFrame:
    agg = {"open": "first", "high": "max", "low": "min", "close": "last"}
    for c in ("volume", "quote_volume", "trades", "taker_buy_quote"):
        if c in df:
            agg[c] = "sum"
    out = df.resample(freq, label="left", closed="left").agg(agg)
    return out.dropna(subset=["close"])


def load_yahoo(group: str, ticker: str, freq: str = "1d", adjusted: bool = True) -> pd.DataFrame:
    safe = ticker.replace("^", "IDX_").replace("=", "_").replace(".", "_")
    df = load(f"{group}_{safe}_{freq}").copy()
    df = df[(df["close"] > 0) & (df["open"] > 0)]
    if adjusted and "adjclose" in df:
        f = df["adjclose"] / df["close"]
        for c in ("open", "high", "low", "close"):
            df[c] = df[c] * f
    # algumas barras do Yahoo vêm com open=0/NaN; corrige com o close anterior
    df["open"] = df["open"].where(df["open"] > 0, df["close"].shift())
    df["high"] = df[["high", "open", "close"]].max(axis=1)
    df["low"] = df[["low", "open", "close"]].min(axis=1)
    if freq == "1d":
        df.index = df.index.tz_convert(None).normalize()
        df = df[~df.index.duplicated(keep="last")]
    if group == "fx":
        df = clean_fx(df, freq)
    return df.dropna(subset=["open", "close"])


def clean_fx(df: pd.DataFrame, freq: str, k: float = 8.0) -> pd.DataFrame:
    """Dados de câmbio do Yahoo têm picos falsos (ex.: EURUSD +17% em 08/12/2008, que se
    desfaz no dia seguinte) e barras de fim de semana. Remove: (1) barras de sábado/domingo
    no diário; (2) barras cujo preço salta > k desvios robustos e volta no período seguinte.
    Choques reais e persistentes (ex.: franco suíço em 15/01/2015) são mantidos."""
    if freq == "1d":
        df = df[df.index.dayofweek < 5]
    for _ in range(3):
        lr = np.log(df["close"]).diff()
        sig = lr.abs().rolling(250, min_periods=20).median().bfill() * 1.4826
        nxt = lr.shift(-1)
        spike = (lr.abs() > k * sig) & (nxt.abs() > k * sig) & (np.sign(lr) != np.sign(nxt)) & \
                ((lr + nxt).abs() < 0.5 * lr.abs())
        if not spike.any():
            break
        df = df[~spike]
    # high/low incoerentes com o fechamento (comuns no Yahoo FX) => limita à faixa [open, close] ampliada
    return df


# ----------------------------------------------------------------------------- backtest
@dataclass
class Result:
    returns: pd.Series     # retorno líquido por barra
    gross: pd.Series       # retorno bruto por barra
    pos: pd.Series         # peso efetivamente mantido em cada barra
    turnover: pd.Series    # |Δpeso| executado em cada barra

    def equity(self) -> pd.Series:
        return (1 + self.returns).cumprod()


def backtest(df: pd.DataFrame, pos: pd.Series, cost_side: float, exec: str = "close",
             carry: pd.Series | None = None) -> Result:
    """`carry` opcional: retorno extra por barra recebido por unidade de peso (ex.: funding)."""
    pos = pos.reindex(df.index).ffill().fillna(0.0).astype(float)
    c, o = df["close"], df["open"]
    if exec == "close":
        held = pos.shift(1).fillna(0.0)
        gross = held * c.pct_change().fillna(0.0)
        trade = (pos - pos.shift(1).fillna(0.0)).abs().shift(1).fillna(0.0)
    elif exec == "open":
        prev = pos.shift(1).fillna(0.0)       # decidido em t-1, executado na abertura de t
        prev2 = pos.shift(2).fillna(0.0)
        gap = o / c.shift(1) - 1
        intra = c / o - 1
        # composição exata: gap com a posição antiga, depois rebalanceia na abertura
        gross = (1 + prev2 * gap.fillna(0.0)) * (1 + prev * intra.fillna(0.0)) - 1
        held = prev
        trade = (prev - prev2).abs()
    else:
        raise ValueError(exec)
    if carry is not None:
        gross = gross + held * carry.reindex(df.index).fillna(0.0)
    net = gross - trade * cost_side
    return Result(net, gross, held, trade)


# ----------------------------------------------------------------------------- métricas
def periods_per_year(idx: pd.Index) -> float:
    years = (idx[-1] - idx[0]).total_seconds() / (365.25 * 86400)
    return len(idx) / years if years > 0 else np.nan


def max_drawdown(eq: pd.Series) -> float:
    return float((eq / eq.cummax() - 1).min())


def probabilistic_sharpe(r: pd.Series, sr_benchmark: float = 0.0) -> float:
    """PSR (Bailey & López de Prado): P(Sharpe verdadeiro > benchmark), por barra."""
    r = r.dropna()
    n = len(r)
    if n < 30 or r.std() == 0:
        return np.nan
    sr = r.mean() / r.std()
    sk, ku = stats.skew(r), stats.kurtosis(r, fisher=False)
    denom = np.sqrt(max(1e-12, 1 - sk * sr + (ku - 1) / 4 * sr ** 2))
    return float(stats.norm.cdf((sr - sr_benchmark) * np.sqrt(n - 1) / denom))


def expected_max_sharpe(n_trials: int, var_sr: float) -> float:
    """Sharpe máximo esperado por SORTE entre n_trials (para o Deflated Sharpe)."""
    if n_trials <= 1:
        return 0.0
    g = 0.5772156649
    z1 = stats.norm.ppf(1 - 1 / n_trials)
    z2 = stats.norm.ppf(1 - 1 / (n_trials * np.e))
    return float(np.sqrt(var_sr) * ((1 - g) * z1 + g * z2))


def metrics(res: Result | pd.Series, ppy: float | None = None) -> dict:
    r = res.returns if isinstance(res, Result) else res
    r = r.dropna()
    if len(r) < 2:
        return {}
    ppy = ppy or periods_per_year(r.index)
    eq = (1 + r).cumprod()
    years = len(r) / ppy
    total = eq.iloc[-1] - 1
    cagr = eq.iloc[-1] ** (1 / years) - 1 if eq.iloc[-1] > 0 else -1.0
    vol = r.std() * np.sqrt(ppy)
    sharpe = r.mean() / r.std() * np.sqrt(ppy) if r.std() > 0 else np.nan
    dn = r[r < 0].std()
    sortino = r.mean() / dn * np.sqrt(ppy) if dn and dn > 0 else np.nan
    mdd = max_drawdown(eq)
    out = {
        "CAGR": cagr, "Vol": vol, "Sharpe": sharpe, "Sortino": sortino, "MaxDD": mdd,
        "Calmar": cagr / abs(mdd) if mdd < 0 else np.nan, "Total": total, "Anos": years,
        "PSR": probabilistic_sharpe(r),
    }
    if isinstance(res, Result):
        p = res.pos.reindex(r.index)
        tr = res.turnover.reindex(r.index)
        out["Exposicao"] = float((p.abs() > 1e-9).mean())
        out["GiroAno"] = float(tr.sum() / years)
        # trades: cada entrada a partir de zero conta como 1
        entries = ((p.abs() > 1e-9) & (p.shift(1).fillna(0).abs() <= 1e-9)).sum()
        out["Trades"] = int(entries)
        out["CustoAno"] = float((res.gross - res.returns).reindex(r.index).sum() / years)
    return out


def split_metrics(res: Result, split: str, ppy: float | None = None) -> dict:
    """Métricas completas, dentro da amostra (IS, < split) e fora da amostra (OOS, >= split)."""
    r = res.returns
    ppy = ppy or periods_per_year(r.index)
    out = {}
    for tag, mask in (("ALL", slice(None)), ("IS", r.index < split), ("OOS", r.index >= split)):
        sub = Result(r[mask], res.gross[mask], res.pos[mask], res.turnover[mask])
        for k, v in metrics(sub, ppy).items():
            out[f"{tag}_{k}"] = v
    return out


def fmt_table(df: pd.DataFrame, cols: list[str] | None = None) -> str:
    d = df[cols] if cols else df
    pct = [c for c in d.columns if any(k in c for k in ("CAGR", "Vol", "MaxDD", "Total",
                                                        "Exposicao", "CustoAno"))]
    out = d.copy()
    for c in out.columns:
        if c in pct:
            out[c] = out[c].map(lambda x: f"{x:7.1%}" if pd.notna(x) else "   -")
        elif out[c].dtype.kind == "f":
            out[c] = out[c].map(lambda x: f"{x:6.2f}" if pd.notna(x) else "  -")
    return out.to_string()


# ----------------------------------------------------------------------------- indicadores
def sma(s: pd.Series, n: int) -> pd.Series:
    return s.rolling(n, min_periods=n).mean()


def ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False, min_periods=n).mean()


def rsi(s: pd.Series, n: int) -> pd.Series:
    d = s.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    rs = up / dn.replace(0, np.nan)
    return (100 - 100 / (1 + rs)).fillna(100.0).where(up.notna())


def atr(df: pd.DataFrame, n: int) -> pd.Series:
    pc = df["close"].shift(1)
    tr = pd.concat([df["high"] - df["low"], (df["high"] - pc).abs(), (df["low"] - pc).abs()],
                   axis=1).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False, min_periods=n).mean()


def realized_vol(s: pd.Series, n: int, ppy: float) -> pd.Series:
    return s.pct_change().rolling(n, min_periods=n).std() * np.sqrt(ppy)


def hold_until(entry: pd.Series, exit_: pd.Series) -> pd.Series:
    """Máquina de estados long-only: entra quando entry, sai quando exit_ (1/0)."""
    e = entry.fillna(False).to_numpy()
    x = exit_.fillna(False).to_numpy()
    out = np.zeros(len(e))
    state = 0.0
    for i in range(len(e)):
        if state == 0 and e[i]:
            state = 1.0
        elif state == 1 and x[i]:
            state = 0.0
        out[i] = state
    return pd.Series(out, index=entry.index)
