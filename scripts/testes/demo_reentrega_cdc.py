#!/usr/bin/env python3
"""
Demonstracao, no PostgreSQL e no Delta reais, da semantica at-least-once com
deduplicacao no destino do CDC de imovel_car.

Usa o codigo de producao (cdc_consumer.processar_lote_cdc) sem alteracao, com um slot
proprio (cdc_demo) e uma tabela Delta propria (descartavel), para nao interferir no
consumidor que ja esta rodando. A queda e simulada no unico ponto que importa: logo
depois do commit no Delta e antes de pg_replication_slot_advance.

Passos:
  1. Cria o slot cdc_demo e faz o snapshot de imovel_car no Delta descartavel.
  2. Altera 3 imoveis no PostgreSQL (3 transacoes).
  3. Consumidor "cai" apos gravar no Delta e antes de avancar o slot.
  4. Consumidor reinicia: o slot reentrega os mesmos eventos e o Delta os recebe de novo.
  5. Compara o Delta apos a queda e apos a reentrega. Reverte as alteracoes no PostgreSQL.

Uso (no compose):   docker compose run --rm demo_reentrega
Uso (no host):      python scripts/testes/demo_reentrega_cdc.py
Sai com codigo 1 se houver duplicata ou divergencia.
"""

import logging
import os
import shutil
import sys
import tempfile
from pathlib import Path

import pandas as pd
import psycopg2
from deltalake import DeltaTable

for candidato in (Path(__file__).resolve().parents[2] / "src" / "pipeline", Path(__file__).resolve().parents[2]):
    sys.path.insert(0, str(candidato))

import cdc_consumer as cdc  # noqa: E402

SLOT = "cdc_demo"
COLUNAS_NEGOCIO = ["cod_imovel", "situacao", "condicao", "area_ha", "operacao_cdc", "lsn_origem"]


class QuedaSimulada(RuntimeError):
    pass


class CursorQueCai:
    """Repassa tudo ao cursor real, mas "mata o processo" ao tentar avancar o slot."""

    def __init__(self, cur):
        self._cur = cur

    def __enter__(self):
        self._cur.__enter__()
        return self

    def __exit__(self, *args):
        return self._cur.__exit__(*args)

    def execute(self, sql, params=None):
        if "pg_replication_slot_advance" in sql:
            raise QuedaSimulada("processo morto depois do commit no Delta e antes do advance do slot")
        return self._cur.execute(sql, params)

    def __getattr__(self, nome):
        return getattr(self._cur, nome)


class ConexaoQueCai:
    def __init__(self, conn):
        self._conn = conn

    def cursor(self):
        return CursorQueCai(self._conn.cursor())

    def __getattr__(self, nome):
        return getattr(self._conn, nome)


def conectar():
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", "5434")),
        dbname=os.getenv("DB_NAME", "corta-fogo-df"),
        user=os.getenv("DB_USER", "corta-fogo"),
        password=os.getenv("DB_PASSWORD", "corta-fogo"),
    )


def eventos_pendentes(conn) -> int:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM pg_logical_slot_peek_changes(%s, NULL, NULL, 'skip-empty-xacts', '1') "
            "WHERE data LIKE 'table public.imovel_car:%%'",
            (SLOT,),
        )
        n = cur.fetchone()[0]
    conn.rollback()
    return n


def lsn_confirmado(conn) -> str:
    with conn.cursor() as cur:
        cur.execute("SELECT confirmed_flush_lsn::text FROM pg_replication_slots WHERE slot_name = %s", (SLOT,))
        valor = cur.fetchone()[0]
    conn.rollback()
    return valor


def estado_delta(caminho: str) -> pd.DataFrame:
    df = DeltaTable(caminho).to_pandas()
    return df[COLUNAS_NEGOCIO].sort_values("cod_imovel").reset_index(drop=True)


