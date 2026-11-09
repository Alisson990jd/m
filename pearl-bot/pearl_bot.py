#!/usr/bin/env python3
"""
pearl_bot.py - aluga GPUs na Vast.ai e coloca para minerar Pearl (PRL) na Kryptex.

Uso rapido:
    python pearl_bot.py scan                 # mostra as ofertas que dao lucro agora (nao precisa de chave)
    python pearl_bot.py status               # mostra as maquinas alugadas pelo bot
    python pearl_bot.py run                  # simula (nao aluga nada), repetindo a cada N minutos
    python pearl_bot.py run --live           # aluga e destroi de verdade (gasta dinheiro)
    python pearl_bot.py run --live --once    # um ciclo so (bom para agendador / cron)
    python pearl_bot.py stop-all --live      # destroi todas as maquinas do bot

So usa a biblioteca padrao do Python (3.8+). Configuracao em config.json (veja config.example.json).
"""
import argparse
import json
import os
import shlex
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
VAST = "https://console.vast.ai"
KRYPTEX = "https://pool.kryptex.com"
LABEL_PREFIX = "pearlbot-"

# Hashrate de PRL por GPU (TH/s), nomes como a Vast.ai usa.
# Fonte: tabela de GPUs da Kryptex (09/11/2026); H100 SXM = 760 TH/s informado pelo usuario.
# O bot substitui esses valores pelo hashrate medido na pool assim que uma maquina roda > 1 h.
DEFAULT_GPUS = {
    "B200": 1343.2, "H200": 705.0, "H200 NVL": 705.0, "H100 SXM": 760.0, "H100 PCIE": 509.3,
    "H100 NVL": 433.3, "RTX PRO 6000 WS": 453.7, "RTX PRO 6000 S": 447.3, "RTX 5090": 400.0,
    "RTX 4090": 343.4, "RTX 4090D": 300.5, "A100 SXM4": 274.8, "RTX 6000Ada": 264.0, "L40S": 259.0,
    "RTX 5080": 242.4, "RTX 4080S": 219.4, "RTX 4080": 213.0, "RTX 5070 Ti": 201.5,
    "A100 PCIE": 200.0, "RTX 4070S Ti": 186.8, "RTX 4070 Ti": 170.3, "RTX 3090 Ti": 163.4,
    "RTX 4070S": 153.2, "RTX 3090": 141.1, "RTX 5070": 139.7, "RTX 3080 Ti": 139.0,
    "RTX A6000": 136.6, "RTX 3080": 130.3, "RTX 4070": 126.4, "L40": 115.0, "A40": 105.0,
    "RTX 4000Ada": 103.2, "RTX 5060 Ti": 102.5, "RTX A5000": 101.8, "RTX 2080 Ti": 98.9,
    "RTX 4060 Ti": 94.3, "RTX 3070 Ti": 92.0, "A10": 91.0, "L4": 88.3, "RTX 3070": 85.0,
    "RTX 5060": 84.8, "RTX A4000": 71.6, "RTX 3060 Ti": 70.0, "RTX 4060": 65.0,
}

# Comandos tirados da pagina de conexao da Kryptex (pool.kryptex.com/prl).
DEFAULT_MINERS = {
    "krig": {  # minerador da propria Kryptex, 0% de taxa, NVIDIA RTX 2000-5000
        "urls": ["https://github.com/kryptex/krig-miner/releases/download/v1.5.14/krig-miner-1.5.14-linux-x64.tar.gz"],
        "bin": "krig-miner",
        "cmd": '"$BIN" --url stratum+ssl://{host}:8048 --user {wallet}/{worker}',
    },
    "peak": {  # PeakMiner: RTX + datacenter (H/A/L/B)
        "urls": ["https://github.com/peakminer/peakminer/releases/download/v2.20.5/peakminer-2.20.5.tar.gz"],
        "bin": "peakminer",
        "cmd": '"$BIN" --coin pearl -o stratum+tcp://{host}:7048 -u {wallet}/{worker}',
    },
    "srb": {  # SRBMiner-MULTI (alternativa)
        "urls": [
            "https://github.com/kryptex-miners-org/kryptex-miners/releases/download/srbminer-3-8-4/SRBMiner-Multi-3-8-4-Linux.tar.gz",
            "https://github.com/doktor83/SRBMiner-Multi/releases/download/3.8.4/SRBMiner-Multi-3-8-4-Linux.tar.gz",
        ],
        "bin": "SRBMiner-MULTI",
        "cmd": '"$BIN" --disable-cpu --algorithm pearlhash --pool {host}:7048 --wallet {wallet}.{worker}',
    },
}

