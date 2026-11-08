"""Gera megasena/RELATORIO.md a partir de dados/estatisticas.json.

Uso: python3 gerar_relatorio.py <estatisticas.json> <RELATORIO.md>
"""
import json
import math
import sys

R = json.load(open(sys.argv[1]))
OUT = sys.argv[2]
F, A, E = R["frequencia"], R["atrasos"], R["estimativa_bayesiana"]
N = R["total_concursos"]
ult = R["ultimo"]


def br(x, casas=2):
    return f"{x:,.{casas}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def dz(n):
    return f"{int(n):02d}"


def jogo_str(j):
    return " - ".join(dz(n) for n in j)


def pval(p):
    return "< 0,001" if p < 0.001 else br(p, 3)


L = []
w = L.append

w(f"# Mega-Sena — análise completa do histórico (concursos 1 a {N})\n")
w(f"Base: **{N} concursos**, de {R['primeiro'][1]} (concurso 1) até {ult[1]} (concurso {ult[0]}: "
  f"**{jogo_str(ult[2])}**). Jogos sugeridos para o **concurso {N + 1}**.\n")

w("## Os 4 jogos sugeridos\n")
w("| Jogo | Dezenas | Soma | Pares/Ímpares | Baixas/Altas | Chance estimada de cada dezena (média) |")
w("|---|---|---|---|---|---|")
for i, j in enumerate(R["jogos"], 1):
    p = j["perfil"]
    w(f"| {i} | **{jogo_str(j['dezenas'])}** | {p['soma']} | {p['pares']}/{6 - p['pares']} | {p['baixos']}/{6 - p['baixos']} | {br(j['p_est_media_pct'], 2)}% (base: 10%) |")
w("")
w("> **Leia antes de apostar.** Num sorteio honesto, **toda combinação de 6 dezenas tem exatamente a mesma chance**: "
  f"1 em {br(R['probabilidades']['sena_1_em'], 0)} para a sena, 1 em {br(R['probabilidades']['quina_1_em'], 0)} para a quina e "
  f"1 em {br(R['probabilidades']['quadra_1_em'], 0)} para a quadra. Com 4 jogos, a chance de sena é 1 em "
  f"{br(R['probabilidades']['quatro_jogos_sena_1_em'], 0)}. Nenhuma análise do passado consegue mudar isso de forma relevante — "
  "e esta análise mostra isso com os próprios dados (seções 5, 6 e 9). Os jogos acima são **a melhor escolha que os dados "
  "permitem**, não uma previsão. Aposte só o que pode perder.\n")

w("O que os jogos fazem de fato:\n")
w("1. **Usam as 24 dezenas com maior chance estimada** por um modelo bayesiano (seção 9) — se existir algum viés físico "
  "minúsculo no sorteio, eles o aproveitam; se não existir, não perdem nada.")
w("2. **Não repetem nenhuma dezena entre si** (24 dezenas diferentes), o que maximiza a cobertura do volante.")
w("3. **Têm o perfil típico** dos sorteios (pares/ímpares, baixas/altas, soma, linhas, finais, consecutivas, primos).")
w("4. **Fogem de \"datas\"**: cada jogo tem pelo menos 3 dezenas acima de 31. Isso não muda a chance de ganhar, mas reduz a "
  "chance de **dividir o prêmio** com quem joga aniversários — é a única \"vantagem\" matematicamente comprovada que um apostador pode ter.\n")

# ---------------------------------------------------------------- 1. dados
w("## 1. Dados\n")
w(f"- {N} concursos, sem lacunas (1 a {N}).")
w("- Concursos 1 a 3082 cruzados entre **5 fontes independentes** (repositórios públicos que espelham a API oficial da Caixa): "
  "`victor-reghini/mega-sena-statistics`, `sosthenis/megasena-data`, `GabrielRossiSoares/megasena`, `edxgar48/rust_spider_dados` "
  "e `guilhermeasn/loteria.json` (este último até o 2797). **Nenhuma divergência** de dezenas ou datas.")
w(f"- Concurso {ult[0]} ({ult[1]}) confirmado por 2 fontes (`automatizadado/conferidor-mega-v2` e o card de resultado de "
  "`loteriacampeao/cards-loteria`: 1 ganhador, Goiânia/GO).")
