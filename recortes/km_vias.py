"""Compara a extensão (km) de vias highway=* por região entre duas pastas de
recortes gerados pelo recorta.py --ruas (ex.: de datas diferentes).

Uso:
  python -X utf8 km_vias.py <pasta_saida_antiga> <pasta_saida_nova> [--csv arquivo.csv]

Cada pasta é uma "saida" do recorta.py: lê ruas/<regiao>.ruas.osm.pbf e o
contorno aux/<regiao>.geojson. As vias são cortadas no contorno da região
(trechos que passam da borda não contam) e medidas na esfera (haversine).
Pistas duplas mapeadas como duas vias contam duas vezes, como no OSM.
"""
import csv
import json
import math
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

from shapely.geometry import shape
from shapely.prepared import prep

args = [a for a in sys.argv[1:] if not a.startswith("--")]
if len(args) < 2:
    sys.exit(__doc__)
antiga, nova = Path(args[0]).resolve(), Path(args[1]).resolve()
saida_csv = sys.argv[sys.argv.index("--csv") + 1] if "--csv" in sys.argv else None
# Monta no Docker o ancestral comum das duas pastas
comum = Path(*[a for a, b in zip(antiga.parts, nova.parts) if a == b] or [antiga.anchor])


def osmium(*params):
    cmd = ["docker", "run", "--rm", "-v", f"{comum}:/dados", "osmium-tool", *params]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL)


def km(coords):
    """Comprimento de uma linha (lon, lat) em km, pela fórmula de haversine."""
    total = 0.0
    for (lon1, lat1), (lon2, lat2) in zip(coords, coords[1:]):
        p1, p2 = math.radians(lat1), math.radians(lat2)
        dp, dl = p2 - p1, math.radians(lon2 - lon1)
        a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
        total += 2 * 6371.0088 * math.asin(math.sqrt(a))
    return total


def linhas(geom):
    if geom.is_empty:
        return []
    if geom.geom_type == "LineString":
        return [list(geom.coords)]
    if hasattr(geom, "geoms"):
        return [c for g in geom.geoms for c in linhas(g)]
    return []


def km_por_tipo(pasta, base):
    """km por valor de highway dentro do contorno da região."""
    pbf = pasta / "ruas" / f"{base}.ruas.osm.pbf"
    poligono = pasta / "aux" / f"{base}.geojson"
    if not pbf.exists() or not poligono.exists():
        return None
    geo = pasta / "aux" / f"{base}.ruas.geojsonseq"
    rel = lambda p: p.relative_to(comum).as_posix()
    osmium("export", rel(pbf), "-f", "geojsonseq", "-o", rel(geo), "--overwrite",
           "--geometry-types=linestring")
    area = shape(json.loads(poligono.read_text(encoding="utf-8"))["features"][0]["geometry"])
    dentro = prep(area)
    tipos = defaultdict(float)
    for linha in geo.read_text(encoding="utf-8").splitlines():
        linha = linha.lstrip("\x1e").strip()
        if not linha:
            continue
        f = json.loads(linha)
        tipo = f["properties"].get("highway")
        if not tipo:
            continue
        g = shape(f["geometry"])
        if not dentro.intersects(g):
            continue
        if not dentro.contains(g):
            g = g.intersection(area)
        tipos[tipo] += sum(km(c) for c in linhas(g))
    geo.unlink()
    return tipos


bases = sorted({p.name.removesuffix(".ruas.osm.pbf") for p in (nova / "ruas").glob("*.ruas.osm.pbf")}
               | {p.name.removesuffix(".ruas.osm.pbf") for p in (antiga / "ruas").glob("*.ruas.osm.pbf")})
linhas_csv = []
total_tipo = defaultdict(lambda: [0.0, 0.0])
print(f"{'Região':42} {'antes km':>10} {'depois km':>10} {'dif km':>9} {'dif %':>7}")
for base in bases:
    a, d = km_por_tipo(antiga, base), km_por_tipo(nova, base)
    ta = sum(a.values()) if a is not None else float("nan")
    td = sum(d.values()) if d is not None else float("nan")
    pct = (td - ta) / ta * 100 if ta else float("nan")
    print(f"{base:42} {ta:10.1f} {td:10.1f} {td - ta:+9.1f} {pct:+6.1f}%")
    for tipo in sorted(set(a or {}) | set(d or {})):
        va, vd = (a or {}).get(tipo, 0.0), (d or {}).get(tipo, 0.0)
        total_tipo[tipo][0] += va
        total_tipo[tipo][1] += vd
        linhas_csv.append([base, tipo, round(va, 3), round(vd, 3), round(vd - va, 3)])

print(f"\n{'Tipo (todas as regiões)':42} {'antes km':>10} {'depois km':>10} {'dif km':>9}")
for tipo, (va, vd) in sorted(total_tipo.items(), key=lambda kv: -kv[1][1]):
    if abs(vd) >= 0.05 or abs(va) >= 0.05:
        print(f"{tipo:42} {va:10.1f} {vd:10.1f} {vd - va:+9.1f}")
ta = sum(v[0] for v in total_tipo.values())
td = sum(v[1] for v in total_tipo.values())
print(f"{'TOTAL':42} {ta:10.1f} {td:10.1f} {td - ta:+9.1f}")

if saida_csv:
    with open(saida_csv, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["regiao", "highway", "km_antes", "km_depois", "dif_km"])
        w.writerows(linhas_csv)
    print(f"\nDetalhe por região e tipo: {saida_csv}")
