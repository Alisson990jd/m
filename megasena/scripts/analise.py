"""Análise estatística aprofundada do histórico da Mega-Sena + geração de 4 jogos.

Só usa a biblioteca padrão do Python.
Uso: python3 analise.py <megasena_resultados.csv> <saida_estatisticas.json>
"""
import csv
import itertools
import json
import math
import random
import statistics
import sys
from collections import Counter

CSV, OUT = sys.argv[1], sys.argv[2]
N_DEZ = 60
TODAS = range(1, N_DEZ + 1)
PRIMOS = {2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37, 41, 43, 47, 53, 59}
C60_6 = math.comb(60, 6)

concursos, datas, sorteios = [], [], []
with open(CSV) as f:
    for r in csv.DictReader(f):
        concursos.append(int(r["concurso"]))
        datas.append(r["data"])
        sorteios.append(tuple(sorted(int(r[f"d{i}"]) for i in range(1, 7))))
N = len(sorteios)
assert concursos == list(range(1, N + 1))
R = {"total_concursos": N, "primeiro": [1, datas[0]], "ultimo": [N, datas[-1], sorteios[-1]]}


# ---------------------------------------------------------------- utilidades
def gamma_q(a, x):
    """Função gama incompleta regularizada superior Q(a, x) (Numerical Recipes)."""
    if x <= 0:
        return 1.0
    gln = math.lgamma(a)
    if x < a + 1:  # série
        s = term = 1.0 / a
        ap = a
        for _ in range(10000):
            ap += 1
            term *= x / ap
            s += term
            if abs(term) < abs(s) * 1e-15:
                break
        return 1.0 - s * math.exp(-x + a * math.log(x) - gln)
    b = x + 1 - a  # fração contínua
    c = 1 / 1e-300
    d = 1 / b
    h = d
    for i in range(1, 10000):
        an = -i * (i - a)
        b += 2
        d = an * d + b
        d = 1e-300 if abs(d) < 1e-300 else d
        c = b + an / c
        c = 1e-300 if abs(c) < 1e-300 else c
        d = 1 / d
        h *= d * c
        if abs(d * c - 1) < 1e-15:
            break
    return math.exp(-x + a * math.log(x) - gln) * h


def chi2_p(stat, df):
    return gamma_q(df / 2, stat / 2)


def normal_p_bilateral(z):
    return math.erfc(abs(z) / math.sqrt(2))


def hiper(k, bons, n=6, total=60):
    """P(k acertos entre 'bons' números de um universo de 'total', sorteando n)."""
    return math.comb(bons, k) * math.comb(total - bons, n - k) / math.comb(total, n)


def pearson(x, y):
    mx, my = statistics.fmean(x), statistics.fmean(y)
    sx = math.sqrt(sum((a - mx) ** 2 for a in x))
    sy = math.sqrt(sum((b - my) ** 2 for b in y))
    return sum((a - mx) * (b - my) for a, b in zip(x, y)) / (sx * sy)


def compara_distribuicao(nome, observado_por_k, teorico_por_k, total=None):
    """Tabela observado x esperado + qui-quadrado (agrupando classes raras)."""
    total = total or N
    linhas, obs_g, esp_g = [], [], []
    acc_o = acc_e = 0.0
    for k in sorted(teorico_por_k):
        o = observado_por_k.get(k, 0)
        e = teorico_por_k[k] * total
        linhas.append({"k": k, "observado": o, "obs_pct": 100 * o / total, "esperado": e, "esp_pct": 100 * teorico_por_k[k]})
        acc_o += o
        acc_e += e
        if acc_e >= 10:
            obs_g.append(acc_o)
            esp_g.append(acc_e)
            acc_o = acc_e = 0.0
    if acc_e > 0:
        obs_g[-1] += acc_o
        esp_g[-1] += acc_e
    stat = sum((o - e) ** 2 / e for o, e in zip(obs_g, esp_g))
    df = len(obs_g) - 1
    return {"nome": nome, "tabela": linhas, "qui2": stat, "gl": df, "p": chi2_p(stat, df)}


# ------------------------------------------------- 1. frequência das dezenas
freq = Counter(n for s in sorteios for n in s)
esp = N * 6 / N_DEZ
chi = sum((freq[n] - esp) ** 2 / esp for n in TODAS)
R["frequencia"] = {
    "esperada_por_dezena": esp,
    "contagem": {n: freq[n] for n in TODAS},
    "qui2": chi, "gl": 59, "p": chi2_p(chi, 59),
    "mais_sorteadas": freq.most_common(10),
    "menos_sorteadas": sorted(freq.items(), key=lambda kv: (kv[1], kv[0]))[:10],
}

