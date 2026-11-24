#!/usr/bin/env python3
"""
ETL reverso: devolve a fila de vistoria da camada Gold (DuckDB) ao PostgreSQL operacional.

Origem:  gold.painel_imoveis_prioritarios (dbt-duckdb), um imovel reincidente por linha.
Destino: operacional.fila_vistoria, lida e atualizada por quem vistoria (docs/etl_reverso_e_acesso.md).

O destino e atualizado por upsert, em uma transacao, com o papel etl_reverso (privilegio minimo):
  - o que a vistoria escreveu (status_vistoria, observacao) nunca e sobrescrito;
  - imovel que saiu da fila fica com na_fila = FALSE, sem apagar o historico;
  - rodar duas vezes seguidas deixa a tabela igual.

Uso (no compose): docker compose --profile transformacao run --rm etl_reverso
"""

import os
import sys
from datetime import datetime, timezone

import duckdb
import psycopg2
from psycopg2.extras import execute_values

# (coluna na Gold, coluna no destino)
COLUNAS = [
    ("cod_imovel", "cod_imovel"),
    ("posicao", "posicao"),
    ("codigo_regiao_administrativa", "codigo_regiao_administrativa"),
    ("regiao_administrativa", "regiao_administrativa"),
    ("situacao", "situacao"),
    ("cadastro_ativo", "cadastro_ativo"),
    ("area_ha", "area_ha"),
    ("classificacao_prioridade", "classificacao_prioridade"),
    ("indice_prioridade", "indice_prioridade"),
    ("anos_com_foco", "anos_com_foco"),
    ("primeiro_ano_com_foco", "primeiro_ano_com_foco"),
    ("ultimo_ano_com_foco", "ultimo_ano_com_foco"),
    ("total_focos", "total_focos"),
    ("focos_reserva_legal", "focos_reserva_legal"),
    ("focos_app", "focos_app"),
    ("focos_uc_1km", "focos_uc_1km"),
]


def ler_fila(duckdb_path: str) -> list[tuple]:
    """Le a fila na ordem de prioridade. gerado_em vem como epoca para nao depender de pytz."""
    con = duckdb.connect(duckdb_path, read_only=True)
    try:
        selecao = ", ".join(origem for origem, _ in COLUNAS)
        linhas = con.execute(
            f"SELECT {selecao}, epoch(gerado_em) FROM gold.painel_imoveis_prioritarios ORDER BY posicao"
        ).fetchall()
    finally:
        con.close()
    return [(*linha[:-1], datetime.fromtimestamp(linha[-1], timezone.utc)) for linha in linhas]


def publicar(conn, linhas: list[tuple]) -> dict:
    """Publica a fila no PostgreSQL. Devolve contagens da carga."""
    if not linhas:
        raise ValueError("Fila vazia: recusando marcar todos os imoveis como fora da fila.")

    carga_em = datetime.now(timezone.utc)
    destino = [d for _, d in COLUNAS] + ["gold_gerado_em"]
    atualizaveis = [d for d in destino if d != "cod_imovel"]
    # carga_em e na_fila entram em todo upsert: sao o que diz "esta linha foi confirmada agora".
    colunas_sql = ", ".join(destino + ["na_fila", "carga_em"])
    sets = ", ".join(f"{c} = EXCLUDED.{c}" for c in atualizaveis + ["na_fila", "carga_em"])

    with conn.cursor() as cur:
        cur.execute("SET LOCAL ROLE etl_reverso")
        resultado = execute_values(
            cur,
            f"""
            INSERT INTO operacional.fila_vistoria ({colunas_sql})
            VALUES %s
            ON CONFLICT (cod_imovel) DO UPDATE SET {sets}
            RETURNING (xmax = 0) AS inserida
            """,
            [(*linha, True, carga_em) for linha in linhas],
            fetch=True,
        )
        inseridas = sum(1 for (nova,) in resultado if nova)
        cur.execute(
            "UPDATE operacional.fila_vistoria SET na_fila = FALSE, carga_em = %s WHERE na_fila AND carga_em < %s",
            (carga_em, carga_em),
        )
        saidas_da_fila = cur.rowcount
        cur.execute("SELECT count(*) FROM operacional.fila_vistoria WHERE na_fila")
        na_fila = cur.fetchone()[0]
    conn.commit()

    return {
        "linhas_origem": len(linhas),
        "inseridas": inseridas,
        "atualizadas": len(linhas) - inseridas,
        "saidas_da_fila": saidas_da_fila,
        "na_fila": na_fila,
        "carga_em": carga_em.isoformat(),
    }


def conectar():
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", "5434")),
        dbname=os.getenv("DB_NAME", "corta-fogo-df"),
        user=os.getenv("DB_USER", "corta-fogo"),
        password=os.getenv("DB_PASSWORD", "corta-fogo"),
    )


def main() -> int:
    duckdb_path = os.getenv("DUCKDB_PATH", "/app/data/warehouse/corta_fogo.duckdb")
    linhas = ler_fila(duckdb_path)
    conn = conectar()
    try:
        resumo = publicar(conn, linhas)
    finally:
        conn.close()
    print("ETL reverso concluido:")
    for chave, valor in resumo.items():
        print(f"  {chave}: {valor}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
