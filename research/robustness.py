"""Fase 2: robustez das estratégias candidatas.

Candidatas (escolhidas por consistência treino->teste, parâmetros fixados pelo TREINO/literatura):
  A. Tendência BTC (conjunto de 8 regras: preço > SMA 50/100/150/200 e momentum 30/60/90/180 d)
  B. Rompimento de volatilidade intradiário BTC+ETH (k=0,5; filtro SMA50; perpétuo)
  C. Arbitragem de funding BTC+ETH (spot comprado + perpétuo vendido, sempre ligado)
  D. IBS em SPY+QQQ (compra fechamento fraco IBS<0,2, vende IBS>0,8)

Testes: retorno ano a ano, custos 2x, atraso de execução, parâmetros vizinhos,
Deflated Sharpe (corrige pelo nº de configurações testadas) e carteira combinada.
"""
import itertools

import numpy as np
import pandas as pd
from scipy import stats

import strategies as S
from bt import (backtest, expected_max_sharpe, load_crypto, load_yahoo, metrics, sma)
from study_crypto_carry import hedge_series, run_pos

pd.set_option("display.width", 260, "display.max_rows", 400)
SPLIT_C, SPLIT_E = "2023-01-01", "2019-01-01"
N_TRIALS = 10657


# ----------------------------------------------------------------------------- estratégias
def trend_ensemble_pos(df):
    sigs = [S.above_sma(df, n) for n in (50, 100, 150, 200)] + [S.tsmom(df, L) for L in (30, 60, 90, 180)]
    return pd.concat(sigs, axis=1).mean(axis=1)


def strat_trend(sym="BTC", cost=0.0010, delay=0):
    df = load_crypto(sym, "1D")
    df = df[df.index >= "2018-01-01"]
    pos = trend_ensemble_pos(df).shift(delay).fillna(0)
    r = backtest(df, pos, cost).returns
    r.index = r.index.tz_convert(None)
    return r


def breakout_returns(d, k=0.5, f=50, cost=0.0006):
    rng = (d.high - d.low).shift(1)
    lvl = d.open + k * rng
    hit = d.high >= lvl
    if f:
        hit &= d.open > sma(d.close, f).shift(1)
    r = pd.Series(np.where(hit, d.close / lvl - 1 - 2 * cost, 0.0), index=d.index).fillna(0.0)
    r.index = r.index.tz_convert(None)
    return r


def strat_breakout(k=0.5, f=50, cost=0.0006, syms=("BTC", "ETH")):
    rs = [breakout_returns(load_crypto(s, "1D").loc["2018-01-01":], k, f, cost) for s in syms]
    return pd.concat(rs, axis=1).fillna(0).mean(axis=1)


def strat_carry(syms=("BTC", "ETH"), cost=0.0016):
    rs = []
    for s in syms:
        d = hedge_series(s)
        r, _ = run_pos(d["h"], pd.Series(1.0, index=d.index), cost)
        r = (1 + r).resample("1D").prod() - 1
        r.index = r.index.tz_convert(None)
        rs.append(r)
    return pd.concat(rs, axis=1).fillna(0).mean(axis=1)


def strat_ibs(tickers=("SPY", "QQQ"), lo=0.2, hi=0.8, cost=0.0002, exec="close"):
    rs = []
    for t in tickers:
        df = load_yahoo("us", t)
        df = df[df.index >= "1999-03-10"]
        rs.append(backtest(df, S.ibs_revert(df, lo, hi), cost, exec=exec).returns)
    return pd.concat(rs, axis=1).fillna(0).mean(axis=1)


# ----------------------------------------------------------------------------- análise
def deflated_sharpe(r, n_trials, sr_sd_annual=0.5, ppy=365.25):
    """P(Sharpe verdadeiro > Sharpe máximo esperado por sorte entre n_trials)."""
    r = r.dropna()
    sr0_annual = expected_max_sharpe(n_trials, sr_sd_annual ** 2)
    sr0 = sr0_annual / np.sqrt(ppy)
    sr = r.mean() / r.std()
    n = len(r)
    sk, ku = stats.skew(r), stats.kurtosis(r, fisher=False)
    z = (sr - sr0) * np.sqrt(n - 1) / np.sqrt(1 - sk * sr + (ku - 1) / 4 * sr ** 2)
    return float(stats.norm.cdf(z)), sr0_annual


def yearly(r):
    return (1 + r).groupby(r.index.year).prod() - 1


def line(name, r, split, ppy):
    a, i, o = metrics(r, ppy), metrics(r[r.index < split], ppy), metrics(r[r.index >= split], ppy)
    return dict(estrategia=name, ALL_CAGR=a["CAGR"], ALL_Sharpe=a["Sharpe"], ALL_MaxDD=a["MaxDD"],
                IS_CAGR=i["CAGR"], IS_Sharpe=i["Sharpe"], OOS_CAGR=o["CAGR"], OOS_Sharpe=o["Sharpe"],
                OOS_MaxDD=o["MaxDD"], OOS_Vol=o["Vol"])


