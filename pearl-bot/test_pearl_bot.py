"""Testes do pearl_bot (sem rede). Rode: python -m unittest -v test_pearl_bot"""
import os
import shutil
import subprocess
import tarfile
import tempfile
import time
import unittest
from unittest import mock

import pearl_bot as pb

MARKET = {"price": 1.5, "prl_per_th_day": 0.012, "usd_per_th_hour": 0.012 * 1.5 / 24}  # $0.00075/TH/h


def cfg(**kw):
    c = pb.load_config("/nao/existe.json")
    c.update(kw)
    return c


def offer(**kw):
    o = {"id": 1, "machine_id": 10, "gpu_name": "RTX 4090", "num_gpus": 1, "dph_total": 0.10,
         "min_bid": 0.05, "storage_total_cost": 0.002, "geolocation": "Texas, US",
         "reliability2": 0.99, "verification": "verified", "_type": "on-demand"}
    o.update(kw)
    return o


class FakeVast:
    def __init__(self, instances=(), offers=(), credit=50.0, balance=0.0):
        self._inst = list(instances)
        self._offers = list(offers)
        self.credit, self.balance = credit, balance
        self.created, self.destroyed = [], []

    def user(self):
        return {"credit": self.credit, "balance": self.balance}

    def instances(self):
        return self._inst

    def search(self, q):
        t = q["type"]
        return [dict(o) for o in self._offers if o["gpu_name"] == q["gpu_name"]["eq"] and o["_type"] == t]

    def create(self, oid, payload):
        self.created.append((oid, payload))
        return {"success": True, "new_contract": 1000 + oid}

    def destroy(self, iid):
        self.destroyed.append(iid)
        return {"success": True}


class TestEvaluate(unittest.TestCase):
    def test_on_demand(self):
        ev = pb.evaluate(offer(num_gpus=2, dph_total=0.30), cfg(), MARKET, {})
        self.assertAlmostEqual(ev["revenue"], 2 * 343.4 * 0.00075)
        self.assertAlmostEqual(ev["cost"], 0.30)
        self.assertIsNone(ev["bid"])

    def test_bid_uses_min_bid_plus_markup_and_storage(self):
        ev = pb.evaluate(offer(_type="bid", min_bid=0.20), cfg(bid_markup=0.10), MARKET, {})
        self.assertAlmostEqual(ev["bid"], 0.22)
        self.assertAlmostEqual(ev["cost"], 0.222)

    def test_learned_hashrate_wins(self):
        ev = pb.evaluate(offer(), cfg(), MARKET, {"RTX 4090": 100.0})
        self.assertAlmostEqual(ev["th"], 100.0)

    def test_unknown_gpu(self):
        self.assertIsNone(pb.evaluate(offer(gpu_name="GTX 9999"), cfg(), MARKET, {}))


class TestBestOffers(unittest.TestCase):
    def test_threshold_dedupe_blacklist_country(self):
        offers = [
            offer(id=1, machine_id=10, num_gpus=1, dph_total=0.10),   # lucro 0.158
            offer(id=2, machine_id=10, num_gpus=2, dph_total=0.20),   # lucro 0.315 (mesma maquina, melhor)
            offer(id=3, machine_id=11, dph_total=0.20),               # lucro 0.058 < 0.10
            offer(id=4, machine_id=12, dph_total=0.05),               # na lista negra
            offer(id=5, machine_id=13, dph_total=0.05, geolocation="Hubei, CN"),  # pais excluido
        ]
        st = {"blacklist": {"12": {}}}
        res = pb.best_offers(offers, cfg(exclude_countries=["cn"]), MARKET, st)
        self.assertEqual([e["id"] for e in res], [2])


