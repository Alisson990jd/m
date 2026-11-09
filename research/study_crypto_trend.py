"""Estudo 1 (cripto): seguimento de tendência em BTC/ETH e numa cesta de altcoins.

Período de treino (IS): até 2022-12-31. Teste (OOS): 2023-01-01 em diante.
Custos por lado: spot 0,10% (BTC/ETH) / 0,15% (alts); perpétuo 0,06%.
"""
import itertools
import sys

import numpy as np
import pandas as pd

import strategies as S
from bt import backtest, load_crypto, periods_per_year, split_metrics

SPLIT = "2023-01-01"
COST_SPOT_MAJOR, COST_SPOT_ALT, COST_PERP = 0.0010, 0.0015, 0.0006

GRIDS = {
    "sma_cross": [dict(fast=f, slow=s) for f, s in itertools.product([5, 10, 20, 50], [20, 50, 100, 200]) if f < s],
    "above_sma": [dict(n=n) for n in [10, 20, 50, 100, 150, 200]],
    "donchian": [dict(n_entry=a, n_exit=b) for a, b in itertools.product([20, 50, 100], [10, 20, 50]) if b <= a],
    "tsmom": [dict(lookback=n) for n in [7, 14, 30, 60, 90, 180]],
}
TF_MULT = {"1D": 1, "4h": 6}   # parâmetros em dias, convertidos em barras


def run(sym, tf, cost_long):
    df = load_crypto(sym, tf)
    df = df[df.index >= "2018-01-01"]
    ppy = periods_per_year(df.index)
    rows = []
    bh = backtest(df, pd.Series(1.0, index=df.index), cost_long)
    rows.append(dict(sym=sym, tf=tf, fam="buy_hold", params="-", mode="long", **split_metrics(bh, SPLIT, ppy)))
    m = TF_MULT[tf]
    for fam, grid in GRIDS.items():
        fn = getattr(S, fam)
        for p in grid:
            pb = {k: v * m for k, v in p.items()}
            for mode, short, cost in (("long", False, cost_long), ("ls", True, COST_PERP)):
                pos = fn(df, **pb, short=short)
                res = backtest(df, pos, cost)
                rows.append(dict(sym=sym, tf=tf, fam=fam, params=str(p), mode=mode,
                                 **split_metrics(res, SPLIT, ppy)))
                # versão com alvo de volatilidade (60% a.a., janela 30 dias, sem alavancagem)
                if mode == "long":
                    pv = S.vol_target(df, pos, 0.6, 30 * m, ppy, cap=1.0)
                    res = backtest(df, pv, cost)
                    rows.append(dict(sym=sym, tf=tf, fam=fam + "+vt", params=str(p), mode=mode,
                                     **split_metrics(res, SPLIT, ppy)))
    return rows


def summarize(res: pd.DataFrame) -> pd.DataFrame:
    out = []
    for (sym, tf, fam, mode), g in res.groupby(["sym", "tf", "fam", "mode"]):
        if g["IS_Sharpe"].isna().all():   # segmento sem período de treino (ex.: FTT#2)
            continue
        best = g.loc[g["IS_Sharpe"].idxmax()]
        out.append(dict(sym=sym, tf=tf, fam=fam, mode=mode, n=len(g),
                        best_params=best["params"],
                        IS_Sharpe_best=best["IS_Sharpe"], OOS_Sharpe_best=best["OOS_Sharpe"],
                        OOS_CAGR_best=best["OOS_CAGR"], OOS_MaxDD_best=best["OOS_MaxDD"],
                        OOS_Sharpe_med=g["OOS_Sharpe"].median(),
                        IS_Sharpe_med=g["IS_Sharpe"].median(),
                        frac_OOS_pos=(g["OOS_Sharpe"] > 0).mean()))
    return pd.DataFrame(out)


if __name__ == "__main__":
    syms = sys.argv[1:] or ["BTC", "ETH"]
    if syms == ["ALL"]:
        from bt import crypto_universe
        syms = crypto_universe()
    rows = []
    for sym in syms:
        cost = COST_SPOT_MAJOR if sym in ("BTC", "ETH") else COST_SPOT_ALT
        for tf in TF_MULT:
            rows += run(sym, tf, cost)
            print("ok", sym, tf, flush=True)
    res = pd.DataFrame(rows)
    tag = "_".join(syms) if len(syms) <= 3 else f"{len(syms)}coins"
    res.to_csv(f"results/crypto_trend_{tag}.csv", index=False)
    summ = summarize(res)
    summ.to_csv(f"results/crypto_trend_{tag}_summary.csv", index=False)
    pd.set_option("display.width", 250, "display.max_rows", 500)
    print(summ.round(2).to_string(index=False))
