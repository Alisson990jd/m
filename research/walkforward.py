"""Walk-forward e bootstrap.

1) Rompimento: a cada 1º de janeiro, escolhe (k, filtro) com melhor Sharpe nos 3 anos
   ANTERIORES e aplica no ano seguinte. Mostra se o PROCESSO de escolha funciona, não só
   o parâmetro escolhido olhando tudo.
2) Bootstrap em blocos (20 dias) do Sharpe no período de teste: intervalo de 90%.
"""
import itertools

import numpy as np
import pandas as pd

from bt import metrics
from robustness import strat_breakout

grid = list(itertools.product([0.3, 0.4, 0.5, 0.6, 0.7], [None, 20, 50, 100]))
R = {g: strat_breakout(*g) for g in grid}
years = range(2021, 2027)
wf, chosen = [], []
for y in years:
    tr = slice(f"{y-3}-01-01", f"{y-1}-12-31")
    best = max(grid, key=lambda g: metrics(R[g][tr], 365.25)["Sharpe"])
    chosen.append((y, best))
    wf.append(R[best][str(y)])
wf = pd.concat(wf)
m = metrics(wf, 365.25)
print("Walk-forward rompimento (parâmetro reescolhido todo ano só com o passado):")
print("  escolhas:", chosen)
print(f"  2021-2026: CAGR {m['CAGR']:.1%}  Sharpe {m['Sharpe']:.2f}  MaxDD {m['MaxDD']:.1%}")
fixed = metrics(R[(0.5, 50)]["2021":], 365.25)
print(f"  fixo k=.5 f=50 mesmo período: CAGR {fixed['CAGR']:.1%} Sharpe {fixed['Sharpe']:.2f}")
print("  por ano:", ((1 + wf).groupby(wf.index.year).prod() - 1).round(3).to_dict())


def block_boot_sharpe(r, ppy, n=2000, block=20, seed=0):
    rng = np.random.default_rng(seed)
    x = r.dropna().to_numpy()
    nb = int(np.ceil(len(x) / block))
    out = []
    for _ in range(n):
        idx = np.concatenate([np.arange(s, s + block) for s in rng.integers(0, len(x) - block, nb)])[:len(x)]
        s = x[idx]
        out.append(s.mean() / s.std() * np.sqrt(ppy))
    return np.percentile(out, [5, 50, 95]), float((np.array(out) > 0).mean())


P = pd.read_csv("results/robustness_daily_returns.csv", index_col=0, parse_dates=True)
print("\nBootstrap do Sharpe no período de TESTE (2023+), blocos de 20 dias — IC 90% e P(Sharpe>0):")
for c in P.columns:
    ppy = 365.25
    (lo, med, hi), p = block_boot_sharpe(P.loc["2023-01-01":, c], ppy)
    print(f"  {c:48s} [{lo:5.2f}, {med:5.2f}, {hi:5.2f}]  P>0 = {p:.3f}")
