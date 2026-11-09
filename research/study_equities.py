"""Estudo 5 (B3 e EUA, diário). Treino: até 2018-12-31. Teste: 2019 em diante.

Custos por lado: SPY/QQQ/IWM 0,02%; ^BVSP (proxy do mini-índice WIN) 0,02%;
BOVA11/ações B3 0,05% (emolumentos + spread). Impostos (15%/20% no Brasil) NÃO incluídos.
Execução: sinal no fechamento, ordem no leilão de fechamento ("close") ou na abertura
seguinte ("open") — os dois são reportados para reversão à média, que é sensível a isso.
"""
import itertools

import numpy as np
import pandas as pd

import strategies as S
from bt import backtest, hold_until, load_yahoo, metrics, periods_per_year, sma, split_metrics

SPLIT = "2019-01-01"
pd.set_option("display.width", 260, "display.max_rows", 400)

INDICES = {("b3", "^BVSP"): 0.0002, ("b3", "BOVA11.SA"): 0.0005, ("us", "SPY"): 0.0002,
           ("us", "QQQ"): 0.0002, ("us", "IWM"): 0.0002}


def turn_of_month(df, before=4, after=3):
    """Comprado dos últimos `before` pregões do mês até o `after`-ésimo pregão do mês seguinte."""
    idx = df.index
    ym = idx.year * 12 + idx.month
    s = pd.Series(ym, index=idx)
    pos_in_month = s.groupby(s).cumcount()
    n_in_month = s.groupby(s).transform("size")
    from_end = n_in_month - pos_in_month  # 1 = último pregão do mês
    # dias cujo retorno queremos capturar: últimos `before` e primeiros `after` pregões
    in_window = (from_end <= before) | (pos_in_month < after)
    # a posição que rende no dia t é decidida no fechamento de t-1 (calendário é conhecido)
    return in_window.shift(-1).fillna(False).astype(float)


def index_strategies():
    rows = []
    for (grp, tk), cost in INDICES.items():
        df = load_yahoo(grp, tk)
        df = df[df.index >= "1995-01-01"]
        ppy = periods_per_year(df.index)
        cand = {"buy_hold": pd.Series(1.0, index=df.index)}
        for n in [50, 100, 150, 200]:
            cand[f"above_sma{n}"] = S.above_sma(df, n)
        for f, s in [(10, 50), (20, 100), (50, 200)]:
            cand[f"sma_cross{f}/{s}"] = S.sma_cross(df, f, s)
        for lb in [63, 126, 252]:
            cand[f"tsmom{lb}"] = S.tsmom(df, lb)
        for lo in [5, 10, 20]:
            cand[f"rsi2_connors<{lo}"] = S.rsi2_connors(df, lo=lo, exit_n=5, trend_n=200)
        cand["rsi2<10 sem filtro"] = S.rsi2_connors(df, lo=10, exit_n=5, trend_n=None)
        for lo in [0.1, 0.2, 0.3]:
            cand[f"ibs<{lo}"] = S.ibs_revert(df, lo=lo, hi=0.8)
        cand["ibs<0.2+sma200"] = S.ibs_revert(df, lo=0.2, hi=0.8, trend_n=200)
        cand["virada_mes(4,3)"] = turn_of_month(df, 4, 3)
        cand["virada_mes(2,2)"] = turn_of_month(df, 2, 2)
        for name, pos in cand.items():
            for ex in ("close", "open"):
                if ex == "open" and not any(k in name for k in ("rsi", "ibs", "virada")):
                    continue
                res = backtest(df, pos, cost, exec=ex)
                rows.append(dict(ativo=tk, estrategia=name, exec=ex, **split_metrics(res, SPLIT, ppy)))
        # overnight x intradiário (comprado só do fechamento à abertura / da abertura ao fechamento)
        on = (df.open / df.close.shift(1) - 1).fillna(0) - 2 * cost
        intra = (df.close / df.open - 1).fillna(0) - 2 * cost
        for name, r in (("overnight", on), ("intradiario", intra)):
            mi, mo = metrics(r[r.index < SPLIT], ppy), metrics(r[r.index >= SPLIT], ppy)
            rows.append(dict(ativo=tk, estrategia=name, exec="-", IS_Sharpe=mi["Sharpe"], IS_CAGR=mi["CAGR"],
                             IS_MaxDD=mi["MaxDD"], OOS_Sharpe=mo["Sharpe"], OOS_CAGR=mo["CAGR"],
                             OOS_MaxDD=mo["MaxDD"]))
    r = pd.DataFrame(rows)
    r.to_csv("results/equity_index.csv", index=False)
    cols = ["ativo", "estrategia", "exec", "IS_CAGR", "IS_Sharpe", "IS_MaxDD", "OOS_CAGR", "OOS_Sharpe",
            "OOS_MaxDD", "OOS_Exposicao", "ALL_Trades"]
    for tk in r.ativo.unique():
        print(f"\n--- {tk}")
        print(r[r.ativo == tk][cols].round(2).to_string(index=False))


