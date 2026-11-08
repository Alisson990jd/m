# Mega-Sena — análise completa do histórico (concursos 1 a 3083)

Base: **3083 concursos**, de 11/03/1996 (concurso 1) até 08/11/2026 (concurso 3083: **22 - 25 - 29 - 37 - 46 - 54**). Jogos sugeridos para o **concurso 3084**.

## Os 4 jogos sugeridos

| Jogo | Dezenas | Soma | Pares/Ímpares | Baixas/Altas | Chance estimada de cada dezena (média) |
|---|---|---|---|---|---|
| 1 | **10 - 16 - 25 - 33 - 42 - 53** | 179 | 3/3 | 3/3 | 10,32% (base: 10%) |
| 2 | **06 - 11 - 27 - 34 - 37 - 44** | 159 | 3/3 | 3/3 | 10,32% (base: 10%) |
| 3 | **14 - 17 - 30 - 35 - 38 - 43** | 177 | 3/3 | 3/3 | 10,32% (base: 10%) |
| 4 | **04 - 05 - 09 - 32 - 46 - 56** | 152 | 4/2 | 3/3 | 10,22% (base: 10%) |

> **Leia antes de apostar.** Num sorteio honesto, **toda combinação de 6 dezenas tem exatamente a mesma chance**: 1 em 50.063.860 para a sena, 1 em 154.518 para a quina e 1 em 2.332 para a quadra. Com 4 jogos, a chance de sena é 1 em 12.515.965. Nenhuma análise do passado consegue mudar isso de forma relevante — e esta análise mostra isso com os próprios dados (seções 5, 6 e 9). Os jogos acima são **a melhor escolha que os dados permitem**, não uma previsão. Aposte só o que pode perder.

O que os jogos fazem de fato:

1. **Usam as 24 dezenas com maior chance estimada** por um modelo bayesiano (seção 9) — se existir algum viés físico minúsculo no sorteio, eles o aproveitam; se não existir, não perdem nada.
2. **Não repetem nenhuma dezena entre si** (24 dezenas diferentes), o que maximiza a cobertura do volante.
3. **Têm o perfil típico** dos sorteios (pares/ímpares, baixas/altas, soma, linhas, finais, consecutivas, primos).
4. **Fogem de "datas"**: cada jogo tem pelo menos 3 dezenas acima de 31. Isso não muda a chance de ganhar, mas reduz a chance de **dividir o prêmio** com quem joga aniversários — é a única "vantagem" matematicamente comprovada que um apostador pode ter.

## 1. Dados

- 3083 concursos, sem lacunas (1 a 3083).
- Concursos 1 a 3082 cruzados entre **5 fontes independentes** (repositórios públicos que espelham a API oficial da Caixa): `victor-reghini/mega-sena-statistics`, `sosthenis/megasena-data`, `GabrielRossiSoares/megasena`, `edxgar48/rust_spider_dados` e `guilhermeasn/loteria.json` (este último até o 2797). **Nenhuma divergência** de dezenas ou datas.
- Concurso 3083 (08/11/2026) confirmado por 2 fontes (`automatizadado/conferidor-mega-v2` e o card de resultado de `loteriacampeao/cards-loteria`: 1 ganhador, Goiânia/GO).
- Arquivo consolidado: [`dados/megasena_resultados.csv`](dados/megasena_resultados.csv). Todas as estatísticas: [`dados/estatisticas.json`](dados/estatisticas.json).

## 2. Frequência das dezenas

Cada dezena deveria ter saído, em média, **308,3 vezes**.

| # | Mais sorteadas | Vezes | | Menos sorteadas | Vezes |
|---|---|---|---|---|---|
| 1 | **10** | 361 | | **26** | 250 |
| 2 | **53** | 350 | | **21** | 261 |
| 3 | **05** | 337 | | **55** | 265 |
| 4 | **37** | 332 | | **15** | 276 |
| 5 | **27** | 331 | | **22** | 278 |
| 6 | **38** | 330 | | **03** | 283 |
| 7 | **33** | 329 | | **12** | 285 |
| 8 | **17** | 329 | | **31** | 286 |
| 9 | **30** | 328 | | **07** | 289 |
| 10 | **04** | 327 | | **48** | 289 |

