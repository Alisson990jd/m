# Bot 24/7 de cripto (Binance)

Executa as 3 estratégias de cripto aprovadas na pesquisa (`research/README.md`):

| Gaveta | Estratégia | Onde opera | Frequência |
|---|---|---|---|
| `trend` | A. Tendência BTC — fração 0–100% em BTC pelo voto de 8 regras | Spot | 1×/dia (00:00 UTC) |
| `breakout` | B. Rompimento intradiário BTC/ETH com filtro SMA50 | Futuros USDⓈ-M | arma 00:00 UTC, fecha 24 h depois |
| `carry` | C. Arbitragem de funding BTC/ETH (spot comprado + perpétuo vendido) | Spot + Futuros | contínuo; re-hedge após ±20% |

**Começa em modo `paper` (dinheiro fictício, preços reais).** Nada é enviado à corretora nesse modo.

## Rodar em modo paper

```bash
pip install -r bot/requirements.txt
cp bot/config.example.yaml bot/config.yaml       # ajuste o capital fictício
python -m bot.run --config bot/config.yaml        # roda 24/7 (Ctrl+C para parar)
python -m bot.run --config bot/config.yaml --status
```
Estado em `bot/state/state.json` (pode reiniciar sem perder posições), patrimônio por hora em
`bot/state/equity.csv`, log em `bot/logs/bot.log`.

## Rodar 24/7 num servidor (VPS)

```bash
cp .env.example .env && cp bot/config.example.yaml bot/config.yaml
docker compose up -d --build        # reinicia sozinho se cair
docker compose logs -f bot
```
⚠️ A Binance **bloqueia servidores nos EUA** (erro 451). Use um VPS no Brasil/América do Sul, Europa ou Ásia.
Alertas no celular: crie um bot no Telegram (@BotFather) e preencha `TELEGRAM_TOKEN`/`TELEGRAM_CHAT_ID` no `.env`.

## Passar para dinheiro real — só depois do paper

Ordem recomendada: **paper (semanas) → testnet → pouco dinheiro real → aumentar aos poucos**.

1. Crie a chave de API na Binance com **apenas** "Spot & Margin Trading" e "Futures" habilitados.
   **Desabilite saques** e restrinja ao IP do seu servidor.
2. Coloque as chaves no `.env` (nunca no código ou no git).
3. Na conta de futuros: modo de posição **One-way** (obrigatório: `breakout` e `carry` usam o mesmo perpétuo e
   a corretora soma as duas numa posição líquida; o bot separa as gavetas no próprio livro-razão), margem
   **cross**, e deixe USDT na carteira de futuros para a margem do `breakout` e do `carry`.
   Use uma subconta exclusiva para o bot se puder.
4. No `config.yaml`: `mode: live` e `testnet: true`; no `.env`: `BOT_LIVE_CONFIRM=SIM`. Teste na testnet.
5. Só então `testnet: false`, começando com capital pequeno.

> O modo real (`LiveBroker`, via ccxt) **não pôde ser testado contra a Binance** no ambiente onde foi escrito
> (região bloqueada). Os sinais e a contabilidade foram testados (`python -m pytest bot/tests`), incluindo
> paridade exata com o backtest. Acompanhe de perto as primeiras ordens reais.

## Proteções embutidas
- Kill switch: se o patrimônio total cair `risk.max_drawdown` (25%) do pico, A e B são zeradas e desligadas
  (o carry, neutro em preço, continua). Para religar, edite `killed: false` em `state.json` depois de revisar.
- Rompimento usa ordem stop **na corretora** (executa mesmo se o bot cair) e é fechado na virada do dia.
- Carry faz re-hedge quando o preço anda 20% para evitar liquidação do perpétuo vendido.
- Erros de rede não derrubam o loop; após 3/30/300 erros seguidos envia alerta.

## Riscos que o bot NÃO elimina
Quebra/bloqueio da corretora, mudança de regras ou taxas, falhas de API, movimentos extremos com slippage,
e a possibilidade de o desempenho passado não se repetir. Não invista o que não pode perder.
