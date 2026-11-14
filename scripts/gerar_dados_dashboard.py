#!/usr/bin/env python3
"""
Gera os arquivos JSON estruturados em docs/assets/dados_dashboard/ para o
Dashboard interativo (D3.js + d3-geo + Leaflet):
- resumo.json: agregacoes historicas, UCs, RAs, sensores, risco, CAR Top 50 e referencia Gold
- geometrias.json: contorno do DF, 37 RAs, 84 UCs, faixas de 1 km e geometrias Top 50 CAR + RL
- focos.json: serie completa compacta dos 38.945 focos (2015-2025) para filtragem cruzada em memoria
"""

import csv
import json
import os
import statistics
import urllib.request
import zipfile
from collections import Counter, defaultdict

import numpy as np
import pyproj
import shapefile
import shapely
from shapely.geometry import MultiPolygon, Point, Polygon, mapping, shape
from shapely.ops import unary_union
from shapely.strtree import STRtree
from shapely.validation import make_valid

IDE_DF_RA_URL = (
    "https://www.geoservicos.ide.df.gov.br/arcgis/rest/services/Publico/LIMITES/"
    "FeatureServer/1/query?where=1%3D1&outFields=*&outSR=4326&f=geojson"
)
IDE_DF_LIMITE_URL = (
    "https://www.geoservicos.ide.df.gov.br/arcgis/rest/services/Publico/LIMITES/"
    "FeatureServer/2/query?where=1%3D1&outFields=*&outSR=4326&f=geojson"
)
SISDIA_UC_URL = (
    "https://sisdia.df.gov.br/server/rest/services/01_AMBIENTAL/"
    "Unidades_de_Conservacao_Gestao_IBRAM/FeatureServer/0/query?where=1%3D1&outFields=*&f=geojson"
)

SENSOR_METADATA = {
    "0": {
        "id": 0,
        "nome": "VIIRS (375 m)",
        "sensor": "VIIRS I-Band",
        "resolucao_m": 375,
        "dimensao": "375 m x 375 m",
        "area_ha": 14.1,
        "orbita": "Polar (Suomi-NPP / NOAA-20 / NOAA-21)",
        "cor": "#ea580c",
        "descricao": "Sensor de alta resolucao espacial com pixel nominal de 375 m (~14,1 ha no nadir).",
    },
    "1": {
        "id": 1,
        "nome": "MODIS (1.000 m)",
        "sensor": "MODIS Termico",
        "resolucao_m": 1000,
        "dimensao": "1.000 m x 1.000 m",
        "area_ha": 100.0,
        "orbita": "Polar (AQUA / TERRA)",
        "cor": "#dc2626",
        "descricao": "Sensor do satelite de referencia do INPE (AQUA_M-T) com pixel nominal de 1 km2 (~100 ha).",
    },
    "2": {
        "id": 2,
        "nome": "GOES (2.000 m)",
        "sensor": "ABI / Banda Termica",
        "resolucao_m": 2000,
        "dimensao": "2.000 m x 2.000 m",
        "area_ha": 400.0,
        "orbita": "Geoestacionaria (GOES-16 / GOES-19 / MSG)",
        "cor": "#0284c7",
        "descricao": "Sensor geoestacionario de alta frequencia temporal (10-15 min) com pixel nominal de ~400 ha.",
    },
    "3": {
        "id": 3,
        "nome": "AVHRR / Outros (1.100 m)",
        "sensor": "AVHRR / Radiometro de Varredura",
        "resolucao_m": 1100,
        "dimensao": "1.100 m x 1.100 m",
        "area_ha": 121.0,
        "orbita": "Polar (NOAA / MetOp)",
        "cor": "#7c3aed",
        "descricao": "Sensores polares classicos com resolucao espacial nominal de 1,1 km (~121 ha).",
    },
}