Testes:

- **Qui-quadrado de uniformidade**: χ² = 82,6 (59 g.l.), p = 0,023. A dispersão é um pouco maior que a do puro acaso.
- **Monte Carlo** (400 históricos simulados com sorteio perfeito): a dezena mais sorteada costuma sair ~348 vezes (a real, 10, saiu 361; p ≈ 0,08 — normal). A menos sorteada costuma sair ~270 vezes; a real, **26, saiu só 250** (p ≈ 0,005 — **incomum**).
- **Persistência**: a correlação entre a frequência de cada dezena na 1ª metade da história e na 2ª é r = 0,07 (p = 0,59). Ou seja: **ser "quente" num período quase não diz nada sobre o período seguinte**.

Frequência recente (top 10 de cada janela):

| Janela | Mais sorteadas | Menos sorteadas |
|---|---|---|
| Últimos 50 | 16, 43, 02, 04, 05, 30, 38, 39, 40, 10 | 26, 32, 34, 45, 03, 19, 46, 08, 12, 15 |
| Últimos 100 | 58, 06, 17, 05, 14, 16, 23, 30, 43, 04 | 34, 46, 03, 12, 26, 56, 59, 15, 19, 20 |
| Últimos 150 | 06, 58, 09, 17, 27, 30, 10, 14, 42, 43 | 34, 12, 26, 19, 55, 03, 20, 25, 41, 50 |
| Últimos 300 | 27, 15, 17, 06, 40, 01, 05, 43, 04, 09 | 26, 12, 41, 34, 29, 07, 45, 20, 44, 59 |

## 3. Estabilidade ao longo do tempo

| Concursos | Período | χ² | p |
|---|---|---|---|
| 1-500 | 11/03/1996 a 27/09/2003 | 63,5 | 0,322 |
| 501-1000 | 01/10/2003 a 30/08/2008 | 44,0 | 0,928 |
| 1001-1500 | 03/09/2008 a 05/06/2013 | 66,9 | 0,224 |
| 1501-2000 | 08/06/2013 a 31/12/2017 | 51,5 | 0,745 |
| 2001-2500 | 03/01/2018 a 13/07/2022 | 81,4 | 0,028 |
| 2501-3000 | 16/07/2022 a 25/04/2026 | 51,3 | 0,752 |
| 3001-3083 | 28/04/2026 a 08/11/2026 | 57,2 | 0,543 |
| **1ª metade** (1-1541) | 11/03/1996 a 23/10/2013 | 58,6 | 0,491 |
| **2ª metade** (1542-3083) | 26/10/2013 a 08/11/2026 | 95,8 | 0,002 |

- A 1ª metade (1996–2013) é perfeitamente compatível com sorteio uniforme. A **2ª metade (2013–2026) tem dispersão acima do esperado** (p ≈ 0,002), puxada principalmente pelo bloco 2018–2022.
- Dezenas **abaixo do esperado nas duas metades** (z < −1 em ambas): 15, 21, 26, 55. Acima nas duas: 53.
- Maiores desvios no histórico completo (escore z): 26 (z = -3,50), 21 (-2,84), 55 (-2,60) para baixo; 10 (3,16) e 53 (2,50) para cima.
- Interpretação: há **indício estatístico fraco** de que algumas dezenas não saem exatamente 10% das vezes. Mas o efeito, se real, é minúsculo (décimos de ponto percentual) e não se mostrou útil para prever (seção 9).

## 4. Atrasos

- Intervalo médio entre aparições: 9,98 concursos (teórico: 10,00).
- Recorde de atraso da história: dezena **42**, 109 concursos seguidos sem sair.
- Os intervalos seguem a distribuição geométrica teórica de um sorteio sem memória: χ² = 45,3 (39 g.l.), p = 0,225.

