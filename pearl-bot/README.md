# pearl-bot

Bot que aluga GPUs na **Vast.ai** e coloca para minerar **Pearl (PRL)** na pool **Kryptex**.
Ele só aluga as máquinas que dão pelo menos **US$ 0,10/h de lucro** (configurável) e destrói
sozinho as que pararem de dar lucro ou não estiverem minerando.

## Como ele decide

A cada 5 minutos (configurável):

1. Pega na API da Kryptex o preço do PRL e o rendimento atual (PRL por TH/s por dia, já descontada a taxa PPS+ de 3%).
2. Para cada máquina que **ele mesmo** alugou (rótulo `pearlbot-...`; as suas outras máquinas nunca são tocadas):
   - não ligou em 20 min → destrói (e põe a máquina numa lista negra);
   - interrompível que foi tirada por lance maior → destrói (para não pagar disco parado);
   - depois de 40 min, confere o hashrate real do worker na Kryptex: abaixo de 50% do esperado → destrói e põe na lista negra;
   - lucro real (hashrate medido × preço − aluguel) abaixo de `stop_profit_per_hour` → destrói;
   - depois de 1 h rodando, aprende o hashrate real daquele modelo de GPU e usa nas próximas contas.
3. Busca na Vast as ofertas de cada modelo de GPU (aluguel fixo e interrompível), calcula
   `lucro = GPUs × TH/s × rendimento × preço − aluguel` e aluga as melhores com lucro ≥ `min_profit_per_hour`,
   respeitando `max_instances`, `max_spend_per_hour` e `min_credit_usd`.

Na máquina alugada, ele baixa o minerador e começa a minerar para `carteira/worker` no servidor da Kryptex mais próximo
(HK, SG, US, BR, EU, RU ou AE):
- **KRig** (da Kryptex, 0% de taxa) nas RTX;
- **PeakMiner** nas placas de datacenter (H100, H200, A100, L40S…);
- **SRBMiner-MULTI** como alternativa (`"gpu_miner": {"RTX 4090": "srb"}`).

## Passo a passo

1. **Deposite na Vast.ai com cripto.** Os termos da Vast dizem que crédito comprado com cartão de crédito
   não pode ser usado para mineração.
2. Crie uma chave de API na Vast (Account → Keys).
3. Tenha uma carteira PRL (`prl1...`) ou um usuário Kryptex (para receber em BTC/USDT).
4. Instale o Python 3.8+ (no Windows, marque "Add to PATH").
5. Copie `config.example.json` para `config.json` e preencha `vast_api_key` e `wallet`.
   Ou use as variáveis de ambiente `VAST_API_KEY` e `PRL_WALLET`. O `config.json` está no `.gitignore`: não suba sua chave.
6. Rode:

```bash
python pearl_bot.py scan                 # ofertas com lucro agora (não precisa de chave)
python pearl_bot.py run                  # simulação: mostra o que alugaria/destruiria, sem gastar
python pearl_bot.py run --live           # pra valer: fica rodando e repete a cada 5 min
python pearl_bot.py status               # suas máquinas do bot, hashrate real e lucro real
python pearl_bot.py stop-all --live      # destrói todas as máquinas do bot
python -m unittest -v test_pearl_bot     # testes
```

O bot precisa ficar ligado (no seu PC ou num servidor) para vigiar as máquinas. Se ele parar, as máquinas
continuam alugadas e cobrando. Use `stop-all --live` antes de desligar de vez.

## Configuração (`config.json`)

| Campo | Padrão | O que faz |
|---|---|---|
| `min_profit_per_hour` | 0.10 | lucro mínimo (US$/h) por máquina para alugar |
| `stop_profit_per_hour` | 0.0 | destrói se o lucro cair abaixo disso |
| `max_instances` | 5 | máximo de máquinas ao mesmo tempo |
| `max_spend_per_hour` | 2.00 | teto da soma dos aluguéis (US$/h) |
| `min_credit_usd` | 3.0 | não aluga mais nada abaixo desse saldo |
| `allow_on_demand` / `allow_interruptible` | true / true | tipos de aluguel permitidos |
| `bid_markup` | 0.05 | lance interrompível = lance mínimo + 5% |
| `min_reliability` | 0.90 | confiabilidade mínima do host |
| `verified_only` | false | só hosts verificados pela Vast |
| `exclude_countries` | [] | ex.: `["CN"]` para evitar hosts na China |
| `max_gpus_per_offer` | 8 | máximo de GPUs por máquina |
| `start_grace_min` | 20 | minutos para a máquina ligar |
| `hashrate_check_min` | 40 | a partir de quando confere o hashrate na pool |
| `min_hashrate_ratio` | 0.5 | destrói se hashrate real < 50% do esperado |
| `loop_interval_min` | 5 | intervalo entre ciclos |
| `gpus` | tabela da Kryptex | sobrescreve o TH/s esperado por GPU, ex.: `{"RTX 4090": 330}` |
| `gpu_miner` | automático | força o minerador por GPU: `krig`, `peak` ou `srb` |
| `image` | `nvidia/cuda:12.4.1-runtime-ubuntu22.04` | imagem Docker usada |

## Riscos

- O lucro é estimado com o preço do PRL agora. Se o preço cair, o bot destrói as máquinas que deixarem de dar lucro,
  mas o que já foi pago não volta.
- Hosts baratos (não verificados, na China, interrompíveis) caem mais. Os primeiros 20–40 min de uma máquina ruim
  são pagos antes de o bot perceber.
- O fork FP8 do Pearl (PIP-3), se for ativado, deixa só H100/H200/B200 minerando; as RTX param.
- O bot não cobra tráfego de rede na conta (mineração usa pouco).
