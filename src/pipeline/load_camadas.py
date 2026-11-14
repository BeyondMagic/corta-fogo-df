#!/usr/bin/env python3
"""
Pipeline de carga e saneamento das camadas geograficas no PostGIS.
Lê os shapefiles/GeoJSONs brutos em data/raw, reprojeta para o SRID 31983,
aplica correcao topologica (make_valid) e insere nas tabelas da E1:
- unidade_conservacao
- area_preservacao_permanente
- imovel_car
- reserva_legal
"""

import argparse
import datetime
import json
import os
import sys
import geopandas as gpd
import psycopg2
from psycopg2.extras import execute_batch
from shapely import make_valid
from shapely.geometry import MultiPolygon, Polygon

TARGET_SRID = 31983

# AREA_IMOVEL.zip e RESERVA_LEGAL.zip sao arquivos estaticos versionados no
# repositorio (nao sao baixados a cada carga). Esta e a data em que Gabriel
# Fernando os obteve do SICAR, conforme o commit que os adicionou
# (ca8e5c4, "feat: add geographic layers extraction and data loading
# pipeline"). Nao confundir com a data em que o load_camadas.py roda.
SICAR_DATA_DOWNLOAD = "2026-09-27"


def ler_data_download(caminho_dado: str, fallback: str) -> str:
    """
    Le a data real de download de um arquivo baixado por extract_camadas.py,
    gravada no sidecar <arquivo>.meta.json. Usa `fallback` (e avisa) se o
    sidecar nao existir, por exemplo quando o GeoJSON foi colocado manualmente.
    """
    meta_path = caminho_dado + ".meta.json"
    if os.path.exists(meta_path):
        with open(meta_path, encoding="utf-8") as f:
            meta = json.load(f)
        return meta["baixado_em"][:10]

    print(f"[AVISO] Sem metadado de download para {caminho_dado}, usando {fallback}.")
    return fallback


def get_db_connection(args):
    """Cria conexao com o banco de dados PostgreSQL."""
    if args.db_url:
        return psycopg2.connect(args.db_url)
    return psycopg2.connect(
        host=args.db_host,
        port=args.db_port,
        dbname=args.db_name,
        user=args.db_user,
        password=args.db_password,
    )


def normalizar_para_multipolygon(geom):
    """
    Saneia e converte qualquer geometria poligonal para MultiPolygon valido.
    Descarta geometrias vazias ou nao poligonais geradas por correcao.
    """
    if geom is None or geom.is_empty:
        return None

    # Correcao topologica de auto-intersecoes e aneis invalidos
    if not geom.is_valid:
        geom = make_valid(geom)

    if geom.is_empty:
        return None

    if isinstance(geom, Polygon):
        return MultiPolygon([geom])
    elif isinstance(geom, MultiPolygon):
        return geom
    elif hasattr(geom, "geoms"):
        # Se for GeometryCollection, filtra apenas poligonos
        polys = []
        for g in geom.geoms:
            if isinstance(g, Polygon):
                polys.append(g)
            elif isinstance(g, MultiPolygon):
                polys.extend(g.geoms)
        if polys:
            return MultiPolygon(polys)
    return None


def carregar_unidades_conservacao(conn, raw_dir: str):
    """Carrega as Unidades de Conservacao a partir do GeoJSON do IBRAM."""
    path = os.path.join(raw_dir, "unidades_conservacao.geojson")
    if not os.path.exists(path):
        print(f"[AVISO] Arquivo nao encontrado: {path}. Pulando UCs.")
        return 0

    data_download = ler_data_download(path, datetime.date.today().isoformat())
    print("Processando Unidades de Conservacao...")
    gdf = gpd.read_file(path)
    if gdf.crs is None or gdf.crs.to_epsg() != TARGET_SRID:
        gdf = gdf.to_crs(epsg=TARGET_SRID)

    registros = []
    for _, row in gdf.iterrows():
        nome = str(row.get("nome") or "").strip()
        if not nome:
            continue

        categoria = str(row.get("categoria") or "")[:100]
        uc_conserv = str(row.get("uc_conserv") or "").lower()

        if "integral" in uc_conserv:
            grupo = "protecao_integral"
        elif "sustentavel" in uc_conserv or "sustentável" in uc_conserv:
            grupo = "uso_sustentavel"
        else:
            grupo = None

        geom = normalizar_para_multipolygon(row.geometry)
        if geom is None or geom.is_empty:
            continue

        area_ha = float(row.get("area_ha") or (geom.area / 10000.0))
        area_ha = max(round(area_ha, 4), 0.0001)

        registros.append(
            (
                nome[:200],
                categoria if categoria else None,
                grupo,
                area_ha,
                "IBRAM / Geoportal DF",
                data_download,
                geom.wkb_hex,
            )
        )

    sql = """
        INSERT INTO unidade_conservacao (nome, categoria, grupo, area_ha, fonte, data_download, geom)
        VALUES (%s, %s, %s, %s, %s, %s, ST_SetSRID(ST_GeomFromWKB(decode(%s, 'hex')), 31983))
    """
    with conn.cursor() as cur:
        execute_batch(cur, sql, registros, page_size=200)
    conn.commit()
    print(f"  -> {len(registros)} Unidades de Conservacao carregadas com sucesso.")
    return len(registros)