if __name__ == "__main__":
    out = {}
    rows = []
    # ---------------- A. tendência BTC
    bh = load_crypto("BTC", "1D").loc["2018-01-01":, "close"].pct_change().fillna(0)
    bh.index = bh.index.tz_convert(None)
    out["A_tendencia_BTC"] = strat_trend("BTC")
    rows += [line("BTC buy&hold (referência)", bh, SPLIT_C, 365.25),
             line("A tendência BTC", out["A_tendencia_BTC"], SPLIT_C, 365.25),
             line("A  custo 2x", strat_trend("BTC", 0.0020), SPLIT_C, 365.25),
             line("A  executa 1 dia atrasado", strat_trend("BTC", delay=1), SPLIT_C, 365.25),
             line("A  mesmo conjunto no ETH", strat_trend("ETH"), SPLIT_C, 365.25)]
    # ---------------- B. rompimento
    out["B_rompimento_BTC_ETH"] = strat_breakout()
    rows += [line("B rompimento BTC+ETH k=.5 f=50", out["B_rompimento_BTC_ETH"], SPLIT_C, 365.25),
             line("B  custo 2x", strat_breakout(cost=0.0012), SPLIT_C, 365.25)]
    for k, f in itertools.product([0.4, 0.5, 0.6, 0.7], [20, 50, 100]):
        rows.append(line(f"B  vizinho k={k} f={f}", strat_breakout(k, f), SPLIT_C, 365.25))
    rows.append(line("B  em SOL+BNB+XRP (fora da amostra de ativos)",
                     strat_breakout(syms=("SOL", "BNB", "XRP")), SPLIT_C, 365.25))
    # ---------------- C. carry
    out["C_carry_BTC_ETH"] = strat_carry()
    rows += [line("C carry BTC+ETH sempre ligado", out["C_carry_BTC_ETH"], SPLIT_C, 365.25),
             line("C  custo 2x", strat_carry(cost=0.0032), SPLIT_C, 365.25),
             line("C  cesta 8 moedas", strat_carry(("BTC", "ETH", "XRP", "DOGE", "ADA", "LTC", "LINK", "ETC")),
                  SPLIT_C, 365.25)]
    # ---------------- D. IBS
    spyqqq = pd.concat([load_yahoo("us", t)["close"].pct_change() for t in ("SPY", "QQQ")], axis=1).mean(axis=1)
    spyqqq = spyqqq[spyqqq.index >= "1999-03-10"].fillna(0)
    out["D_IBS_SPY_QQQ"] = strat_ibs()
    rows += [line("SPY+QQQ buy&hold (referência)", spyqqq, SPLIT_E, 252),
             line("D IBS SPY+QQQ (leilão de fechamento)", out["D_IBS_SPY_QQQ"], SPLIT_E, 252),
             line("D  executando na abertura seguinte", strat_ibs(exec="open"), SPLIT_E, 252),
             line("D  custo 2x", strat_ibs(cost=0.0004), SPLIT_E, 252),
             line("D  em IWM+DIA+EFA (outros ativos)", strat_ibs(("IWM", "DIA", "EFA")), SPLIT_E, 252)]
    for lo, hi in itertools.product([0.1, 0.15, 0.25, 0.3], [0.7, 0.8, 0.9]):
        rows.append(line(f"D  vizinho lo={lo} hi={hi}", strat_ibs(lo=lo, hi=hi), SPLIT_E, 252))
    btc = load_crypto("BTC", "1D").loc["2018-01-01":]
    r = backtest(btc, S.ibs_revert(btc, 0.2, 0.8), 0.0006).returns
    r.index = r.index.tz_convert(None)
    rows.append(line("D  IBS aplicado ao BTC (24/7?)", r, SPLIT_C, 365.25))

    tab = pd.DataFrame(rows)
    tab.to_csv("results/robustness.csv", index=False)
    print(tab.round(2).to_string(index=False))

    # ---------------- Deflated Sharpe (amostra inteira de cada candidata)
    print(f"\nDeflated Sharpe (corrigido por {N_TRIALS} configurações testadas; e por 100 'efetivas'):")
    for k, r in out.items():
        ppy = 252 if k.startswith("D") else 365.25
        d1, sr0 = deflated_sharpe(r, N_TRIALS, ppy=ppy)
        d2, sr0b = deflated_sharpe(r, 100, ppy=ppy)
        print(f"  {k:24s} Sharpe {metrics(r, ppy)['Sharpe']:.2f} | DSR(N={N_TRIALS})={d1:.3f} "
              f"[limiar {sr0:.2f}] | DSR(N=100)={d2:.3f} [limiar {sr0b:.2f}]")

    # ---------------- ano a ano
    Y = pd.DataFrame({k: yearly(v) for k, v in out.items()})
    Y["BTC_buy&hold"] = yearly(bh)
    Y["SPY+QQQ_buy&hold"] = yearly(spyqqq)
    print("\nRetorno por ano:")
    print((Y.loc[2018:] * 100).round(1).to_string())
    Y.to_csv("results/robustness_yearly.csv")

    # ---------------- carteira combinada (dias corridos; IBS = 0 em dias sem pregão)
    P = pd.DataFrame(out).loc["2020-01-01":].fillna(0)
    print("\nCorrelação diária entre as estratégias (2020+):")
    print(P.corr().round(2).to_string())
    combos = {"capital igual (25% cada)": pd.Series(0.25, index=P.columns),
              "40% carry / 20% cada outra": pd.Series({"A_tendencia_BTC": .2, "B_rompimento_BTC_ETH": .2,
                                                       "C_carry_BTC_ETH": .4, "D_IBS_SPY_QQQ": .2}),
              "só cripto 24/7 (A+B+C = 1/3 cada)": pd.Series({"A_tendencia_BTC": 1 / 3, "B_rompimento_BTC_ETH": 1 / 3,
                                                              "C_carry_BTC_ETH": 1 / 3, "D_IBS_SPY_QQQ": 0.0})}
    crows = []
    for name, w in combos.items():
        port = (P * w).sum(axis=1)   # rebalanceamento diário para os pesos-alvo
        out_name = f"carteira: {name}"
        crows.append(line(out_name, port, SPLIT_C, 365.25))
        P[out_name] = port
    print(pd.DataFrame(crows).round(3).to_string(index=False))
    P.to_csv("results/robustness_daily_returns.csv")