w("- Arquivo consolidado: [`dados/megasena_resultados.csv`](dados/megasena_resultados.csv). Todas as estatísticas: "
  "[`dados/estatisticas.json`](dados/estatisticas.json).\n")

# ---------------------------------------------------------- 2. frequência
w("## 2. Frequência das dezenas\n")
w(f"Cada dezena deveria ter saído, em média, **{br(F['esperada_por_dezena'], 1)} vezes**.\n")
w("| # | Mais sorteadas | Vezes | | Menos sorteadas | Vezes |")
w("|---|---|---|---|---|---|")
for i, ((a, fa), (b, fb)) in enumerate(zip(F["mais_sorteadas"], F["menos_sorteadas"]), 1):
    w(f"| {i} | **{dz(a)}** | {fa} | | **{dz(b)}** | {fb} |")
w("")
mc = F["monte_carlo"]
w("Testes:\n")
w(f"- **Qui-quadrado de uniformidade**: χ² = {br(F['qui2'], 1)} (59 g.l.), p = {pval(F['p'])}. A dispersão é um pouco maior que a do puro acaso.")
w(f"- **Monte Carlo** ({mc['simulacoes']} históricos simulados com sorteio perfeito): a dezena mais sorteada costuma sair "
  f"~{br(mc['max_sim_media'], 0)} vezes (a real, 10, saiu {mc['max_obs']}; p ≈ {br(mc['p_max_ao_menos_obs'], 2)} — normal). "
  f"A menos sorteada costuma sair ~{br(mc['min_sim_media'], 0)} vezes; a real, **26, saiu só {mc['min_obs']}** "
  f"(p ≈ {br(mc['p_min_no_maximo_obs'], 3)} — **incomum**).")
cm = F["correlacao_1a_vs_2a_metade"]
w(f"- **Persistência**: a correlação entre a frequência de cada dezena na 1ª metade da história e na 2ª é r = {br(cm['r'], 2)} "
  f"(p = {br(cm['p_aprox'], 2)}). Ou seja: **ser \"quente\" num período quase não diz nada sobre o período seguinte**.\n")
w("Frequência recente (top 10 de cada janela):\n")
w("| Janela | Mais sorteadas | Menos sorteadas |")
w("|---|---|---|")
for j in (50, 100, 150, 300):
    d = F[f"ultimos_{j}"]
    w(f"| Últimos {j} | {', '.join(dz(n) for n in d['top10'])} | {', '.join(dz(n) for n in d['bottom10'])} |")
w("")

# ---------------------------------------------------------------- 3. eras
w("## 3. Estabilidade ao longo do tempo\n")
w("| Concursos | Período | χ² | p |")
w("|---|---|---|---|")
for b in R["eras"]["blocos_500"]:
    w(f"| {b['concursos']} | {b['periodo']} | {br(b['qui2'], 1)} | {pval(b['p'])} |")
for k in ("1a_metade", "2a_metade"):
    b = R["eras"][k]
    w(f"| **{k.replace('a_metade', 'ª metade')}** ({b['concursos']}) | {b['periodo']} | {br(b['qui2'], 1)} | {pval(b['p'])} |")
w("")
w("- A 1ª metade (1996–2013) é perfeitamente compatível com sorteio uniforme. A **2ª metade (2013–2026) tem dispersão acima do "
  "esperado** (p ≈ 0,002), puxada principalmente pelo bloco 2018–2022.")
w(f"- Dezenas **abaixo do esperado nas duas metades** (z < −1 em ambas): {', '.join(dz(n) for n in R['eras']['consistentes_abaixo'])}. "
  f"Acima nas duas: {', '.join(dz(n) for n in R['eras']['consistentes_acima'])}.")
z = R["eras"]["z_total"]
w(f"- Maiores desvios no histórico completo (escore z): 26 (z = {br(z['26'], 2)}), 21 ({br(z['21'], 2)}), 55 ({br(z['55'], 2)}) "
  f"para baixo; 10 ({br(z['10'], 2)}) e 53 ({br(z['53'], 2)}) para cima.")
w("- Interpretação: há **indício estatístico fraco** de que algumas dezenas não saem exatamente 10% das vezes. Mas o efeito, "
  "se real, é minúsculo (décimos de ponto percentual) e não se mostrou útil para prever (seção 9).\n")

