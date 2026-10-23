"""Compara as Regiões Geográficas Intermediárias e Imediatas do IBGE com o OSM.

Uso: python -X utf8 compare.py <pasta_dados>
A pasta deve conter rgint.json, rgi.json, mun.json (API de localidades do IBGE),
pop.json (SIDRA tabela 4709, Censo 2022) e osm.json (resultado do Overpass).
Gera report.md e report.json na pasta atual.
"""
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

d = Path(sys.argv[1])
load = lambda f: json.loads((d / f).read_text(encoding="utf-8"))

rgint = load("rgint.json")
rgi = load("rgi.json")
mun = load("mun.json")
pop_rows = load("pop.json")[1:]
osm = load("osm.json")["elements"]

pop_mun = {r["D1C"]: int(r["V"]) for r in pop_rows}

# População por região = soma da população dos municípios (Censo 2022)
pop = defaultdict(int)
mun_sem_pop = []
for m in mun:
    p = pop_mun.get(str(m["municipio-id"]))
    if p is None:
        mun_sem_pop.append(m)
        continue
    pop[str(m["regiao-imediata-id"])] += p
    pop[str(m["regiao-intermediaria-id"])] += p

ibge = {}
for r in rgint:
    ibge[str(r["id"])] = {
        "nivel": "intermediaria", "admin_level": "5", "nome": r["nome"],
        "uf": r["UF"]["sigla"],
        "nome_osm": f"Região Geográfica Intermediária de {r['nome']}",
    }
for r in rgi:
    ibge[str(r["id"])] = {
        "nivel": "imediata", "admin_level": "7", "nome": r["nome"],
        "uf": r["regiao-intermediaria"]["UF"]["sigla"],
        "nome_osm": f"Região Geográfica Imediata de {r['nome']}",
    }
for k, v in ibge.items():
    v["populacao"] = pop[k]

import unicodedata


def norm(s):
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"^regiao (geografica )?(intermediaria|imediata) d[eoa]s? ", "", s)
    s = re.sub(r"\s*[-?]\s*|\s+", " ", s)  # "A - B", "A-B" e o "?" corrompido do IBGE
    s = re.sub(r" d[eoa]s? ", " ", s)
    return s.strip()


uf_cod = {}
for m in mun:
    uf_cod[str(m["UF-id"])] = m["UF-sigla"]
by_name = defaultdict(list)
for k, v in ibge.items():
    by_name[(v["uf"], v["admin_level"], norm(v["nome"]))].append(k)

# Atribui cada relação a um código IBGE: pelo GEOCODIGO quando o nome bate,
# senão pelo nome dentro da mesma UF (estado inferido do prefixo do código no OSM)
osm_by_code = defaultdict(list)
codigo_errado = {}
for e in osm:
    t = e["tags"]
    c = t.get("IBGE:GEOCODIGO", "")
    lvl = t.get("admin_level") or ("5" if len(c) == 4 else "7")
    if c in ibge and norm(t.get("name", "")) == norm(ibge[c]["nome"]):
        osm_by_code[c].append(e)
        continue
    cand = []
    if t.get("name", "").startswith("Região"):  # evita casar distritos/municípios homônimos
        cand = by_name.get((uf_cod.get(c[:2]), lvl, norm(t.get("name", ""))), [])
        if not cand:  # UF do código também pode estar errada: aceita nome único no país
            cand = [k for (_, l, n), ks in by_name.items() if l == lvl and n == norm(t["name"]) for k in ks]
    if len(cand) == 1:
        osm_by_code[cand[0]].append(e)
        codigo_errado[e["id"]] = c
    elif c in ibge:
        osm_by_code[c].append(e)  # nome diferente, mas código válido: mantém
    else:
        osm_by_code["?" + c].append(e)


def nome_ok(osm_name, ib):
    return norm(osm_name) == norm(ib["nome"])