class TestManage(unittest.TestCase):
    def inst(self, **kw):
        i = {"id": 7, "label": "pearlbot-vb1", "gpu_name": "RTX 4090", "num_gpus": 1, "machine_id": 10,
             "actual_status": "running", "intended_status": "running", "dph_total": 0.10,
             "start_date": time.time() - 10 * 60, "is_bid": False}
        i.update(kw)
        return i

    def run_manage(self, inst, workers, state=None):
        v = FakeVast()
        st = state if state is not None else {}
        keep = pb.manage_instance(v, inst, cfg(), MARKET, workers, st, live=True)
        return keep, v, st

    def test_young_loading_kept(self):
        keep, v, _ = self.run_manage(self.inst(actual_status="loading", start_date=time.time() - 5 * 60), {})
        self.assertTrue(keep)
        self.assertEqual(v.destroyed, [])

    def test_never_started_destroyed_and_blacklisted(self):
        keep, v, st = self.run_manage(self.inst(actual_status="created", start_date=time.time() - 30 * 60), {})
        self.assertFalse(keep)
        self.assertEqual(v.destroyed, [7])
        self.assertIn("10", st["blacklist"])

    def test_outbid_interruptible_destroyed_not_blacklisted(self):
        keep, v, st = self.run_manage(
            self.inst(actual_status="exited", is_bid=True, start_date=time.time() - 120 * 60), {"vb1": 340})
        self.assertFalse(keep)
        self.assertNotIn("blacklist", st)

    def test_low_hashrate_destroyed(self):
        keep, v, st = self.run_manage(self.inst(start_date=time.time() - 45 * 60), {"vb1": 50.0})
        self.assertFalse(keep)
        self.assertIn("10", st["blacklist"])

    def test_missing_worker_destroyed_after_check_time(self):
        keep, v, _ = self.run_manage(self.inst(start_date=time.time() - 45 * 60), {})
        self.assertFalse(keep)

    def test_unprofitable_destroyed(self):
        keep, v, st = self.run_manage(self.inst(dph_total=0.40, start_date=time.time() - 45 * 60), {"vb1": 340.0})
        self.assertFalse(keep)
        self.assertNotIn("blacklist", st)

    def test_good_kept_and_learns(self):
        keep, v, st = self.run_manage(self.inst(start_date=time.time() - 90 * 60), {"vb1": 300.0})
        self.assertTrue(keep)
        self.assertAlmostEqual(st["learned"]["RTX 4090"], 300.0)

    def test_simulation_never_destroys(self):
        v = FakeVast()
        pb.manage_instance(v, self.inst(dph_total=5.0), cfg(), MARKET, {}, {}, live=False)
        self.assertEqual(v.destroyed, [])