# --------------------------------------------------------------- 4. atrasos
w("## 4. Atrasos\n")
w(f"- Intervalo médio entre aparições: {br(A['intervalo_medio_observado'], 2)} concursos (teórico: 10,00).")
rec = A["recorde_geral"]
w(f"- Recorde de atraso da história: dezena **{dz(rec[1])}**, {rec[0]} concursos seguidos sem sair.")
w(f"- Os intervalos seguem a distribuição geométrica teórica de um sorteio sem memória: χ² = {br(A['teste_geometrico']['qui2'], 1)} "
  f"(39 g.l.), p = {pval(A['teste_geometrico']['p'])}.\n")
w("Mais atrasadas agora (antes do concurso {}):\n".format(N + 1))
w("| Dezena | Atraso atual | Maior atraso da história |")
w("|---|---|---|")
for n in A["top10_atrasadas"]:
    w(f"| {dz(n)} | {A['atual'][str(n)]} | {A['maior_atraso_historico'][str(n)]} |")
w("")
w("**A \"lei dos atrasos\" não existe.** Medimos, em todos os concursos desde o 101, a chance de uma dezena sair dado o seu atraso:\n")
w("| Atraso da dezena | Casos | Saiu no concurso seguinte | Taxa | z vs 10% |")
w("|---|---|---|---|---|")
for x in A["chance_por_faixa_de_atraso"]:
    w(f"| {x['faixa']} | {br(x['casos'], 0)} | {br(x['saiu'], 0)} | {br(x['taxa_pct'], 2)}% | {br(x['z'], 2)} |")
w("")
w("Atrasada ou não, a chance fica em ~10%. O globo não tem memória. A 26, por exemplo, é a mais atrasada **e** a menos sorteada "
  "de todos os tempos — se algo, os dados sugerem evitá-la, não apostar nela.\n")

# ----------------------------------------------------------- 5. quente/frio
w("## 5. Dezenas \"quentes\" e \"frias\"\n")
w("Classificando, a cada concurso, as dezenas pela frequência nos 50 concursos anteriores:\n")
w("| Grupo | Casos | Taxa de saída no concurso seguinte | z vs 10% |")
w("|---|---|---|---|")
nomes = {"quentes_top10": "10 mais quentes", "medias": "40 do meio", "frias_bottom10": "10 mais frias"}
for k, v in R["quente_frio_50"].items():
    w(f"| {nomes[k]} | {br(v['casos'], 0)} | {br(v['taxa_pct'], 2)}% | {br(v['z'], 2)} |")
w("")
w("As frias saíram um pouco menos (9,6%), as quentes um pouco mais (10,2%) — diferença de ~0,5 ponto percentual, no limite da "
  "significância e pequena demais para fazer diferença prática.\n")

# -------------------------------------------------------------- 6. backtest
w("## 6. Backtest de estratégias populares\n")
w("Cada estratégia foi aplicada em todos os concursos de 301 a {} usando só a informação disponível antes de cada sorteio. "
  "O esperado para qualquer jogo é **0,600 acertos por concurso**.\n".format(N))
w("| Estratégia | Concursos | Média de acertos | Ternos | Quadras | Quinas |")
w("|---|---|---|---|---|---|")
for k, v in R["backtest"].items():
    d = v["distribuicao"]
    w(f"| {k} | {v['concursos']} | {br(v['media_acertos'], 3)} | {d['3']} | {d['4']} | {d['5']} |")
w("")
bt100 = R["backtest"]["Mais sorteadas nos últimos 100"]
z100 = (bt100["media_acertos"] - 0.6) / (math.sqrt(6 * 0.1 * 0.9 * 54 / 59) / math.sqrt(bt100["concursos"]))
w("Esperado por puro acaso em 2.783 concursos: ~26 ternos e ~1,2 quadra. A melhor foi \"mais sorteadas nos últimos 100\" "
  f"({br(bt100['media_acertos'], 3)} acertos e 5 quadras; z = {br(z100, 2)} na média). Parece promissor, mas com 6 estratégias e "
  "vários indicadores comparados ao mesmo tempo, é esperado que alguma \"vença\" por sorte; corrigindo para as comparações "
  "múltiplas, a diferença não é significativa. **Nenhuma estratégia se destaca de forma confiável**: da pior "
  "(\"menos sorteadas\") à \"surpresinha\", todas ficam dentro da faixa de ruído em torno de 0,600.\n")

