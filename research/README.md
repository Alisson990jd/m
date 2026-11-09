# Pesquisa de estratégias — cripto, B3/EUA e Forex

Resultado de ~10.700 configurações testadas em 3 mercados com dados reais, custos realistas e
separação treino/teste. **Backtest não é garantia de resultado futuro** — leia as ressalvas no fim.

## Metodologia

| Item | Como foi feito |
|---|---|
| Dados | Binance (spot 1h desde 2017, perpétuos e funding desde 2019, 42 séries incluindo moedas que **morreram**, ex. LUNA/FTT); Yahoo (B3, EUA e Forex diários desde 1993–2006 e 1h dos últimos 2 anos) |
| Sem olhar o futuro | Sinal no fechamento da barra *t*, retorno a partir de *t+1*. Motor validado: buy&hold bate exatamente com o preço, sinais aleatórios dão Sharpe ≈ 0 e um sinal "trapaceiro" proposital dá Sharpe 14 |
| Custos por lado | Cripto spot 0,10% (alts 0,15%), perpétuo 0,06%; ETFs EUA 0,02%; B3 0,05%; Forex 0,01–0,05% |
| Treino × teste | Cripto: treino até 2022, **teste 2023 → nov/2026**. Ações/Forex: treino até 2018, **teste 2019 →** |
| Limpeza | Séries emendadas cortadas (LUNA "subia" 171.115× em 31/05/2022 na emenda com a LUNA 2.0); picos falsos do Forex do Yahoo removidos |
| Robustez | Parâmetros vizinhos, custo 2×, execução atrasada, outros ativos, walk-forward, bootstrap e Deflated Sharpe |

## Estratégias aprovadas

Números do período de **teste** (não usado para escolher parâmetros).

| | Estratégia | Mercado | Retorno a.a. | Sharpe | Queda máx. | Referência (buy&hold) |
|---|---|---|---|---|---|---|
| **A** | Tendência BTC (8 regras: preço > SMA 50/100/150/200 e momentum 30/60/90/180 d) | Cripto 24/7 | 39% | 1,15 | −28% | 48% / 1,08 / **−53%** |
| **B** | Rompimento intradiário BTC+ETH (abertura + 0,5×amplitude de ontem, filtro SMA50, sai no fim do dia) | Cripto 24/7 | 24% | 1,17 | −19% | — |
| **C** | Arbitragem de funding BTC+ETH (spot comprado + perpétuo vendido) | Cripto 24/7 | 7% sobre o nocional (~5% sobre o capital) | >3 | −1% | — |
| **D** | IBS em SPY+QQQ (compra fechamento fraco, vende fechamento forte) | Bolsa EUA | 20% (14% executando só na abertura) | 1,40 (1,01) | −11% | 19% / 0,93 / −31% |
| | **Carteira 40% C + 20% A + 20% B + 20% D** | | **18%** | **1,75** | **−8%** | |
| | Carteira só cripto 24/7 (A+B+C, 1/3 cada) | | 24% | 1,47 | −14% | |

Correlação diária entre elas: 0,00–0,12 (exceto A×B = 0,50) — por isso a carteira é melhor que cada uma.

### Retorno por ano (%)

| Ano | A tendência | B rompimento | C funding | D IBS | BTC buy&hold | SPY+QQQ |
|---|---|---|---|---|---|---|
| 2018 | −24,1 | 8,4 | — | −10,3 | −72,3 | −2,3 |
| 2019 | 90,5 | 26,9 | — | 10,6 | 94,3 | 35,1 |
| 2020 | 189,0 | 135,8 | 23,4 | 82,1 | 302,0 | 32,8 |
| 2021 | 60,1 | 56,1 | 40,1 | 18,6 | 59,8 | 28,2 |
| 2022 | −27,6 | −26,6 | 2,5 | 18,7 | −64,2 | −25,6 |
| 2023 | 96,7 | 32,3 | 8,1 | 17,3 | 155,6 | 39,9 |
| 2024 | 77,6 | 35,5 | 13,3 | 3,1 | 121,3 | 25,3 |
| 2025 | 1,1 | 16,5 | 5,2 | 15,5 | −6,3 | 19,3 |
| 2026* | 0,9 | 8,6 | 2,1 | 7,5 | −14,4 | 10,5 |

\* até 09/11/2026.

