#!/usr/bin/env python3
"""
Gera docs/assets/dados_mapa_df.js com a serie historica completa
dos focos de calor do DF (2015-2025), estatisticas anuais, poligonos reais
das 84 Unidades de Conservacao (SISDIA/IBRAM), faixas de amortecimento de 1.000 m
e geometrias dos 10 imoveis rurais reincidentes com mais focos (CAR)
para o componente Leaflet da Entrega 3.
"""

import csv
import json
import os
import zipfile
from collections import defaultdict

import numpy as np
import pyproj
import shapefile
import shapely
from shapely.geometry import mapping, shape
from shapely.validation import make_valid


def round_coords(obj, decimals=4):
    """Arredonda coordenadas geograficas para reduzir tamanho do JSON."""
    if isinstance(obj, float):
        return round(obj, decimals)
    if isinstance(obj, (list, tuple)):
        return [round_coords(x, decimals) for x in obj]
    if isinstance(obj, dict):
        return {k: round_coords(v, decimals) for k, v in obj.items()}
    return obj


def carregar_focos_e_estatisticas(csv_path):
    focos_ano = defaultdict(list)
    stats_ano = {}

    for a in range(2015, 2026):
        stats_ano[a] = {
            "total": 0,
            "seca": 0,
            "referencia": 0,
            "pct_seca": 0.0,
            "pct_referencia": 0.0,
        }

    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            ano = int(row["data_hora_evento"][:4])
            mes = int(row["data_hora_evento"][5:7])
            is_ref = 1 if row["is_satelite_referencia"] == "True" else 0
            is_seca = 1 if 5 <= mes <= 9 else 0
            lat = round(float(row["latitude"]), 3)
            lon = round(float(row["longitude"]), 3)

            focos_ano[ano].append([lat, lon, is_ref, is_seca, mes])
            s = stats_ano[ano]
            s["total"] += 1
            if is_seca:
                s["seca"] += 1
            if is_ref:
                s["referencia"] += 1

    for a, s in stats_ano.items():
        if s["total"] > 0:
            s["pct_seca"] = round((s["seca"] / s["total"]) * 100, 1)
            s["pct_referencia"] = round((s["referencia"] / s["total"]) * 100, 1)

    return focos_ano, stats_ano