DEFAULT_CONFIG = {
    "vast_api_key": "",            # ou variavel de ambiente VAST_API_KEY
    "wallet": "",                  # carteira PRL (prl1...) ou usuario Kryptex; ou env PRL_WALLET
    "min_profit_per_hour": 0.10,   # US$/h de lucro minimo por maquina para alugar
    "stop_profit_per_hour": 0.0,   # destroi a maquina se o lucro cair abaixo disso
    "max_instances": 5,
    "max_spend_per_hour": 2.00,    # soma do aluguel de todas as maquinas do bot (US$/h)
    "min_credit_usd": 3.0,         # nao aluga mais nada se o saldo na Vast ficar abaixo disso
    "allow_on_demand": True,
    "allow_interruptible": True,
    "bid_markup": 0.05,            # lance = lance minimo x (1 + bid_markup)
    "min_reliability": 0.90,
    "verified_only": False,
    "min_cuda": 12.4,
    "min_inet_down_mbps": 100,
    "max_gpus_per_offer": 8,
    "exclude_countries": [],       # ex.: ["CN"] para evitar hosts na China
    "disk_gb": 10,
    "image": "nvidia/cuda:12.4.1-runtime-ubuntu22.04",
    "start_grace_min": 20,         # tempo para a maquina ligar antes de desistir
    "hashrate_check_min": 40,      # a partir daqui confere o hashrate real na Kryptex
    "min_hashrate_ratio": 0.5,     # destroi se o hashrate real for < 50% do esperado
    "loop_interval_min": 5,
    "gpus": {},                    # sobrescreve DEFAULT_GPUS: {"RTX 4090": 343.4, ...}
    "gpu_miner": {},               # forca minerador por GPU: {"RTX 4090": "srb"}
    "miners": {},                  # sobrescreve DEFAULT_MINERS
}

# ---------------------------------------------------------------- utilidades


def log(msg):
    line = time.strftime("%Y-%m-%d %H:%M:%S ") + msg
    print(line, flush=True)
    try:
        with open(os.path.join(HERE, "pearl_bot.log"), "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


def http(method, url, body=None, headers=None, timeout=60, retries=3):
    data = json.dumps(body).encode() if body is not None else None
    hdrs = {"User-Agent": "pearl-bot/1.0", "Accept": "application/json"}
    if data is not None:
        hdrs["Content-Type"] = "application/json"
    hdrs.update(headers or {})
    delay = 2
    for attempt in range(retries + 1):
        req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                raw = r.read()
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as e:
            text = e.read().decode(errors="replace")[:300]
            if e.code in (429, 500, 502, 503, 504) and attempt < retries:
                time.sleep(delay)
                delay *= 2
                continue
            raise RuntimeError(f"{method} {url.split('?')[0]} -> HTTP {e.code}: {text}") from None
        except (urllib.error.URLError, TimeoutError) as e:
            if attempt < retries:
                time.sleep(delay)
                delay *= 2
                continue
            raise RuntimeError(f"{method} {url.split('?')[0]} -> {e}") from None


def load_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def save_json(path, obj):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=1, sort_keys=True)
    os.replace(tmp, path)


