#!/usr/bin/env python3
"""
Gera mutacoes reais no OLTP (PostgreSQL) para provar a captura do CDC.

Cada operacao roda em uma transacao propria, para virar um BEGIN/COMMIT
separado no WAL:

1. INSERT: N focos de calor ficticios em foco_calor, com satelite cadastrado
   e coordenadas dentro do DF.
2. UPDATE: retificacao cadastral de um imovel_car existente (area_ha e condicao).
3. DELETE: remocao do ultimo foco inserido na operacao 1 (foco temporario).

foco_calor e insert-only (trigger tg_foco_calor_imutavel, migracao V3). O DELETE
desativa o trigger dentro da mesma transacao e o reativa antes do COMMIT: outras
sessoes nunca veem a tabela sem o trigger, e o unico registro removido e o foco
criado por este script.

Para cada operacao o log mostra: IDs afetados, carimbo do banco, xid da
transacao e LSN apos o COMMIT. O xid e o mesmo que aparece nas linhas
BEGIN/COMMIT do test_decoding, o que permite casar a mutacao com o evento no slot.

Uso:
    python scripts/cdc/gerar_mutacoes_oltp.py
    python scripts/cdc/gerar_mutacoes_oltp.py --focos 3 --cod-imovel DF-5300108-...
    python scripts/cdc/gerar_mutacoes_oltp.py --slot cdc_imovel
"""

import argparse
import logging
import os
import random
import sys
from datetime import timedelta

import psycopg2

# Retangulo interno ao DF (bbox do DF: lon -48.29 a -47.31, lat -16.05 a -15.50),
# recuado das bordas para nao gerar ponto em GO ou MG.
LON_MIN, LON_MAX = -47.95, -47.55
LAT_MIN, LAT_MAX = -15.95, -15.60

CONDICAO_RETIFICADA = "Analisado, em regularizacao ambiental (PRA) - retificacao de teste CDC"

log = logging.getLogger("mutacoes_oltp")


def conectar(args):
    if args.db_url:
        conn = psycopg2.connect(args.db_url)
    else:
        conn = psycopg2.connect(
            host=args.host,
            port=args.port,
            dbname=args.dbname,
            user=args.user,
            password=args.password,
        )
    conn.autocommit = False
    return conn


def xid_atual(cur) -> int:
    cur.execute("SELECT txid_current()")
    return cur.fetchone()[0]


def lsn_atual(conn) -> str:
    with conn.cursor() as cur:
        cur.execute("SELECT pg_current_wal_lsn()::text")
        lsn = cur.fetchone()[0]
    conn.commit()
    return lsn


def escolher_satelite(cur, nome: str | None) -> tuple[int, str]:
    if nome:
        cur.execute("SELECT id_satelite, nome FROM satelite WHERE nome = %s", (nome,))
    else:
        cur.execute(
            "SELECT id_satelite, nome FROM satelite ORDER BY is_referencia DESC, id_satelite LIMIT 1"
        )
    linha = cur.fetchone()
    if linha is None:
        alvo = f"'{nome}'" if nome else "nenhum"
        raise RuntimeError(f"Satelite {alvo} nao cadastrado. Rode a carga (servico load) antes.")
    return linha


def inserir_focos(conn, quantidade: int, nome_satelite: str | None, rng: random.Random) -> list[int]:
    with conn.cursor() as cur:
        xid = xid_atual(cur)
        id_satelite, nome = escolher_satelite(cur, nome_satelite)
        ids = []
        for _ in range(quantidade):
            lon = round(rng.uniform(LON_MIN, LON_MAX), 5)
            lat = round(rng.uniform(LAT_MIN, LAT_MAX), 5)
            atraso_min = rng.randint(5, 180)
            risco = round(rng.uniform(0.1, 1.0), 3)
            cur.execute(
                """
                INSERT INTO foco_calor
                    (id_satelite, data_hora_evento, municipio, bioma, risco_fogo, geom)
                VALUES (
                    %s, now() - %s, 'BRASÍLIA', 'Cerrado', %s,
                    ST_Transform(ST_SetSRID(ST_MakePoint(%s, %s), 4326), 31983)
                )
                RETURNING id_foco, data_hora_evento, data_hora_ingestao
                """,
                (id_satelite, timedelta(minutes=atraso_min), risco, lon, lat),
            )
            id_foco, evento, ingestao = cur.fetchone()
            ids.append(id_foco)
            log.info(
                "INSERT foco_calor id_foco=%s satelite=%s lon=%s lat=%s risco_fogo=%s "
                "data_hora_evento=%s data_hora_ingestao=%s",
                id_foco, nome, lon, lat, risco, evento.isoformat(), ingestao.isoformat(),
            )
    conn.commit()
    log.info("COMMIT INSERT xid=%s lsn=%s focos=%s", xid, lsn_atual(conn), ids)
    return ids


