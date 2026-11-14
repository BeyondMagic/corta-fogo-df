#!/usr/bin/env python3
import psycopg2

conn = psycopg2.connect(
    host="localhost",
    port=5434,
    dbname="corta-fogo-df",
    user="corta-fogo",
    password="corta-fogo",
)

with conn.cursor() as cur:
    queries = [
        (
            "Unidades de Conservacao",
            "SELECT count(*), Find_SRID('public', 'unidade_conservacao', 'geom'), count(*) FILTER (WHERE ST_IsValid(geom)) FROM unidade_conservacao",
        ),
        (
            "Areas de Preservacao Permanente (APPs)",
            "SELECT count(*), Find_SRID('public', 'area_preservacao_permanente', 'geom'), count(*) FILTER (WHERE ST_IsValid(geom)) FROM area_preservacao_permanente",
        ),
        (
            "Regioes Administrativas",
            "SELECT count(*), Find_SRID('public', 'regiao_administrativa', 'geom'), count(*) FILTER (WHERE ST_IsValid(geom)) FROM regiao_administrativa",
        ),
        (
            "Imoveis Rurais (CAR)",
            "SELECT count(*), Find_SRID('public', 'imovel_car', 'geom'), count(*) FILTER (WHERE ST_IsValid(geom)) FROM imovel_car",
        ),
        (
            "Reservas Legais",
            "SELECT count(*), Find_SRID('public', 'reserva_legal', 'geom'), count(*) FILTER (WHERE ST_IsValid(geom)) FROM reserva_legal",
        ),
    ]

    print(f"{'CAMADA':<40} | {'TOTAL REGISTROS':<16} | {'SRID':<6} | {'VALIDAS (ST_IsValid)'}")
    print("-" * 75)
    for title, q in queries:
        cur.execute(q)
        total, srid, val = cur.fetchone()
        print(f"{title:<40} | {total:<16} | {srid:<6} | {val}")

conn.close()