def load_config(path):
    cfg = dict(DEFAULT_CONFIG)
    cfg.update(load_json(path, {}))
    cfg["vast_api_key"] = os.environ.get("VAST_API_KEY") or cfg["vast_api_key"]
    cfg["wallet"] = os.environ.get("PRL_WALLET") or cfg["wallet"]
    gpus = dict(DEFAULT_GPUS)
    gpus.update(cfg.get("gpus") or {})
    cfg["gpus"] = gpus
    miners = {k: dict(v) for k, v in DEFAULT_MINERS.items()}
    for k, v in (cfg.get("miners") or {}).items():
        miners.setdefault(k, {}).update(v)
    cfg["miners"] = miners
    return cfg


# ---------------------------------------------------------------- Kryptex


def get_market():
    """Preco do PRL (US$) e rendimento em PRL por TH/s por dia (estimativa PPS+ da Kryptex, ja sem a taxa)."""
    info = http("GET", KRYPTEX + "/prl/api/v1/pool/info")
    chart = http("GET", KRYPTEX + "/api/v1/coin/prl/price/chart")
    price = float(chart[-1]["price"])
    prl_per_th_day = float(info["estimated_profit_day"]) * 1e12
    if not (0 < price < 1e4 and 0 < prl_per_th_day < 10):
        raise RuntimeError(f"dados da Kryptex estranhos: preco={price} rendimento={prl_per_th_day}")
    return {"price": price, "prl_per_th_day": prl_per_th_day,
            "usd_per_th_hour": prl_per_th_day * price / 24.0}


def get_workers(wallet):
    """worker -> hashrate medio dos ultimos 30 min (TH/s)."""
    out = {}
    if not wallet:
        return out
    url = KRYPTEX + "/prl/api/v3/miner/workers/" + urllib.parse.quote(wallet, safe="")
    for w in http("GET", url).get("results", []):
        try:
            out[w["worker"]] = float(w.get("avg_hashrate_30m") or 0) / 1e12
        except (TypeError, ValueError):
            out[w["worker"]] = 0.0
    return out


def pool_host(geolocation):
    cc = (geolocation or "").split(",")[-1].strip().upper()
    if cc in ("CN", "HK", "TW", "MO"):
        return "prl-hk.kryptex.network"
    if cc in ("SG", "VN", "TH", "MY", "ID", "PH", "KR", "JP", "IN", "AU", "NZ"):
        return "prl-sg.kryptex.network"
    if cc in ("US", "CA", "MX"):
        return "prl-us.kryptex.network"
    if cc in ("BR", "AR", "CL", "CO", "PE", "UY", "PY", "BO", "EC", "VE"):
        return "prl-br.kryptex.network"
    if cc in ("RU", "BY", "KZ"):
        return "prl-ru.kryptex.network"
    if cc in ("AE", "SA", "QA", "KW", "BH", "OM", "IL"):
        return "prl-ae.kryptex.network"
    if len(cc) == 2:
        return "prl-eu.kryptex.network"
    return "prl.kryptex.network"


# ---------------------------------------------------------------- Vast.ai


class Vast:
    def __init__(self, api_key):
        self.key = api_key

    def _h(self):
        return {"Authorization": "Bearer " + self.key} if self.key else {}

    def search(self, query):
        return http("POST", VAST + "/api/v0/bundles/", query, self._h()).get("offers", [])

    def user(self):
        return http("GET", VAST + "/api/v0/users/current", headers=self._h())

    def instances(self):
        rows, params = [], {"select_filters": {}, "order_by": [{"col": "id", "dir": "asc"}], "limit": 25}
        while True:
            qs = "&".join(f"{k}={urllib.parse.quote_plus(v if isinstance(v, str) else json.dumps(v))}"
                          for k, v in params.items())
            data = http("GET", VAST + "/api/v1/instances/?" + qs, headers=self._h())
            rows += data.get("instances") or []
            if not data.get("next_token"):
                return rows
            params["after_token"] = data["next_token"]

    def create(self, offer_id, payload):
        return http("PUT", f"{VAST}/api/v0/asks/{offer_id}/", payload, self._h())

    def destroy(self, instance_id):
        return http("DELETE", f"{VAST}/api/v0/instances/{instance_id}/", {}, self._h())


