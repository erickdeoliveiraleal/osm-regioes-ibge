"""Recorta regiões geográficas imediatas (ou intermediárias) de um .osm.pbf
para abrir no JOSM. Roda o osmium-tool no Docker (imagem "osmium-tool",
feita a partir do Dockerfile desta pasta).

Uso:
  python -X utf8 recorta.py <arquivo.osm.pbf> <regiao> [<regiao> ...] [--osm] [--ruas]

  <regiao>  código IBGE (ex.: 310037) ou id de relação do OSM com "r" na frente
            (ex.: r12907541)
  --osm     trata os números sem "r" como ids de relação do OSM (para colar a
            coluna "Relação OSM" da planilha)
  --ruas    gera também, em saida/ruas/, um arquivo só com as vias highway=*
            (e os nós delas), mais o contorno da região

Exemplos:
  python -X utf8 recorta.py brazil-latest.osm.pbf 310037 310038 310039
  python -X utf8 recorta.py brazil-latest.osm.pbf r12907541 r12907534
  python -X utf8 recorta.py brazil-latest.osm.pbf --osm 12907541 12907534 --ruas

Os recortes saem em saida/<codigo>_<nome>.osm.pbf (pedido por código IBGE) ou
saida/r<id>_<nome>.osm.pbf (pedido por id), ao lado do .pbf de entrada.
Polígonos (.geojson) e arquivos intermediários ficam em saida/aux/.
As regiões são recortadas em lotes de 5 por leitura do .pbf, para caber na
memória do Docker.
"""
import json
import re
import subprocess
import sys
import unicodedata
from pathlib import Path

args = [a for a in sys.argv[1:] if not a.startswith("--")]
so_ruas = "--ruas" in sys.argv
ids_osm = "--osm" in sys.argv
LOTE = 5  # regiões por leitura do .pbf (limite de memória do Docker)
if len(args) < 2:
    sys.exit(__doc__)
pbf = Path(args[0]).resolve()
pasta = pbf.parent

# Cada região pedida vira ("cod", "310037") ou ("rel", "12907541")
pedidos = []
for a in args[1:]:
    if re.fullmatch(r"[rR]\d+", a):
        pedidos.append(("rel", a[1:]))
    elif re.fullmatch(r"\d+", a):
        pedidos.append(("rel" if ids_osm else "cod", a))
    else:
        print(f"{a}: ignorado (use um código IBGE ou r<id da relação>)")
codigos = [v for t, v in pedidos if t == "cod"]
relacoes = [v for t, v in pedidos if t == "rel"]


def osmium(*params):
    """Roda o osmium no Docker com a pasta do .pbf montada em /dados."""
    cmd = ["docker", "run", "--rm", "-v", f"{pasta}:/dados", "osmium-tool", *params]
    subprocess.run(cmd, check=True)


def slug(texto):
    texto = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return re.sub(r"[^A-Za-z0-9]+", "_", texto).strip("_")


# 1. Contornos das regiões pedidas: por IBGE:GEOCODIGO (não depende de
# boundary/border_type, que podem estar desatualizados no .pbf) e/ou por id
saida = pasta / "saida"
aux = saida / "aux"  # polígonos e arquivos intermediários; em saida/ ficam só os recortes
aux.mkdir(parents=True, exist_ok=True)
print("Separando os contornos das regiões...")
partes = []
if codigos:
    osmium("tags-filter", pbf.name, "r/IBGE:GEOCODIGO=" + ",".join(codigos),
           "-o", "saida/aux/contornos_cod.osm.pbf", "--overwrite")
    partes.append("saida/aux/contornos_cod.osm.pbf")
if relacoes:
    osmium("getid", "-r", pbf.name, *[f"r{r}" for r in relacoes],
           "-o", "saida/aux/contornos_rel.osm.pbf", "--overwrite")
    partes.append("saida/aux/contornos_rel.osm.pbf")
