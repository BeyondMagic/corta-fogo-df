#!/usr/bin/env python3
"""
Verifica a camada analitica aberta (Delta Lake) lendo direto os arquivos com DuckDB.

Checagens que reprovam (exit 1):
- foco_calor: id_foco unico no Delta.
- imovel_car: o conjunto de cod_imovel vivos no Delta (operacao_cdc <> 'D') e igual ao
  do OLTP. O CDC e assincrono, entao a comparacao e repetida ate convergir ou ate --timeout.

Checagens so informativas: contagem de foco_calor frente ao OLTP, arquivos Parquet fisicos
frente ao que o log Delta considera ativo, linhas por particao.

Uso (no compose): docker compose run --rm verificar_lakehouse
"""

import argparse
import os
import sys
import time

import duckdb
import psycopg2

DELTA_DIR = os.getenv("DELTA_DIR", "data/delta")


def conectar_oltp():
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", "5434")),
        dbname=os.getenv("DB_NAME", "corta-fogo-df"),
        user=os.getenv("DB_USER", "corta-fogo"),
        password=os.getenv("DB_PASSWORD", "corta-fogo"),
    )


def esperar_tabela(con, nome, timeout):
    caminho = f"{DELTA_DIR}/{nome}"
    fim = time.time() + timeout
    while True:
        try:
            con.execute(f"SELECT count(*) FROM delta_scan('{caminho}')").fetchone()
            return caminho
        except Exception as erro:
            if time.time() > fim:
                raise SystemExit(f"FALHA: tabela Delta '{caminho}' nao ficou legivel: {erro}")
            time.sleep(3)


def verificar_foco_calor(con, oltp):
    caminho = esperar_tabela(con, "foco_calor", timeout=60)
    total, distintos = con.execute(
        f"SELECT count(*), count(DISTINCT id_foco) FROM delta_scan('{caminho}')"
    ).fetchone()
    particoes = con.execute(
        f"SELECT count(*), min(n), round(avg(n)), max(n) FROM "
        f"(SELECT ano, mes, count(*) AS n FROM delta_scan('{caminho}') GROUP BY ano, mes)"
    ).fetchone()
    arquivos, linhas_fisicas = con.execute(
        f"SELECT count(DISTINCT filename), count(*) FROM read_parquet('{caminho}/**/*.parquet', filename=true)"
    ).fetchone()
    with oltp.cursor() as cur:
        cur.execute("SELECT count(*) FROM foco_calor")
        total_oltp = cur.fetchone()[0]

    print("foco_calor (lote)")
    print(f"  linhas no Delta (delta_scan): {total} | OLTP: {total_oltp} | diferenca: {total_oltp - total} (informativo)")
    print(f"  particoes ano/mes: {particoes[0]} | linhas por particao min/media/max: {particoes[1]}/{int(particoes[2])}/{particoes[3]}")
    print(f"  arquivos Parquet fisicos: {arquivos} | linhas somadas nos arquivos fisicos: {linhas_fisicas} (delta_scan ignora arquivos removidos pelo log)")
    ok = total == distintos
    print(f"  [{'OK' if ok else 'FALHA'}] id_foco unico ({distintos} distintos em {total} linhas)")
    return ok


def verificar_imovel_car(con, oltp, timeout):
    caminho = esperar_tabela(con, "imovel_car", timeout=60)
    with oltp.cursor() as cur:
        cur.execute("SELECT cod_imovel FROM imovel_car")
        chaves_oltp = {linha[0] for linha in cur.fetchall()}

    fim = time.time() + timeout
    while True:
        vivos = {
            linha[0]
            for linha in con.execute(
                f"SELECT cod_imovel FROM delta_scan('{caminho}') WHERE operacao_cdc <> 'D'"
            ).fetchall()
        }
        faltando, sobrando = chaves_oltp - vivos, vivos - chaves_oltp
        if not faltando and not sobrando:
            break
        if time.time() > fim:
            break
        time.sleep(3)

    por_origem = dict(
        con.execute(
            f"SELECT origem_ingestao || '/' || operacao_cdc, count(*) FROM delta_scan('{caminho}') GROUP BY 1"
        ).fetchall()
    )
    print("imovel_car (CDC)")
    print(f"  linhas vivas no Delta: {len(vivos)} | OLTP: {len(chaves_oltp)}")
    print(f"  por origem/operacao: {por_origem}")
    ok = not faltando and not sobrando
    print(f"  [{'OK' if ok else 'FALHA'}] cod_imovel do Delta igual ao do OLTP "
          f"(faltando no Delta: {len(faltando)}, a mais no Delta: {len(sobrando)})")
    if sobrando:
        print(f"  exemplos a mais no Delta: {sorted(sobrando)[:3]}")
    return ok


def main():
    parser = argparse.ArgumentParser(description="Verifica as tabelas Delta com DuckDB.")
    parser.add_argument("--timeout", type=int, default=90, help="Segundos esperando o CDC convergir.")
    args = parser.parse_args()

    con = duckdb.connect()
    con.execute("INSTALL delta; LOAD delta;")
    oltp = conectar_oltp()
    try:
        resultados = [verificar_foco_calor(con, oltp), verificar_imovel_car(con, oltp, args.timeout)]
    finally:
        oltp.close()

    if not all(resultados):
        sys.exit(1)
    print("Lakehouse verificado.")


if __name__ == "__main__":
    main()
