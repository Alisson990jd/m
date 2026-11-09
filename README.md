# m — pesquisa de estratégias de trading + bot 24/7

- **[research/](research/README.md)** — teste de ~10.700 configurações em cripto, B3/EUA e Forex com dados reais,
  custos, separação treino/teste e testes de robustez. Resumo dos resultados, estratégias aprovadas e reprovadas.
- **[bot/](bot/README.md)** — bot 24/7 para a Binance com as 3 estratégias de cripto aprovadas
  (tendência BTC, rompimento intradiário BTC/ETH, arbitragem de funding). Começa em modo **paper**.

```bash
pip install -r bot/requirements.txt
cp bot/config.example.yaml bot/config.yaml
python -m bot.run --config bot/config.yaml      # paper trading 24/7
python -m pytest bot/tests -q                   # testes (paridade com o backtest)
```

Backtest não garante resultado futuro. Leia as ressalvas em `research/README.md` antes de usar dinheiro real.