# Monte Carlo: quão extremos são o máximo/mínimo observados num mundo 100% aleatório?
rng = random.Random(2026_11_08)
SIMS = 400
max_sim, min_sim = [], []
for _ in range(SIMS):
    c = Counter()
    for _ in range(N):
        c.update(rng.sample(range(1, 61), 6))
    v = [c[n] for n in TODAS]
    max_sim.append(max(v))
    min_sim.append(min(v))
obs_max, obs_min = max(freq.values()), min(freq.values())
R["frequencia"]["monte_carlo"] = {
    "simulacoes": SIMS,
    "max_obs": obs_max, "max_sim_media": statistics.fmean(max_sim),
    "max_sim_p05_p95": [sorted(max_sim)[int(.05 * SIMS)], sorted(max_sim)[int(.95 * SIMS)]],
    "p_max_ao_menos_obs": sum(m >= obs_max for m in max_sim) / SIMS,
    "min_obs": obs_min, "min_sim_media": statistics.fmean(min_sim),
    "min_sim_p05_p95": [sorted(min_sim)[int(.05 * SIMS)], sorted(min_sim)[int(.95 * SIMS)]],
    "p_min_no_maximo_obs": sum(m <= obs_min for m in min_sim) / SIMS,
}

# Persistência: quem saiu muito na 1ª metade continua saindo muito na 2ª?
meio = N // 2
f1 = Counter(n for s in sorteios[:meio] for n in s)
f2 = Counter(n for s in sorteios[meio:] for n in s)
r_meias = pearson([f1[n] for n in TODAS], [f2[n] for n in TODAS])
R["frequencia"]["correlacao_1a_vs_2a_metade"] = {"r": r_meias, "p_aprox": normal_p_bilateral(r_meias * math.sqrt(58) / math.sqrt(1 - r_meias**2))}

# Frequência em janelas recentes
for jan in (50, 100, 150, 300):
    fj = Counter(n for s in sorteios[-jan:] for n in s)
    R["frequencia"][f"ultimos_{jan}"] = {
        "esperada": jan * 6 / 60,
        "contagem": {n: fj[n] for n in TODAS},
        "top10": sorted(TODAS, key=lambda n: (-fj[n], n))[:10],
        "bottom10": sorted(TODAS, key=lambda n: (fj[n], n))[:10],
    }

# ------------------------------------------------------------ 2. atrasos
ultima_vez = {}
gaps = {n: [] for n in TODAS}
for i, s in enumerate(sorteios):
    for n in s:
        if n in ultima_vez:
            gaps[n].append(i - ultima_vez[n])
        ultima_vez[n] = i
atraso = {n: N - 1 - ultima_vez[n] for n in TODAS}
todos_gaps = [g for n in TODAS for g in gaps[n]]
R["atrasos"] = {
    "atual": atraso,
    "maior_atraso_historico": {n: max(gaps[n]) for n in TODAS},
    "intervalo_medio_teorico": 10.0,
    "intervalo_medio_observado": statistics.fmean(todos_gaps),
    "top10_atrasadas": sorted(TODAS, key=lambda n: (-atraso[n], n))[:10],
    "recorde_geral": max((max(gaps[n]), n) for n in TODAS),
}
# Distribuição dos intervalos x geométrica teórica (p = 0,1)
gap_cnt = Counter(min(g, 40) for g in todos_gaps)
G = len(todos_gaps)
obs_k = {k: gap_cnt[k] for k in range(1, 41)}
teo_k = {k: 0.9 ** (k - 1) * 0.1 for k in range(1, 40)}
teo_k[40] = 0.9 ** 39
stat = sum((obs_k[k] - G * teo_k[k]) ** 2 / (G * teo_k[k]) for k in teo_k)
R["atrasos"]["teste_geometrico"] = {"qui2": stat, "gl": 39, "p": chi2_p(stat, 39), "n_intervalos": G}