### O que sustenta cada uma
- **A**: segue o BTC na alta e sai na baixa. Não ganha do buy&hold em alta forte, mas corta a queda máxima pela metade (2018: −24% vs −72%; 2022: −28% vs −64%). Resistiu a custo 2× (Sharpe 1,11) e a executar 1 dia atrasado (1,10); também funciona no ETH (0,78 vs 0,55 do buy&hold).
- **B**: os 12 parâmetros vizinhos testados deram Sharpe de teste entre 0,77 e 1,30; funcionou em SOL/BNB/XRP (não usados na escolha). **Sensível a custo**: com custo 2× o Sharpe cai para 0,65 → só vale em futuros com taxa baixa. Reotimizar os parâmetros todo ano *piorou* (Sharpe 0,59): use parâmetros fixos.
- **C**: lucrou em todos os anos. O risco não é volatilidade, é **contraparte** (a corretora quebrar, como a FTX em 2022) e liquidação do perpétuo em alta forte (o bot faz re-hedge a cada 20%). O rendimento está **caindo** (40% em 2021 → 2% em 2026).
- **D**: efeito documentado na literatura e que continuou funcionando após publicado; 12/12 vizinhos positivos; funcionou em IWM/DIA/EFA. Precisa de ordem no leilão de fechamento (MOC) e de corretora com API nos EUA — por isso não está no bot 24/7.

## Estratégias reprovadas (e por quê)

| Estratégia | Treino → Teste (Sharpe) | Motivo |
|---|---|---|
| Momentum entre altcoins (rotação semanal) | até 1,55 → 0,6–0,8 | Pior que segurar BTC no teste (1,08); ganho vinha do filtro de BTC |
| Momentum comprado/vendido entre moedas | 0,5–1,3 → negativo | Perdeu dinheiro no teste |
| Tendência comprado/vendido em cripto | sempre pior que só comprado | Vender cripto contra a deriva de alta custa caro |
| Tendência em altcoins | mediana 0,37 vs 0,33 buy&hold | Altcoin mediana rendeu −8% a.a. no teste |
| Reversão à média 1h/4h em cripto (RSI, z-score) | ≈0 → ≈0 / negativo | Custos comem tudo |
| Sazonalidade por hora do dia (BTC) | — | Correlação treino×teste = −0,02 (ruído) |
| Pares na B3 (PETR3/4, ITUB4/BBDC4 …) | positivo → negativo | Relações não se mantêm (PETR3/4: 3% a.a.) |
| IBS / tendência / virada de mês no Ibovespa | inconsistentes | Ibovespa sem efeito estável |
| Rotação de setores EUA | 0,9 → 0,9 | Não supera o SPY no teste |
| Forex: tendência e reversão (diário e 1h) | ≈0 → ≈0 | Mercado eficiente nesses horizontes |

## Ressalvas importantes

1. **Correção por múltiplos testes.** Com 10.657 configurações testadas, o Sharpe máximo esperado *por sorte* é ≈1,9.
   Pelo Deflated Sharpe só a estratégia **C** é estatisticamente inequívoca. A, B e D (Sharpe ≈1) têm a seu favor a
   lógica econômica, a literatura e a consistência treino→teste→vizinhos→outros ativos, mas **não há prova estatística**.
2. **2025–2026 foram anos fracos** para todas (mercado cripto em baixa e funding baixo).
3. **Impostos não incluídos** (no Brasil incidem sobre ganhos de cripto e de ações). As estratégias rendem em dólar (USDT):
   compare com o que você teria em renda fixa — o CDI pagou dois dígitos ao ano recentemente.
4. **Risco de corretora/contraparte**, falhas de API, slippage maior em dias extremos e mudanças de regra não aparecem no backtest.
5. O teste foi visto ao escolher as candidatas (os parâmetros vieram do treino, mas a escolha *de quais famílias* manter usou o teste).
   **A validação final de verdade é rodar o bot em modo paper por algumas semanas/meses.**

## Reproduzir

```bash
pip install pandas numpy scipy pyarrow requests matplotlib
python research/fetch_data.py all          # ~200 MB em research/data (não versionado)
cd research
python study_crypto_trend.py ALL           # tendência em 42 séries
python study_crypto_xs.py                  # momentum entre moedas
python study_crypto_carry.py               # funding
python study_crypto_misc.py                # reversão, sazonalidade, rompimento
python study_equities.py                   # B3 e EUA
python study_fx.py                         # Forex
python robustness.py && python walkforward.py
```
Resultados em `research/results/*.csv`.
