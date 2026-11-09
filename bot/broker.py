"""Corretoras: PaperBroker (simulação com dinheiro fictício) e LiveBroker (Binance via ccxt).

Interface comum, em unidades do ativo-base (ex.: BTC):
  spot_buy(asset, qty, price_hint)      spot_sell(asset, qty, price_hint)
  perp_trade(symbol, qty, price_hint)   (qty > 0 compra, < 0 vende; posição líquida)
  place_stop_buy(symbol, qty, stop)     cancel_stops(symbol)       (só live: ordem na corretora)
Cada estratégia tem sua própria "gaveta" (sleeve) de capital para medir o resultado em separado.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path

log = logging.getLogger("bot.broker")


class PaperBroker:
    """Simulação: preenche ao preço informado + slippage, cobra taxas, credita funding."""

    def __init__(self, state_path: Path, capital: dict, fee_spot=0.001, fee_perp=0.0005, slippage=0.0002):
        self.path = Path(state_path)
        self.fee_spot, self.fee_perp, self.slip = fee_spot, fee_perp, slippage
        if self.path.exists():
            self.state = json.loads(self.path.read_text())
        else:
            self.state = {"sleeves": {k: {"usdt": float(v), "spot": {}, "perp": {}} for k, v in capital.items()},
                          "trades": [], "meta": {}}

    # ------------------------------------------------------------------ util
    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.state, indent=1, default=str))
        tmp.replace(self.path)

    def sleeve(self, name):
        return self.state["sleeves"][name]

    def _trade(self, sleeve, kind, sym, qty, price, fee):
        self.state["trades"].append(dict(sleeve=sleeve, kind=kind, sym=sym, qty=qty, price=price, fee=fee))
        self.state["trades"] = self.state["trades"][-2000:]
        log.info("[PAPER] %s %s %s qty=%.6f @ %.2f fee=%.4f", sleeve, kind, sym, qty, price, fee)

    # ------------------------------------------------------------------ spot
    def spot_buy(self, sleeve, asset, qty, price_hint):
        s = self.sleeve(sleeve)
        px = price_hint * (1 + self.slip)
        fee = qty * px * self.fee_spot
        s["usdt"] -= qty * px + fee
        s["spot"][asset] = s["spot"].get(asset, 0.0) + qty
        self._trade(sleeve, "spot_buy", asset, qty, px, fee)

    def spot_sell(self, sleeve, asset, qty, price_hint):
        s = self.sleeve(sleeve)
        qty = min(qty, s["spot"].get(asset, 0.0))
        px = price_hint * (1 - self.slip)
        fee = qty * px * self.fee_spot
        s["usdt"] += qty * px - fee
        s["spot"][asset] = s["spot"].get(asset, 0.0) - qty
        self._trade(sleeve, "spot_sell", asset, qty, px, fee)

    def spot_qty(self, sleeve, asset):
        return self.sleeve(sleeve)["spot"].get(asset, 0.0)

    # ------------------------------------------------------------------ perpétuo (margem em USDT)
    def perp_trade(self, sleeve, symbol, qty, price_hint, exact_price=False):
        """Ajusta a posição líquida em `qty`. PnL realizado vai para o caixa da gaveta."""
        s = self.sleeve(sleeve)
        px = price_hint if exact_price else price_hint * (1 + self.slip * (1 if qty > 0 else -1))
        pos = s["perp"].get(symbol, {"qty": 0.0, "entry": 0.0})
        q0, e0 = pos["qty"], pos["entry"]
        q1 = q0 + qty
        if q0 != 0 and (q0 > 0) != (qty > 0):           # reduzindo/invertendo
            closed = min(abs(qty), abs(q0)) * (1 if q0 > 0 else -1)
            s["usdt"] += closed * (px - e0)
        if q1 == 0:
            pos = {"qty": 0.0, "entry": 0.0}
        elif q0 == 0 or (q0 > 0) != (q1 > 0):
            pos = {"qty": q1, "entry": px}
        elif (q0 > 0) == (qty > 0):                      # aumentando: preço médio
            pos = {"qty": q1, "entry": (q0 * e0 + qty * px) / q1}
        else:
            pos = {"qty": q1, "entry": e0}
        fee = abs(qty) * px * self.fee_perp
        s["usdt"] -= fee
        s["perp"][symbol] = pos
        self._trade(sleeve, "perp", symbol, qty, px, fee)

    def record_perp(self, sleeve, symbol, qty, price):
        """Registra no livro-razão um preenchimento que já aconteceu (ex.: stop executado na corretora)."""
        PaperBroker.perp_trade(self, sleeve, symbol, qty, price, exact_price=True)

    def perp_qty(self, sleeve, symbol):
        return self.sleeve(sleeve)["perp"].get(symbol, {"qty": 0.0})["qty"]

    def perp_entry(self, sleeve, symbol):
        return self.sleeve(sleeve)["perp"].get(symbol, {"entry": 0.0})["entry"]

    def transfer_to_futures(self, usdt):   # no paper as carteiras não são separadas
        pass

    def credit_funding(self, sleeve, symbol, rate, mark):
        """Funding positivo: comprados pagam vendidos. Posição vendida (qty<0) recebe."""
        q = self.perp_qty(sleeve, symbol)
        amt = -q * mark * rate
        self.sleeve(sleeve)["usdt"] += amt
        return amt

    def place_stop_buy(self, *a, **k):   # no paper, o motor simula o disparo com candles de 1m
        pass

    def cancel_stops(self, *a, **k):
        pass

    # ------------------------------------------------------------------ patrimônio
    def equity(self, prices: dict) -> dict:
        out = {}
        for name, s in self.state["sleeves"].items():
            v = s["usdt"]
            v += sum(q * prices[a + "USDT"] for a, q in s["spot"].items() if q)
            v += sum(p["qty"] * (prices[sym] - p["entry"]) for sym, p in s["perp"].items() if p["qty"])
            out[name] = v
        out["total"] = sum(out.values())
        return out


class LiveBroker(PaperBroker):
    """Envia ordens reais para a Binance (spot + futuros USDⓈ-M) usando ccxt.

    O livro-razão por gaveta (state.json) continua sendo mantido localmente para medir cada
    estratégia — o bot só opera as quantidades que ELE abriu; não mexe no resto da sua conta.
    Use primeiro testnet=True. NÃO foi testado contra a corretora real neste ambiente.
    """

    def __init__(self, state_path, capital, testnet=True, **kw):
        super().__init__(state_path, capital, **kw)
        import ccxt  # import tardio: o modo paper não precisa do ccxt
        key, secret = os.environ.get("BINANCE_API_KEY"), os.environ.get("BINANCE_API_SECRET")
        if not key or not secret:
            raise RuntimeError("defina BINANCE_API_KEY e BINANCE_API_SECRET no ambiente")
        opts = {"apiKey": key, "secret": secret, "enableRateLimit": True}
        self.spot = ccxt.binance(opts)
        self.fut = ccxt.binanceusdm(opts)
        if testnet:
            for ex in (self.spot, self.fut):
                try:
                    ex.set_sandbox_mode(True)
                except Exception:  # versões novas do ccxt usam "demo trading" para futuros
                    ex.enable_demo_trading(True)
        self.spot.load_markets()
        self.fut.load_markets()

    @staticmethod
    def _px(order, fallback):
        return float(order.get("average") or order.get("price") or fallback)

    def spot_buy(self, sleeve, asset, qty, price_hint):
        sym = f"{asset}/USDT"
        q = float(self.spot.amount_to_precision(sym, qty))
        o = self.spot.create_market_buy_order(sym, q)
        super().spot_buy(sleeve, asset, float(o.get("filled") or q), self._px(o, price_hint) / (1 + self.slip))

    def spot_sell(self, sleeve, asset, qty, price_hint):
        sym = f"{asset}/USDT"
        q = float(self.spot.amount_to_precision(sym, min(qty, self.spot_qty(sleeve, asset))))
        o = self.spot.create_market_sell_order(sym, q)
        super().spot_sell(sleeve, asset, float(o.get("filled") or q), self._px(o, price_hint) / (1 - self.slip))

    def perp_trade(self, sleeve, symbol, qty, price_hint, exact_price=False):
        sym = symbol.replace("USDT", "/USDT:USDT")
        q = float(self.fut.amount_to_precision(sym, abs(qty)))
        side = "buy" if qty > 0 else "sell"
        # Sem reduceOnly de propósito: 'breakout' (comprado) e 'carry' (vendido) usam o mesmo
        # perpétuo e, no modo One-way, a corretora mantém UMA posição líquida. Uma venda que
        # reduz a gaveta 'breakout' pode aumentar o vendido líquido — reduceOnly seria rejeitado.
        o = self.fut.create_order(sym, "market", side, q, None)
        filled = float(o.get("filled") or q) * (1 if qty > 0 else -1)
        super().perp_trade(sleeve, symbol, filled, self._px(o, price_hint), exact_price=True)

    def set_leverage(self, symbol, lev):
        self.fut.set_leverage(lev, symbol.replace("USDT", "/USDT:USDT"))

    def place_stop_buy(self, sleeve, symbol, qty, stop):
        sym = symbol.replace("USDT", "/USDT:USDT")
        q = float(self.fut.amount_to_precision(sym, qty))
        p = float(self.fut.price_to_precision(sym, stop))
        o = self.fut.create_order(sym, "STOP_MARKET", "buy", q, None, {"stopPrice": p, "workingType": "CONTRACT_PRICE"})
        self.state["meta"].setdefault("stops", {})[symbol] = o["id"]
        log.info("[LIVE] stop de compra %s qty=%s gatilho=%s id=%s", symbol, q, p, o["id"])

    def stop_filled(self, symbol):
        oid = self.state["meta"].get("stops", {}).get(symbol)
        if not oid:
            return None
        o = self.fut.fetch_order(oid, symbol.replace("USDT", "/USDT:USDT"))
        return o if o.get("status") == "closed" else None

    def cancel_stops(self, symbol):
        sym = symbol.replace("USDT", "/USDT:USDT")
        oid = self.state["meta"].get("stops", {}).pop(symbol, None)
        if oid:
            try:
                self.fut.cancel_order(oid, sym)
            except Exception as e:  # já executada ou expirada
                log.info("cancelamento de stop %s: %s", symbol, e)

    def transfer_to_futures(self, usdt):
        self.spot.transfer("USDT", usdt, "spot", "future")
