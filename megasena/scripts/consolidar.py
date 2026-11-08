"""Consolida o histórico da Mega-Sena a partir de fontes independentes e cruza os dados.

Uso: python3 consolidar.py <dir_fontes> <saida_csv>
"""
import csv
import json
import sys
from pathlib import Path

src = Path(sys.argv[1])
out = Path(sys.argv[2])

# Fonte A (com datas): victor-reghini/mega-sena-statistics
a = {x["c"]: (x["d"], sorted(x["n"])) for x in json.load(open(src / "victor-reghini_mega-sena-statistics/data/megasena.json"))}
# Fonte B: sosthenis/megasena-data
b = {x["concurso"]: sorted(int(n) for n in x["dezenas"]) for x in json.load(open(src / "sosthenis_megasena-data/megasena.json"))}
# Fonte C: GabrielRossiSoares/megasena
c = {r["concurso"]: (r["data"], sorted(r["dezenas"])) for r in json.load(open(src / "GabrielRossiSoares_megasena/data.json"))["results"]}
# Fonte D: edxgar48/rust_spider_dados
d = {k: (dt, sorted(n)) for k, dt, n in json.load(open(src / "edxgar48_rust_spider_dados/v1/megasena/historico.json"))["concursos"]}
# Fonte E (até 2797): guilhermeasn/loteria.json
e = {int(k): sorted(int(n) for n in v) for k, v in json.load(open(src / "raw/megasena.json")).items()}

ultimo = max(a)
assert sorted(a) == list(range(1, ultimo + 1)), "fonte A com lacunas"
divergencias = 0
for k in range(1, ultimo + 1):
    ref = a[k][1]
    outras = [b.get(k), c.get(k, (None, None))[1], d.get(k, (None, None))[1], e.get(k)]
    for o in outras:
        if o is not None and o != ref:
            divergencias += 1
            print("DIVERGÊNCIA", k, ref, o)
    if c.get(k) and c[k][0] != a[k][0]:
        print("DATA DIVERGENTE", k, a[k][0], c[k][0])

linhas = [(k, a[k][0], *a[k][1]) for k in range(1, ultimo + 1)]
# Concurso 3083 (08/11/2026): automatizadado/conferidor-mega-v2 + card loteriacampeao/cards-loteria
extra = {3083: ("08/11/2026", [22, 25, 29, 37, 46, 54])}
for k, (dt, n) in extra.items():
    if k not in a:
        linhas.append((k, dt, *sorted(n)))

with open(out, "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["concurso", "data", "d1", "d2", "d3", "d4", "d5", "d6"])
    w.writerows(linhas)
print(f"{len(linhas)} concursos gravados; divergências entre fontes: {divergencias}")
