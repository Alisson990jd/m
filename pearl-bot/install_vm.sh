#!/bin/bash
# Instala o pearl-bot como servico (systemd) numa VM Linux: Oracle Linux (usuario opc), Ubuntu etc.
# Uso, na VM:
#   curl -fsSL https://raw.githubusercontent.com/Alisson990jd/m/ccr-2c0cdf22-hm31ht/pearl-bot/install_vm.sh \
#     | VAST_API_KEY=SUA_CHAVE PRL_WALLET=SUA_CARTEIRA bash
# Rodar de novo atualiza o codigo e reinicia o servico.
set -euo pipefail
: "${VAST_API_KEY:?defina VAST_API_KEY=sua chave da Vast}"
: "${PRL_WALLET:?defina PRL_WALLET=sua carteira PRL ou usuario Kryptex}"
BRANCH="${BRANCH:-ccr-2c0cdf22-hm31ht}"
REPO="${REPO:-https://github.com/Alisson990jd/m}"
DIR="$HOME/pearl-bot-app"

echo "== instalando git e python3 (se faltar)"
if ! command -v git >/dev/null 2>&1 || ! command -v python3 >/dev/null 2>&1; then
  if command -v dnf >/dev/null 2>&1; then sudo dnf install -y -q git python3
  elif command -v yum >/dev/null 2>&1; then sudo yum install -y -q git python3
  else sudo apt-get update -qq && sudo apt-get install -y -qq git python3; fi
fi

echo "== baixando o bot ($BRANCH)"
if [ -d "$DIR/.git" ]; then
  git -C "$DIR" fetch -q origin "$BRANCH"
  git -C "$DIR" checkout -q -B "$BRANCH" "origin/$BRANCH"
else
  git clone -q -b "$BRANCH" "$REPO" "$DIR"
fi
cd "$DIR/pearl-bot"

echo "== gravando config.json (so o seu usuario le)"
umask 077
if [ -f config.json ]; then
  python3 - "$VAST_API_KEY" "$PRL_WALLET" <<'PY'
import json, sys
c = json.load(open("config.json"))
c["vast_api_key"], c["wallet"] = sys.argv[1], sys.argv[2]
json.dump(c, open("config.json", "w"), indent=1)
PY
else
  printf '{"vast_api_key": "%s", "wallet": "%s"}\n' "$VAST_API_KEY" "$PRL_WALLET" > config.json
fi

echo "== testes"
python3 -m unittest -q test_pearl_bot || echo "aviso: algum teste falhou, veja acima"

echo "== criando o servico pearl-bot"
PY="$(command -v python3)"
sudo tee /etc/systemd/system/pearl-bot.service >/dev/null <<EOF
[Unit]
Description=pearl-bot (Vast.ai + Kryptex)
After=network-online.target
Wants=network-online.target

[Service]
User=$(id -un)
WorkingDirectory=$DIR/pearl-bot
ExecStart=$PY $DIR/pearl-bot/pearl_bot.py run --live
Restart=always
RestartSec=30

[Install]
WantedBy=multi-user.target
EOF
sudo systemctl daemon-reload
sudo systemctl enable pearl-bot >/dev/null 2>&1
sudo systemctl restart pearl-bot
sleep 8
sudo systemctl --no-pager --lines=0 status pearl-bot | head -3 || true
echo
echo "pronto. Comandos uteis:"
echo "  ver o bot ao vivo:   tail -f $DIR/pearl-bot/pearl_bot.log"
echo "  maquinas e lucro:    cd $DIR/pearl-bot && python3 pearl_bot.py status"
echo "  parar o bot:         sudo systemctl stop pearl-bot"
echo "  destruir maquinas:   cd $DIR/pearl-bot && python3 pearl_bot.py stop-all --live"
