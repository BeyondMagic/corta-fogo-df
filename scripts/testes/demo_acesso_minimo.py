#!/usr/bin/env python3
"""
Demonstra, no PostgreSQL real, o ETL reverso e o privilegio minimo (migracao V10).

  1. ETL reverso: publica a fila da Gold em operacional.fila_vistoria; repetir nao duplica.
  2. O que a vistoria escreve (status_vistoria) sobrevive a uma nova carga.
  3. fiscal_vistoria (recorte de linha, RLS): ve so a fila ativa, altera so status e observacao.
  4. analista_leitura (recorte de coluna): le o cadastro sem a geometria e nao entra em operacional.
  5. Imovel que sai da fila fica marcado (na_fila = FALSE), some para o fiscal e volta na carga seguinte.

Os papeis sao exercidos com SET ROLE a partir da conexao do dono, sem senhas. Ao final reverte
o que alterou. Sai com codigo 1 se alguma verificacao falhar.

Uso (no compose): docker compose --profile transformacao --profile demonstracao run --rm demo_acesso
"""

import os
import sys
from pathlib import Path

import psycopg2
from psycopg2 import errors

for candidato in (Path(__file__).resolve().parents[2] / "src" / "pipeline", Path(__file__).resolve().parents[2]):
    sys.path.insert(0, str(candidato))

import etl_reverso as etl  # noqa: E402

falhas = []


def checar(ok, descricao):
    print(f"  [{'OK' if ok else 'FALHA'}] {descricao}")
    if not ok:
        falhas.append(descricao)


def nega(cur, sql, params=None):
    """True se o PostgreSQL recusa o comando por falta de privilegio."""
    try:
        cur.execute(sql, params)
        return False
    except errors.InsufficientPrivilege:
        return True


def como(cur, papel):
    cur.execute("RESET ROLE")
    if papel:
        cur.execute(f"SET ROLE {papel}")