Mais atrasadas agora (antes do concurso 3084):

| Dezena | Atraso atual | Maior atraso da história |
|---|---|---|
| 26 | 36 | 89 |
| 21 | 26 | 68 |
| 56 | 25 | 68 |
| 15 | 23 | 66 |
| 11 | 21 | 65 |
| 08 | 18 | 61 |
| 50 | 18 | 76 |
| 53 | 18 | 42 |
| 48 | 17 | 51 |
| 01 | 16 | 50 |

**A "lei dos atrasos" não existe.** Medimos, em todos os concursos desde o 101, a chance de uma dezena sair dado o seu atraso:

| Atraso da dezena | Casos | Saiu no concurso seguinte | Taxa | z vs 10% |
|---|---|---|---|---|
| 0 | 17.898 | 1.732 | 9,68% | -1,44 |
| 1-4 | 55.524 | 5.648 | 10,17% | 1,35 |
| 5-9 | 42.992 | 4.355 | 10,13% | 0,90 |
| 10-19 | 40.344 | 3.984 | 9,88% | -0,84 |
| 20-29 | 14.186 | 1.410 | 9,94% | -0,24 |
| 30-49 | 6.983 | 664 | 9,51% | -1,37 |
| 50+ | 1.053 | 105 | 9,97% | -0,03 |

Atrasada ou não, a chance fica em ~10%. O globo não tem memória. A 26, por exemplo, é a mais atrasada **e** a menos sorteada de todos os tempos — se algo, os dados sugerem evitá-la, não apostar nela.

## 5. Dezenas "quentes" e "frias"

Classificando, a cada concurso, as dezenas pela frequência nos 50 concursos anteriores:

| Grupo | Casos | Taxa de saída no concurso seguinte | z vs 10% |
|---|---|---|---|
| 10 mais quentes | 30.330 | 10,21% | 1,21 |
| 40 do meio | 121.320 | 10,04% | 0,46 |
| 10 mais frias | 30.330 | 9,63% | -2,12 |

As frias saíram um pouco menos (9,6%), as quentes um pouco mais (10,2%) — diferença de ~0,5 ponto percentual, no limite da significância e pequena demais para fazer diferença prática.

## 6. Backtest de estratégias populares

Cada estratégia foi aplicada em todos os concursos de 301 a 3083 usando só a informação disponível antes de cada sorteio. O esperado para qualquer jogo é **0,600 acertos por concurso**.

| Estratégia | Concursos | Média de acertos | Ternos | Quadras | Quinas |
|---|---|---|---|---|---|
| Mais sorteadas (histórico até ali) | 2783 | 0,601 | 27 | 0 | 0 |
| Menos sorteadas (histórico até ali) | 2783 | 0,568 | 19 | 0 | 0 |
| Mais sorteadas nos últimos 100 | 2783 | 0,626 | 33 | 5 | 0 |
| Mais atrasadas | 2783 | 0,575 | 26 | 1 | 0 |
| Repetir o concurso anterior | 2783 | 0,584 | 22 | 1 | 1 |
| Aleatório (surpresinha) | 2783 | 0,613 | 33 | 3 | 0 |

Esperado por puro acaso em 2.783 concursos: ~26 ternos e ~1,2 quadra. A melhor foi "mais sorteadas nos últimos 100" (0,626 acertos e 5 quadras; z = 1,95 na média). Parece promissor, mas com 6 estratégias e vários indicadores comparados ao mesmo tempo, é esperado que alguma "vença" por sorte; corrigindo para as comparações múltiplas, a diferença não é significativa. **Nenhuma estratégia se destaca de forma confiável**: da pior ("menos sorteadas") à "surpresinha", todas ficam dentro da faixa de ruído em torno de 0,600.

## 7. Estrutura dos sorteios (observado x teórico)

