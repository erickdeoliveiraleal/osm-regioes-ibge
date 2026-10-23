"""Confere se o contorno de cada intermediária no OSM bate com a borda externa
das suas imediatas (vias usadas por uma só imediata da intermediária).

Uso: python -X utf8 check_contornos.py <pasta_dados>   (lê report.json e rgi.json; consulta a API do OSM)
Gera contornos.json com as diferenças.
"""
import json
import sys
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path

API = "https://api.openstreetmap.org/api/0.6/"
UA = {"User-Agent": "br-regioes-ibge-check/1.0"}


def fetch(kind, ids):
    out = {}
    ids = sorted(ids)
    for i in range(0, len(ids), 100):
        url = f"{API}{kind}s.json?{kind}s=" + ",".join(map(str, ids[i:i + 100]))
        for e in json.load(urllib.request.urlopen(urllib.request.Request(url, headers=UA)))["elements"]:
            out[e["id"]] = e
    return out


rep = json.load(open("report.json", encoding="utf-8"))
osm = {r["codigo"]: r["osm_id"] for r in rep["rows"]}
osm["3107"] = 21773077  # Barbacena, criada depois do report
rels = fetch("relation", osm.values())

filhas = defaultdict(list)
# Imediata -> intermediária pela API de localidades (mesmos dados usados no compare.py)
rgi = json.loads((Path(sys.argv[1]) / "rgi.json").read_text(encoding="utf-8"))
for r in rgi:
    filhas[str(r["regiao-intermediaria"]["id"])].append(str(r["id"]))

outer = lambda rid: [m["ref"] for m in rels[rid]["members"] if m["type"] == "way" and m["role"] == "outer"]
problemas = {}
for ci, imds in sorted(filhas.items()):
    uso = Counter(w for c in imds for w in outer(osm[c]))
    esperadas = {w for w, n in uso.items() if n == 1}
    atuais = set(outer(osm[ci]))
    if esperadas != atuais:
        problemas[ci] = {"osm_id": osm[ci], "nome": rels[osm[ci]]["tags"].get("name"),
                         "faltam": sorted(esperadas - atuais), "sobram": sorted(atuais - esperadas),
                         "esperadas": sorted(esperadas)}
        print(ci, osm[ci], rels[osm[ci]]["tags"].get("name"),
              f"faltam {len(esperadas - atuais)}, sobram {len(atuais - esperadas)}")
print(len(problemas), "intermediárias com contorno diferente de", len(filhas))
json.dump(problemas, open("contornos.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