def carregar_apps_ibram(conn, raw_dir: str):
    """Carrega as APPs fisicas mapeadas pelo IBRAM/SISDIA."""
    camadas_app = [
        ("app_nascentes.geojson", "nascente"),
        ("app_borda_chapada.geojson", "borda_de_chapada"),
        ("app_reservatorio.geojson", "reservatorio"),
    ]

    total_carregado = 0

    for filename, tipo in camadas_app:
        path = os.path.join(raw_dir, filename)
        if not os.path.exists(path):
            continue

        data_download = ler_data_download(path, datetime.date.today().isoformat())
        print(f"Processando APPs ({tipo})...")
        gdf = gpd.read_file(path)
        if gdf.crs is None or gdf.crs.to_epsg() != TARGET_SRID:
            gdf = gdf.to_crs(epsg=TARGET_SRID)

        registros = []
        for _, row in gdf.iterrows():
            geom = normalizar_para_multipolygon(row.geometry)
            if geom is None or geom.is_empty:
                continue

            area_ha = geom.area / 10000.0
            area_ha = max(round(area_ha, 4), 0.0001)

            registros.append(
                (
                    None,
                    tipo,
                    area_ha,
                    "IBRAM / Geoportal DF",
                    data_download,
                    geom.wkb_hex,
                )
            )

        with conn.cursor() as cur:
            execute_batch(
                cur,
                """
                INSERT INTO area_preservacao_permanente (cod_imovel, tipo, area_ha, fonte, data_download, geom)
                VALUES (%s, %s, %s, %s, %s, ST_SetSRID(ST_GeomFromWKB(decode(%s, 'hex')), 31983))
                """,
                registros,
                page_size=500,
            )
        conn.commit()
        print(f"  -> {len(registros)} APPs ({tipo}) carregadas.")
        total_carregado += len(registros)

    return total_carregado


def normalizar_codigo_ra(codigo_bruto) -> str:
    """Padroniza o codigo da RA para RA-<romano> (a fonte alterna entre 'RA-VI' e 'VI')."""
    codigo = str(codigo_bruto or "").strip().upper()
    if codigo and not codigo.startswith("RA-"):
        codigo = "RA-" + codigo
    return codigo


def formatar_nome_ra(nome_bruto) -> str:
    """'SOBRADINHO II' -> 'Sobradinho II'; 'SOL NASCENTE E POR DO SOL' -> 'Sol Nascente e Por do Sol'."""
    conectivos = {"de", "da", "do", "das", "dos", "e"}
    romanos = {"ii", "iii", "iv"}
    palavras = []
    for i, palavra in enumerate(str(nome_bruto or "").strip().lower().split()):
        if palavra in romanos:
            palavras.append(palavra.upper())
        elif palavra in conectivos and i > 0:
            palavras.append(palavra)
        else:
            palavras.append(palavra.capitalize())
    return " ".join(palavras)