class TestCycle(unittest.TestCase):
    def run_cycle(self, fake, live=True, **kw):
        c = cfg(vast_api_key="k", wallet="prl1abc", **kw)
        with mock.patch.object(pb, "Vast", return_value=fake), \
                mock.patch.object(pb, "get_market", return_value=MARKET), \
                mock.patch.object(pb, "get_workers", return_value={}), \
                mock.patch.object(pb.time, "sleep"), \
                mock.patch.object(pb, "log"):
            pb.cycle(c, live, {})

    def test_rents_best_within_budget_and_limits(self):
        offers = [offer(id=i, machine_id=i, dph_total=0.10) for i in range(1, 8)]
        offers.append(offer(id=50, machine_id=50, gpu_name="H200 NVL", num_gpus=8, _type="bid",
                            min_bid=3.0, dph_total=3.0))  # lucro alto mas estoura o orcamento
        fake = FakeVast(offers=offers)
        self.run_cycle(fake, max_instances=3, max_spend_per_hour=2.0)
        self.assertEqual(len(fake.created), 3)
        oid, p = fake.created[0]
        self.assertTrue(p["label"].startswith("pearlbot-vb"))
        self.assertIn("prl-us.kryptex.network:8048", p["onstart"])
        self.assertIn("prl1abc/vb", p["onstart"])
        self.assertIsNone(p["price"])
        self.assertTrue(p["cancel_unavail"])

    def test_bid_offer_sends_price(self):
        fake = FakeVast(offers=[offer(id=9, machine_id=9, _type="bid", min_bid=0.10)])
        self.run_cycle(fake, allow_on_demand=False)
        self.assertAlmostEqual(fake.created[0][1]["price"], 0.105)

    def test_waits_for_deposit_below_min_credit(self):
        fake = FakeVast(offers=[offer()], credit=0.05)
        self.run_cycle(fake)
        self.assertEqual(fake.created, [])

    def test_negative_balance_waits(self):
        fake = FakeVast(offers=[offer()], credit=0, balance=-1.55)
        self.run_cycle(fake)
        self.assertEqual(fake.created, [])

    def test_small_bank_rents_cheap_machine(self):
        fake = FakeVast(offers=[offer(dph_total=0.10)], credit=0.30)  # precisa 0.10 + 0.10*(1+8/60)
        self.run_cycle(fake)
        self.assertEqual(len(fake.created), 1)

    def test_skips_machine_without_one_hour_of_runway(self):
        fake = FakeVast(offers=[offer(dph_total=0.10)], credit=0.20)
        self.run_cycle(fake)
        self.assertEqual(fake.created, [])

    def bot_inst(self, **kw):
        i = {"id": 7, "label": "pearlbot-vb1", "gpu_name": "H200 NVL", "num_gpus": 1, "machine_id": 10,
             "actual_status": "running", "intended_status": "running", "dph_total": 0.10,
             "start_date": time.time() - 10 * 60, "is_bid": False}
        i.update(kw)
        return i

    def test_kill_switch_destroys_all_before_limit(self):
        insts = [self.bot_inst(id=7, dph_total=0.45), self.bot_inst(id=8, dph_total=0.45)]
        other = {"id": 99, "label": "outra", "actual_status": "running", "start_date": time.time()}
        # maquinas com lucro, gastando $0.90/h; ate o proximo ciclo (8 min) ~$0.12 -> 0.20 - 0.12 < 0.10
        fake = FakeVast(instances=insts + [other], offers=[offer()], credit=0.20)
        self.run_cycle(fake)
        self.assertEqual(sorted(fake.destroyed), [7, 8])
        self.assertEqual(fake.created, [])

    def test_kill_switch_quiet_with_enough_credit(self):
        fake = FakeVast(instances=[self.bot_inst(dph_total=0.45)], credit=5.0)
        self.run_cycle(fake)
        self.assertEqual(fake.destroyed, [])

    def test_kill_switch_respects_simulation(self):
        fake = FakeVast(instances=[self.bot_inst(dph_total=0.45)], credit=0.12)
        self.run_cycle(fake, live=False)
        self.assertEqual(fake.destroyed, [])

    def test_ignores_instances_without_bot_label(self):
        other = {"id": 99, "label": "meu-treino", "actual_status": "exited", "start_date": 0}
        fake = FakeVast(instances=[other])
        self.run_cycle(fake)
        self.assertEqual(fake.destroyed, [])

    def test_dry_run_creates_nothing(self):
        fake = FakeVast(offers=[offer()])
        self.run_cycle(fake, live=False)
        self.assertEqual(fake.created, [])


class TestCredit(unittest.TestCase):
    def test_available_credit(self):
        self.assertAlmostEqual(pb.available_credit({"credit": 0, "balance": -1.55}), -1.55)
        self.assertAlmostEqual(pb.available_credit({"credit": 5.0, "balance": 0}), 5.0)
        self.assertAlmostEqual(pb.available_credit({"credit": 5.0, "balance": -1.5}), 3.5)
        self.assertAlmostEqual(pb.available_credit({"credit": 2.0, "balance": 10.0}), 2.0)


class TestPoolHost(unittest.TestCase):
    def test_regions(self):
        self.assertEqual(pb.pool_host("Hubei, CN"), "prl-hk.kryptex.network")
        self.assertEqual(pb.pool_host("Texas, US"), "prl-us.kryptex.network")
        self.assertEqual(pb.pool_host("Sao Paulo, BR"), "prl-br.kryptex.network")
        self.assertEqual(pb.pool_host("Czechia, CZ"), "prl-eu.kryptex.network")
        self.assertEqual(pb.pool_host("Vietnam, VN"), "prl-sg.kryptex.network")
        self.assertEqual(pb.pool_host(None), "prl.kryptex.network")

    def test_miner_choice(self):
        c = cfg()
        self.assertEqual(pb.miner_for("RTX 4090", c), "krig")
        self.assertEqual(pb.miner_for("H200 NVL", c), "peak")
        c["gpu_miner"] = {"RTX 4090": "srb"}
        self.assertEqual(pb.miner_for("RTX 4090", c), "srb")