def pairs():
    print("\n=== Pares (z-score do log da razão; entra |z|>2, sai z cruza 0). Custo 0,05%/perna/lado + aluguel 2% a.a.")
    pairs_ = [("PETR3.SA", "PETR4.SA"), ("ITUB4.SA", "BBDC4.SA"), ("ITUB4.SA", "ITSA4.SA"),
              ("BBAS3.SA", "ITUB4.SA"), ("GGBR4.SA", "CSNA3.SA"), ("CSNA3.SA", "USIM5.SA"),
              ("VALE3.SA", "CSNA3.SA"), ("BBDC4.SA", "BBAS3.SA"), ("XLK", "QQQ"), ("SPY", "DIA")]
    rows = []
    for a, b in pairs_:
        ga = "us" if "." not in a else "b3"
        A, B = load_yahoo(ga, a)["close"], load_yahoo(ga, b)["close"]
        idx = A.index.intersection(B.index)
        A, B = A.reindex(idx), B.reindex(idx)
        lr = np.log(A / B)
        ra, rb = A.pct_change().fillna(0), B.pct_change().fillna(0)
        for n, k in itertools.product([20, 60, 120], [1.5, 2.0, 2.5]):
            z = (lr - lr.rolling(n).mean()) / lr.rolling(n).std()
            longp = hold_until(z < -k, z > 0)    # compra A, vende B
            shortp = hold_until(z > k, z < 0)    # vende A, compra B
            pos = longp - shortp
            held = pos.shift(1).fillna(0)
            gross = held * (ra - rb) * 0.5      # 50% em cada perna (capital = 1)
            trade = (pos - held).abs().shift(1).fillna(0)
            net = gross - trade * 0.0005 - held.abs() * 0.5 * 0.02 / 252
            mi, mo = metrics(net[net.index < SPLIT], 252), metrics(net[net.index >= SPLIT], 252)
            rows.append(dict(par=f"{a}/{b}", n=n, k=k, IS_Sharpe=mi.get("Sharpe"), IS_CAGR=mi.get("CAGR"),
                             OOS_Sharpe=mo.get("Sharpe"), OOS_CAGR=mo.get("CAGR"), OOS_MaxDD=mo.get("MaxDD"),
                             expo=float((held != 0).mean())))
    r = pd.DataFrame(rows)
    r.to_csv("results/equity_pairs.csv", index=False)
    out = []
    for p, g in r.groupby("par"):
        b = g.loc[g.IS_Sharpe.idxmax()]
        out.append(dict(par=p, IS_med=g.IS_Sharpe.median(), OOS_med=g.OOS_Sharpe.median(),
                        best=f"n={b.n},k={b.k}", IS_best=b.IS_Sharpe, OOS_best=b.OOS_Sharpe,
                        OOS_CAGR_best=b.OOS_CAGR))
    print(pd.DataFrame(out).round(2).to_string(index=False))