osmium("merge", *partes, "-o", "saida/aux/contornos.osm.pbf", "--overwrite")
osmium("export", "saida/aux/contornos.osm.pbf", "-o", "saida/aux/contornos.geojson", "--overwrite",
       "--geometry-types=polygon", "-a", "type,id")

por_codigo, por_relacao = {}, {}
for f in json.loads((aux / "contornos.geojson").read_text(encoding="utf-8"))["features"]:
    p = f["properties"]
    if p.get("@type") != "relation":
        continue
    por_relacao[str(p["@id"])] = f
    if p.get("IBGE:GEOCODIGO"):
        por_codigo[p["IBGE:GEOCODIGO"]] = f

# 2. Um polígono GeoJSON por região pedida e um arquivo de configuração do extract
extracts = []
relacao_do_recorte = {}
for tipo, valor in pedidos:
    f = (por_codigo if tipo == "cod" else por_relacao).get(valor)
    if f is None:
        rotulo = valor if tipo == "cod" else f"r{valor}"
        print(f"{rotulo}: não encontrado no .pbf (código/id errado ou contorno inválido)")
        continue
    p = f["properties"]
    nome = re.sub(r"^Regi[aã]o (Geogr[aá]fica )?\w+ d[eoa]s? ", "", p.get("name", ""))
    # Pedido por id usa r<id> no nome: o IBGE:GEOCODIGO do .pbf pode estar desatualizado
    base = f"{valor if tipo == 'cod' else 'r' + valor}_{slug(nome)}"
    poligono = aux / f"{base}.geojson"
    poligono.write_text(json.dumps({"type": "FeatureCollection", "features": [f]}), encoding="utf-8")
    extracts.append({"output": f"{base}.osm.pbf",
                     "polygon": {"file_name": poligono.name, "file_type": "geojson"}})  # relativo ao config.json
    relacao_do_recorte[f"{base}.osm.pbf"] = str(p["@id"])
if not extracts:
    sys.exit("nenhuma região para recortar")

# 3. Recorte em lotes: cada região do lote ocupa ~1 GB de memória no osmium
# ao ler o Brasil inteiro, então várias regiões numa leitura só estouram o Docker
config = aux / "config.json"
lotes = [extracts[i:i + LOTE] for i in range(0, len(extracts), LOTE)]
for n, lote in enumerate(lotes, 1):
    print(f"Recortando {len(lote)} região(ões), lote {n} de {len(lotes)}...")
    config.write_text(json.dumps({"directory": "saida", "extracts": lote}, indent=1), encoding="utf-8")
    osmium("extract", "-c", "saida/aux/config.json", "-s", "complete_ways", "--overwrite", pbf.name)

# 4. Opcional: só as ruas, mais a relação do contorno com suas vias e nós
arquivos = [e["output"] for e in extracts]
if so_ruas:
    (saida / "ruas").mkdir(exist_ok=True)
    for e in extracts:
        ruas = "ruas/" + e["output"].replace(".osm.pbf", ".ruas.osm.pbf")
        osmium("tags-filter", f"saida/{e['output']}", "w/highway", "-o", "saida/aux/_ruas.osm.pbf", "--overwrite")
        osmium("getid", "-r", f"saida/{e['output']}", f"r{relacao_do_recorte[e['output']]}", "-o", "saida/aux/_contorno.osm.pbf",
               "--overwrite")
        osmium("merge", "saida/aux/_ruas.osm.pbf", "saida/aux/_contorno.osm.pbf", "-o", f"saida/{ruas}", "--overwrite")
        arquivos.append(ruas)
    for tmp in ("_ruas.osm.pbf", "_contorno.osm.pbf"):
        (aux / tmp).unlink(missing_ok=True)

for nome in arquivos:
    arq = saida / nome
    print(f"{arq}  ({arq.stat().st_size / 1e6:.1f} MB)")