def carregar_regioes_administrativas(conn, raw_dir: str):
    """Carrega as Regioes Administrativas do DF a partir do GeoJSON da IDE-DF."""
    path = os.path.join(raw_dir, "regioes_administrativas.geojson")
    if not os.path.exists(path):
        print(f"[AVISO] Arquivo nao encontrado: {path}. Pulando Regioes Administrativas.")
        return 0

    data_download = ler_data_download(path, datetime.date.today().isoformat())
    print("Processando Regioes Administrativas...")
    gdf = gpd.read_file(path)
    if gdf.crs is None or gdf.crs.to_epsg() != TARGET_SRID:
        gdf = gdf.to_crs(epsg=TARGET_SRID)

    registros = []
    codigos = set()
    for _, row in gdf.iterrows():
        codigo = normalizar_codigo_ra(row.get("ra_codigo"))
        nome = str(row.get("ra_nome") or "").strip()
        if not codigo or codigo == "RA-NAN" or not nome or nome.lower() == "nan" or codigo in codigos:
            continue

        geom = normalizar_para_multipolygon(row.geometry)
        if geom is None or geom.is_empty:
            continue

        codigos.add(codigo)
        registros.append(
            (
                codigo[:20],
                formatar_nome_ra(nome)[:100],
                round(geom.area / 1_000_000.0, 2),
                "IDE-DF / SEDUH",
                data_download,
                geom.wkb_hex,
            )
        )

    sql = """
        INSERT INTO regiao_administrativa (codigo, nome, area_km2, fonte, data_download, geom)
        VALUES (%s, %s, %s, %s, %s, ST_SetSRID(ST_GeomFromWKB(decode(%s, 'hex')), 31983))
    """
    with conn.cursor() as cur:
        execute_batch(cur, sql, registros, page_size=100)
    conn.commit()
    print(f"  -> {len(registros)} Regioes Administrativas carregadas.")
    return len(registros)


def carregar_imoveis_car(conn, raw_dir: str) -> set:
    """Carrega os imoveis rurais do CAR-DF a partir do zip do SICAR."""
    zip_path = os.path.join(raw_dir, "AREA_IMOVEL.zip")
    if not os.path.exists(zip_path):
        print(f"[AVISO] Arquivo {zip_path} nao encontrado. Pulando imoveis.")
        return set()

    data_download = SICAR_DATA_DOWNLOAD
    print("Processando Imoveis Rurais do CAR-DF (pode levar cerca de 1 minuto)...")
    gdf = gpd.read_file(f"zip://{zip_path}")
    if gdf.crs is None or gdf.crs.to_epsg() != TARGET_SRID:
        gdf = gdf.to_crs(epsg=TARGET_SRID)

    registros = []
    cods_inseridos = set()

    for _, row in gdf.iterrows():
        cod = str(row.get("cod_imovel") or "").strip()
        if not cod.startswith("DF-") or cod in cods_inseridos:
            continue

        situacao = str(row.get("ind_status") or "")[:40]
        condicao = str(row.get("des_condic") or "")[:200]

        geom = normalizar_para_multipolygon(row.geometry)
        if geom is None or geom.is_empty:
            continue

        try:
            area_ha = float(row.get("num_area") or (geom.area / 10000.0))
        except (ValueError, TypeError):
            area_ha = geom.area / 10000.0

        area_ha = max(round(area_ha, 4), 0.0001)

        registros.append(
            (
                cod,
                situacao if situacao else None,
                condicao if condicao else None,
                area_ha,
                data_download,
                geom.wkb_hex,
            )
        )
        cods_inseridos.add(cod)

    sql = """
        INSERT INTO imovel_car (cod_imovel, situacao, condicao, area_ha, data_download, geom)
        VALUES (%s, %s, %s, %s, %s, ST_SetSRID(ST_GeomFromWKB(decode(%s, 'hex')), 31983))
        ON CONFLICT (cod_imovel) DO NOTHING
    """
    with conn.cursor() as cur:
        execute_batch(cur, sql, registros, page_size=1000)
    conn.commit()
    print(f"  -> {len(registros)} Imoveis rurais do CAR carregados.")
    return cods_inseridos