- **Soma das 6 dezenas**: média 183,1 (teórica 183,0), desvio-padrão 40,0 (teórico 40,6). 50% dos sorteios ficaram entre 155 e 211; 80% entre 132 e 234. Menor soma: 63 (02 - 03 - 08 - 11 - 17 - 22); maior: 331 (50 - 51 - 56 - 57 - 58 - 59).

**Quantidade de pares** — χ² = 8,69, p = 0,192

| Valor | 0 | 1 | 2 | 3 | 4 | 5 | 6 |
|---|---|---|---|---|---|---|---|
| Observado | 1,3% | 8,8% | 24,1% | 30,8% | 24,3% | 9,5% | 1,2% |
| Teórico | 1,2% | 8,5% | 23,8% | 32,9% | 23,8% | 8,5% | 1,2% |

**Quantidade de baixos (1-30)** — χ² = 7,56, p = 0,272

| Valor | 0 | 1 | 2 | 3 | 4 | 5 | 6 |
|---|---|---|---|---|---|---|---|
| Observado | 0,9% | 8,3% | 25,0% | 33,9% | 22,7% | 8,0% | 1,1% |
| Teórico | 1,2% | 8,5% | 23,8% | 32,9% | 23,8% | 8,5% | 1,2% |

**Quantidade de primos** — χ² = 3,00, p = 0,701

| Valor | 0 | 1 | 2 | 3 | 4 | 5 | 6 |
|---|---|---|---|---|---|---|---|
| Observado | 11,6% | 32,8% | 33,5% | 16,8% | 4,6% | 0,7% | 0,0% |
| Teórico | 12,2% | 32,7% | 33,5% | 16,8% | 4,3% | 0,5% | 0,0% |

**Dezenas repetidas do concurso anterior** — χ² = 7,25, p = 0,064

| Valor | 0 | 1 | 2 | 3 | 4 | 5 | 6 |
|---|---|---|---|---|---|---|---|
| Observado | 52,0% | 39,0% | 8,2% | 0,8% | 0,0% | 0,0% | 0,0% |
| Teórico | 51,6% | 37,9% | 9,5% | 1,0% | 0,0% | 0,0% | 0,0% |

**Pares de dezenas consecutivas** — χ² = 4,83, p = 0,184

| Valor | 0 | 1 | 2 | 3 | 4 | 5 |
|---|---|---|---|---|---|---|
| Observado | 58,0% | 35,0% | 6,7% | 0,2% | 0,0% | 0,0% |
| Teórico | 57,9% | 34,8% | 6,7% | 0,5% | 0,0% | 0,0% |

**Linhas do volante ocupadas (01-10, 11-20, ...)** — χ² = 2,89, p = 0,576

| Valor | 1 | 2 | 3 | 4 | 5 | 6 |
|---|---|---|---|---|---|---|
| Observado | 0,0% | 1,0% | 18,1% | 51,5% | 27,5% | 1,9% |
| Teórico | 0,0% | 1,2% | 19,2% | 50,7% | 27,1% | 2,0% |

**Máximo de dezenas com o mesmo final** — χ² = 0,58, p = 0,900

| Valor | 1 | 2 | 3 | 4 | 5 |
|---|---|---|---|---|---|
| Observado | 19,0% | 70,5% | 10,0% | 0,4% | 0,0% |
| Teórico | 19,6% | 70,1% | 9,9% | 0,4% | 0,0% |

**Linhas do volante** (esperado: 3.083 dezenas por linha): 01-10: 3121, 11-20: 3045, 21-30: 3006, 31-40: 3157, 41-50: 3108, 51-60: 3061.

Todas as estruturas batem com o que a matemática prevê para um sorteio aleatório (todos os p > 0,05). Os perfis "típicos" (3 pares, 3 baixas, soma perto de 183, 4–5 linhas) são os mais comuns **porque existem mais combinações assim**, não porque o sorteio os prefira. Por isso os filtros dos jogos servem para manter um perfil comum, não para aumentar a chance.