@unittest.skipUnless(shutil.which("bash") and shutil.which("curl"), "precisa de bash e curl")
class TestOnstartScript(unittest.TestCase):
    """Roda o script de inicializacao de verdade, com mineradores falsos servidos por file://."""

    def setUp(self):
        self.d = tempfile.mkdtemp()

    def tearDown(self):
        subprocess.run(["pkill", "-f", self.d], check=False)
        shutil.rmtree(self.d, ignore_errors=True)

    def fake_tgz(self, filename, marker):
        pkg = os.path.join(self.d, "pkg_" + marker, "krig-miner-x")
        os.makedirs(pkg)
        with open(os.path.join(pkg, "krig-miner"), "w") as f:
            f.write('#!/bin/bash\necho "%s ARGS: $@" >> "%s/args.txt"\nsleep 1000\n' % (marker, self.d))
        os.chmod(os.path.join(pkg, "krig-miner"), 0o755)
        path = os.path.join(self.d, filename)
        with tarfile.open(path, "w:gz") as t:
            t.add(pkg, arcname="krig-miner-x")
        return "file://" + path

    def run_script(self, miner, use_latest=True):
        script = pb.onstart_script(miner, "prl1carteira", "vb123", "prl-us.kryptex.network", use_latest)
        script = script.replace("/root/", self.d + "/root_").replace("/opt/miner", self.d + "/opt_miner")
        subprocess.run(["bash", "-c", script], check=True, timeout=30)
        args_file = os.path.join(self.d, "args.txt")
        for _ in range(100):
            if os.path.exists(args_file):
                break
            time.sleep(0.1)
        with open(args_file) as f:
            return f.read()

    def api_json(self, urls):
        path = os.path.join(self.d, "latest.json")
        assets = ",\n".join('    {"name": "x", "browser_download_url": "%s"}' % u for u in urls)
        with open(path, "w") as f:
            f.write('{\n  "tag_name": "v9.9.9",\n  "assets": [\n%s\n  ]\n}\n' % assets)
        return "file://" + path

    def test_uses_latest_release(self):
        pinned = self.fake_tgz("krig-miner-1.0.0-linux-x64.tar.gz", "FIXA")
        hive = self.fake_tgz("krig-miner-9.9.9.hiveos.tar.gz", "HIVEOS")
        latest = self.fake_tgz("krig-miner-9.9.9-linux-x64.tar.gz", "NOVA")
        miner = dict(pb.DEFAULT_MINERS["krig"], urls=[pinned], latest_api=self.api_json([hive, latest]))
        got = self.run_script(miner)
        self.assertIn("NOVA ARGS: --url stratum+ssl://prl-us.kryptex.network:8048 --user prl1carteira/vb123", got)

    def test_falls_back_to_pinned_when_github_fails(self):
        pinned = self.fake_tgz("krig-miner-1.0.0-linux-x64.tar.gz", "FIXA")
        miner = dict(pb.DEFAULT_MINERS["krig"], urls=[pinned], latest_api="file:///nao/existe.json")
        self.assertIn("FIXA ARGS:", self.run_script(miner))

    def test_pinned_only_when_latest_disabled(self):
        pinned = self.fake_tgz("krig-miner-1.0.0-linux-x64.tar.gz", "FIXA")
        latest = self.fake_tgz("krig-miner-9.9.9-linux-x64.tar.gz", "NOVA")
        miner = dict(pb.DEFAULT_MINERS["krig"], urls=[pinned], latest_api=self.api_json([latest]))
        self.assertIn("FIXA ARGS:", self.run_script(miner, use_latest=False))

    def test_asset_patterns_match_real_release_names(self):
        import re
        names = {
            "krig": "https://github.com/kryptex/krig-miner/releases/download/v1.6.0/krig-miner-1.6.0-linux-x64.tar.gz",
            "peak": "https://github.com/peakminer/peakminer/releases/download/v2.20.7/peakminer-2.20.7.tar.gz",
            "srb": "https://github.com/doktor83/SRBMiner-Multi/releases/download/3.8.6/SRBMiner-Multi-3-8-6-Linux.tar.gz",
        }
        for k, url in names.items():
            self.assertTrue(re.search(pb.DEFAULT_MINERS[k]["asset"], url), k)
        self.assertFalse(re.search(pb.DEFAULT_MINERS["krig"]["asset"], "x/krig-miner-1.6.0.hiveos.tar.gz"))
        self.assertFalse(re.search(pb.DEFAULT_MINERS["peak"]["asset"], "x/peakminer-2.20.8rc1.tar.gz"))


if __name__ == "__main__":
    unittest.main()