rows, faltando, duplicados = [], [], []
for code, ib in sorted(ibge.items(), key=lambda kv: (len(kv[0]), kv[0])):
    els = osm_by_code.get(code, [])
    if not els:
        faltando.append(code)
        continue
    if len(els) > 1:
        duplicados.append(code)
    for e in els:
        t = e["tags"]
        problemas = []
        if e["id"] in codigo_errado:
            problemas.append(f"IBGE:GEOCODIGO={codigo_errado[e['id']]} (correto {code})")
        if t.get("boundary") != "statistical":
            problemas.append(f"boundary={t.get('boundary')}")
        if "admin_level" in t:
            problemas.append(f"admin_level={t['admin_level']}")
        if not t.get("name", "").startswith("Região Geográfica "):
            problemas.append("nome fora do padrão")
        if not nome_ok(t.get("name", ""), ib):
            problemas.append("nome difere do IBGE")
        elif t.get("name") != ib["nome_osm"]:
            problemas.append("grafia levemente diferente")
        if "wikidata" not in t:
            problemas.append("sem wikidata")
        pop_osm = t.get("population")
        rows.append({
            "codigo": code, **ib, "osm_id": e["id"], "osm_name": t.get("name"),
            "osm_tags": t, "osm_population": pop_osm, "problemas": problemas,
            "precisa_pop": pop_osm != str(ib["populacao"]),
        })

extras = [e for c, els in osm_by_code.items() if c.startswith("?") for e in els]

Path("report.json").write_text(json.dumps({
    "rows": rows, "faltando": [{"codigo": c, **ibge[c]} for c in faltando],
    "duplicados": duplicados,
    "extras": [{"osm_id": e["id"], **e["tags"]} for e in extras],
    "mun_sem_pop": [{"id": m["municipio-id"], "nome": m["municipio-nome"], "uf": m["UF-sigla"]} for m in mun_sem_pop],
}, ensure_ascii=False, indent=1), encoding="utf-8")

n_int = sum(1 for v in ibge.values() if v["nivel"] == "intermediaria")
n_imd = len(ibge) - n_int
achados = {r["codigo"] for r in rows}
L = []
L.append("# Regiões Geográficas IBGE x OpenStreetMap\n")
L.append(f"- IBGE: {n_int} intermediárias, {n_imd} imediatas")
L.append(f"- OSM: {len(osm)} relações candidatas, {len(achados)} códigos IBGE encontrados")
L.append(f"- Faltando no OSM: {len(faltando)}")
L.append(f"- Códigos duplicados no OSM: {len(duplicados)}")
L.append(f"- Relações no OSM com código que não é do IBGE: {len(extras)}")
L.append(f"- Sem `population` ou com valor diferente do Censo 2022: {sum(r['precisa_pop'] for r in rows)}")
L.append(f"- Municípios sem dado no Censo 2022 (criados depois): " +
         ", ".join(f"{m['municipio-nome']}/{m['UF-sigla']}" for m in mun_sem_pop) + "\n")

if faltando:
    L.append("## Faltando no OSM\n\n| Código | Nível | UF | Nome |\n|---|---|---|---|")
    L += [f"| {c} | {ibge[c]['nivel']} | {ibge[c]['uf']} | {ibge[c]['nome']} |" for c in faltando]
    L.append("")
if duplicados:
    L.append("## Códigos duplicados\n\n| Código | Relações |\n|---|---|")
    L += [f"| {c} | " + ", ".join(f"r{e['id']}" for e in osm_by_code[c]) + " |" for c in duplicados]
    L.append("")
if extras:
    L.append("## Relações com código fora da lista do IBGE\n\n| Relação | Código | Nome |\n|---|---|---|")
    L += [f"| r{e['id']} | {e['tags'].get('IBGE:GEOCODIGO')} | {e['tags'].get('name')} |" for e in extras]
    L.append("")
IGN = ("sem wikidata", "grafia levemente diferente", "boundary=administrative", "nome fora do padrão") + tuple(f"admin_level={n}" for n in "57")
prob = [r for r in rows if any(p not in IGN for p in r["problemas"])]
if prob:
    L.append("## Problemas de tags (fora população, wikidata e grafia)\n\n| Relação | Código | UF | Nome no OSM | Nome IBGE | Problemas |\n|---|---|---|---|---|---|")
    L += [f"| r{r['osm_id']} | {r['codigo']} | {r['uf']} | {r['osm_name']} | {r['nome_osm']} | "
          + "; ".join(p for p in r["problemas"] if p not in IGN) + " |" for r in prob]
    L.append("")
sem_wd = [r for r in rows if "sem wikidata" in r["problemas"]]
L.append(f"## Sem wikidata ({len(sem_wd)})\n")
L.append(", ".join(f"r{r['osm_id']} ({r['nome']}/{r['uf']})" for r in sem_wd) + "\n")
Path("report.md").write_text("\n".join(L), encoding="utf-8")
print("\n".join(L[:9]))
