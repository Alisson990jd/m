"""Estudo 2 (cripto): momentum entre moedas (cross-sectional) com rotação periódica.

A cada R dias: entre as N moedas mais líquidas (volume médio de 30 dias) com histórico
suficiente, compra as K de maior retorno nos últimos L dias (peso igual). Filtro opcional
de regime: só investe se o BTC estiver acima da sua média móvel de F dias (senão, caixa).
Moedas que deixam de negociar (LUNA, FTT, etc.) são vendidas no último preço.
Universo sem viés de sobrevivência: inclui moedas que morreram.
"""
import itertools

import numpy as np
import pandas as pd

from bt import crypto_universe, load_crypto, metrics, periods_per_year

SPLIT = "2023-01-01"
COST = 0.0015


def panel():
    closes, vols = {}, {}
    for s in crypto_universe():
        d = load_crypto(s, "1D")
        closes[s], vols[s] = d["close"], d["quote_volume"]
    C = pd.DataFrame(closes).sort_index()
    V = pd.DataFrame(vols).reindex(C.index)
    C = C[C.index >= "2018-01-01"]
    return C, V.reindex(C.index)


def xs_momentum(C, V, L, K, R, F=None, N=20, abs_filter=False, skip=0, long_short=False,
                cost=COST):
    rets = C.pct_change(fill_method=None)
    alive = C.notna()
    liq = V.rolling(30, min_periods=20).mean()
    score = C.shift(skip) / C.shift(L + skip) - 1
    btc = C["BTC"]
    regime = (btc > btc.rolling(F).mean()) if F else pd.Series(True, index=C.index)
    dates = C.index
    W = np.zeros(len(C.columns))
    cols = C.columns
    out_ret, out_turn, out_w = [], [], []
    for i, t in enumerate(dates):
        # 1) retorno do dia com os pesos herdados (drift)
        r = rets.iloc[i].to_numpy()
        a = alive.iloc[i].to_numpy()
        r = np.where(np.isnan(r), 0.0, r)
        port = float(np.nansum(W * r))
        # pesos derivam com os preços; moeda que morreu vira caixa
        gross_val = 1 + port
        W = W * (1 + r) / gross_val if gross_val > 0 else W * 0
        W = np.where(a, W, 0.0)
        turn = 0.0
        # 2) rebalanceia no fechamento de t (vale a partir de t+1)
        if i % R == 0:
            tgt = np.zeros(len(cols))
            if regime.iloc[i]:
                sc = score.iloc[i]
                lq = liq.iloc[i]
                ok = sc.notna() & lq.notna() & alive.iloc[i]
                elig = lq[ok].nlargest(N).index
                ranked = sc[elig].sort_values(ascending=False)
                if abs_filter:
                    ranked = ranked[ranked > 0]
                top = ranked.index[:K]
                for c in top:
                    tgt[cols.get_loc(c)] = 1.0 / K
                if long_short and len(sc[elig]) >= 2 * K:
                    for c in sc[elig].sort_values().index[:K]:
                        tgt[cols.get_loc(c)] = -1.0 / K
            turn = float(np.abs(tgt - W).sum())
            W = tgt
        out_ret.append(port - turn * cost)
        out_turn.append(turn)
        out_w.append(W.copy())
    # 'port' em t usa pesos definidos no fechamento de t-1 (sem olhar o futuro);
    # o custo do rebalance feito no fechamento de t é cobrado em t.
    ret = pd.Series(out_ret, index=dates)
    return ret, pd.Series(out_turn, index=dates), pd.DataFrame(out_w, index=dates, columns=cols)


def split_stats(ret, turn):
    ppy = 365.25
    res = {}
    for tag, m in (("ALL", slice(None)), ("IS", ret.index < SPLIT), ("OOS", ret.index >= SPLIT)):
        mm = metrics(ret[m], ppy)
        for k in ("CAGR", "Sharpe", "MaxDD", "Calmar", "PSR"):
            res[f"{tag}_{k}"] = mm.get(k)
    res["GiroAno"] = turn.sum() / (len(turn) / ppy)
    return res


if __name__ == "__main__":
    C, V = panel()
    print("painel:", C.shape, C.index[0].date(), C.index[-1].date(), flush=True)
    rows = []
    # benchmarks
    btc = C["BTC"].pct_change().fillna(0)
    rows.append(dict(name="BTC buy&hold", **split_stats(btc, btc * 0)))
    ew, tw, _ = xs_momentum(C, V, L=1, K=20, R=7, N=20)  # K=N => peso igual no top-20 líquido
    rows.append(dict(name="Peso igual top-20 liquidas (semanal)", **split_stats(ew, tw)))
    ew, tw, _ = xs_momentum(C, V, L=1, K=20, R=7, N=20, F=100)
    rows.append(dict(name="Peso igual top-20 + filtro BTC>SMA100", **split_stats(ew, tw)))
    grid = itertools.product([7, 14, 30, 60, 90], [1, 3, 5], [7, 14], [None, 50, 100], [10, 20])
    for L, K, R, F, N in grid:
        ret, turn, _ = xs_momentum(C, V, L, K, R, F, N)
        rows.append(dict(name="xsmom", L=L, K=K, R=R, F=F, N=N, **split_stats(ret, turn)))
    print("grid ok", flush=True)
    # long/short (perpétuos): custo menor, sem funding (conservador p/ a perna vendida)
    for L, K in itertools.product([7, 14, 30, 60], [3, 5]):
        ret, turn, _ = xs_momentum(C, V, L, K, 7, None, 20, long_short=True, cost=0.0006)
        rows.append(dict(name="xsmom_LS", L=L, K=K, R=7, N=20, **split_stats(ret, turn)))
    res = pd.DataFrame(rows)
    res.to_csv("results/crypto_xs.csv", index=False)
    pd.set_option("display.width", 250, "display.max_rows", 400)
    show = ["name", "L", "K", "R", "F", "N", "IS_CAGR", "IS_Sharpe", "IS_MaxDD", "OOS_CAGR",
            "OOS_Sharpe", "OOS_MaxDD", "GiroAno"]
    print(res[show].head(3).round(2).to_string(index=False))
    g = res[res.name == "xsmom"]
    print("\nTop 15 por Sharpe no TREINO e o que aconteceu no TESTE:")
    print(g.sort_values("IS_Sharpe", ascending=False)[show].head(15).round(2).to_string(index=False))
    print("\nMediana OOS por filtro F:", g.groupby(g.F.fillna(0))[["IS_Sharpe", "OOS_Sharpe", "OOS_CAGR"]].median().round(2).to_dict())
    print("Mediana OOS por L:", g.groupby("L")[["IS_Sharpe", "OOS_Sharpe"]].median().round(2).to_dict())
    print("Mediana OOS por K:", g.groupby("K")[["IS_Sharpe", "OOS_Sharpe"]].median().round(2).to_dict())
    print("\nLong/short:")
    print(res[res.name == "xsmom_LS"][show].round(2).to_string(index=False))