def offer_country(o):
    return (o.get("geolocation") or "").split(",")[-1].strip().upper()


def search_offers(vast, cfg):
    """Busca ofertas por modelo de GPU (fixo e/ou interrompivel)."""
    types = (["on-demand"] if cfg["allow_on_demand"] else []) + (["bid"] if cfg["allow_interruptible"] else [])
    out = []
    for name in sorted(cfg["gpus"]):
        for t in types:
            q = {
                "rentable": {"eq": True}, "external": {"eq": False},
                "gpu_name": {"eq": name},
                "num_gpus": {"lte": int(cfg["max_gpus_per_offer"])},
                "reliability2": {"gte": float(cfg["min_reliability"])},
                "cuda_max_good": {"gte": float(cfg["min_cuda"])},
                "inet_down": {"gte": float(cfg["min_inet_down_mbps"])},
                "order": [["dph_total", "asc"]], "type": t, "limit": 64,
                "allocated_storage": float(cfg["disk_gb"]),
            }
            if cfg["verified_only"]:
                q["verified"] = {"eq": True}
            try:
                for o in vast.search(q):
                    o["_type"] = t
                    out.append(o)
            except RuntimeError as e:
                log(f"  busca {name}/{t} falhou: {e}")
            time.sleep(0.3)
    return out


def evaluate(o, cfg, market, learned):
    """Lucro (US$/h) da oferta inteira. Retorna dict ou None se a GPU nao for conhecida."""
    name = o.get("gpu_name")
    th_gpu = learned.get(name) or cfg["gpus"].get(name)
    if not th_gpu:
        return None
    n = int(o.get("num_gpus") or 1)
    storage = float(o.get("storage_total_cost") or 0)
    if o["_type"] == "bid":
        if not o.get("min_bid"):
            return None
        bid = round(float(o["min_bid"]) * (1 + float(cfg["bid_markup"])), 4)
        cost = bid + storage
    else:
        bid = None
        cost = float(o["dph_total"])
    revenue = n * th_gpu * market["usd_per_th_hour"]
    return {"offer": o, "id": o["id"], "machine_id": o.get("machine_id"), "gpu": name, "n": n,
            "th": n * th_gpu, "type": o["_type"], "bid": bid, "cost": cost, "revenue": revenue,
            "profit": revenue - cost, "country": offer_country(o),
            "rel": float(o.get("reliability2") or 0), "verified": o.get("verification")}


def best_offers(offers, cfg, market, state, skip_machines=()):
    blacklist = state.get("blacklist", {})
    excl = {c.upper() for c in cfg["exclude_countries"]}
    best = {}
    for o in offers:
        if str(o.get("machine_id")) in blacklist or o.get("machine_id") in skip_machines:
            continue
        if offer_country(o) in excl:
            continue
        ev = evaluate(o, cfg, market, state.get("learned", {}))
        if not ev or ev["profit"] < float(cfg["min_profit_per_hour"]):
            continue
        k = ev["machine_id"]
        if k not in best or ev["profit"] > best[k]["profit"]:
            best[k] = ev
    return sorted(best.values(), key=lambda e: -e["profit"])


# ---------------------------------------------------------------- minerador


def miner_for(gpu_name, cfg):
    forced = cfg["gpu_miner"].get(gpu_name)
    if forced:
        return forced
    return "krig" if gpu_name.upper().startswith(("RTX", "GTX", "TITAN")) else "peak"