def b3_momentum():
    print("\n=== Momentum entre ações da B3 (30 grandes empresas ATUAIS => viés de sobrevivência a favor!)")
    from fetch_data import YAHOO
    C = {}
    for t in YAHOO["b3"]:
        if t in ("^BVSP", "BOVA11.SA", "SMAL11.SA"):
            continue
        try:
            C[t] = load_yahoo("b3", t)["close"]
        except FileNotFoundError:
            pass
    C = pd.DataFrame(C).sort_index()
    C = C[C.index >= "2005-01-01"]
    M = C.resample("ME").last()
    rets_m = M.pct_change(fill_method=None)
    ibov = load_yahoo("b3", "^BVSP")["close"].resample("ME").last()
    rows = []
    for L, K, skip, filt in itertools.product([3, 6, 12], [5, 10], [0, 1], [False, True]):
        score = M.shift(skip) / M.shift(L + skip) - 1
        w = pd.DataFrame(0.0, index=M.index, columns=M.columns)
        for t in M.index:
            sc = score.loc[t].dropna()
            if len(sc) < K:
                continue
            if filt and not (ibov.reindex([t]).iloc[0] > ibov.rolling(10).mean().reindex([t]).iloc[0]):
                continue
            w.loc[t, sc.nlargest(K).index] = 1.0 / K
        held = w.shift(1).fillna(0)
        gross = (held * rets_m.fillna(0)).sum(axis=1)
        turn = (w - held).abs().sum(axis=1).shift(1).fillna(0)
        net = gross - turn * 0.0005
        mi, mo = metrics(net[net.index < SPLIT], 12), metrics(net[net.index >= SPLIT], 12)
        rows.append(dict(L=L, K=K, skip=skip, filtro_ibov=filt, IS_Sharpe=mi["Sharpe"], IS_CAGR=mi["CAGR"],
                         OOS_Sharpe=mo["Sharpe"], OOS_CAGR=mo["CAGR"], OOS_MaxDD=mo["MaxDD"]))
    ew = rets_m.mean(axis=1).fillna(0)
    ib = ibov.pct_change().reindex(M.index).fillna(0)
    for name, r in (("peso igual 27 ações", ew), ("Ibovespa", ib)):
        mi, mo = metrics(r[r.index < SPLIT], 12), metrics(r[r.index >= SPLIT], 12)
        rows.append(dict(L=name, IS_Sharpe=mi["Sharpe"], IS_CAGR=mi["CAGR"], OOS_Sharpe=mo["Sharpe"],
                         OOS_CAGR=mo["CAGR"], OOS_MaxDD=mo["MaxDD"]))
    r = pd.DataFrame(rows)
    r.to_csv("results/b3_momentum.csv", index=False)
    print(r.round(2).to_string(index=False))


def us_rotation():
    print("\n=== Rotação de ETFs EUA (setores + TLT + GLD), mensal, top K por retorno de L meses")
    tks = ["XLK", "XLF", "XLE", "XLV", "XLY", "XLP", "XLI", "XLU", "XLB", "TLT", "GLD"]
    C = pd.DataFrame({t: load_yahoo("us", t)["close"] for t in tks}).dropna()
    M = C.resample("ME").last()
    rm = M.pct_change()
    spy = load_yahoo("us", "SPY")["close"].resample("ME").last().reindex(M.index)
    rows = []
    for L, K, filt in itertools.product([3, 6, 12], [1, 2, 3], [False, True]):
        score = M / M.shift(L) - 1
        w = pd.DataFrame(0.0, index=M.index, columns=M.columns)
        for t in M.index:
            sc = score.loc[t].dropna()
            if len(sc) < K:
                continue
            top = sc.nlargest(K)
            if filt:
                top = top[top > 0]   # momentum absoluto: só o que está subindo
            for c in top.index:
                w.loc[t, c] = 1.0 / K
        held = w.shift(1).fillna(0)
        net = (held * rm.fillna(0)).sum(axis=1) - (w - held).abs().sum(axis=1).shift(1).fillna(0) * 0.0002
        mi, mo = metrics(net[net.index < SPLIT], 12), metrics(net[net.index >= SPLIT], 12)
        rows.append(dict(L=L, K=K, abs_mom=filt, IS_Sharpe=mi["Sharpe"], IS_CAGR=mi["CAGR"], IS_MaxDD=mi["MaxDD"],
                         OOS_Sharpe=mo["Sharpe"], OOS_CAGR=mo["CAGR"], OOS_MaxDD=mo["MaxDD"]))
    sp = spy.pct_change().fillna(0)
    mi, mo = metrics(sp[sp.index < SPLIT], 12), metrics(sp[sp.index >= SPLIT], 12)
    rows.append(dict(L="SPY B&H", IS_Sharpe=mi["Sharpe"], IS_CAGR=mi["CAGR"], IS_MaxDD=mi["MaxDD"],
                     OOS_Sharpe=mo["Sharpe"], OOS_CAGR=mo["CAGR"], OOS_MaxDD=mo["MaxDD"]))
    r = pd.DataFrame(rows)
    r.to_csv("results/us_rotation.csv", index=False)
    print(r.round(2).to_string(index=False))


if __name__ == "__main__":
    index_strategies()
    pairs()
    b3_momentum()
    us_rotation()
