"""Valida a geometria de relações boundary como o validador do JOSM faria:
anéis fechados, nenhum nó onde mais de dois trechos se encontram,
polígonos válidos, outer sem sobreposição entre si e inner dentro de algum outer.

Uso: python -X utf8 valida_geometria.py [--overpass] <relation_id> [...]
"""
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict

from shapely.geometry import Polygon
from shapely.validation import explain_validity

UA = {"User-Agent": "br-regioes-ibge-check/1.0"}


def aneis(ways):
    """Junta vias pelas pontas em anéis; devolve (anéis, pontas soltas)."""
    pontas = defaultdict(list)
    for wid, nds in ways.items():
        pontas[nds[0]].append(wid)
        pontas[nds[-1]].append(wid)
    soltas = [n for n, ws in pontas.items() if len(ws) % 2]
    usadas, resultado = set(), []
    for wid, nds in ways.items():
        if wid in usadas:
            continue
        usadas.add(wid)
        anel = list(nds)
        while anel[0] != anel[-1]:
            prox = [w for w in pontas[anel[-1]] if w not in usadas]
            if not prox:
                break
            w = prox[0]
            usadas.add(w)
            seg = ways[w] if ways[w][0] == anel[-1] else ways[w][::-1]
            anel += seg[1:]
        resultado.append(anel)
    return resultado, soltas


# --overpass: baixa pelo Overpass em vez da API (que limita o volume de download)
overpass = "--overpass" in sys.argv
for rid in [a for a in sys.argv[1:] if a != "--overpass"]:
    if overpass:
        q = urllib.parse.urlencode({"data": f"[out:json][timeout:300];(rel({rid});>;);out;"}).encode()
        req = urllib.request.Request("https://overpass-api.de/api/interpreter", data=q, headers=UA)
    else:
        req = urllib.request.Request(f"https://api.openstreetmap.org/api/0.6/relation/{rid}/full.json", headers=UA)
    # Overpass e API às vezes respondem 429/502/504: tenta de novo com espera crescente
    for tentativa in range(5):
        try:
            els = json.load(urllib.request.urlopen(req, timeout=400))["elements"]
            break
        except (urllib.error.URLError, TimeoutError) as e:
            erro = e
            time.sleep(30 * (tentativa + 1))
    else:
        print(f"r{rid}: não foi possível baixar ({erro})", flush=True)
        continue
    nodes = {e["id"]: (e["lon"], e["lat"]) for e in els if e["type"] == "node"}
    ways = {e["id"]: e["nodes"] for e in els if e["type"] == "way"}
    rel = next(e for e in els if e["type"] == "relation" and e["id"] == int(rid))
    erros = []
    polys = {}
    for papel in ("outer", "inner"):
        ws = {m["ref"]: ways[m["ref"]] for m in rel["members"] if m["type"] == "way" and m["role"] == papel}
        rs, soltas = aneis(ws)
        if soltas:
            erros.append(f"{papel}: {len(soltas)} pontas soltas")
        # Nó onde 3+ pontas se encontram = anéis se tocando (aviso do JOSM)
        grau = defaultdict(int)
        for nds in ws.values():
            grau[nds[0]] += 1
            grau[nds[-1]] += 1
        toque = [n for n, g in grau.items() if g > 2]
        if toque:
            erros.append(f"{papel}: anéis se tocam em {len(toque)} nós, ex. n{toque[0]}")
        polys[papel] = []
        for a in rs:
            if a[0] != a[-1]:
                erros.append(f"{papel}: anel aberto")
                continue
            p = Polygon([nodes[n] for n in a])
            if not p.is_valid:
                erros.append(f"{papel}: anel inválido ({explain_validity(p)})")
            polys[papel].append(p)
    outs = polys["outer"]
    for i in range(len(outs)):
        for j in range(i + 1, len(outs)):
            if outs[i].is_valid and outs[j].is_valid and outs[i].intersection(outs[j]).area > 0:
                erros.append(f"outer {i} e {j} se sobrepõem")
    for p in polys["inner"]:
        if not any(o.contains(p) for o in outs):
            erros.append("inner fora de qualquer outer")
    nome = rel["tags"].get("name")
    print(f"r{rid} {nome}: {len(outs)} outer, {len(polys['inner'])} inner -> "
          + ("OK" if not erros else "; ".join(erros)), flush=True)