def carregar_reserva_legal(conn, raw_dir: str, cods_validos: set):
    """Carrega as Reservas Legais do CAR-DF respeitando a FK com imovel_car."""
    zip_path = os.path.join(raw_dir, "RESERVA_LEGAL.zip")
    if not os.path.exists(zip_path):
        print(f"[AVISO] Arquivo {zip_path} nao encontrado. Pulando reserva legal.")
        return 0

    data_download = SICAR_DATA_DOWNLOAD
    print("Processando Reserva Legal do CAR-DF...")
    gdf = gpd.read_file(f"zip://{zip_path}")
    if gdf.crs is None or gdf.crs.to_epsg() != TARGET_SRID:
        gdf = gdf.to_crs(epsg=TARGET_SRID)

    registros = []
    for _, row in gdf.iterrows():
        cod = str(row.get("cod_imovel") or "").strip()
        if not cod or (cods_validos and cod not in cods_validos):
            continue

        situacao = str(row.get("ind_status") or "")[:40]
        geom = normalizar_para_multipolygon(row.geometry)
        if geom is None or geom.is_empty:
            continue

        try:
            area_ha = float(row.get("num_area") or (geom.area / 10000.0))
        except (ValueError, TypeError):
            area_ha = geom.area / 10000.0

        area_ha = max(round(area_ha, 4), 0.0001)

        registros.append(
            (
                cod,
                situacao if situacao else None,
                area_ha,
                data_download,
                geom.wkb_hex,
            )
        )

    sql = """
        INSERT INTO reserva_legal (cod_imovel, situacao, area_ha, data_download, geom)
        VALUES (%s, %s, %s, %s, ST_SetSRID(ST_GeomFromWKB(decode(%s, 'hex')), 31983))
    """
    with conn.cursor() as cur:
        execute_batch(cur, sql, registros, page_size=1000)
    conn.commit()
    print(f"  -> {len(registros)} Reservas Legais carregadas com sucesso.")
    return len(registros)


def main():
    parser = argparse.ArgumentParser(
        description="Carrega camadas geograficas (UCs, APPs e CAR) no PostGIS com SRID 31983."
    )
    parser.add_argument(
        "--raw-dir",
        default=os.path.join("data", "raw"),
        help="Diretorio com arquivos brutos (padrao: data/raw).",
    )
    parser.add_argument(
        "--db-host",
        default=os.getenv("DB_HOST", "localhost"),
        help="Host do PostgreSQL (padrao: localhost).",
    )
    parser.add_argument(
        "--db-port",
        default=int(os.getenv("DB_PORT", "5434")),
        help="Porta do PostgreSQL (padrao: 5434).",
    )
    parser.add_argument(
        "--db-name",
        default=os.getenv("DB_NAME", "corta-fogo-df"),
        help="Nome do banco de dados (padrao: corta-fogo-df).",
    )
    parser.add_argument(
        "--db-user",
        default=os.getenv("DB_USER", "corta-fogo"),
        help="Usuario do banco (padrao: corta-fogo).",
    )
    parser.add_argument(
        "--db-password",
        default=os.getenv("DB_PASSWORD", "corta-fogo"),
        help="Senha do banco (padrao: corta-fogo).",
    )
    parser.add_argument(
        "--db-url",
        default=os.getenv("DATABASE_URL"),
        help="URL completa de conexao (sobrescreve parametros individuais).",
    )
    parser.add_argument(
        "--no-truncate",
        action="store_true",
        help="Nao limpa as tabelas antes da carga.",
    )

    args = parser.parse_args()

    try:
        conn = get_db_connection(args)
        print("Conexao com o PostgreSQL estabelecida com sucesso.")
    except Exception as e:
        print(f"Erro ao conectar ao PostgreSQL: {e}", file=sys.stderr)
        sys.exit(1)

    try:
        if not args.no_truncate:
            print("Limpando tabelas geograficas para carga limpa...")
            with conn.cursor() as cur:
                cur.execute("""
                    TRUNCATE TABLE reserva_legal, imovel_car, area_preservacao_permanente, unidade_conservacao, hidrografia, regiao_administrativa RESTART IDENTITY CASCADE;
                """)
            conn.commit()

        carregar_unidades_conservacao(conn, args.raw_dir)
        carregar_apps_ibram(conn, args.raw_dir)
        carregar_regioes_administrativas(conn, args.raw_dir)
        cods = carregar_imoveis_car(conn, args.raw_dir)
        carregar_reserva_legal(conn, args.raw_dir, cods)

        with conn.cursor() as cur:
            cur.execute("ANALYZE unidade_conservacao, area_preservacao_permanente, regiao_administrativa, imovel_car, reserva_legal;")
        conn.commit()

        print("\nCarga de todas as camadas geograficas finalizada com exito.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
