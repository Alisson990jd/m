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
3. **Trava de saldo:** se o saldo da Vast, descontado o que as máquinas vão gastar até o próximo ciclo,
   chegar a `stop_credit_usd` (US$ 0,10), destrói todas as máquinas do bot. Assim o saldo não fica negativo.
4. Saldo abaixo de `min_credit_usd` (US$ 0,10): não aluga nada e fica esperando depósito. Quando o depósito cai,
   volta a alugar sozinho.
5. Busca na Vast as ofertas de cada modelo de GPU (aluguel fixo e interrompível), calcula
   `lucro = GPUs × TH/s × rendimento × preço − aluguel` e aluga as melhores com lucro ≥ `min_profit_per_hour`,
   respeitando `max_instances`, `max_spend_per_hour` e se o saldo paga pelo menos `min_runway_hours` (1 h)
   da máquina nova sem passar da trava.

O "saldo" é o crédito da Vast menos o que a conta estiver devendo (campo `balance` negativo).

Na máquina alugada, ele pergunta ao GitHub qual é a **versão mais recente** do minerador, baixa e começa a minerar
para `carteira/worker` no servidor da Kryptex mais próximo (HK, SG, US, BR, EU, RU ou AE). Se o GitHub falhar,
usa a versão fixa do código (KRig 1.6.0, PeakMiner 2.20.7, SRBMiner 3.8.6). Mineradores:
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
continuam alugadas e cobrando, e a trava de saldo também para de funcionar. Use `stop-all --live` antes de desligar de vez.

O lucro vai em PRL para a sua carteira, não para a Vast. Para "crescer a banca" na Vast, venda o PRL e deposite de novo.

## Configuração (`config.json`)

| Campo | Padrão | O que faz |
|---|---|---|
| `min_profit_per_hour` | 0.10 | lucro mínimo (US$/h) por máquina para alugar |
| `stop_profit_per_hour` | 0.0 | destrói se o lucro cair abaixo disso |
| `max_instances` | 5 | máximo de máquinas ao mesmo tempo |
| `max_spend_per_hour` | 2.00 | teto da soma dos aluguéis (US$/h) |
| `min_credit_usd` | 0.10 | abaixo desse saldo não aluga nada e espera depósito |
| `stop_credit_usd` | 0.10 | destrói todas as máquinas do bot antes de o saldo passar daqui |
| `min_runway_hours` | 1.0 | só aluga se o saldo pagar pelo menos 1 h da máquina nova |
| `use_latest_miner` | true | baixa a versão mais nova do minerador; `false` usa a versão fixa |
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
| `image` | `nvidia/cuda:12.4.1-base-ubuntu22.04` | imagem Docker (pequena; os mineradores já trazem o CUDA) |

## Riscos

- O lucro é estimado com o preço do PRL agora. Se o preço cair, o bot destrói as máquinas que deixarem de dar lucro,
  mas o que já foi pago não volta.
- Hosts baratos (não verificados, na China, interrompíveis) caem mais. Os primeiros 20–40 min de uma máquina ruim
  são pagos antes de o bot perceber.
- O fork FP8 do Pearl (PIP-3), se for ativado, deixa só H100/H200/B200 minerando; as RTX param.
- O bot não cobra tráfego de rede na conta (mineração usa pouco).

## Rodando numa VM (recomendado: Oracle Cloud Always Free)

Na VM (Oracle Linux com usuário `opc`, ou Ubuntu), rode:

```bash
curl -fsSLo install_vm.sh https://raw.githubusercontent.com/Alisson990jd/m/ccr-2c0cdf22-hm31ht/pearl-bot/install_vm.sh
VAST_API_KEY=SUA_CHAVE PRL_WALLET=SUA_CARTEIRA bash install_vm.sh
```

Ele instala git e python3 se faltar, baixa o bot em `~/pearl-bot-app`, grava o `config.json` (permissão 600),
roda os testes e cria o serviço `pearl-bot` (systemd), que liga sozinho junto com a VM e reinicia se cair.
Rodar de novo atualiza o código. Para mudar limites, edite `~/pearl-bot-app/pearl-bot/config.json`
e rode `sudo systemctl restart pearl-bot`.

## Rodando no GitHub Actions (desativado)

O workflow `.github/workflows/pearl-bot.yml` roda o bot sem precisar do seu PC.

1. No GitHub: **Settings → Secrets and variables → Actions → New repository secret**,
   nome `VAST_API_KEY`, valor = sua chave da Vast. Sem esse secret ele só simula.
2. **Teste** (push no branch do bot): roda 60 min ao vivo e destrói as máquinas do bot no fim
   (mesmo se o job for cancelado).
3. **Produção** (arquivo no branch `main`): dispara a cada hora; cada job vigia por ~5h40 e o seguinte
   fica na fila e assume quando ele termina. No último ciclo de cada job, a trava de saldo reserva 90 min
   de gasto, para o caso de o próximo job atrasar.
4. A lista negra e o hashrate aprendido ficam salvos no cache do Actions entre um job e outro.

Os termos do GitHub proíbem usar o Actions para mineração ou para tarefas sem relação com o código do
repositório. O GitHub pode cancelar os jobs ou bloquear o Actions. Se isso acontecer, as máquinas ficam
sem vigilância: entre na Vast e destrua as máquinas `pearlbot-...`, ou rode `stop-all --live` em outro lugar.
O repositório é público, então os logs (saldo, máquinas, gastos) ficam visíveis para qualquer pessoa.