## 8. Pares, trios e repetições

- Pares mais frequentes (esperado ~26,1 vezes cada): 05-27 (43x), 04-52 (42x), 38-53 (42x), 23-53 (42x), 36-53 (42x), 05-11 (41x).
- Num histórico simulado, o par campeão costuma sair ~45 vezes → os 43 do par 05-27 são normais.
- Todos os 1.770 pares possíveis já saíram juntos ao menos uma vez (pares nunca sorteados: 0).
- Trios mais frequentes saíram 8 vezes (média esperada por trio: ~1,8) — normal: entre 34.220 trios possíveis, o acaso sozinho produz vários com 8–9 aparições.
- **Nenhuma sena jamais se repetiu.** Quinas repetidas: 26 (esperado pelo acaso: ~30,8).

## 9. Como os jogos foram montados

1. **Estimativa da chance de cada dezena** (bayesiana empírica): frequência de cada dezena ponderada no tempo (meia-vida de 1000 concursos, ~7 anos — o recente pesa mais, caso o equipamento/bolas tenham mudado), "encolhida" em direção a 10% na proporção em que a dispersão observada excede o acaso (dispersão observada = 1,65× a do acaso → fator de encolhimento 0,39). Resultado: as estimativas vão de 9,20% (26) a 10,90% (10).
2. **Seleção**: as 24 dezenas de maior estimativa: 10, 53, 27, 38, 11, 46, 35, 37, 30, 17, 43, 32, 44, 05, 56, 06, 34, 14, 33, 42, 16, 04, 09, 25.
3. **Repartição em 4 jogos** de 6, sem repetir dezenas, exigindo de cada jogo: 2–4 pares; 2–4 baixas (01–30); soma 150–216; 1–3 primos; dezenas em ≥ 4 linhas do volante; no máximo 2 dezenas com o mesmo final; no máximo 1 par de consecutivas; no máximo 1 dezena do concurso 3083; pelo menos 3 dezenas acima de 31. Entre todas as repartições válidas, escolheu-se a mais equilibrada (jogos com força parecida).
   - Esses filtros são atendidos por 20,7% dos sorteios reais e por 19,3% das combinações aleatórias — confirmação de que descrevem o perfil comum, sem "truque".
4. **Validação honesta fora da amostra**: o mesmo método foi aplicado em cada concurso de 1001 a 3083, usando só os dados anteriores. As 24 dezenas escolhidas acertaram em média **2,422** dezenas por sorteio, contra **2,400** esperadas por acaso (z = 0,86, não significativo). As 6 melhores acertaram 0,629 contra 0,600. **Ou seja: o método não demonstrou poder de previsão.**
5. Mesmo no cenário otimista em que as estimativas estivessem certas, cada jogo teria ~1,21× a chance de um jogo qualquer — algo como 1 em 41,4 milhões em vez de 1 em 50,1 milhões.

## 10. Detalhe dos jogos

### Jogo 1: 10 - 16 - 25 - 33 - 42 - 53

Soma 179 · 3 pares / 3 ímpares · 3 baixas / 3 altas · 1 primo(s) · 6 linhas do volante · 0 par(es) consecutivo(s) · máximo já coincidido com um sorteio real: 4 dezenas

| Dezena | Vezes sorteada | Chance estimada | Atraso atual | z 1996–2013 | z 2013–2026 |
|---|---|---|---|---|---|
| 10 | 361 | 10,90% | 2 | 0,67 | 3,80 |
| 16 | 321 | 10,14% | 1 | 0,76 | 0,32 |
| 25 | 304 | 10,09% | 0 | -0,94 | 0,58 |
| 33 | 329 | 10,15% | 16 | 1,52 | 0,24 |
| 42 | 327 | 10,15% | 2 | 0,93 | 0,66 |
| 53 | 350 | 10,51% | 18 | 1,35 | 2,19 |

### Jogo 2: 06 - 11 - 27 - 34 - 37 - 44