def onstart_script(miner, wallet, worker, host):
    cmd = miner["cmd"].format(host=host, wallet=shlex.quote(wallet), worker=shlex.quote(worker))
    urls = " ".join(shlex.quote(u) for u in miner["urls"])
    binname = shlex.quote(miner["bin"])
    return f"""cat > /root/pearl_mine.sh <<'PEARLEOF'
#!/bin/bash
echo "pearl-bot: iniciando $(date)"
if ! command -v curl >/dev/null 2>&1 && ! command -v wget >/dev/null 2>&1; then
  apt-get update -y >/dev/null 2>&1
  DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends curl ca-certificates >/dev/null 2>&1
fi
mkdir -p /opt/miner && cd /opt/miner
BIN=$(find /opt/miner -type f -name {binname} 2>/dev/null | head -1)
if [ -z "$BIN" ]; then
  for u in {urls}; do
    echo "baixando $u"
    rm -f m.tgz
    if command -v curl >/dev/null 2>&1; then curl -fsSL --retry 3 -o m.tgz "$u"; else wget -q -O m.tgz "$u"; fi
    tar xzf m.tgz && break
  done
  BIN=$(find /opt/miner -type f -name {binname} | head -1)
fi
if [ -z "$BIN" ]; then echo "pearl-bot: minerador nao encontrado"; exit 1; fi
chmod +x "$BIN"
cd "$(dirname "$BIN")"
while true; do
  echo "pearl-bot: rodando $BIN $(date)"
  {cmd}
  echo "pearl-bot: minerador saiu ($?), reiniciando em 15 s"
  sleep 15
done
PEARLEOF
chmod +x /root/pearl_mine.sh
nohup /root/pearl_mine.sh > /root/pearl_mine.log 2>&1 &
"""


def rent(vast, ev, cfg, live):
    worker = f"vb{ev['id']}"
    mname = miner_for(ev["gpu"], cfg)
    miner = cfg["miners"][mname]
    host = pool_host(ev["offer"].get("geolocation"))
    payload = {
        "client_id": "me", "image": cfg["image"], "env": {}, "price": ev["bid"],
        "disk": float(cfg["disk_gb"]), "label": LABEL_PREFIX + worker,
        "onstart": onstart_script(miner, cfg["wallet"], worker, host),
        "runtype": "ssh_proxy", "cancel_unavail": True,
    }
    tag = "INTERROMPIVEL" if ev["type"] == "bid" else "FIXO"
    desc = (f"{ev['n']}x {ev['gpu']} ({ev['country']}, conf {ev['rel']:.2f}) {tag} "
            f"aluguel ${ev['cost']:.3f}/h rende ${ev['revenue']:.3f}/h lucro ${ev['profit']:+.3f}/h "
            f"minerador {mname} pool {host} worker {worker}")
    if not live:
        log("  [simulacao] alugaria " + desc)
        return None
    res = vast.create(ev["id"], payload)
    if not res.get("success", True) or not res.get("new_contract"):
        raise RuntimeError(f"Vast recusou: {res}")
    log(f"  ALUGOU instancia {res['new_contract']}: " + desc)
    return res["new_contract"]


# ---------------------------------------------------------------- ciclo


def bot_instances(vast):
    return [i for i in vast.instances() if str(i.get("label") or "").startswith(LABEL_PREFIX)]