# ------------------------------------------------------------- 7. estrutura
w("## 7. Estrutura dos sorteios (observado x teórico)\n")
s = R["soma"]
w(f"- **Soma das 6 dezenas**: média {br(s['media_obs'], 1)} (teórica 183,0), desvio-padrão {br(s['dp_obs'], 1)} (teórico "
  f"{br(s['dp_teo'], 1)}). 50% dos sorteios ficaram entre {s['percentis']['25']} e {s['percentis']['75']}; 80% entre "
  f"{s['percentis']['10']} e {s['percentis']['90']}. Menor soma: {s['min'][0]} ({jogo_str(s['min'][1])}); maior: {s['max'][0]} "
  f"({jogo_str(s['max'][1])}).\n")
for e in R["estrutura"]:
    w(f"**{e['nome']}** — χ² = {br(e['qui2'], 2)}, p = {pval(e['p'])}\n")
    w("| Valor | " + " | ".join(str(t["k"]) for t in e["tabela"]) + " |")
    w("|---|" + "---|" * len(e["tabela"]))
    w("| Observado | " + " | ".join(f"{br(t['obs_pct'], 1)}%" for t in e["tabela"]) + " |")
    w("| Teórico | " + " | ".join(f"{br(t['esp_pct'], 1)}%" for t in e["tabela"]) + " |")
    w("")
v = R["volante"]
w("**Linhas do volante** (esperado: {} dezenas por linha): ".format(br(v["esperado_por_grupo"], 0))
  + ", ".join(f"{k}: {x}" for k, x in v["linhas"].items()) + ".\n")
w("Todas as estruturas batem com o que a matemática prevê para um sorteio aleatório (todos os p > 0,05). Os perfis \"típicos\" "
  "(3 pares, 3 baixas, soma perto de 183, 4–5 linhas) são os mais comuns **porque existem mais combinações assim**, não porque "
  "o sorteio os prefira. Por isso os filtros dos jogos servem para manter um perfil comum, não para aumentar a chance.\n")

# ---------------------------------------------------------- 8. combinações
c = R["combinacoes"]
w("## 8. Pares, trios e repetições\n")
w(f"- Pares mais frequentes (esperado ~{br(c['par_esperado'], 1)} vezes cada): "
  + ", ".join(f"{dz(p[0])}-{dz(p[1])} ({k}x)" for p, k in c["pares_top10"][:6]) + ".")
w(f"- Num histórico simulado, o par campeão costuma sair ~{br(c['max_par_sim']['media'], 0)} vezes → os {c['pares_top10'][0][1]} "
  "do par 05-27 são normais.")
w(f"- Todos os 1.770 pares possíveis já saíram juntos ao menos uma vez (pares nunca sorteados: {c['pares_nunca_sairam']}).")
w(f"- Trios mais frequentes saíram {c['trios_top10'][0][1]} vezes (média esperada por trio: ~{br(c['trio_esperado'], 1)}) — normal: entre "
  "34.220 trios possíveis, o acaso sozinho produz vários com 8–9 aparições.")
w(f"- **Nenhuma sena jamais se repetiu.** Quinas repetidas: {len(c['quinas_repetidas'])} (esperado pelo acaso: "
  f"~{br(c['quinas_repetidas_esperado'], 1)}).\n")

# ----------------------------------------------------------- 9. metodologia
vm = R["validacao_metodo"]
w("## 9. Como os jogos foram montados\n")
w(f"1. **Estimativa da chance de cada dezena** (bayesiana empírica): frequência de cada dezena ponderada no tempo (meia-vida de "
  f"{E['meia_vida']} concursos, ~7 anos — o recente pesa mais, caso o equipamento/bolas tenham mudado), \"encolhida\" em direção "
  f"a 10% na proporção em que a dispersão observada excede o acaso (dispersão observada = {br(E['var_obs_sobre_acaso'], 2)}× a do "
  f"acaso → fator de encolhimento {br(E['fator_encolhimento'], 2)}). Resultado: as estimativas vão de "
  f"{br(min(E['p_est_pct'].values()), 2)}% (26) a {br(max(E['p_est_pct'].values()), 2)}% (10).")
