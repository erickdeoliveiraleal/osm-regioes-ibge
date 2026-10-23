"""Gera barbacena_intermediaria.osm: relação nova da Região Geográfica Intermediária
de Barbacena (3107), com o contorno externo das suas 3 regiões imediatas.

Uso: python -X utf8 make_barbacena.py <pasta com 12907541.osm, 12907534.osm, 12907494.osm>
(cada arquivo é o /relation/<id>/full da API do OSM)
"""
import json
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

IMEDIATAS = [12907541, 12907534, 12907494]  # Barbacena, Conselheiro Lafaiete, São João del Rei
d = Path(sys.argv[1])

ways, nodes, uso = {}, {}, Counter()
for rid in IMEDIATAS:
    root = ET.parse(d / f"{rid}.osm").getroot()
    for n in root.findall("node"):
        nodes[n.get("id")] = n
    for w in root.findall("way"):
        ways[w.get("id")] = w
    rel = root.find(f"relation[@id='{rid}']")
    uso.update(m.get("ref") for m in rel.findall("member") if m.get("type") == "way" and m.get("role") == "outer")

# Vias usadas por uma só imediata formam a borda externa; as compartilhadas são divisas internas
externas = sorted(w for w, c in uso.items() if c == 1)
internas = [w for w, c in uso.items() if c > 1]

# Confere se a borda fecha: todo nó de ponta de via deve aparecer um número par de vezes
pontas = Counter()
for w in externas:
    nd = [n.get("ref") for n in ways[w].findall("nd")]
    pontas.update([nd[0], nd[-1]])
abertas = [n for n, c in pontas.items() if c % 2]
print(f"{len(externas)} vias externas, {len(internas)} internas, pontas soltas: {len(abertas)}")
if abertas:
    sys.exit("contorno não fecha: " + ", ".join(abertas[:10]))

# População do Censo 2022: soma das 3 imediatas, já calculada no report.json
rep = json.load(open("report.json", encoding="utf-8"))
pop = sum(r["populacao"] for r in rep["rows"] if r["osm_id"] in IMEDIATAS)

out = ET.Element("osm", version="0.6", generator="br-regioes-ibge")
usados = {nd.get("ref") for w in externas for nd in ways[w].findall("nd")}
for n in sorted(usados, key=int):
    out.append(nodes[n])
for w in externas:
    out.append(ways[w])
rel = ET.SubElement(out, "relation", id="-1", action="modify", visible="true")
for w in externas:
    ET.SubElement(rel, "member", type="way", ref=w, role="outer")
for k, v in {
    "type": "boundary",
    "boundary": "statistical",
    "border_type": "intermediate_geographic_region",
    "name": "Região Geográfica Intermediária de Barbacena",
    "IBGE:GEOCODIGO": "3107",
    "source": "IBGE",
    "wikidata": "Q65171418",
    "population": str(pop),
    "population:date": "2022",
    "source:population": "IBGE - Censo Demográfico 2022",
}.items():
    ET.SubElement(rel, "tag", k=k, v=v)

ET.indent(out)
ET.ElementTree(out).write("barbacena_intermediaria.osm", encoding="UTF-8", xml_declaration=True)
print("população:", pop)