def retificar_imovel(conn, cod_imovel: str | None, rng: random.Random) -> str:
    with conn.cursor() as cur:
        xid = xid_atual(cur)
        if cod_imovel:
            cur.execute(
                "SELECT cod_imovel, area_ha, condicao FROM imovel_car WHERE cod_imovel = %s FOR UPDATE",
                (cod_imovel,),
            )
        else:
            # Amostra aleatoria sem ORDER BY random() na tabela inteira.
            cur.execute(
                """
                SELECT cod_imovel, area_ha, condicao FROM imovel_car TABLESAMPLE SYSTEM (1)
                WHERE area_ha IS NOT NULL LIMIT 1 FOR UPDATE
                """
            )
            if cur.rowcount == 0:
                # Amostra de paginas pode vir vazia; cai para o primeiro imovel.
                cur.execute(
                    """
                    SELECT cod_imovel, area_ha, condicao FROM imovel_car
                    WHERE area_ha IS NOT NULL ORDER BY cod_imovel LIMIT 1 FOR UPDATE
                    """
                )
        linha = cur.fetchone()
        if linha is None:
            raise RuntimeError("Nenhum imovel_car encontrado. Rode a carga (servico load_camadas) antes.")
        cod, area_antes, condicao_antes = linha

        # Retificacao de area entre -2% e +2%, nunca igual a anterior.
        fator = rng.choice([-1, 1]) * rng.uniform(0.005, 0.02)
        cur.execute(
            """
            UPDATE imovel_car
               SET area_ha = round(area_ha * (1 + %s)::numeric, 4),
                   condicao = %s
             WHERE cod_imovel = %s
            RETURNING area_ha, condicao, clock_timestamp()
            """,
            (fator, CONDICAO_RETIFICADA, cod),
        )
        area_depois, condicao_depois, carimbo = cur.fetchone()
        log.info(
            "UPDATE imovel_car cod_imovel=%s area_ha: %s -> %s | condicao: %r -> %r | carimbo=%s",
            cod, area_antes, area_depois, condicao_antes, condicao_depois, carimbo.isoformat(),
        )
    conn.commit()
    log.info("COMMIT UPDATE xid=%s lsn=%s cod_imovel=%s", xid, lsn_atual(conn), cod)
    return cod


def remover_foco_temporario(conn, id_foco: int) -> None:
    with conn.cursor() as cur:
        xid = xid_atual(cur)
        cur.execute("ALTER TABLE foco_calor DISABLE TRIGGER tg_foco_calor_imutavel")
        cur.execute(
            "DELETE FROM foco_calor WHERE id_foco = %s RETURNING id_foco, clock_timestamp()",
            (id_foco,),
        )
        linha = cur.fetchone()
        cur.execute("ALTER TABLE foco_calor ENABLE TRIGGER tg_foco_calor_imutavel")
        if linha is None:
            conn.rollback()
            raise RuntimeError(f"Foco temporario id_foco={id_foco} nao encontrado para DELETE.")
        log.info("DELETE foco_calor id_foco=%s carimbo=%s", linha[0], linha[1].isoformat())
    conn.commit()
    log.info("COMMIT DELETE xid=%s lsn=%s id_foco=%s", xid, lsn_atual(conn), id_foco)


def mostrar_slot(conn, slot: str) -> None:
    """Peek (sem consumir) das mudancas pendentes no slot, para conferencia."""
    with conn.cursor() as cur:
        cur.execute("SELECT plugin FROM pg_replication_slots WHERE slot_name = %s", (slot,))
        if cur.fetchone() is None:
            log.warning("Slot %s nao existe. Pulando conferencia.", slot)
            conn.rollback()
            return
        cur.execute(
            "SELECT lsn::text, xid, data FROM pg_logical_slot_peek_changes(%s, NULL, NULL, 'skip-empty-xacts', '1')",
            (slot,),
        )
        linhas = cur.fetchall()
    conn.commit()
    log.info("Slot %s: %s linhas pendentes (peek, nada consumido).", slot, len(linhas))
    for lsn, xid, data in linhas[-50:]:
        log.info("  lsn=%s xid=%s %s", lsn, xid, data[:200])


def main():
    parser = argparse.ArgumentParser(description="Gera INSERT, UPDATE e DELETE no OLTP para prova do CDC.")
    parser.add_argument("--db-url", default=os.getenv("DATABASE_URL"), help="URL completa (sobrepoe os demais).")
    parser.add_argument("--host", default=os.getenv("DB_HOST", "localhost"))
    parser.add_argument("--port", type=int, default=int(os.getenv("DB_PORT", "5434")))
    parser.add_argument("--dbname", default=os.getenv("DB_NAME", "corta-fogo-df"))
    parser.add_argument("--user", default=os.getenv("DB_USER", "corta-fogo"))
    parser.add_argument("--password", default=os.getenv("DB_PASSWORD", "corta-fogo"))
    parser.add_argument("--focos", type=int, default=2, help="Focos ficticios inseridos (>= 1). O ultimo e removido.")
    parser.add_argument("--satelite", help="Nome do satelite. Padrao: satelite de referencia.")
    parser.add_argument("--cod-imovel", help="Imovel a retificar. Padrao: amostra aleatoria.")
    parser.add_argument("--seed", type=int, help="Semente para coordenadas e retificacao reprodutiveis.")
    parser.add_argument("--slot", help="Slot logico para conferir os eventos via peek ao final (ex: cdc_imovel).")
    args = parser.parse_args()

    if args.focos < 1:
        parser.error("--focos precisa ser >= 1")

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S%z",
    )
    rng = random.Random(args.seed)

    try:
        conn = conectar(args)
    except psycopg2.Error as e:
        log.error("Falha ao conectar ao PostgreSQL: %s", e)
        sys.exit(1)

    try:
        log.info("Inicio. lsn=%s", lsn_atual(conn))
        log.info("Operacao 1/3: INSERT de %s foco(s) ficticio(s)", args.focos)
        ids = inserir_focos(conn, args.focos, args.satelite, rng)

        log.info("Operacao 2/3: UPDATE (retificacao cadastral) em imovel_car")
        cod = retificar_imovel(conn, args.cod_imovel, rng)

        log.info("Operacao 3/3: DELETE do foco temporario id_foco=%s", ids[-1])
        remover_foco_temporario(conn, ids[-1])

        log.info(
            "Resumo: focos inseridos=%s, foco removido=%s, imovel retificado=%s",
            ids, ids[-1], cod,
        )
        if args.slot:
            mostrar_slot(conn, args.slot)
    except (psycopg2.Error, RuntimeError) as e:
        conn.rollback()
        log.error("Falha: %s", e)
        sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