def processar_unidades_conservacao(geojson_path):
    """
    Processa as 84 UCs oficiais do SISDIA/IBRAM:
    - Projeta para EPSG:31983 (metrico)
    - Simplifica geometria poligonal da UC (tolerancia 15 m)
    - Gera poligono exato de amortecimento de 1.000 m (buffer metrico simplificado a 25 m)
    - Reprojeta ambos para EPSG:4326 com coordenadas arredondadas
    """
    trans_to_m = pyproj.Transformer.from_crs("EPSG:4326", "EPSG:31983", always_xy=True)
    trans_to_geo = pyproj.Transformer.from_crs("EPSG:31983", "EPSG:4326", always_xy=True)

    with open(geojson_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    ucs_features = []
    buffers_features = []

    for feat in data["features"]:
        props = feat["properties"]
        geom_geo = shape(feat["geometry"])
        if not geom_geo.is_valid:
            geom_geo = make_valid(geom_geo)

        # Projecao metrica para calculo espacial acurado
        geom_m = shapely.transform(geom_geo, lambda c: np.column_stack(trans_to_m.transform(c[:, 0], c[:, 1])))
        geom_m_sim = geom_m.simplify(15.0, preserve_topology=True)

        # Faixa de amortecimento oficial de 1.000 m
        buf_m = geom_m_sim.buffer(1000.0)
        buf_m_sim = buf_m.simplify(25.0, preserve_topology=True)

        # Reprojecao de volta para WGS84
        geom_simp_geo = shapely.transform(geom_m_sim, lambda c: np.column_stack(trans_to_geo.transform(c[:, 0], c[:, 1])))
        buf_simp_geo = shapely.transform(buf_m_sim, lambda c: np.column_stack(trans_to_geo.transform(c[:, 0], c[:, 1])))

        uc_id = props.get("id") or props.get("objectid")
        nome = props.get("nome", "Unidade de Conservacao")
        sigla = props.get("sigla", "")
        uc_conserv = props.get("uc_conserv", "Espaco Protegido")
        area_ha = round(float(props.get("area_ha", 0)), 1)
        ano_criaca = props.get("ano_criaca", "")
        gestao = props.get("gestao", "Distrital (IBRAM)")

        ucs_features.append({
            "type": "Feature",
            "properties": {
                "id": uc_id,
                "nome": nome,
                "sigla": sigla,
                "uc_conserv": uc_conserv,
                "area_ha": area_ha,
                "ano_criaca": ano_criaca,
                "gestao": gestao,
            },
            "geometry": round_coords(mapping(geom_simp_geo), 4)
        })

        buffers_features.append({
            "type": "Feature",
            "properties": {
                "id": uc_id,
                "nome": nome,
            },
            "geometry": round_coords(mapping(buf_simp_geo), 4)
        })

    ucs_geojson = {"type": "FeatureCollection", "features": ucs_features}
    buffers_geojson = {"type": "FeatureCollection", "features": buffers_features}

    return ucs_geojson, buffers_geojson


def processar_imoveis_reincidentes(zip_path):
    """
    Processa os 10 imoveis com maior volume de focos reincidentes
    documentados na secao 12 da Entrega 3, extraindo seus poligonos reais do CAR.
    """
    target_info = {
        "DF-5300108-AB840D7B499B43E69C3D999165FF2475": {
            "situacao": "Cancelado (CA)",
            "area_ha": 94379.0,
            "anos": list(range(2015, 2026)),
            "focos": 3597,
            "rl": False,
            "app": True,
            "uc": True,
            "detalhe": "Imóvel cancelado de grande extensão territorial com 3.597 focos registrados em 11 anos contínuos, com sobreposição a APP e faixa de UC."
        },
        "DF-5300108-1274A9532343473DB7413440C0ABF8AD": {
            "situacao": "Cancelado (CA)",
            "area_ha": 103414.5,
            "anos": list(range(2015, 2026)),
            "focos": 3077,
            "rl": False,
            "app": True,
            "uc": True,
            "detalhe": "Cadastro cancelado com 3.077 focos de calor distribuídos ao longo de toda a série histórica em áreas de preservação permanente."
        },
        "DF-5300108-B46B13EE13B14D348E3124DD0F77D8B1": {
            "situacao": "Suspenso (SU)",
            "area_ha": 63232.2,
            "anos": list(range(2015, 2026)),
            "focos": 2623,
            "rl": False,
            "app": True,
            "uc": True,
            "detalhe": "Cadastro suspenso com 2.623 focos detectados em 11 anos, incidindo sobre APP e amortecimento de Unidade de Conservação."
        },
        "DF-5300108-0AA80F34AD524112AF32834A78277A32": {
            "situacao": "Pendente (PE)",
            "area_ha": 16398.0,
            "anos": list(range(2015, 2026)),
            "focos": 1370,
            "rl": False,
            "app": True,
            "uc": True,
            "detalhe": "Imóvel com análise pendente contendo 1.370 focos em 11 anos consecutivos, com presença de APP e proximidade com UC."
        },
        "DF-5300108-BB7A677A0ACB4496B63D413536F8DE0E": {
            "situacao": "Cancelado (CA)",
            "area_ha": 38793.5,
            "anos": list(range(2015, 2026)),
            "focos": 1332,
            "rl": False,
            "app": True,
            "uc": True,
            "detalhe": "Propriedade cancelada com 1.332 registros de queimadas entre 2015 e 2025 incidindo em faixas de proteção."
        },
        "DF-5300108-981FD2BCDD10433693BFCD3A6D69DD2E": {
            "situacao": "Pendente (PE)",
            "area_ha": 8441.2,
            "anos": list(range(2015, 2026)),
            "focos": 1010,
            "rl": False,
            "app": True,
            "uc": True,
            "detalhe": "Cadastro pendente com 1.010 focos em 11 anos contínuos, com sobreposição a APP e faixa de 1 km de amortecimento."
        },
        "DF-5300108-1A34898F66584106B176A816F4FDCD5E": {
            "situacao": "Pendente (PE)",
            "area_ha": 11582.8,
            "anos": list(range(2015, 2026)),
            "focos": 755,
            "rl": False,
            "app": True,
            "uc": True,
            "detalhe": "Imóvel rural pendente com 755 focos de calor confirmados ao longo de 11 anos na zona leste do DF."
        },
        "DF-5300108-DCFF71953F5F40FF84B8A1D477E3E733": {
            "situacao": "Suspenso (SU)",
            "area_ha": 35219.0,
            "anos": list(range(2015, 2026)),
            "focos": 545,
            "rl": False,
            "app": True,
            "uc": True,
            "detalhe": "Área cadastral suspensa com 545 detecções em 11 anos em área limítrofe a Unidade de Conservação distrital."
        },
        "DF-5300108-6B90D19CDB024E799BD7D49DA7B4AFE8": {
            "situacao": "Ativo (AT)",
            "area_ha": 2893.7,
            "anos": [2016, 2017, 2020, 2024],
            "focos": 502,
            "rl": False,
            "app": True,
            "uc": True,
            "detalhe": "Único imóvel com cadastro Ativo entre os 10 mais incidentes do DF, somando 502 focos em 4 anos distintos em APP e faixa de UC."
        },
        "DF-5300108-CCB5F18038C349AE9EEA9AD26EE5E5A6": {
            "situacao": "Pendente (PE)",
            "area_ha": 5718.2,
            "anos": list(range(2015, 2026)),
            "focos": 470,
            "rl": True,
            "app": True,
            "uc": True,
            "detalhe": "Propriedade pendente com 470 focos em 11 anos com sobreposição crítica tríplice: Reserva Legal, APP e faixa de 1 km de UC."
        }
    }

    imoveis_out = []
    with zipfile.ZipFile(zip_path) as z:
        with shapefile.Reader(
            shp=z.open("AREA_IMOVEL_1.shp"),
            shx=z.open("AREA_IMOVEL_1.shx"),
            dbf=z.open("AREA_IMOVEL_1.dbf"),
            encoding="latin1"
        ) as sf:
            fields = [f[0] for f in sf.fields[1:]]
            idx_cod = fields.index("cod_imovel")
            idx_cond = fields.index("des_condic")
            idx_mun = fields.index("municipio")

            for sr in sf.iterShapeRecords():
                cod = sr.record[idx_cod]
                if cod in target_info:
                    info = target_info[cod]
                    geom = shape(sr.shape.__geo_interface__)
                    if not geom.is_valid:
                        geom = make_valid(geom)
                    cent = geom.centroid
                    sim = geom.simplify(0.0008, preserve_topology=True)

                    imoveis_out.append({
                        "cod_imovel": cod,
                        "municipio": sr.record[idx_mun],
                        "condicao": sr.record[idx_cond],
                        "situacao": info["situacao"],
                        "lat": round(cent.y, 4),
                        "lon": round(cent.x, 4),
                        "area_ha": info["area_ha"],
                        "anos": info["anos"],
                        "focos_total": info["focos"],
                        "atinge_rl": info["rl"],
                        "atinge_app": info["app"],
                        "atinge_uc1km": info["uc"],
                        "detalhe": info["detalhe"],
                        "geometry": round_coords(mapping(sim), 4)
                    })

    # Ordena por total de focos decrescente
    imoveis_out.sort(key=lambda x: x["focos_total"], reverse=True)
    return imoveis_out


def main():
    csv_path = "data/processed/focos_df_2015_2025.csv"
    uc_geojson_path = "data/raw/unidades_conservacao.geojson"
    car_zip_path = "data/raw/AREA_IMOVEL.zip"
    output_js = "docs/assets/dados_mapa_df.js"

    print("Processando serie temporal de focos de calor...")
    focos_ano, stats_ano = carregar_focos_e_estatisticas(csv_path)

    print("Processando 84 Unidades de Conservacao e buffers de 1 km...")
    ucs_geojson, buffers_geojson = processar_unidades_conservacao(uc_geojson_path)

    print("Processando 10 imoveis CAR reincidentes criticos...")
    imoveis = processar_imoveis_reincidentes(car_zip_path)

    bundle = {
        "stats_ano": stats_ano,
        "focos_ano": focos_ano,
        "ucs_geojson": ucs_geojson,
        "buffers_geojson": buffers_geojson,
        "imoveis_reincidentes": imoveis,
        "limites_df": {
            "centro": [-15.78, -47.88],
            "zoom": 10,
            "bounds": [[-16.05, -48.30], [-15.45, -47.30]],
        },
    }

    os.makedirs(os.path.dirname(output_js), exist_ok=True)
    with open(output_js, "w", encoding="utf-8") as out:
        out.write("window.DADOS_MAPA_DF = ")
        json.dump(bundle, out, ensure_ascii=False, separators=(",", ":"))
        out.write(";\n")

    tamanho_kb = os.path.getsize(output_js) / 1024
    print(f"[OK] Dados do mapa gravados em {output_js} ({tamanho_kb:.1f} KB).")


if __name__ == "__main__":
    main()
