"""Estudo 3 (cripto): arbitragem de funding (cash-and-carry, delta-neutro).

Posição: COMPRADO no spot + VENDIDO no perpétuo, mesmo nocional. O preço se cancela;
o resultado é  funding recebido (quando positivo, os comprados pagam os vendidos)
+ variação da base (spot vs perp) − custos.

Retorno por hora (nocional 1):  h_t = r_spot,t − r_perp,t + funding pago no fim da hora.
Custos por lado da operação completa (2 pernas): spot 0,10% + perp 0,06% = 0,16%.
Capital: 1 no spot + margem do perp (com 2x de alavancagem no perp, 0,5) => 1,5 por unidade
de nocional. As métricas abaixo são sobre o NOCIONAL; sobre o capital, divida o retorno por 1,5.
"""
import itertools

import numpy as np
import pandas as pd

from bt import load, metrics

SPLIT = "2023-01-01"
SYMS = ["BTC", "ETH", "BNB", "SOL", "XRP", "DOGE", "ADA", "LTC", "LINK", "AVAX", "DOT", "BCH",
        "TRX", "ETC", "XLM", "ATOM"]
COST = 0.0010 + 0.0006


def hedge_series(sym):
    spot = load(f"crypto_spot_{sym}_1h")["close"]
    perp = load(f"crypto_perp_{sym}_1h")["close"]
    fr = load(f"crypto_funding_{sym}")["funding"]
    idx = perp.index.intersection(spot.index)
    idx = idx[idx >= "2020-01-01"]
    spot, perp = spot.reindex(idx), perp.reindex(idx)
    # funding no instante T é pago a quem estava posicionado durante a barra que fecha em T
    f_bar = fr.copy()
    f_bar.index = f_bar.index.floor("h") - pd.Timedelta(hours=1)
    f_bar = f_bar.groupby(level=0).sum().reindex(idx).fillna(0.0)
    h = spot.pct_change() - perp.pct_change() + f_bar
    # sinal: média dos últimos 3 pagamentos (conhecidos no fechamento da barra)
    f_known = fr.copy()
    f_known.index = f_known.index.floor("h") - pd.Timedelta(hours=1)
    f_known = f_known.groupby(level=0).last()
    avg3 = f_known.rolling(3).mean().reindex(idx).ffill()
    avg21 = f_known.rolling(21).mean().reindex(idx).ffill()   # ~7 dias
    basis = perp / spot - 1
    return pd.DataFrame({"h": h.fillna(0.0), "f": f_bar, "avg3": avg3, "avg21": avg21,
                         "basis": basis}).dropna(subset=["avg3"])


def run_pos(h, pos, cost=COST):
    pos = pos.fillna(0.0)
    held = pos.shift(1).fillna(0.0)
    trade = (pos - held).abs()
    return held * h - trade.shift(1).fillna(0.0) * cost, held


def hysteresis(sig, th_in, th_out):
    s = sig.to_numpy()
    out = np.zeros(len(s))
    st = 0.0
    for i, v in enumerate(s):
        if np.isnan(v):
            out[i] = st
            continue
        if st == 0 and v > th_in:
            st = 1.0
        elif st == 1 and v < th_out:
            st = 0.0
        out[i] = st
    return pd.Series(out, index=sig.index)


def stats(r, held=None):
    ppy = 24 * 365.25
    out = {}
    for tag, m in (("ALL", slice(None)), ("IS", r.index < SPLIT), ("OOS", r.index >= SPLIT)):
        mm = metrics(r[m], ppy)
        for k in ("CAGR", "Sharpe", "MaxDD"):
            out[f"{tag}_{k}"] = mm.get(k)
        if held is not None:
            out[f"{tag}_Expo"] = float(held[m].mean())
    return out


if __name__ == "__main__":
    pd.set_option("display.width", 250, "display.max_rows", 400)
    H = {s: hedge_series(s) for s in SYMS}
    # 0) estatística do funding por ano (taxa anualizada média recebida pelo vendido)
    ann = pd.DataFrame({s: d["f"].groupby(d.index.year).sum() for s, d in H.items()}).round(3)
    print("Funding acumulado por ano (fração do nocional) — positivo = vendido recebe:")
    print(ann[["BTC", "ETH", "SOL", "BNB", "XRP", "DOGE", "LINK", "AVAX"]].to_string())
    rows = []
    for s, d in H.items():
        # 1) sempre ligado
        r, held = run_pos(d["h"], pd.Series(1.0, index=d.index))
        rows.append(dict(sym=s, rule="sempre", **stats(r, held)))
        # 2) liga/desliga por funding médio recente (com histerese)
        for (sig, win), th_in, th_out in itertools.product(
                [("avg3", "24h"), ("avg21", "7d")], [0.0, 0.0001, 0.0002, 0.0003], [0.0, 0.00005]):
            if th_out > th_in:
                continue
            pos = hysteresis(d[sig], th_in, th_out)
            r, held = run_pos(d["h"], pos)
            rows.append(dict(sym=s, rule=f"{win}>{th_in*1e4:.1f}bp sai<{th_out*1e4:.1f}bp", **stats(r, held)))
    res = pd.DataFrame(rows)
    res.to_csv("results/crypto_carry.csv", index=False)
    cols = ["sym", "rule", "IS_CAGR", "IS_Sharpe", "IS_MaxDD", "IS_Expo", "OOS_CAGR", "OOS_Sharpe",
            "OOS_MaxDD", "OOS_Expo"]
    print("\nSempre ligado, por moeda:")
    print(res[res.rule == "sempre"][cols].round(3).to_string(index=False))
    print("\nMediana entre moedas, por regra:")
    print(res.groupby("rule")[["IS_CAGR", "IS_Sharpe", "OOS_CAGR", "OOS_Sharpe", "OOS_MaxDD", "OOS_Expo"]]
          .median().sort_values("IS_Sharpe", ascending=False).round(3).to_string())
    print("\nBTC e ETH, todas as regras:")
    print(res[res.sym.isin(["BTC", "ETH"])][cols].round(3).to_string(index=False))
