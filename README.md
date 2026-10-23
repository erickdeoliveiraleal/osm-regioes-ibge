# Regiões Geográficas do IBGE no OpenStreetMap

Scripts para conferir e corrigir no OSM as 133 Regiões Geográficas Intermediárias
e as 510 Imediatas do IBGE (divisão de 2017), e para recortar regiões de um
`.osm.pbf` e revisar o mapeamento no JOSM.

Nenhum script envia nada ao OSM: os que propõem correções geram arquivos `.osm`
para abrir, revisar e enviar pelo JOSM.

## Padrão de tags usado

```
type=boundary
boundary=statistical
border_type=immediate_geographic_region | intermediate_geographic_region
name=Região Geográfica Imediata de … | Região Geográfica Intermediária de …
IBGE:GEOCODIGO=<código de 6 ou 4 dígitos>
population=<Censo 2022>
population:date=2022
source:population=IBGE - Censo Demográfico 2022
```

A população de cada região é a soma da população residente dos seus municípios
no Censo 2022 (SIDRA, tabela 4709).

## Requisitos

- Python 3.10+ e `pip install openpyxl shapely`
- `curl`
- Para os recortes: Docker (o osmium-tool roda num contêiner Debian)

## Auditoria das regiões

Os scripts leem e gravam na pasta atual (`report.json`, `contornos.json`).

```bash
sh baixar_dados.sh dados                     # IBGE, SIDRA e Overpass
python -X utf8 compare.py dados              # report.md e report.json
```

| Script | O que faz |
|---|---|
| `compare.py dados` | Compara IBGE x OSM: regiões faltando, código IBGE errado (casa pelo nome), duplicadas, tags e nomes fora do padrão. Gera `report.md` e `report.json`. |
| `make_josm.py` | Gera `regioes_update.osm`: corrige `IBGE:GEOCODIGO`, aplica o padrão de tags e nome e adiciona a população. |
| `make_sheet.py dados` | Gera `regioes_geograficas.xlsx` com abas Imediatas e Intermediárias, nomes com link para a relação no OSM. |
| `check_contornos.py dados` | Confere se o contorno de cada intermediária é a borda externa das suas imediatas (vias usadas por uma só imediata). Gera `contornos.json`. |
| `fix_contorno.py <codigo>` | Gera `contorno_<codigo>.osm` trocando os membros `outer` da intermediária pela borda calculada. Mantém `inner`. |
| `valida_geometria.py [--overpass] <relation_id> …` | Valida a geometria como o validador do JOSM: anéis fechados, anéis que se tocam, polígonos válidos, outer sobrepostos, inner fora do outer. `--overpass` baixa pelo Overpass em vez da API do OSM, que limita o volume de download. |
| `make_barbacena.py <pasta>` | Exemplo de criação de uma intermediária que faltava a partir das suas imediatas (usado para a de Barbacena, 3107). |

## Recortar regiões para revisar no JOSM

```bash
cd recortes
docker build -t osmium-tool .
curl -L -o brazil-latest.osm.pbf https://download.geofabrik.de/south-america/brazil-latest.osm.pbf
python -X utf8 recorta.py brazil-latest.osm.pbf 310037 310038 310039
python -X utf8 recorta.py brazil-latest.osm.pbf 310037 --ruas
```

Os recortes saem em `saida/<codigo>_<nome>.osm.pbf`, ao lado do `.pbf`, com o
contorno da região incluído. `--ruas` gera também `…ruas.osm.pbf` só com as vias
`highway=*`. A região é encontrada pelo `IBGE:GEOCODIGO`, então funciona com
qualquer código de região (ou município) que tenha relação no OSM.

O extrato da Geofabrik é atualizado uma vez por dia e vem sem usuário e
changeset (mantém versão e data). Antes de editar no JOSM, use
*Arquivo → Atualizar dados* para evitar conflitos.

### Alternativa sem `.pbf`: Overpass direto no JOSM

Em *Arquivo → Baixar dados → Baixar do Overpass API* (modo avançado), cole a
consulta abaixo trocando `10570191` pelo id da relação da região (no exemplo,
a Região Geográfica Imediata de Barreiros - Sirinhaém):

```
[out:xml][timeout:600];
rel(10570191);
map_to_area->.regiao;
(
  way(area.regiao);
);
(._;>;);
out meta;
```

- `map_to_area` transforma a relação numa área; `way(area.regiao)` pega todas
  as vias dentro dela (as que cruzam a borda vêm inteiras).
- `(._;>;)` inclui os nós das vias e `out meta` traz versão e autor, o que
  permite editar e enviar pelo JOSM.
- Para incluir pontos e relações, troque `way(area.regiao);` por
  `nwr(area.regiao);`. Para só as ruas, use `way[highway](area.regiao);`.
- Em regiões grandes (São Paulo, Rio de Janeiro, Belo Horizonte) a consulta
  pode estourar o tempo ou pesar no JOSM: baixe por município ou filtre por
  tipo de via.