def manage_instance(vast, inst, cfg, market, workers, state, live):
    """Decide se a maquina continua. Retorna True se continua."""
    iid = inst["id"]
    worker = str(inst["label"])[len(LABEL_PREFIX):]
    gpu, n = inst.get("gpu_name"), int(inst.get("num_gpus") or 1)
    age = (time.time() - float(inst.get("start_date") or time.time())) / 60.0
    status = inst.get("actual_status") or "?"
    cost = float(inst.get("dph_total") or 0)
    th_gpu = state.get("learned", {}).get(gpu) or cfg["gpus"].get(gpu) or 0
    expected = th_gpu * n
    measured = workers.get(worker)
    th = measured if (measured is not None and age >= cfg["hashrate_check_min"]) else expected
    profit = th * market["usd_per_th_hour"] - cost
    info = (f"#{iid} {n}x {gpu} {status} {age:.0f} min, aluguel ${cost:.3f}/h, "
            f"hashrate {('%.0f' % measured) if measured is not None else '-'}/{expected:.0f} TH/s, "
            f"lucro ${profit:+.3f}/h")

    reason, blacklist = None, False
    if status != "running":
        if age > cfg["start_grace_min"]:
            reason = f"nao esta rodando ({status}: {str(inst.get('status_msg') or '')[:80]})"
            blacklist = inst.get("intended_status") == "running" and not inst.get("is_bid")
    elif age >= cfg["hashrate_check_min"]:
        if (measured or 0) < cfg["min_hashrate_ratio"] * expected:
            reason = f"hashrate baixo na pool ({measured or 0:.0f} de {expected:.0f} TH/s)"
            blacklist = True
        elif profit < cfg["stop_profit_per_hour"]:
            reason = "deixou de dar lucro"
        elif age >= 60 and measured:
            old = state.setdefault("learned", {}).get(gpu)
            per_gpu = measured / n
            state["learned"][gpu] = round(per_gpu if not old else 0.7 * old + 0.3 * per_gpu, 2)
    elif profit < cfg["stop_profit_per_hour"]:
        reason = "deixou de dar lucro"

    if not reason:
        log("  ok   " + info)
        return True
    log(f"  DESTRUIR {info} -> {reason}" + ("" if live else " [simulacao]"))
    if live:
        vast.destroy(iid)
        if blacklist and inst.get("machine_id"):
            state.setdefault("blacklist", {})[str(inst["machine_id"])] = {"reason": reason, "ts": int(time.time())}
    return False


def cycle(cfg, live, state):
    vast = Vast(cfg["vast_api_key"])
    try:
        market = get_market()
    except RuntimeError as e:
        log(f"sem dados da Kryptex, pulando o ciclo: {e}")
        return
    log(f"PRL ${market['price']:.4f} | {market['prl_per_th_day']:.5f} PRL/TH/dia | "
        f"${market['usd_per_th_hour'] * 100:.4f}/h por 100 TH/s")

    active, credit = [], None
    if cfg["vast_api_key"]:
        user = vast.user()
        credit = float(user.get("credit", user.get("balance", 0)) or 0)
        workers = get_workers(cfg["wallet"])
        for inst in bot_instances(vast):
            if manage_instance(vast, inst, cfg, market, workers, state, live):
                active.append(inst)
        spend = sum(float(i.get("dph_total") or 0) for i in active)
        runway = credit / spend if spend else float("inf")
        log(f"saldo Vast ${credit:.2f} | {len(active)} maquinas | gasto ${spend:.3f}/h"
            + (f" | saldo dura ~{runway:.1f} h" if spend else ""))
    else:
        log("sem VAST_API_KEY: so simulando escolhas (nao ve as maquinas alugadas)")
        spend = 0.0

    if credit is not None and credit < cfg["min_credit_usd"]:
        log(f"saldo abaixo de ${cfg['min_credit_usd']:.2f}: nao aluga mais nada")
        return
    free = int(cfg["max_instances"]) - len(active)
    if free <= 0:
        return
    offers = search_offers(vast, cfg)
    used_machines = {i.get("machine_id") for i in active}
    cands = best_offers(offers, cfg, market, state, used_machines)
    log(f"{len(offers)} ofertas vistas, {len(cands)} com lucro >= ${cfg['min_profit_per_hour']:.2f}/h")
    for ev in cands:
        if free <= 0:
            break
        if spend + ev["cost"] > cfg["max_spend_per_hour"]:
            continue
        if credit is not None and credit < ev["cost"] * 2:
            continue
        try:
            rent(vast, ev, cfg, live)
            free -= 1
            spend += ev["cost"]
        except RuntimeError as e:
            log(f"  falhou ao alugar oferta {ev['id']}: {e}")