def main() -> int:
    logging.getLogger("cdc_consumer").setLevel(logging.WARNING)
    delta_dir = tempfile.mkdtemp(prefix="delta_demo_")
    caminho = os.path.join(delta_dir, "imovel_car")
    conn = conectar()
    alterados, falhas = [], []

    def checar(ok: bool, descricao: str):
        print(f"  [{'OK' if ok else 'FALHA'}] {descricao}")
        if not ok:
            falhas.append(descricao)

    try:
        print("1. Slot proprio e snapshot inicial no Delta descartavel")
        lsn0 = cdc.garantir_slot(conn, SLOT)
        conn.commit()
        total = cdc.executar_snapshot_inicial(conn, caminho, lsn0)
        conn.commit()
        print(f"   slot '{SLOT}' criado em {lsn0}; snapshot com {total} imoveis")

        print("2. Tres retificacoes reais no PostgreSQL (uma transacao cada)")
        with conn.cursor() as cur:
            cur.execute("SELECT cod_imovel, area_ha, condicao FROM imovel_car ORDER BY cod_imovel LIMIT 3")
            alterados = cur.fetchall()
        conn.commit()
        for cod, _area, _condicao in alterados:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE imovel_car SET area_ha = area_ha + 1, condicao = 'demo reentrega' WHERE cod_imovel = %s",
                    (cod,),
                )
            conn.commit()
        pendentes = eventos_pendentes(conn)
        print(f"   eventos de imovel_car pendentes no slot: {pendentes}")
        checar(pendentes >= 3, "slot reteve os eventos das 3 retificacoes")

        lsn_antes = lsn_confirmado(conn)

        print("3. Queda: o consumidor grava no Delta e morre antes de avancar o slot")
        try:
            cdc.processar_lote_cdc(ConexaoQueCai(conn), SLOT, caminho)
            checar(False, "a queda simulada deveria ter interrompido o consumidor")
        except QuedaSimulada as erro:
            conn.rollback()
            print(f"   {erro}")
        apos_queda = estado_delta(caminho)
        pend_queda = eventos_pendentes(conn)
        print(f"   Delta ja reflete as mudancas; slot ainda confirmado em {lsn_confirmado(conn)} (antes: {lsn_antes})")
        checar(lsn_confirmado(conn) == lsn_antes, "slot NAO avancou")
        checar(pend_queda == pendentes, f"os mesmos {pend_queda} eventos continuam pendentes")
        checar(int((apos_queda.condicao == "demo reentrega").sum()) == 3, "Delta recebeu as 3 retificacoes")

        print("4. Reinicio: o slot reentrega os mesmos eventos e o Delta os recebe de novo")
        mutacoes, ultimo = cdc.processar_lote_cdc(conn, SLOT, caminho)
        apos_reentrega = estado_delta(caminho)
        pend_final = eventos_pendentes(conn)
        print(f"   eventos reaplicados: {mutacoes} | slot avancado ate {ultimo} | pendentes agora: {pend_final}")

        print("5. Efeito nos dados")
        checar(len(apos_reentrega) == total, f"linhas no Delta: {len(apos_reentrega)} (snapshot: {total}), sem duplicatas")
        checar(apos_reentrega.cod_imovel.is_unique, "cod_imovel unico")
        checar(apos_reentrega.equals(apos_queda), "estado do Delta apos a reentrega identico ao de antes dela")
        checar(pend_final == 0, "slot esvaziado depois da reentrega")
    finally:
        # Reverte as retificacoes de teste (o consumidor de producao tambem recebe essa reversao).
        conn.rollback()
        with conn.cursor() as cur:
            for cod, area, condicao in alterados:
                cur.execute(
                    "UPDATE imovel_car SET area_ha = %s, condicao = %s WHERE cod_imovel = %s AND condicao = 'demo reentrega'",
                    (area, condicao, cod),
                )
            cur.execute("SELECT pg_drop_replication_slot(slot_name) FROM pg_replication_slots WHERE slot_name = %s", (SLOT,))
        conn.commit()
        conn.close()
        shutil.rmtree(delta_dir, ignore_errors=True)
        print("   Limpeza: retificacoes revertidas, slot cdc_demo removido, Delta descartavel apagado")

    print("Demonstracao concluida sem falhas." if not falhas else f"{len(falhas)} verificacao(oes) falharam.")
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main())