Soma 159 · 3 pares / 3 ímpares · 3 baixas / 3 altas · 2 primo(s) · 5 linhas do volante · 0 par(es) consecutivo(s) · máximo já coincidido com um sorteio real: 4 dezenas

| Dezena | Vezes sorteada | Chance estimada | Atraso atual | z 1996–2013 | z 2013–2026 |
|---|---|---|---|---|---|
| 06 | 315 | 10,20% | 7 | -0,35 | 0,92 |
| 11 | 325 | 10,47% | 21 | -0,86 | 2,27 |
| 27 | 331 | 10,48% | 8 | 0,16 | 1,77 |
| 34 | 324 | 10,18% | 5 | 0,25 | 1,09 |
| 37 | 332 | 10,38% | 0 | 0,08 | 1,94 |
| 44 | 323 | 10,24% | 1 | 0,42 | 0,83 |

### Jogo 3: 14 - 17 - 30 - 35 - 38 - 43

Soma 177 · 3 pares / 3 ímpares · 3 baixas / 3 altas · 2 primo(s) · 4 linhas do volante · 0 par(es) consecutivo(s) · máximo já coincidido com um sorteio real: 5 dezenas

| Dezena | Vezes sorteada | Chance estimada | Atraso atual | z 1996–2013 | z 2013–2026 |
|---|---|---|---|---|---|
| 14 | 304 | 10,16% | 6 | -0,86 | 0,49 |
| 17 | 329 | 10,30% | 2 | 1,18 | 0,58 |
| 30 | 328 | 10,33% | 7 | 0,16 | 1,51 |
| 35 | 325 | 10,39% | 6 | -0,69 | 2,11 |
| 38 | 330 | 10,48% | 1 | -0,69 | 2,53 |
| 43 | 327 | 10,29% | 2 | 0,84 | 0,75 |

### Jogo 4: 04 - 05 - 09 - 32 - 46 - 56

Soma 152 · 4 pares / 2 ímpares · 3 baixas / 3 altas · 1 primo(s) · 4 linhas do volante · 1 par(es) consecutivo(s) · máximo já coincidido com um sorteio real: 4 dezenas

| Dezena | Vezes sorteada | Chance estimada | Atraso atual | z 1996–2013 | z 2013–2026 |
|---|---|---|---|---|---|
| 04 | 327 | 10,14% | 1 | 1,86 | -0,27 |
| 05 | 337 | 10,22% | 4 | 2,37 | 0,07 |
| 09 | 296 | 10,09% | 4 | -1,71 | 0,66 |
| 32 | 326 | 10,27% | 7 | 0,50 | 1,00 |
| 46 | 320 | 10,39% | 0 | -1,11 | 2,11 |
| 56 | 320 | 10,21% | 25 | -0,09 | 1,09 |

## 11. Conclusão

- O histórico da Mega-Sena é, no essencial, **indistinguível de um sorteio perfeitamente aleatório**: atrasos, quentes/frias, pares/ímpares, somas, linhas e repetições batem com a teoria.
- Há um **indício fraco** de desvio em algumas dezenas (26, 21 e 55 abaixo; 10 e 53 acima), concentrado em 2013–2026. Os jogos foram montados para aproveitar esse desvio caso ele seja real, mas a validação mostra que ele não ajudou a prever sorteios no passado.
- **Não existe jogo com "mais chance de sair"** de forma relevante. O que dá para melhorar de verdade é o **valor do prêmio se você ganhar** (evitando combinações populares, como datas e sequências) — e isso os 4 jogos fazem.

## Como reproduzir

```bash
python3 scripts/analise.py dados/megasena_resultados.csv dados/estatisticas.json   # ~1 min
python3 scripts/gerar_relatorio.py dados/estatisticas.json RELATORIO.md
```

Os scripts usam só a biblioteca padrão do Python 3. Para atualizar a base, acrescente os novos concursos ao CSV (`scripts/consolidar.py` mostra como a base foi montada e cruzada).