def check_ready(cfg, need_key, need_wallet):
    if need_key and not cfg["vast_api_key"]:
        sys.exit("faltou a chave da Vast: defina VAST_API_KEY ou vast_api_key no config.json")
    if need_wallet and not cfg["wallet"]:
        sys.exit("faltou a carteira: defina PRL_WALLET ou wallet no config.json")


def main():
    ap = argparse.ArgumentParser(description="Aluga GPUs na Vast.ai para minerar Pearl na Kryptex")
    ap.add_argument("command", choices=["scan", "status", "run", "stop-all"])
    ap.add_argument("--live", action="store_true", help="executa de verdade (gasta dinheiro)")
    ap.add_argument("--once", action="store_true", help="roda um ciclo e sai")
    ap.add_argument("--config", default=os.path.join(HERE, "config.json"))
    ap.add_argument("--state", default=os.path.join(HERE, "state.json"))
    a = ap.parse_args()
    cfg = load_config(a.config)
    state = load_json(a.state, {})

    if a.command == "scan":
        market = get_market()
        offers = search_offers(Vast(cfg["vast_api_key"]), cfg)
        cands = best_offers(offers, cfg, market, state)
        print(f"PRL ${market['price']:.4f}  {market['prl_per_th_day']:.5f} PRL/TH/dia  "
              f"{len(offers)} ofertas, {len(cands)} com lucro >= ${cfg['min_profit_per_hour']:.2f}/h\n")
        print(f"{'oferta':>9} {'GPU':>18} {'tipo':>6} {'pais':>4} {'conf':>5} "
              f"{'TH/s':>6} {'aluguel':>8} {'rende':>7} {'lucro/h':>8}")
        for e in cands[:30]:
            print(f"{e['id']:>9} {str(e['n']) + 'x ' + e['gpu']:>18} {'int' if e['type'] == 'bid' else 'fixo':>6} "
                  f"{e['country']:>4} {e['rel']:5.2f} {e['th']:6.0f} {e['cost']:8.3f} {e['revenue']:7.3f} "
                  f"{e['profit']:+8.3f}")
        return

    check_ready(cfg, need_key=a.live or a.command in ("status", "stop-all"),
                need_wallet=a.live and a.command == "run")
    vast = Vast(cfg["vast_api_key"])

    if a.command == "status":
        market = get_market()
        workers = get_workers(cfg["wallet"])
        insts = bot_instances(vast)
        user = vast.user()
        print(f"saldo ${float(user.get('credit', 0) or 0):.2f} | PRL ${market['price']:.4f} | {len(insts)} maquinas")
        for i in insts:
            w = str(i["label"])[len(LABEL_PREFIX):]
            th = workers.get(w)
            cost = float(i.get("dph_total") or 0)
            prof = (th or 0) * market["usd_per_th_hour"] - cost
            print(f"#{i['id']} {i.get('num_gpus')}x {i.get('gpu_name')} {i.get('actual_status')} "
                  f"aluguel ${cost:.3f}/h hashrate {th if th is not None else '-'} TH/s lucro real ${prof:+.3f}/h")
        return

    if a.command == "stop-all":
        for i in bot_instances(vast):
            log(f"destruindo #{i['id']} {i.get('gpu_name')}" + ("" if a.live else " [simulacao]"))
            if a.live:
                vast.destroy(i["id"])
        return

    log(f"pearl-bot iniciado ({'AO VIVO' if a.live else 'SIMULACAO'})")
    while True:
        try:
            cycle(cfg, a.live, state)
        except RuntimeError as e:
            log(f"erro no ciclo: {e}")
        save_json(a.state, state)
        if a.once:
            break
        time.sleep(float(cfg["loop_interval_min"]) * 60)


if __name__ == "__main__":
    main()