w("2. **Seleção**: as 24 dezenas de maior estimativa: " + ", ".join(dz(n) for n in E["ranking"][:24]) + ".")
w("3. **Repartição em 4 jogos** de 6, sem repetir dezenas, exigindo de cada jogo: 2–4 pares; 2–4 baixas (01–30); soma 150–216; "
  "1–3 primos; dezenas em ≥ 4 linhas do volante; no máximo 2 dezenas com o mesmo final; no máximo 1 par de consecutivas; no máximo "
  f"1 dezena do concurso {ult[0]}; pelo menos 3 dezenas acima de 31. Entre todas as repartições válidas, escolheu-se a mais "
  "equilibrada (jogos com força parecida).")
w(f"   - Esses filtros são atendidos por {br(R['filtros']['historico_pct'], 1)}% dos sorteios reais e por "
  f"{br(R['filtros']['aleatorio_pct'], 1)}% das combinações aleatórias — confirmação de que descrevem o perfil comum, sem \"truque\".")
w(f"4. **Validação honesta fora da amostra**: o mesmo método foi aplicado em cada concurso de 1001 a {N}, usando só os dados "
  f"anteriores. As 24 dezenas escolhidas acertaram em média **{br(vm['top24_media'], 3)}** dezenas por sorteio, contra "
  f"**{br(vm['top24_esperado'], 3)}** esperadas por acaso (z = {br(vm['top24_z'], 2)}, não significativo). As 6 melhores acertaram "
  f"{br(vm['top6_media'], 3)} contra {br(vm['top6_esperado'], 3)}. **Ou seja: o método não demonstrou poder de previsão.**")
cr = R["jogos"][0]["chance_relativa_vs_jogo_qualquer"]
w(f"5. Mesmo no cenário otimista em que as estimativas estivessem certas, cada jogo teria ~{br(cr, 2)}× a chance de um jogo "
  f"qualquer — algo como 1 em {br(R['probabilidades']['sena_1_em'] / cr / 1e6, 1)} milhões em vez de 1 em 50,1 milhões.\n")

# ------------------------------------------------------------- 10. jogos
w("## 10. Detalhe dos jogos\n")
for i, j in enumerate(R["jogos"], 1):
    p = j["perfil"]
    w(f"### Jogo {i}: {jogo_str(j['dezenas'])}\n")
    w(f"Soma {p['soma']} · {p['pares']} pares / {6 - p['pares']} ímpares · {p['baixos']} baixas / {6 - p['baixos']} altas · "
      f"{p['primos']} primo(s) · {p['linhas_distintas']} linhas do volante · {p['pares_consecutivos']} par(es) consecutivo(s) · "
      f"máximo já coincidido com um sorteio real: {j['max_coincidencia_historica']} dezenas\n")
    w("| Dezena | Vezes sorteada | Chance estimada | Atraso atual | z 1996–2013 | z 2013–2026 |")
    w("|---|---|---|---|---|---|")
    for n, d in j["detalhe"].items():
        w(f"| {dz(n)} | {d['freq_total']} | {br(d['p_est_pct'], 2)}% | {d['atraso']} | {br(d['z_1a_metade'], 2)} | {br(d['z_2a_metade'], 2)} |")
    w("")

# ------------------------------------------------------------- conclusão
w("## 11. Conclusão\n")
w("- O histórico da Mega-Sena é, no essencial, **indistinguível de um sorteio perfeitamente aleatório**: atrasos, quentes/frias, "
  "pares/ímpares, somas, linhas e repetições batem com a teoria.")
w("- Há um **indício fraco** de desvio em algumas dezenas (26, 21 e 55 abaixo; 10 e 53 acima), concentrado em 2013–2026. "
  "Os jogos foram montados para aproveitar esse desvio caso ele seja real, mas a validação mostra que ele não ajudou a prever "
  "sorteios no passado.")
w("- **Não existe jogo com \"mais chance de sair\"** de forma relevante. O que dá para melhorar de verdade é o **valor do prêmio "
  "se você ganhar** (evitando combinações populares, como datas e sequências) — e isso os 4 jogos fazem.\n")
w("## Como reproduzir\n")
w("```bash\npython3 scripts/analise.py dados/megasena_resultados.csv dados/estatisticas.json   # ~1 min\n"
  "python3 scripts/gerar_relatorio.py dados/estatisticas.json RELATORIO.md\n```\n")
w("Os scripts usam só a biblioteca padrão do Python 3. Para atualizar a base, acrescente os novos concursos ao CSV "
  "(`scripts/consolidar.py` mostra como a base foi montada e cruzada).")

open(OUT, "w").write("\n".join(L) + "\n")
print(f"{OUT}: {len(L)} linhas")
