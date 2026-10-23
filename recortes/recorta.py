"""Recorta regiões geográficas imediatas (ou intermediárias) de um .osm.pbf
para abrir no JOSM. Roda o osmium-tool no Docker (imagem "osmium-tool",
feita a partir do Dockerfile desta pasta).

Uso:
  python -X utf8 recorta.py <arquivo.osm.pbf> <codigo_ibge> [<codigo_ibge> ...] [--ruas]

  --ruas   mantém só as vias com highway=* (e os nós delas), mais o contorno da região

Exemplo:
  python -X utf8 recorta.py brazil-latest.osm.pbf 310037 310038 310039

Os recortes saem em saida/<codigo>_<nome>.osm.pbf, ao lado do .pbf de entrada.
O contorno das regiões vem do próprio .pbf: a relação com o IBGE:GEOCODIGO pedido.
"""
import json
import re
import subprocess
import sys
import unicodedata
from pathlib import Path

args = [a for a in sys.argv[1:] if not a.startswith("--")]
so_ruas = "--ruas" in sys.argv
if len(args) < 2:
    sys.exit(__doc__)
pbf = Path(args[0]).resolve()
codigos = args[1:]
pasta = pbf.parent


def osmium(*params):
    """Roda o osmium no Docker com a pasta do .pbf montada em /dados."""
    cmd = ["docker", "run", "--rm", "-v", f"{pasta}:/dados", "osmium-tool", *params]
    subprocess.run(cmd, check=True)


def slug(texto):
    texto = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return re.sub(r"[^A-Za-z0-9]+", "_", texto).strip("_")


# 1. Contornos das regiões pedidas, achadas pelo IBGE:GEOCODIGO (não depende de
# boundary/border_type, que podem estar desatualizados no .pbf)
saida = pasta / "saida"
saida.mkdir(exist_ok=True)
print("Separando os contornos das regiões...")
osmium("tags-filter", pbf.name, "r/IBGE:GEOCODIGO=" + ",".join(codigos),
       "-o", "saida/contornos.osm.pbf", "--overwrite")
osmium("export", "saida/contornos.osm.pbf", "-o", "saida/contornos.geojson", "--overwrite",
       "--geometry-types=polygon")

regioes = {}
for f in json.loads((saida / "contornos.geojson").read_text(encoding="utf-8"))["features"]:
    regioes[f["properties"].get("IBGE:GEOCODIGO")] = f

# 2. Um polígono GeoJSON por região pedida e um arquivo de configuração do extract
extracts = []
for cod in codigos:
    if cod not in regioes:
        print(f"{cod}: não encontrado no .pbf (código errado ou contorno inválido)")
        continue
    nome = re.sub(r"^Regi[aã]o (Geogr[aá]fica )?\w+ d[eoa]s? ", "", regioes[cod]["properties"].get("name", ""))
    base = f"{cod}_{slug(nome)}"
    poligono = saida / f"{base}.geojson"
    poligono.write_text(json.dumps({"type": "FeatureCollection", "features": [regioes[cod]]}),
                        encoding="utf-8")
    extracts.append({"output": f"{base}.osm.pbf",
                     "polygon": {"file_name": poligono.name, "file_type": "geojson"}})  # relativo ao config.json
if not extracts:
    sys.exit("nenhuma região para recortar")

config = saida / "config.json"
config.write_text(json.dumps({"directory": "saida", "extracts": extracts}, indent=1), encoding="utf-8")

# 3. Recorte de todas as regiões numa única leitura do .pbf
print(f"Recortando {len(extracts)} região(ões)...")
osmium("extract", "-c", "saida/config.json", "-s", "complete_ways", "--overwrite", pbf.name)

# 4. Opcional: só as ruas
if so_ruas:
    for e in extracts:
        ruas = e["output"].replace(".osm.pbf", ".ruas.osm.pbf")
        cod = e["output"].split("_", 1)[0]
        # O tags-filter traz junto as vias e nós da relação do contorno
        osmium("tags-filter", f"saida/{e['output']}", "w/highway", f"r/IBGE:GEOCODIGO={cod}",
               "-o", f"saida/{ruas}", "--overwrite")
        e["output"] = ruas

for e in extracts:
    arq = saida / e["output"]
    print(f"{arq}  ({arq.stat().st_size / 1e6:.1f} MB)")
