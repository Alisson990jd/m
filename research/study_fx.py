"""Estudo 6 (Forex + ouro). Diário: treino até 2018-12-31, teste 2019+.
Horário (≈2,8 anos disponíveis): treino até 2025-06-30, teste depois.
Custos por lado: majors 0,01%; cruzamentos e ouro 0,02%; emergentes (BRL, MXN) 0,05%.
Swap/rollover (juros de carregar a posição) NÃO incluído — relevante em posições longas.
"""
import itertools

import numpy as np
import pandas as pd

import strategies as S
from bt import backtest, load_yahoo, metrics, periods_per_year, split_metrics

pd.set_option("display.width", 260, "display.max_rows", 400)
COSTS = {**{p: 0.0001 for p in ["EURUSD=X", "GBPUSD=X", "USDJPY=X", "AUDUSD=X", "USDCAD=X", "USDCHF=X", "NZDUSD=X"]},
         **{p: 0.0002 for p in ["EURJPY=X", "GBPJPY=X", "EURGBP=X", "AUDJPY=X", "GC=F"]},
         "USDBRL=X": 0.0005, "USDMXN=X": 0.0005}
START = {"USDBRL=X": "2006-04-01"}   # série do Yahoo quebrada antes disso


def candidates(df, hourly=False):
    m = 24 if hourly else 1
    c = {}
    for f, s in [(10, 50), (20, 100), (50, 200)]:
        c[f"sma_cross{f}/{s}"] = S.sma_cross(df, f * m, s * m, short=True)
    for a, b in [(20, 10), (50, 20), (100, 50)]:
        c[f"donchian{a}/{b}"] = S.donchian(df, a * m, b * m, short=True)
    for lb in [21, 63, 126, 252]:
        c[f"tsmom{lb}"] = S.tsmom(df, lb * m, short=True)
    for n, k in itertools.product([5, 10, 20], [1.0, 1.5, 2.0]):
        c[f"zrev{n}/{k}"] = S.zscore_revert_ls(df, n * m if hourly else n, k)
    for n, lo in [(2, 10), (2, 5), (3, 15), (14, 30)]:
        c[f"rsi{n}<{lo}"] = S.rsi_revert_ls(df, n, lo, 100 - lo)
    return c


def family(name):
    return "tendencia" if any(k in name for k in ("sma", "donchian", "tsmom")) else "reversao"


def run(freq, split):
    rows, rets = [], {}
    for tk, cost in COSTS.items():
        df = load_yahoo("fx", tk, freq)
        df = df[df.index >= START.get(tk, "2000-01-01")]
        if freq == "1h":
            df = df.copy()
        ppy = periods_per_year(df.index)
        for name, pos in candidates(df, hourly=(freq == "1h")).items():
            res = backtest(df, pos, cost)
            rows.append(dict(par=tk, estrategia=name, fam=family(name), **split_metrics(res, split, ppy)))
            rets[(tk, name)] = res.returns
    return pd.DataFrame(rows), rets


def portfolio(rets, names, split, ppy):
    """Carteira de risco igual: cada série escalada para 10% de vol (janela 60, sem olhar o futuro)."""
    scaled = []
    for (tk, name), r in rets.items():
        if name not in names:
            continue
        vol = r.rolling(60).std().shift(1) * np.sqrt(ppy)
        scaled.append((r * (0.10 / vol).clip(upper=3)).rename(f"{tk}|{name}"))
    P = pd.concat(scaled, axis=1).fillna(0).mean(axis=1)
    return {k: v for k, v in split_metrics_series(P, split, ppy).items()}


def split_metrics_series(r, split, ppy):
    out = {}
    for tag, m in (("IS", r.index < split), ("OOS", r.index >= split)):
        mm = metrics(r[m], ppy)
        for k in ("CAGR", "Sharpe", "MaxDD"):
            out[f"{tag}_{k}"] = mm.get(k)
    return out


if __name__ == "__main__":
    for freq, split in (("1d", "2019-01-01"), ("1h", "2025-07-01")):
        r, rets = run(freq, split)
        r.to_csv(f"results/fx_{freq}.csv", index=False)
        print(f"\n######## Forex {freq} — mediana entre pares, por estratégia (ordenado pelo treino)")
        g = r.groupby(["fam", "estrategia"])[["IS_Sharpe", "OOS_Sharpe", "OOS_CAGR", "OOS_MaxDD"]].median()
        g["frac_pares_OOS>0"] = r.groupby(["fam", "estrategia"])["OOS_Sharpe"].apply(lambda s: (s > 0).mean())
        print(g.sort_values("IS_Sharpe", ascending=False).round(2).to_string())
        ppy = 260 if freq == "1d" else 260 * 24
        print("\nCarteiras diversificadas (risco igual entre pares):")
        for label, names in (("tendência tsmom63+126+252", ["tsmom63", "tsmom126", "tsmom252"]),
                             ("tendência sma_cross 50/200", ["sma_cross50/200"]),
                             ("tendência donchian 50/20", ["donchian50/20"]),
                             ("reversão zrev5/1.5", ["zrev5/1.5"]),
                             ("reversão rsi2<10", ["rsi2<10"])):
            print(f"  {label:32s}", {k: round(v, 2) for k, v in portfolio(rets, names, split, ppy).items()})
        best = r.sort_values("IS_Sharpe", ascending=False).head(12)
        print("\nTop 12 combinações par/estratégia no treino -> teste:")
        print(best[["par", "estrategia", "IS_Sharpe", "OOS_Sharpe", "OOS_CAGR", "OOS_MaxDD"]].round(2).to_string(index=False))
