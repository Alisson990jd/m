"""Estudo 4 (cripto): reversão à média intradiária, sazonalidade e rompimento de volatilidade."""
import itertools

import numpy as np
import pandas as pd
from scipy import stats

import strategies as S
from bt import backtest, load_crypto, periods_per_year, sma, split_metrics

SPLIT = "2023-01-01"
pd.set_option("display.width", 250, "display.max_rows", 400)


def mean_reversion():
    rows = []
    for sym, tf in itertools.product(["BTC", "ETH"], ["1h", "4h"]):
        df = load_crypto(sym, tf)
        df = df[df.index >= "2018-01-01"]
        ppy = periods_per_year(df.index)
        grids = (
            [("rsi", dict(n=n, lo=lo, hi=hi, trend_n=t)) for n, lo, hi, t in
             itertools.product([2, 3, 6, 14], [10, 20, 30], [50, 70], [None, 200])]
            + [("zscore", dict(n=n, k_in=k, k_out=0.0, trend_n=t)) for n, k, t in
               itertools.product([20, 50, 100], [1.5, 2.0, 2.5], [None, 200])]
        )
        for fam, p in grids:
            fn = S.rsi_revert if fam == "rsi" else S.zscore_revert
            pos = fn(df, **p)
            for cname, cost in (("perp_maker", 0.0003), ("perp_taker", 0.0006), ("spot", 0.0010)):
                res = backtest(df, pos, cost)
                rows.append(dict(sym=sym, tf=tf, fam=fam, params=str(p), cost=cname,
                                 **split_metrics(res, SPLIT, ppy)))
    r = pd.DataFrame(rows)
    r.to_csv("results/crypto_meanrev.csv", index=False)
    print("=== Reversão à média (mediana do grid / melhor no treino -> teste)")
    out = []
    for k, g in r.groupby(["sym", "tf", "fam", "cost"]):
        b = g.loc[g.IS_Sharpe.idxmax()]
        out.append(dict(zip(["sym", "tf", "fam", "cost"], k), IS_med=g.IS_Sharpe.median(),
                        OOS_med=g.OOS_Sharpe.median(), best=b.params, IS_best=b.IS_Sharpe,
                        OOS_best=b.OOS_Sharpe, OOS_CAGR_best=b.OOS_CAGR, trades_ano=b.ALL_Trades / b.ALL_Anos))
    print(pd.DataFrame(out).round(2).to_string(index=False))


def seasonality():
    print("\n=== Sazonalidade BTC (retorno médio por hora UTC e dia da semana, em bp)")
    df = load_crypto("BTC", "1h")
    df = df[df.index >= "2018-01-01"]
    r = df.close.pct_change().dropna()
    isr, oos = r[r.index < SPLIT], r[r.index >= SPLIT]
    hi = isr.groupby(isr.index.hour).mean() * 1e4
    ho = oos.groupby(oos.index.hour).mean() * 1e4
    t_is = isr.groupby(isr.index.hour).apply(lambda x: stats.ttest_1samp(x, 0).statistic)
    tab = pd.DataFrame({"IS_bp": hi, "t_IS": t_is, "OOS_bp": ho}).round(2)
    print(tab.T.to_string())
    print("correlação do perfil horário IS x OOS:", round(np.corrcoef(hi, ho)[0, 1], 2))
    # estratégia: ficar comprado só nas horas com retorno médio positivo no TREINO (t>1)
    good = t_is[t_is > 1.0].index.tolist()
    print("horas escolhidas no treino:", good)
    pos = pd.Series(df.index.hour.isin([(h - 1) % 24 for h in good]).astype(float), index=df.index)
    # pos decidida no fechamento da barra h-1 => mantida durante a barra h
    for cname, cost in (("perp_maker", 0.0003), ("spot", 0.0010)):
        m = split_metrics(backtest(df, pos, cost), SPLIT)
        print(f"  horas boas ({cname}): IS Sharpe {m['IS_Sharpe']:.2f} CAGR {m['IS_CAGR']:.1%} | "
              f"OOS Sharpe {m['OOS_Sharpe']:.2f} CAGR {m['OOS_CAGR']:.1%}")
    d = df.resample("1D").agg({"open": "first", "close": "last"}).dropna()
    dr = d.close.pct_change().dropna()
    dw = pd.DataFrame({"IS_bp": dr[dr.index < SPLIT].groupby(dr[dr.index < SPLIT].index.dayofweek).mean() * 1e4,
                       "OOS_bp": dr[dr.index >= SPLIT].groupby(dr[dr.index >= SPLIT].index.dayofweek).mean() * 1e4})
    dw.index = ["seg", "ter", "qua", "qui", "sex", "sab", "dom"]
    print(dw.round(1).T.to_string())


def vol_breakout():
    print("\n=== Rompimento de volatilidade diário (entra em open + k*amplitude de ontem, sai no fechamento)")
    rows = []
    for sym in ["BTC", "ETH", "SOL", "BNB", "XRP"]:
        d = load_crypto(sym, "1D")
        d = d[d.index >= "2018-01-01"]
        rng = (d.high - d.low).shift(1)
        for k, f, cost in itertools.product([0.3, 0.5, 0.7], [None, 20, 50], [0.0006, 0.0010]):
            lvl = d.open + k * rng
            hit = d.high >= lvl
            if f:
                hit &= d.open > sma(d.close, f).shift(1)
            ret = np.where(hit, d.close / lvl - 1 - 2 * cost, 0.0)
            ret = pd.Series(ret, index=d.index).fillna(0.0)
            from bt import metrics
            mi = metrics(ret[ret.index < SPLIT], 365.25)
            mo = metrics(ret[ret.index >= SPLIT], 365.25)
            rows.append(dict(sym=sym, k=k, filtro=f, cost=cost, IS_Sharpe=mi["Sharpe"], IS_CAGR=mi["CAGR"],
                             OOS_Sharpe=mo["Sharpe"], OOS_CAGR=mo["CAGR"], OOS_MaxDD=mo["MaxDD"],
                             freq=hit.mean()))
    r = pd.DataFrame(rows)
    r.to_csv("results/crypto_volbreakout.csv", index=False)
    print(r.groupby(["cost", "filtro"], dropna=False)[["IS_Sharpe", "OOS_Sharpe", "OOS_CAGR"]].median().round(2).to_string())
    print(r[r.sym == "BTC"].round(2).to_string(index=False))


if __name__ == "__main__":
    mean_reversion()
    seasonality()
    vol_breakout()
