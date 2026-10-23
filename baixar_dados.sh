#!/bin/sh
# Baixa os dados de entrada do compare.py para a pasta indicada (padrão: dados/).
# IBGE: lista de regiões e municípios; SIDRA: população do Censo 2022;
# Overpass: relações das regiões no OSM.
set -e
D="${1:-dados}"
mkdir -p "$D"
UA="osm-regioes-ibge/1.0"

curl -sf -o "$D/rgint.json" "https://servicodados.ibge.gov.br/api/v1/localidades/regioes-intermediarias"
curl -sf -o "$D/rgi.json" "https://servicodados.ibge.gov.br/api/v1/localidades/regioes-imediatas"
curl -sf -o "$D/mun.json" "https://servicodados.ibge.gov.br/api/v1/localidades/municipios?view=nivelado"
curl -sf -o "$D/pop.json" "https://apisidra.ibge.gov.br/values/t/4709/n6/all/v/93/p/all"

curl -sf -A "$UA" -o "$D/osm.json" --data-urlencode 'data=[out:json][timeout:300];
area["ISO3166-1"="BR"][admin_level=2]->.br;
(
  rel(area.br)["name"~"^Região Geográfica (Intermediária|Imediata)"];
  rel(area.br)[border_type~"^(immediate|intermediate)_geographic_region$"];
  rel(area.br)["IBGE:GEOCODIGO"~"^([0-9]{4}|[0-9]{6})$"];
);
out tags meta;' https://overpass-api.de/api/interpreter

echo "Dados em $D/"
