"""Motor 24/7: orquestra as três estratégias de cripto aprovadas na pesquisa.

  A. trend    — BTC spot, fração 0..1 do capital pelo conjunto de 8 regras (rebalanceia 1x/dia)
  B. breakout — perpétuos BTC/ETH: stop de compra em abertura + k×amplitude de ontem, filtro SMA50;
                fecha no fim do dia UTC
  C. carry    — spot comprado + perpétuo vendido (delta-neutro), recebe funding; re-hedge após grandes
                movimentos para não correr risco de liquidação

O passo (`step`) é idempotente e pode ser chamado a cada minuto; o estado fica em state.json,
então o bot pode reiniciar sem perder posições.
"""
from __future__ import annotations

import csv
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

from bot import signals

log = logging.getLogger("bot.engine")


def notify(msg: str):
    log.warning(msg)
    tok, chat = os.environ.get("TELEGRAM_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    if tok and chat:
        try:
            requests.post(f"https://api.telegram.org/bot{tok}/sendMessage",
                          data={"chat_id": chat, "text": msg[:3500]}, timeout=10)
        except requests.RequestException:
            pass


class Engine:
    def __init__(self, cfg: dict, broker, market):
        self.cfg, self.b, self.m = cfg, broker, market
        self.meta = self.b.state["meta"]
        self.meta.setdefault("armed", {})
        self.meta.setdefault("carry", {})
        self.meta.setdefault("peak", None)
        self.meta.setdefault("killed", False)
        self.equity_csv = Path(cfg.get("equity_csv", Path(cfg["state_file"]).parent / "equity.csv"))

    # ------------------------------------------------------------------ helpers
    def _prices(self):
        syms = {self.cfg["trend"]["symbol"], *self.cfg["breakout"]["symbols"], *self.cfg["carry"]["symbols"]}
        return {s + "USDT": self.m.last_price(s + "USDT") for s in syms}

    def _sleeve_equity(self, name, prices):
        return self.b.equity(prices)[name]

    # ------------------------------------------------------------------ ciclo
    def step(self, now: datetime | None = None):
        now = now or datetime.now(timezone.utc)
        prices = self._prices()
        day = now.strftime("%Y-%m-%d")
        if self.meta.get("last_day") != day and now >= now.replace(hour=0, minute=0, second=30, microsecond=0):
            self.on_new_day(now, prices)
            prices = self._prices()
        self.check_breakout(now)
        self.manage_carry(now, prices)
        self.risk_and_snapshot(now, prices)
        self.b.save()

    # ------------------------------------------------------------------ virada do dia (00:00 UTC)
    def on_new_day(self, now, prices):
        log.info("=== novo dia UTC %s ===", now.date())
        # B: fecha posições do dia anterior e cancela stops não disparados
        for sym in self.cfg["breakout"]["symbols"]:
            p = sym + "USDT"
            self.b.cancel_stops(p)
            q = self.b.perp_qty("breakout", p)
            if q:
                self.b.perp_trade("breakout", p, -q, prices[p])
        self.meta["armed"] = {}
        killed = self.meta.get("killed")
        # A: rebalanceia BTC spot para a fração-alvo
        tc = self.cfg["trend"]
        sym = tc["symbol"]
        closed, _ = self.m.daily_closed(sym + "USDT")
        tgt = 0.0 if killed else signals.trend_target(closed["close"])
        px = prices[sym + "USDT"]
        eq = self._sleeve_equity("trend", prices)
        cur = self.b.spot_qty("trend", sym)
        diff = tgt * eq / px - cur
        if abs(diff * px) > tc.get("rebalance_band", 0.05) * eq or (tgt == 0 and cur > 0):
            if diff > 0:
                self.b.spot_buy("trend", sym, diff * 0.995, px)   # 0,5% de folga p/ taxa
            else:
                self.b.spot_sell("trend", sym, -diff, px)
        log.info("tendência: alvo %.3f (%s) patrimônio %.2f", tgt, sym, eq)
        # B: arma os gatilhos do dia
        bc = self.cfg["breakout"]
        eqb = self._sleeve_equity("breakout", prices)
        per = eqb / len(bc["symbols"])
        day_start = int(now.replace(hour=0, minute=0, second=0, microsecond=0).timestamp() * 1000)
        for s in bc["symbols"]:
            closed, day_open = self.m.daily_closed(s + "USDT")
            plan = signals.breakout_plan(closed, day_open, bc.get("k", 0.5), bc.get("trend_n", 50))
            log.info("rompimento %s: ativo=%s gatilho=%.2f (abertura %.2f)", s, plan.active, plan.level, day_open)
            if plan.active and not killed and per > 0:
                qty = per / plan.level
                self.meta["armed"][s] = {"level": plan.level, "qty": qty, "since": day_start,
                                         "checked": day_start, "filled": False}
                self.b.place_stop_buy("breakout", s + "USDT", qty, plan.level)
        self.meta["last_day"] = now.strftime("%Y-%m-%d")

    # ------------------------------------------------------------------ B: disparo do stop
    def check_breakout(self, now):
        for s, a in self.meta["armed"].items():
            if a["filled"]:
                continue
            p = s + "USDT"
            if hasattr(self.b, "stop_filled"):            # live: a corretora executa o stop
                o = self.b.stop_filled(p)
                if o:
                    self.b.record_perp("breakout", p, float(o["filled"]), float(o.get("average") or a["level"]))
                    a["filled"] = True
                    notify(f"Rompimento {s}: comprado @ {o.get('average')}")
                continue
            hi = self.m.max_high_since(p, a["checked"])     # paper: simula com candles de 1m
            a["checked"] = int(now.timestamp() * 1000) - 60_000
            if hi is not None and hi >= a["level"]:
                self.b.perp_trade("breakout", p, a["qty"], a["level"])
                a["filled"] = True
                notify(f"[PAPER] Rompimento {s}: comprado {a['qty']:.5f} @ ~{a['level']:.2f}")

    # ------------------------------------------------------------------ C: hedge de funding
    def manage_carry(self, now, prices):
        cc = self.cfg["carry"]
        syms, lev = cc["symbols"], float(cc.get("perp_leverage", 2))
        if not syms:
            return
        eq = self._sleeve_equity("carry", prices)
        for s in syms:
            p = s + "USDT"
            px = prices[p]
            st = self.meta["carry"].setdefault(s, {})
            q_spot, q_perp = self.b.spot_qty("carry", s), self.b.perp_qty("carry", p)
            target_q = (eq / len(syms)) / (1 + 1 / lev) / px
            moved = st.get("ref_px") and abs(px / st["ref_px"] - 1) > cc.get("rebalance_move", 0.20)
            if q_spot == 0 and q_perp == 0:
                self.b.spot_buy("carry", s, target_q, px)
                self.b.perp_trade("carry", p, -target_q, px)
                st.update(ref_px=px, funding_from=int(now.timestamp() * 1000))
                notify(f"Carry {s}: hedge aberto, nocional {target_q * px:.2f} USDT")
            elif moved:
                # re-hedge: devolve as duas pernas ao tamanho-alvo no preço atual
                up = px > st["ref_px"]
                if up:   # perp perdeu margem: move parte do lucro do spot para a carteira de futuros
                    self.b.transfer_to_futures(max(0.0, -q_perp * (px - st["ref_px"])))
                d = target_q - q_spot
                if d > 0:
                    self.b.spot_buy("carry", s, d, px)
                else:
                    self.b.spot_sell("carry", s, -d, px)
                self.b.perp_trade("carry", p, -target_q - q_perp, px)
                st["ref_px"] = px
                notify(f"Carry {s}: re-hedge após movimento de preço (novo nocional {target_q * px:.2f})")
            # funding recebido/pago (ledger; na conta real a Binance credita sozinha).
            # Consulta no máximo a cada 15 min (o funding é pago a cada 4–8 h).
            now_ms = int(now.timestamp() * 1000)
            if now_ms < st.get("next_funding_check", 0):
                continue
            st["next_funding_check"] = now_ms + 15 * 60_000
            hist = self.m.funding_history(p, st.get("funding_from", now_ms))
            if hist is None:   # região bloqueada/sem rede: tenta de novo em 30 min, sem quebrar
                st["next_funding_check"] = now_ms + 30 * 60_000
                continue
            for t, rate in hist.items():
                ts = int(t.timestamp() * 1000)
                if ts <= st.get("funding_from", 0):
                    continue
                amt = self.b.credit_funding("carry", p, rate, px)
                st["funding_from"] = ts
                st["funding_total"] = st.get("funding_total", 0.0) + amt
                log.info("funding %s %.5f%% => %.4f USDT", s, rate * 100, amt)

    # ------------------------------------------------------------------ risco e registro
    def risk_and_snapshot(self, now, prices):
        e = self.b.equity(prices)
        peak = max(self.meta["peak"] or e["total"], e["total"])
        self.meta["peak"] = peak
        dd = e["total"] / peak - 1
        lim = self.cfg.get("risk", {}).get("max_drawdown", 0.25)
        if dd < -lim and not self.meta["killed"]:
            self.meta["killed"] = True
            notify(f"KILL SWITCH: patrimônio caiu {dd:.1%} do pico. Estratégias direcionais desligadas "
                   f"(A e B). O carry, neutro em preço, continua. Revise antes de religar (killed=false).")
            sym = self.cfg["trend"]["symbol"]
            q = self.b.spot_qty("trend", sym)
            if q:
                self.b.spot_sell("trend", sym, q, prices[sym + "USDT"])
            for s in self.cfg["breakout"]["symbols"]:
                q = self.b.perp_qty("breakout", s + "USDT")
                if q:
                    self.b.perp_trade("breakout", s + "USDT", -q, prices[s + "USDT"])
            self.meta["armed"] = {}
        hour = now.strftime("%Y-%m-%d %H:00")
        if self.meta.get("last_snapshot") != hour:
            self.meta["last_snapshot"] = hour
            new = not self.equity_csv.exists()
            self.equity_csv.parent.mkdir(parents=True, exist_ok=True)
            with self.equity_csv.open("a", newline="") as f:
                w = csv.writer(f)
                if new:
                    w.writerow(["time", "trend", "breakout", "carry", "total", "drawdown"])
                w.writerow([now.isoformat(timespec="seconds")] + [round(e[k], 2) for k in
                           ("trend", "breakout", "carry", "total")] + [round(dd, 4)])
            log.info("patrimônio: %s | drawdown %.2f%%", {k: round(v, 2) for k, v in e.items()}, dd * 100)