def main() -> int:
    conn = psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", "5434")),
        dbname=os.getenv("DB_NAME", "corta-fogo-df"),
        user=os.getenv("DB_USER", "corta-fogo"),
        password=os.getenv("DB_PASSWORD", "corta-fogo"),
    )
    conn.autocommit = True
    cur = conn.cursor()
    linhas = etl.ler_fila(os.getenv("DUCKDB_PATH", "/app/data/warehouse/corta_fogo.duckdb"))
    total = len(linhas)
    conn.autocommit = False

    try:
        print("1. ETL reverso: Gold -> operacional.fila_vistoria")
        primeira = etl.publicar(conn, linhas)
        segunda = etl.publicar(conn, linhas)
        print(f"   1a carga: {primeira['inseridas']} inseridas, {primeira['atualizadas']} atualizadas")
        print(f"   2a carga: {segunda['inseridas']} inseridas, {segunda['atualizadas']} atualizadas")
        conn.autocommit = True
        cur.execute("SELECT count(*), count(*) FILTER (WHERE cadastro_ativo) FROM operacional.fila_vistoria WHERE na_fila")
        na_fila, ativos = cur.fetchone()
        checar(na_fila == total, f"{na_fila} imoveis na fila, igual a Gold ({total})")
        checar(segunda["inseridas"] == 0, "repetir a carga nao insere nada (idempotente)")

        cur.execute("SELECT cod_imovel FROM operacional.fila_vistoria WHERE na_fila AND cadastro_ativo ORDER BY posicao LIMIT 1")
        alvo = cur.fetchone()[0]
        cur.execute("SELECT cod_imovel FROM operacional.fila_vistoria WHERE na_fila AND NOT cadastro_ativo ORDER BY posicao LIMIT 1")
        inativo = cur.fetchone()[0]

        print("2. fiscal_vistoria: recorte de linha (RLS) e de coluna")
        como(cur, "fiscal_vistoria")
        cur.execute("SELECT count(*) FROM operacional.fila_vistoria")
        visivel = cur.fetchone()[0]
        checar(visivel == ativos and visivel < na_fila, f"ve {visivel} de {na_fila} imoveis: so os de cadastro ativo")
        cur.execute("SELECT count(*) FROM operacional.fila_vistoria WHERE cod_imovel = %s", (inativo,))
        checar(cur.fetchone()[0] == 0, "imovel com cadastro nao ativo e invisivel para ele")
        cur.execute(
            "UPDATE operacional.fila_vistoria SET status_vistoria = 'AGENDADA', observacao = 'demo' WHERE cod_imovel = %s",
            (alvo,),
        )
        checar(cur.rowcount == 1, "altera status_vistoria e observacao do imovel visivel")
        cur.execute("UPDATE operacional.fila_vistoria SET status_vistoria = 'REALIZADA' WHERE cod_imovel = %s", (inativo,))
        checar(cur.rowcount == 0, "nao consegue alterar o imovel que a RLS esconde")
        checar(nega(cur, "UPDATE operacional.fila_vistoria SET indice_prioridade = 100 WHERE cod_imovel = %s", (alvo,)),
               "negado: alterar indice_prioridade (coluna de metrica)")
        checar(nega(cur, "DELETE FROM operacional.fila_vistoria WHERE cod_imovel = %s", (alvo,)), "negado: apagar linha")
        checar(nega(cur, "SELECT cod_imovel FROM public.imovel_car LIMIT 1"), "negado: ler public.imovel_car")

        print("3. Nova carga do ETL reverso preserva o que a vistoria escreveu")
        como(cur, None)
        conn.autocommit = False
        etl.publicar(conn, linhas)
        conn.autocommit = True
        cur.execute("SELECT status_vistoria, observacao FROM operacional.fila_vistoria WHERE cod_imovel = %s", (alvo,))
        checar(cur.fetchone() == ("AGENDADA", "demo"), "status_vistoria e observacao continuam como o fiscal deixou")

        print("4. analista_leitura: recorte de coluna")
        como(cur, "analista_leitura")
        cur.execute("SELECT cod_imovel, situacao, area_ha FROM public.imovel_car LIMIT 1")
        checar(cur.fetchone() is not None, "le cod_imovel, situacao e area_ha de imovel_car")
        checar(nega(cur, "SELECT geom FROM public.imovel_car LIMIT 1"), "negado: ler a geometria (geom)")
        checar(nega(cur, "SELECT * FROM public.imovel_car LIMIT 1"), "negado: SELECT * (inclui geom)")
        checar(nega(cur, "SELECT count(*) FROM operacional.fila_vistoria"), "negado: schema operacional")

        print("5. Imovel que sai da fila")
        como(cur, None)
        conn.autocommit = False
        saida = etl.publicar(conn, linhas[:-5])
        conn.autocommit = True
        checar(saida["saidas_da_fila"] == 5, f"{saida['saidas_da_fila']} imoveis marcados com na_fila = FALSE")
        cur.execute("SELECT count(*) FROM operacional.fila_vistoria")
        checar(cur.fetchone()[0] == total, "as linhas continuam na tabela (historico preservado)")
        conn.autocommit = False
        volta = etl.publicar(conn, linhas)
        conn.autocommit = True
        checar(volta["saidas_da_fila"] == 0 and volta["na_fila"] == total, "na carga seguinte voltam todos para a fila")
    finally:
        conn.rollback()
        conn.autocommit = True
        cur.execute("RESET ROLE")
        cur.execute("UPDATE operacional.fila_vistoria SET status_vistoria = 'PENDENTE', observacao = NULL WHERE observacao = 'demo'")
        cur.execute("UPDATE operacional.fila_vistoria SET atualizado_em = NULL WHERE status_vistoria = 'PENDENTE'")
        conn.close()
        print("   Limpeza: status e observacao de teste revertidos")

    print("Acesso minimo e ETL reverso demonstrados sem falhas." if not falhas else f"{len(falhas)} verificacao(oes) falharam.")
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main())
