"""Gera regioes_update.osm para abrir no JOSM, a partir do report.json.

Baixa a versão atual de cada relação pela API do OSM (com membros e versão),
corrige IBGE:GEOCODIGO quando necessário e adiciona a população do Censo 2022.
Uso: python -X utf8 make_josm.py
"""
import json
import urllib.request
import xml.etree.ElementTree as ET

# Relações com nome (e wikidata) de outra coisa: "Tuiuti" não é região, o código 350041 é Bragança Paulista
NOME_CORRETO = {"350041": "Região Geográfica Imediata de Bragança Paulista"}
WIKI_CORRETO = {"350041": {"wikidata": "Q48878780",
                           "wikipedia": "pt:Região Geográfica Imediata de Bragança Paulista"}}

rep = json.load(open("report.json", encoding="utf-8"))
rows = {r["osm_id"]: r for r in rep["rows"]}

print("População total (intermediárias):",
      sum(r["populacao"] for r in rep["rows"] if r["nivel"] == "intermediaria"))

out = ET.Element("osm", version="0.6", generator="br-regioes-ibge")
ids = sorted(rows)
mudou = {"codigo": 0, "pop": 0, "tipo": 0, "nome": 0}
for i in range(0, len(ids), 100):
    url = "https://api.openstreetmap.org/api/0.6/relations?relations=" + ",".join(map(str, ids[i:i + 100]))
    req = urllib.request.Request(url, headers={"User-Agent": "br-regioes-ibge-check/1.0"})
    root = ET.fromstring(urllib.request.urlopen(req).read())
    for rel in root.findall("relation"):
        r = rows[int(rel.get("id"))]
        tags = {t.get("k"): t for t in rel.findall("tag")}

        def put(k, v):
            if k in tags:
                if tags[k].get("v") == v:
                    return False
                tags[k].set("v", v)
            else:
                tags[k] = ET.SubElement(rel, "tag", k=k, v=v)
            return True

        def drop(k):
            if k in tags:
                rel.remove(tags.pop(k))
                return True
            return False

        changed = False
        if put("IBGE:GEOCODIGO", r["codigo"]):
            mudou["codigo"] += 1
            changed = True

        # Padrão: boundary=statistical + border_type, sem admin_level
        tipo = "intermediate" if r["nivel"] == "intermediaria" else "immediate"
        t = put("boundary", "statistical")
        t |= put("border_type", f"{tipo}_geographic_region")
        t |= drop("admin_level")
        if t:
            mudou["tipo"] += 1
            changed = True

        # Nome: "Região Geográfica Imediata/Intermediária de …"; mantém o resto do nome existente
        nome = tags["name"].get("v")
        if r["codigo"] in NOME_CORRETO:
            novo = NOME_CORRETO[r["codigo"]]
        elif nome.startswith("Região Imediata "):
            novo = "Região Geográfica Imediata " + nome[len("Região Imediata "):]
        elif nome.startswith("Região Intermediária "):
            novo = "Região Geográfica Intermediária " + nome[len("Região Intermediária "):]
        else:
            novo = nome
        if put("name", novo):
            mudou["nome"] += 1
            changed = True
        for k, v in WIKI_CORRETO.get(r["codigo"], {}).items():
            changed |= put(k, v)
        p = put("population", str(r["populacao"]))
        p |= put("population:date", "2022")
        p |= put("source:population", "IBGE - Censo Demográfico 2022")
        if p:
            mudou["pop"] += 1
        if changed or p:
            rel.set("action", "modify")
            out.append(rel)

ET.indent(out)
ET.ElementTree(out).write("regioes_update.osm", encoding="UTF-8", xml_declaration=True)
print(f"{len(out)} relações modificadas;", mudou)
