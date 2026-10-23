"""Gera contorno_<codigo>.osm: a relação da intermediária com os membros trocados
pela borda externa das suas imediatas (calculada pelo check_contornos.py).

Uso: python -X utf8 fix_contorno.py <codigo_ibge>   (lê contornos.json)
"""
import json
import sys
import urllib.request
import xml.etree.ElementTree as ET
from collections import Counter

API = "https://api.openstreetmap.org/api/0.6/"
UA = {"User-Agent": "br-regioes-ibge-check/1.0"}
get = lambda url: urllib.request.urlopen(urllib.request.Request(API + url, headers=UA)).read()

codigo = sys.argv[1]
p = json.load(open("contornos.json", encoding="utf-8"))[codigo]
esperadas = p["esperadas"]

# Confere se a nova borda fecha (pontas de via aparecem um número par de vezes)
pontas = Counter()
for i in range(0, len(esperadas), 100):
    for e in json.loads(get("ways.json?ways=" + ",".join(map(str, esperadas[i:i + 100]))))["elements"]:
        pontas.update([e["nodes"][0], e["nodes"][-1]])
abertas = [n for n, c in pontas.items() if c % 2]
print(f"{p['nome']}: {len(esperadas)} vias, pontas soltas: {len(abertas)}")
if abertas:
    sys.exit("contorno não fecha: " + ", ".join(map(str, abertas[:10])))

root = ET.fromstring(get(f"relation/{p['osm_id']}"))
rel = root.find("relation")
# Troca só os membros outer; inner (lagos etc.) ficam como estão
for m in rel.findall("member"):
    if m.get("role") == "outer":
        rel.remove(m)
inner = rel.findall("member")
for m in inner:
    rel.remove(m)
tags = rel.findall("tag")
for t in tags:
    rel.remove(t)
for w in esperadas:
    ET.SubElement(rel, "member", type="way", ref=str(w), role="outer")
for m in inner:
    rel.append(m)
for t in tags:
    rel.append(t)
rel.set("action", "modify")
ET.indent(root)
ET.ElementTree(root).write(f"contorno_{codigo}.osm", encoding="UTF-8", xml_declaration=True)
print(f"contorno_{codigo}.osm: versão {rel.get('version')}, {len(esperadas)} outer, {len(inner)} outros")

# Vias que saem da relação e ficam sem uso (sem tags e sem outra relação)
orfas = []
for w in p["sobram"]:
    tags_w = json.loads(get(f"way/{w}.json"))["elements"][0].get("tags", {})
    pais = json.loads(get(f"way/{w}/relations.json"))["elements"]
    if not tags_w and [r["id"] for r in pais] == [p["osm_id"]]:
        orfas.append(w)
if orfas:
    print("  vias que ficam órfãs (apagar no JOSM):", ", ".join(map(str, orfas)))