# "Lei dos atrasos": a chance de sair no próximo concurso cresce com o atraso?
faixas = [(0, 0), (1, 4), (5, 9), (10, 19), (20, 29), (30, 49), (50, 999)]
hits = {f: [0, 0] for f in faixas}
ult = {}
for i, s in enumerate(sorteios):
    if i >= 100:
        for n in TODAS:
            a = i - 1 - ult[n] if n in ult else None
            if a is None:
                continue
            for f in faixas:
                if f[0] <= a <= f[1]:
                    hits[f][1] += 1
                    hits[f][0] += n in s
                    break
    for n in s:
        ult[n] = i
R["atrasos"]["chance_por_faixa_de_atraso"] = [
    {"faixa": (str(a) if a == b else f"{a}-{b}") if b < 999 else f"{a}+", "casos": t, "saiu": h, "taxa_pct": 100 * h / t if t else None,
     "z": (h - 0.1 * t) / math.sqrt(t * 0.09) if t else None}
    for (a, b), (h, t) in hits.items()
]

# Quente/frio recente prevê o próximo? (frequência nos 50 concursos anteriores)
bucket = {"quentes_top10": [0, 0], "medias": [0, 0], "frias_bottom10": [0, 0]}
for i in range(50, N):
    fj = Counter(n for s in sorteios[i - 50:i] for n in s)
    ordem = sorted(TODAS, key=lambda n: (-fj[n], rng.random()))
    for pos, n in enumerate(ordem):
        b = "quentes_top10" if pos < 10 else ("frias_bottom10" if pos >= 50 else "medias")
        bucket[b][1] += 1
        bucket[b][0] += n in sorteios[i]
R["quente_frio_50"] = {k: {"casos": t, "saiu": h, "taxa_pct": 100 * h / t, "z": (h - 0.1 * t) / math.sqrt(t * 0.09)} for k, (h, t) in bucket.items()}

# ------------------------------------------------- 3. backtest de estratégias
def bt(estrategia, inicio=300):
    dist = Counter()
    for i in range(inicio, N):
        jogo = estrategia(i)
        dist[len(set(jogo) & set(sorteios[i]))] += 1
    total = sum(dist.values())
    return {"concursos": total, "media_acertos": sum(k * v for k, v in dist.items()) / total,
            "distribuicao": {k: dist[k] for k in range(7)}}


freq_acum = []  # frequência acumulada até i (exclusive)
c = Counter()
for s in sorteios:
    freq_acum.append(dict(c))
    c.update(s)
ult_acum = []
u = {}
for i, s in enumerate(sorteios):
    ult_acum.append(dict(u))
    for n in s:
        u[n] = i
rng_bt = random.Random(42)
estrategias = {
    "Mais sorteadas (histórico até ali)": lambda i: sorted(TODAS, key=lambda n: (-freq_acum[i].get(n, 0), n))[:6],
    "Menos sorteadas (histórico até ali)": lambda i: sorted(TODAS, key=lambda n: (freq_acum[i].get(n, 0), n))[:6],
    "Mais sorteadas nos últimos 100": lambda i: sorted(TODAS, key=lambda n: (-sum(n in s for s in sorteios[i - 100:i]), n))[:6],
    "Mais atrasadas": lambda i: sorted(TODAS, key=lambda n: (ult_acum[i].get(n, -1), n))[:6],
    "Repetir o concurso anterior": lambda i: sorteios[i - 1],
    "Aleatório (surpresinha)": lambda i: rng_bt.sample(range(1, 61), 6),
}
R["backtest"] = {nome: bt(f) for nome, f in estrategias.items()}
R["backtest_teorico"] = {"media_acertos": 0.6, "distribuicao_pct": {k: 100 * hiper(k, 6) for k in range(7)}}