GOLD_REFERENCIA = {
    "fonte": "mart_reincidencia_imovel_ano (dbt-duckdb / Entrega 3)",
    "imoveis_total_car": 21047,
    "imoveis_com_foco_protegido": 4068,
    "imoveis_reincidentes": 1593,
    "focos_em_reincidentes": 37693,
    "reincidentes_por_categoria": {
        "uc_1km": 1231,
        "reserva_legal": 958,
        "app": 382,
    },
    "distribuicao_anos": {
        "2": 717,
        "3": 331,
        "4": 159,
        "5": 120,
        "6": 74,
        "7": 47,
        "8": 50,
        "9": 31,
        "10": 23,
        "11": 41,
    },
    "situacao_cadastral": {
        "AT": 1413,
        "PE": 107,
        "SU": 41,
        "CA": 32,
    },
}


def round_coords(obj, decimals=4):
    """Arredonda coordenadas geograficas recursivamente para reduzir tamanho dos JSONs."""
    if isinstance(obj, float):
        return round(obj, decimals)
    if isinstance(obj, (list, tuple)):
        return [round_coords(x, decimals) for x in obj]
    if isinstance(obj, dict):
        return {k: round_coords(v, decimals) for k, v in obj.items()}
    return obj


def ensure_geojson(path, url, label):
    """Garante que o arquivo GeoJSON exista localmente, baixando se ausente."""
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    os.makedirs(os.path.dirname(path), exist_ok=True)
    print(f"Baixando {label}...")
    req = urllib.request.Request(url, headers={"User-Agent": "corta-fogo-df/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        raw = resp.read()
    data = json.loads(raw.decode("utf-8"))
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    return data


def shape_to_valid_geom(shp):
    """
    Converte um shape pyshp para geometria Shapely valida.
    Evita RingSamplingError e ruido de stderr em aneis degenerados do SICAR.
    """
    pts = shp.points
    parts = list(shp.parts)
    if not pts or not parts:
        return None

    if len(parts) == 1:
        if len(pts) < 4:
            return None
        geom = Polygon(pts)
    else:
        end_indices = parts[1:] + [len(pts)]
        polys = []
        for start, end in zip(parts, end_indices):
            ring = pts[start:end]
            if len(ring) >= 4:
                p = Polygon(ring)
                if not p.is_valid:
                    p = make_valid(p)
                if not p.is_empty and p.area > 0:
                    polys.append(p)
        if not polys:
            return None
        geom = polys[0]
        for p in polys[1:]:
            geom = geom.symmetric_difference(p)

    if not geom.is_valid:
        geom = make_valid(geom)
    if geom.is_empty:
        return None
    return geom


def obter_tipo_sensor(nome_satelite):
    """Classifica o satelite na familia de sensor orbital (0..3)."""
    sat = (nome_satelite or "").upper()
    if "NPP" in sat or "NOAA-20" in sat or "NOAA-21" in sat or "375" in sat:
        return 0
    if "AQUA" in sat or "TERRA" in sat or "MODIS" in sat:
        return 1
    if "GOES" in sat or "MSG" in sat:
        return 2
    return 3


def classificar_grupo_uc(uc_conserv):
    """Padroniza o grupo de manejo da UC."""
    txt = (uc_conserv or "").lower()
    if "integral" in txt:
        return "Proteção Integral"
    if "sustent" in txt:
        return "Uso Sustentável"
    return "Outros ETEP"


def faixa_area_label(area_ha):
    """Retorna a faixa fundiaria padronizada em hectares."""
    if area_ha <= 20:
        return "Até 20 ha"
    if area_ha <= 100:
        return "20 a 100 ha"
    if area_ha <= 500:
        return "100 a 500 ha"
    if area_ha <= 5000:
        return "500 a 5.000 ha"
    return "Acima de 5.000 ha"


def carregar_focos(csv_path):
    """Le todos os 38.945 focos com atributos temporais, orbitais e de risco."""
    focos = []
    satelites_counter = Counter()

    with open(csv_path, "r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            dt = row["data_hora_evento"]
            ano = int(dt[:4])
            mes = int(dt[5:7])
            hora_utc = int(dt[11:13])
            hora_brt = (hora_utc - 3) % 24
            lat = round(float(row["latitude"]), 4)
            lon = round(float(row["longitude"]), 4)
            sat = (row.get("satelite") or "").strip()
            is_ref = 1 if row["is_satelite_referencia"] == "True" else 0
            is_seca = 1 if 5 <= mes <= 9 else 0
            sensor_tipo = obter_tipo_sensor(sat)

            risco_raw = (row.get("risco_fogo") or "").strip()
            risco_pct = int(round(float(risco_raw) * 100)) if risco_raw else -1

            satelites_counter[sat] += 1
            focos.append({
                "lat": lat,
                "lon": lon,
                "ano": ano,
                "mes": mes,
                "hora": hora_brt,
                "ref": is_ref,
                "seca": is_seca,
                "sensor": sensor_tipo,
                "risco": risco_pct,
                "satelite": sat,
            })

    return focos, satelites_counter


def processar_camadas_territoriais(raw_dir, trans_to_m, trans_to_geo):
    """Processa contorno do DF, 37 RAs e 84 UCs (+ buffers metricos de 1 km)."""
    limite_raw = ensure_geojson(
        os.path.join(raw_dir, "limite_df.geojson"),
        IDE_DF_LIMITE_URL,
        "Limite oficial do DF (IDE-DF)",
    )
    ras_raw = ensure_geojson(
        os.path.join(raw_dir, "regioes_administrativas.geojson"),
        IDE_DF_RA_URL,
        "Regioes Administrativas do DF (IDE-DF)",
    )
    ucs_raw = ensure_geojson(
        os.path.join(raw_dir, "unidades_conservacao.geojson"),
        SISDIA_UC_URL,
        "Unidades de Conservacao do DF (SISDIA/IBRAM)",
    )

    def proj_to_m(g):
        gm = shapely.transform(g, lambda c: np.column_stack(trans_to_m.transform(c[:, 0], c[:, 1])))
        return gm if gm.is_valid else make_valid(gm)

    def proj_to_geo(gm):
        return shapely.transform(gm, lambda c: np.column_stack(trans_to_geo.transform(c[:, 0], c[:, 1])))

    # 1. Contorno DF
    limite_features = []
    for ft in limite_raw.get("features", []):
        g = make_valid(shape(ft["geometry"]))
        gm_sim = proj_to_m(g).simplify(45.0, preserve_topology=True)
        limite_features.append({
            "type": "Feature",
            "properties": {"nome": "Distrito Federal"},
            "geometry": round_coords(mapping(proj_to_geo(gm_sim)), 4),
        })

    # 2. 37 Regioes Administrativas
    ras_sorted = sorted(
        ras_raw.get("features", []),
        key=lambda x: (x["properties"].get("ra_cira") or 999, x["properties"].get("ra_nome") or ""),
    )
    ras_features = []
    ras_geoms_geo = []
    ras_meta = []
    for idx, ft in enumerate(ras_sorted):
        p = ft["properties"]
        g = make_valid(shape(ft["geometry"]))
        gm_sim = proj_to_m(g).simplify(35.0, preserve_topology=True)
        g_sim = proj_to_geo(gm_sim)

        codigo = str(p.get("ra_codigo") or "").strip()
        if codigo and not codigo.startswith("RA-") and codigo.startswith("X"):
            codigo = "RA-" + codigo
        nome = str(p.get("ra_nome") or f"RA {idx + 1}").strip().title()
        nome = nome.replace(" E ", " e ").replace(" De ", " de ").replace(" Das ", " das ")
        area_km2 = round(float(p.get("ra_areakm2") or (gm_sim.area / 1e6)), 2)

        ras_geoms_geo.append(g)
        ras_meta.append({
            "idx": idx,
            "codigo": codigo or f"RA-{idx + 1}",
            "nome": nome,
            "area_km2": area_km2,
            "centroide": [round(g.centroid.y, 4), round(g.centroid.x, 4)],
        })
        ras_features.append({
            "type": "Feature",
            "properties": {
                "idx": idx,
                "codigo": codigo or f"RA-{idx + 1}",
                "nome": nome,
                "area_km2": area_km2,
            },
            "geometry": round_coords(mapping(g_sim), 4),
        })

    # 3. 84 Unidades de Conservacao + Buffers de 1 km
    ucs_sorted = sorted(
        ucs_raw.get("features", []),
        key=lambda x: str(x["properties"].get("nome") or ""),
    )
    ucs_features = []
    buffers_features = []
    uc_geoms_m = []
    buf_geoms_m = []
    ucs_meta = []

    for idx, ft in enumerate(ucs_sorted):
        p = ft["properties"]
        g = make_valid(shape(ft["geometry"]))
        gm = proj_to_m(g)
        gm_sim = gm.simplify(18.0, preserve_topology=True)
        buf_m = gm.buffer(1000.0)
        buf_m_sim = buf_m.simplify(30.0, preserve_topology=True)

        uc_id = p.get("id") or p.get("objectid") or (idx + 1)
        nome = str(p.get("nome") or "Unidade de Conservação").strip()
        sigla = str(p.get("sigla") or "").strip()
        uc_conserv = str(p.get("uc_conserv") or "Espaço Protegido").strip()
        grupo = classificar_grupo_uc(uc_conserv)
        area_ha = round(float(p.get("area_ha") or (gm.area / 10000.0)), 1)
        ano_criaca = str(p.get("ano_criaca") or "").strip()
        gestao = str(p.get("gestao") or "Distrital (IBRAM)").strip()
        cent = g.centroid

        uc_geoms_m.append(gm)
        buf_geoms_m.append(buf_m)
        ucs_meta.append({
            "idx": idx,
            "id": uc_id,
            "nome": nome,
            "sigla": sigla,
            "categoria": uc_conserv,
            "grupo": grupo,
            "gestao": gestao,
            "area_ha": area_ha,
            "ano_criacao": ano_criaca,
            "centroide": [round(cent.y, 4), round(cent.x, 4)],
        })

        ucs_features.append({
            "type": "Feature",
            "properties": {
                "idx": idx,
                "id": uc_id,
                "nome": nome,
                "sigla": sigla,
                "uc_conserv": uc_conserv,
                "grupo": grupo,
                "area_ha": area_ha,
                "ano_criaca": ano_criaca,
                "gestao": gestao,
            },
            "geometry": round_coords(mapping(proj_to_geo(gm_sim)), 4),
        })

        buffers_features.append({
            "type": "Feature",
            "properties": {
                "idx": idx,
                "id": uc_id,
                "nome": nome,
            },
            "geometry": round_coords(mapping(proj_to_geo(buf_m_sim)), 4),
        })

    return {
        "limite_df_geojson": {"type": "FeatureCollection", "features": limite_features},
        "ras_geojson": {"type": "FeatureCollection", "features": ras_features},
        "ucs_geojson": {"type": "FeatureCollection", "features": ucs_features},
        "buffers_geojson": {"type": "FeatureCollection", "features": buffers_features},
        "ras_geoms_geo": ras_geoms_geo,
        "ras_meta": ras_meta,
        "uc_geoms_m": uc_geoms_m,
        "buf_geoms_m": buf_geoms_m,
        "ucs_meta": ucs_meta,
    }


def carregar_car_e_rl(raw_dir):
    """Carrega os imoveis rurais (IRU) e Reservas Legais do SICAR em EPSG:4326."""
    car_zip = os.path.join(raw_dir, "AREA_IMOVEL.zip")
    rl_zip = os.path.join(raw_dir, "RESERVA_LEGAL.zip")

    car_geoms = []
    car_cods = []
    car_info = {}
    seen_cods = set()

    with zipfile.ZipFile(car_zip) as z:
        with shapefile.Reader(
            shp=z.open("AREA_IMOVEL_1.shp"),
            shx=z.open("AREA_IMOVEL_1.shx"),
            dbf=z.open("AREA_IMOVEL_1.dbf"),
            encoding="latin1",
        ) as sf:
            fields = [f[0] for f in sf.fields[1:]]
            i_cod = fields.index("cod_imovel")
            i_tp = fields.index("ind_tipo")
            i_st = fields.index("ind_status")
            i_ar = fields.index("num_area")
            i_cond = fields.index("des_condic")
            i_mun = fields.index("municipio")

            for sr in sf.iterShapeRecords():
                if sr.record[i_tp] != "IRU":
                    continue
                cod = str(sr.record[i_cod] or "").strip()
                if not cod.startswith("DF-") or cod in seen_cods:
                    continue
                g = shape_to_valid_geom(sr.shape)
                if g is None:
                    continue
                seen_cods.add(cod)
                car_geoms.append(g)
                car_cods.append(cod)
                car_info[cod] = {
                    "situacao": str(sr.record[i_st] or "AT").strip(),
                    "area_ha": round(float(sr.record[i_ar] or 0.0), 1),
                    "condicao": str(sr.record[i_cond] or "").strip(),
                    "municipio": str(sr.record[i_mun] or "Brasília").strip(),
                    "geom": g,
                }

    rl_geoms = []
    rl_cods = []
    rl_by_cod = defaultdict(list)

    with zipfile.ZipFile(rl_zip) as z:
        with shapefile.Reader(
            shp=z.open("RESERVA_LEGAL_1.shp"),
            shx=z.open("RESERVA_LEGAL_1.shx"),
            dbf=z.open("RESERVA_LEGAL_1.dbf"),
            encoding="latin1",
        ) as sf:
            fields = [f[0] for f in sf.fields[1:]]
            i_cod = fields.index("cod_imovel")
            for sr in sf.iterShapeRecords():
                cod = str(sr.record[i_cod] or "").strip()
                if cod not in seen_cods:
                    continue
                g = shape_to_valid_geom(sr.shape)
                if g is not None:
                    rl_geoms.append(g)
                    rl_cods.append(cod)
                    rl_by_cod[cod].append(g)

    return car_geoms, car_cods, car_info, rl_geoms, rl_cods, rl_by_cod


def main():
    csv_path = "data/processed/focos_df_2015_2025.csv"
    raw_dir = os.path.join("data", "raw")
    output_dir = os.path.join("docs", "assets", "dados_dashboard")
    os.makedirs(output_dir, exist_ok=True)

    trans_to_m = pyproj.Transformer.from_crs("EPSG:4326", "EPSG:31983", always_xy=True)
    trans_to_geo = pyproj.Transformer.from_crs("EPSG:31983", "EPSG:4326", always_xy=True)

    print("1/5 Carregando focos de calor (2015-2025)...")
    focos, satelites_counter = carregar_focos(csv_path)
    n_focos = len(focos)
    pts_geo = [Point(f["lon"], f["lat"]) for f in focos]
    lons = np.array([f["lon"] for f in focos])
    lats = np.array([f["lat"] for f in focos])
    xm, ym = trans_to_m.transform(lons, lats)
    pts_m = [Point(x, y) for x, y in zip(xm, ym)]

    print("2/5 Processando Limite DF, 37 RAs e 84 UCs (+ buffers 1 km)...")
    camadas = processar_camadas_territoriais(raw_dir, trans_to_m, trans_to_geo)

    print("3/5 Carregando 21.047 imoveis CAR e 13.499 Reservas Legais...")
    car_geoms, car_cods, car_info, rl_geoms, rl_cods, rl_by_cod = carregar_car_e_rl(raw_dir)

    print("4/5 Executando cruzamentos espaciais em lote (shapely.STRtree)...")
    ra_tree = STRtree(camadas["ras_geoms_geo"])
    uc_tree = STRtree(camadas["uc_geoms_m"])
    buf_tree = STRtree(camadas["buf_geoms_m"])
    car_tree = STRtree(car_geoms)
    rl_tree = STRtree(rl_geoms)

    q_ra = ra_tree.query(pts_geo, predicate="intersects")
    q_uc = uc_tree.query(pts_m, predicate="intersects")
    q_buf = buf_tree.query(pts_m, predicate="intersects")
    q_car = car_tree.query(pts_geo, predicate="intersects")
    q_rl = rl_tree.query(pts_geo, predicate="intersects")

    # Mapear RA por foco (com fallback de proximidade <= 0.015 deg para pontos na borda)
    foco_ra = [-1] * n_focos
    for fi, ri in zip(q_ra[0].tolist(), q_ra[1].tolist()):
        if foco_ra[fi] == -1:
            foco_ra[fi] = ri
    for fi in range(n_focos):
        if foco_ra[fi] == -1:
            nearest_idx = int(ra_tree.nearest(pts_geo[fi]))
            if pts_geo[fi].distance(camadas["ras_geoms_geo"][nearest_idx]) < 0.015:
                foco_ra[fi] = nearest_idx

    # Mapear UCs e Buffers por foco (suportando sobreposicoes multi-UC)
    foco_ucs_in = defaultdict(list)
    for fi, ui in zip(q_uc[0].tolist(), q_uc[1].tolist()):
        foco_ucs_in[fi].append(ui)

    foco_ucs_buf = defaultdict(list)
    for fi, ui in zip(q_buf[0].tolist(), q_buf[1].tolist()):
        foco_ucs_buf[fi].append(ui)

    # Mapear RL e CAR por foco
    foco_rl_cods = defaultdict(set)
    for fi, ri in zip(q_rl[0].tolist(), q_rl[1].tolist()):
        foco_rl_cods[fi].add(rl_cods[ri])

    foco_has_car = set(q_car[0].tolist())

    # Estatisticas agregadas por RA e UC
    ras_resumo = []
    for meta in camadas["ras_meta"]:
        ras_resumo.append({
            **meta,
            "total": 0,
            "seca": 0,
            "ref": 0,
            "por_ano": {str(a): 0 for a in range(2015, 2026)},
        })

    ucs_resumo = []
    for meta in camadas["ucs_meta"]:
        ucs_resumo.append({
            **meta,
            "dentro": 0,
            "buffer_1km": 0,
            "total_influencia": 0,
            "ref_total": 0,
            "seca_total": 0,
            "por_ano": {str(a): {"dentro": 0, "buffer_1km": 0} for a in range(2015, 2026)},
        })

    # Compactacao dos 38.945 focos + uc_extra para pontos em multiplas UCs
    focos_compactos = []
    uc_extra = {}

    for fi, f in enumerate(focos):
        ano_str = str(f["ano"])
        ra_i = foco_ra[fi]
        if ra_i != -1:
            r = ras_resumo[ra_i]
            r["total"] += 1
            r["por_ano"][ano_str] += 1
            if f["seca"]:
                r["seca"] += 1
            if f["ref"]:
                r["ref"] += 1

        in_list = sorted(set(foco_ucs_in.get(fi, [])))
        buf_all = sorted(set(foco_ucs_buf.get(fi, [])))
        in_set = set(in_list)
        buf_only_list = [u for u in buf_all if u not in in_set]

        for ui in in_list:
            u = ucs_resumo[ui]
            u["dentro"] += 1
            u["total_influencia"] += 1
            u["por_ano"][ano_str]["dentro"] += 1
            if f["ref"]:
                u["ref_total"] += 1
            if f["seca"]:
                u["seca_total"] += 1

        for ui in buf_only_list:
            u = ucs_resumo[ui]
            u["buffer_1km"] += 1
            u["total_influencia"] += 1
            u["por_ano"][ano_str]["buffer_1km"] += 1
            if f["ref"]:
                u["ref_total"] += 1
            if f["seca"]:
                u["seca_total"] += 1

        uc_in_primary = in_list[0] if in_list else -1
        uc_buf_primary = buf_only_list[0] if buf_only_list else -1

        if len(in_list) > 1 or len(buf_only_list) > 1 or (in_list and buf_only_list):
            uc_extra[str(fi)] = [in_list, buf_only_list]

        em_car = 1 if fi in foco_has_car else 0
        em_rl = 2 if fi in foco_rl_cods else 0
        em_uc = 4 if in_list else 0
        ate_1km = 8 if buf_all else 0
        flags = em_car | em_rl | em_uc | ate_1km

        focos_compactos.append([
            f["lat"],
            f["lon"],
            f["ano"],
            f["mes"],
            f["hora"],
            f["ref"],
            f["seca"],
            f["sensor"],
            f["risco"],
            ra_i,
            uc_in_primary,
            uc_buf_primary,
            flags,
        ])

    # Estatisticas CAR + RL + UC 1km por imovel
    imovel_anos_prot = defaultdict(set)
    imovel_focos_prot = Counter()
    imovel_focos_total = Counter()
    imovel_por_ano = defaultdict(lambda: Counter())
    imovel_rl_flag = set()
    imovel_uc_flag = set()

    for fi, ci in zip(q_car[0].tolist(), q_car[1].tolist()):
        cod = car_cods[ci]
        ano = focos[fi]["ano"]
        imovel_focos_total[cod] += 1
        in_rl = cod in foco_rl_cods.get(fi, ())
        in_uc1km = bool(foco_ucs_buf.get(fi))
        if in_rl or in_uc1km:
            imovel_anos_prot[cod].add(ano)
            imovel_focos_prot[cod] += 1
            imovel_por_ano[cod][str(ano)] += 1
            if in_rl:
                imovel_rl_flag.add(cod)
            if in_uc1km:
                imovel_uc_flag.add(cod)

    reincidentes = [cod for cod, anos in imovel_anos_prot.items() if len(anos) >= 2]

    sit_counts = Counter()
    sit_focos = Counter()
    sit_areas = defaultdict(list)
    faixa_counts = Counter()
    anos_hist = Counter()

    for cod in reincidentes:
        meta = car_info[cod]
        st = meta["situacao"]
        sit_counts[st] += 1
        sit_focos[st] += imovel_focos_prot[cod]
        sit_areas[st].append(meta["area_ha"])
        faixa_counts[faixa_area_label(meta["area_ha"])] += 1
        anos_hist[str(len(imovel_anos_prot[cod]))] += 1

    # Top 50 imoveis reincidentes criticos (ordenados por focos protegidos desc)
    top50_cods = sorted(
        reincidentes,
        key=lambda c: (imovel_focos_prot[c], len(imovel_anos_prot[c]), car_info[c]["area_ha"]),
        reverse=True,
    )[:50]

    car_top50 = []
    car_top50_geoms = {}
    for rank, cod in enumerate(top50_cods, start=1):
        meta = car_info[cod]
        geom = meta["geom"]
        cent = geom.centroid
        sim = geom.simplify(0.0006, preserve_topology=True)
        anos_lista = sorted(imovel_anos_prot[cod])

        rl_geoms_simp = []
        for rg in rl_by_cod.get(cod, []):
            r_sim = rg.simplify(0.0006, preserve_topology=True)
            if not r_sim.is_empty:
                rl_geoms_simp.append(round_coords(mapping(r_sim), 4))

        car_top50.append({
            "rank": rank,
            "cod_imovel": cod,
            "situacao": meta["situacao"],
            "condicao": meta["condicao"],
            "municipio": meta["municipio"],
            "area_ha": meta["area_ha"],
            "lat": round(cent.y, 4),
            "lon": round(cent.x, 4),
            "anos": anos_lista,
            "anos_qtd": len(anos_lista),
            "focos_total": imovel_focos_total[cod],
            "focos_prot": imovel_focos_prot[cod],
            "atinge_rl": cod in imovel_rl_flag,
            "atinge_uc1km": cod in imovel_uc_flag,
            "por_ano": dict(sorted(imovel_por_ano[cod].items())),
        })
        car_top50_geoms[cod] = {
            "imovel": round_coords(mapping(sim), 4),
            "reserva_legal": rl_geoms_simp,
        }

    # Resumos gerais
    por_situacao = {}
    for st in ["AT", "PE", "SU", "CA"]:
        areas = sit_areas.get(st, [])
        por_situacao[st] = {
            "imoveis": sit_counts.get(st, 0),
            "focos": sit_focos.get(st, 0),
            "mediana_ha": round(statistics.median(areas), 1) if areas else 0.0,
        }

    satelites_lista = [
        {"nome": sat, "focos": cnt, "sensor_tipo": obter_tipo_sensor(sat)}
        for sat, cnt in satelites_counter.most_common()
    ]

    resumo_json = {
        "escopo": {
            "total_focos": n_focos,
            "periodo": [2015, 2025],
            "total_ucs": len(ucs_resumo),
            "total_ras": len(ras_resumo),
            "total_imoveis_car": len(car_cods),
            "total_reservas_legais": len(rl_cods),
        },
        "metadata_sensores": SENSOR_METADATA,
        "satelites": satelites_lista,
        "gold_referencia": GOLD_REFERENCIA,
        "car_cruzamento": {
            "nota": "Cruzamento local em Python (CAR + Reserva Legal + Faixa 1 km de UC). Para APP, consulte gold_referencia.",
            "imoveis_com_foco_prot": len(imovel_anos_prot),
            "total_reincidentes": len(reincidentes),
            "reincidentes_rl": len(imovel_rl_flag & set(reincidentes)),
            "reincidentes_uc1km": len(imovel_uc_flag & set(reincidentes)),
            "por_situacao": por_situacao,
            "por_faixa_area": {
                k: faixa_counts.get(k, 0)
                for k in ["Até 20 ha", "20 a 100 ha", "100 a 500 ha", "500 a 5.000 ha", "Acima de 5.000 ha"]
            },
            "distribuicao_anos": {str(a): anos_hist.get(str(a), 0) for a in range(2, 12)},
        },
        "ras_resumo": ras_resumo,
        "ucs_resumo": ucs_resumo,
        "car_top50": car_top50,
    }

    geometrias_json = {
        "limites_df": {
            "centro": [-15.78, -47.88],
            "zoom": 10,
            "bounds": [[-16.06, -48.30], [-15.44, -47.30]],
        },
        "limite_df": camadas["limite_df_geojson"],
        "ras": camadas["ras_geojson"],
        "ucs": camadas["ucs_geojson"],
        "buffers": camadas["buffers_geojson"],
        "car_top50_geoms": car_top50_geoms,
    }

    focos_json = {
        "schema": ["lat", "lon", "ano", "mes", "hora", "ref", "seca", "sensor", "risco", "ra", "uc_in", "uc_buf", "flags"],
        "focos": focos_compactos,
        "uc_extra": uc_extra,
    }

    print("5/5 Gravando arquivos JSON em docs/assets/dados_dashboard/...")
    outputs = [
        ("resumo.json", resumo_json),
        ("geometrias.json", geometrias_json),
        ("focos.json", focos_json),
    ]
    for filename, payload in outputs:
        out_path = os.path.join(output_dir, filename)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))
        kb = os.path.getsize(out_path) / 1024
        print(f"  [OK] {out_path} ({kb:.1f} KB)")


if __name__ == "__main__":
    main()