# ------------------------------------------- 4. estrutura dos sorteios
def perfil(s):
    linhas = Counter((n - 1) // 10 for n in s)
    finais = Counter(n % 10 for n in s)
    consec = sum(1 for a, b in zip(s, s[1:]) if b - a == 1)
    return {
        "pares": sum(n % 2 == 0 for n in s),
        "baixos": sum(n <= 30 for n in s),
        "soma": sum(s),
        "primos": sum(n in PRIMOS for n in s),
        "linhas_distintas": len(linhas),
        "max_por_linha": max(linhas.values()),
        "max_mesmo_final": max(finais.values()),
        "pares_consecutivos": consec,
        "ate_31": sum(n <= 31 for n in s),
        "amplitude": s[-1] - s[0],
    }


perfis = [perfil(s) for s in sorteios]
somas = [p["soma"] for p in perfis]
somas_ord = sorted(somas)
R["soma"] = {
    "media_obs": statistics.fmean(somas), "dp_obs": statistics.pstdev(somas),
    "media_teo": 183.0, "dp_teo": math.sqrt(6 * (3600 - 1) / 12 * 54 / 59),
    "percentis": {p: somas_ord[int(p / 100 * (N - 1))] for p in (5, 10, 25, 50, 75, 90, 95)},
    "min": (min(somas), sorteios[somas.index(min(somas))]), "max": (max(somas), sorteios[somas.index(max(somas))]),
}

# Distribuições teóricas exatas via enumeração por Monte Carlo grande (estruturas complexas)
# e via hipergeométrica (estruturas simples).
R["estrutura"] = [
    compara_distribuicao("Quantidade de pares", Counter(p["pares"] for p in perfis), {k: hiper(k, 30) for k in range(7)}),
    compara_distribuicao("Quantidade de baixos (1-30)", Counter(p["baixos"] for p in perfis), {k: hiper(k, 30) for k in range(7)}),
    compara_distribuicao("Quantidade de primos", Counter(p["primos"] for p in perfis), {k: hiper(k, 17) for k in range(7)}),
]
rep_ant = Counter(len(set(sorteios[i]) & set(sorteios[i - 1])) for i in range(1, N))
R["estrutura"].append(compara_distribuicao("Dezenas repetidas do concurso anterior", rep_ant, {k: hiper(k, 6) for k in range(7)}, total=N - 1))

# Monte Carlo de 300 mil jogos aleatórios para estruturas sem fórmula simples
rng_mc = random.Random(7)
MC = 300_000
mc_perfis = [perfil(tuple(sorted(rng_mc.sample(range(1, 61), 6)))) for _ in range(MC)]
for chave, nome in [("pares_consecutivos", "Pares de dezenas consecutivas"),
                    ("linhas_distintas", "Linhas do volante ocupadas (01-10, 11-20, ...)"),
                    ("max_mesmo_final", "Máximo de dezenas com o mesmo final")]:
    teo = Counter(p[chave] for p in mc_perfis)
    R["estrutura"].append(compara_distribuicao(nome, Counter(p[chave] for p in perfis), {k: v / MC for k, v in teo.items()}))

# Linhas e colunas do volante (contagem total)
R["volante"] = {
    "linhas": {f"{10*l+1:02d}-{10*l+10:02d}": sum(freq[n] for n in range(10 * l + 1, 10 * l + 11)) for l in range(6)},
    "finais": {d: sum(freq[n] for n in TODAS if n % 10 == d) for d in range(10)},
    "esperado_por_grupo": N * 6 / 6,
}

# ------------------------------------------------- 5. pares, trios, repetições
pares = Counter(p for s in sorteios for p in itertools.combinations(s, 2))
esp_par = N * 15 / math.comb(60, 2)
trios = Counter(t for s in sorteios for t in itertools.combinations(s, 3))
esp_trio = N * 20 / math.comb(60, 3)
quinas = Counter(q for s in sorteios for q in itertools.combinations(s, 5))
R["combinacoes"] = {
    "pares_top10": [(list(k), v) for k, v in pares.most_common(10)],
    "par_esperado": esp_par,
    "pares_nunca_sairam": sum(1 for p in itertools.combinations(TODAS, 2) if pares[p] == 0),
    "trios_top10": [(list(k), v) for k, v in trios.most_common(10)],
    "trio_esperado": esp_trio,
    "senas_repetidas": [s for s, v in Counter(sorteios).items() if v > 1],
    "quinas_repetidas": [(list(k), v) for k, v in quinas.items() if v > 1],
    # nº esperado de pares de concursos que compartilham >= 5 dezenas
    "quinas_repetidas_esperado": math.comb(N, 2) * (hiper(5, 6) + hiper(6, 6)),
}
# Monte Carlo do par mais frequente em mundo aleatório
max_par_sim = []
rng_p = random.Random(99)
for _ in range(60):
    cp = Counter()
    for _ in range(N):
        cp.update(itertools.combinations(sorted(rng_p.sample(range(1, 61), 6)), 2))
    max_par_sim.append(max(cp.values()))
R["combinacoes"]["max_par_sim"] = {"media": statistics.fmean(max_par_sim), "min": min(max_par_sim), "max": max(max_par_sim),
                                   "p_ao_menos_obs": sum(m >= pares.most_common(1)[0][1] for m in max_par_sim) / len(max_par_sim)}

# ------------------------------------------- 6. estabilidade por era / viés persistente
blocos = []
for a in range(0, N, 500):
    b = min(N, a + 500)
    c = Counter(n for s in sorteios[a:b] for n in s)
    e = (b - a) * 6 / 60
    x = sum((c[n] - e) ** 2 / e for n in TODAS)
    blocos.append({"concursos": f"{a + 1}-{b}", "periodo": f"{datas[a]} a {datas[b - 1]}", "qui2": x, "p": chi2_p(x, 59),
                   "mais": c.most_common(3), "menos": sorted(c.items(), key=lambda kv: (kv[1], kv[0]))[:3]})
R["eras"] = {"blocos_500": blocos}
for nome, (a, b) in {"1a_metade": (0, meio), "2a_metade": (meio, N)}.items():
    c = Counter(n for s in sorteios[a:b] for n in s)
    e = (b - a) * 6 / 60
    x = sum((c[n] - e) ** 2 / e for n in TODAS)
    R["eras"][nome] = {"concursos": f"{a + 1}-{b}", "periodo": f"{datas[a]} a {datas[b - 1]}", "qui2": x, "p": chi2_p(x, 59),
                       "z": {n: (c[n] - e) / math.sqrt(e * 0.9) for n in TODAS}}
z_total = {n: (freq[n] - esp) / math.sqrt(esp * 0.9) for n in TODAS}
R["eras"]["z_total"] = z_total
R["eras"]["consistentes_acima"] = [n for n in TODAS if R["eras"]["1a_metade"]["z"][n] > 1 and R["eras"]["2a_metade"]["z"][n] > 1]
R["eras"]["consistentes_abaixo"] = [n for n in TODAS if R["eras"]["1a_metade"]["z"][n] < -1 and R["eras"]["2a_metade"]["z"][n] < -1]

# Estimativa bayesiana empírica da chance "verdadeira" de cada dezena:
# frequência ponderada (meia-vida de 1.000 concursos, ~7 anos) encolhida para 10%
# na proporção em que a dispersão observada excede a esperada pelo puro acaso.
MEIA_VIDA = 1000
w = [0.5 ** ((N - 1 - i) / MEIA_VIDA) for i in range(N)]
sw, sw2 = sum(w), sum(x * x for x in w)
taxa_pond = {n: sum(wi for wi, s in zip(w, sorteios) if n in s) / sw for n in TODAS}
var_acaso = 0.1 * 0.9 * sw2 / sw ** 2
var_obs = statistics.fmean((taxa_pond[n] - 0.1) ** 2 for n in TODAS) * 60 / 59
B = max(0.0, 1 - var_acaso / var_obs)
p_est = {n: 0.1 + B * (taxa_pond[n] - 0.1) for n in TODAS}
R["estimativa_bayesiana"] = {"meia_vida": MEIA_VIDA, "fator_encolhimento": B, "var_obs_sobre_acaso": var_obs / var_acaso,
                             "p_est_pct": {n: 100 * p_est[n] for n in TODAS},
                             "ranking": sorted(TODAS, key=lambda n: -p_est[n])}

# ----------------------------------------------------- 7. geração dos jogos
ULTIMO = sorteios[-1]


def passa_filtros(j, anterior=ULTIMO):
    p = perfil(j)
    return (2 <= p["pares"] <= 4
            and 2 <= p["baixos"] <= 4
            and 150 <= p["soma"] <= 216
            and 1 <= p["primos"] <= 3
            and p["linhas_distintas"] >= 4
            and p["max_mesmo_final"] <= 2
            and p["pares_consecutivos"] <= 1
            and len(set(j) & set(anterior)) <= 1
            and p["ate_31"] <= 3)  # anti-popularidade: ao menos 3 dezenas acima de 31 (fora de "datas")


hist_ok = sum(passa_filtros(sorteios[i], sorteios[i - 1]) for i in range(1, N))
rng_f = random.Random(11)
mc_ok = sum(passa_filtros(tuple(sorted(rng_f.sample(range(1, 61), 6)))) for _ in range(200_000))
R["filtros"] = {"historico_pct": 100 * hist_ok / (N - 1), "aleatorio_pct": 100 * mc_ok / 200_000}

# As 24 dezenas de maior chance estimada, repartidas em 4 jogos disjuntos que passem nos filtros.
# Se não houver repartição possível, troca-se a(s) dezena(s) de menor estimativa pela(s) seguinte(s).
ranking = R["estimativa_bayesiana"]["ranking"]
score = {n: 100 * (p_est[n] - 0.1) for n in TODAS}


def coberturas(conj, limite=100_000):
    conj = sorted(conj)
    validos = [c for c in itertools.combinations(conj, 6) if passa_filtros(c)]
    por_min = {}
    for c in validos:
        por_min.setdefault(c[0], []).append(c)
    achadas = []

    def dfs(rest, atual):
        if len(achadas) >= limite:
            return
        if not rest:
            achadas.append(list(atual))
            return
        m = min(rest)
        for c in por_min.get(m, []):
            if rest.issuperset(c):
                atual.append(c)
                dfs(rest - set(c), atual)
                atual.pop()

    dfs(set(conj), [])
    return achadas


melhor = None
for extra in range(0, 7):
    pool = ranking[:24 + extra]
    candidatos = sorted(itertools.combinations(pool, extra), key=lambda d: sum(score[n] for n in d))
    for descarta in candidatos:
        conj = [n for n in pool if n not in descarta]
        covs = coberturas(conj)
        if covs:
            # mais equilibrada: menor diferença entre o jogo mais forte e o mais fraco
            melhor = min(covs, key=lambda cv: (max(sum(score[n] for n in g) for g in cv) - min(sum(score[n] for n in g) for g in cv), cv))
            break
    if melhor:
        break
melhor.sort(key=lambda g: -sum(score[n] for n in g))
R["jogos"] = [{"dezenas": list(g), "perfil": perfil(g), "p_est_media_pct": statistics.fmean(100 * p_est[n] for n in g),
               "detalhe": {n: {"freq_total": freq[n], "p_est_pct": 100 * p_est[n], "atraso": atraso[n],
                               "z_1a_metade": R["eras"]["1a_metade"]["z"][n], "z_2a_metade": R["eras"]["2a_metade"]["z"][n]}
                           for n in g}} for g in melhor]
# Validação fora da amostra do próprio método: em cada concurso t >= 1000, estima com os dados
# anteriores a t, escolhe as 24 (e as 6) melhores e confere o que saiu em t.
decai = 0.5 ** (1 / MEIA_VIDA)
Wn = {n: 0.0 for n in TODAS}
sw_t = sw2_t = 0.0
acc24 = acc6 = casos = 0
for t, s in enumerate(sorteios):
    if t >= 1000:
        tp = {n: Wn[n] / sw_t for n in TODAS}
        vo = statistics.fmean((tp[n] - 0.1) ** 2 for n in TODAS) * 60 / 59
        bt_B = max(0.0, 1 - (0.09 * sw2_t / sw_t ** 2) / vo)
        rk = sorted(TODAS, key=lambda n: (-(0.1 + bt_B * (tp[n] - 0.1)), n))
        acc24 += len(set(rk[:24]) & set(s))
        acc6 += len(set(rk[:6]) & set(s))
        casos += 1
    for n in TODAS:
        Wn[n] *= decai
    for n in s:
        Wn[n] += 1
    sw_t = sw_t * decai + 1
    sw2_t = sw2_t * decai ** 2 + 1
dp24 = math.sqrt(6 * 0.4 * 0.6 * 54 / 59 / casos)
R["validacao_metodo"] = {"concursos": casos, "top24_media": acc24 / casos, "top24_esperado": 2.4,
                         "top24_z": (acc24 / casos - 2.4) / dp24,
                         "top6_media": acc6 / casos, "top6_esperado": 0.6}
for jg in R["jogos"]:
    jg["max_coincidencia_historica"] = max(len(set(jg["dezenas"]) & set(s)) for s in sorteios)
# Ganho teórico, se a estimativa estivesse certa: P(sena) relativa a um jogo qualquer
for jg in R["jogos"]:
    jg["chance_relativa_vs_jogo_qualquer"] = math.prod(p_est[n] / 0.1 for n in jg["dezenas"])
R["probabilidades"] = {
    "sena_1_em": C60_6 / 1, "quina_1_em": C60_6 / (6 * 54), "quadra_1_em": C60_6 / (15 * math.comb(54, 2)),
    "quatro_jogos_sena_1_em": C60_6 / 4,
}

with open(OUT, "w") as f:
    json.dump(R, f, ensure_ascii=False, indent=1, default=str)
print(json.dumps({k: R[k] for k in ("jogos", "filtros")}, ensure_ascii=False, default=str)[:3000])
