#!/usr/bin/env python3
"""
Consumidor CDC para sincronizacao continua de imovel_car na camada aberta Delta Lake.

Atende a Tarefa #09 (GH #3) e implementa a arquitetura oficial da E2:
- Decodificacao logica nativa do PostgreSQL via plugin test_decoding (D2)
- Auto-inicializacao do slot cdc_imovel e snapshot inicial automatico (D3)
- Gravacao na tabela aberta data/delta/imovel_car conforme contrato de dados (D4)
- Semantica de entrega at-least-once com deduplicacao idempotente por LSN (D5)
"""

import argparse
import logging
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import psycopg2
import pyarrow as pa
from deltalake import DeltaTable, write_deltalake

# Esquema padrao da tabela aberta Delta Lake para imovel_car (contrato_tabela_aberta.yaml)
SCHEMA_IMOVEL_DELTA = pa.schema(
    [
        ("cod_imovel", pa.string()),
        ("situacao", pa.string()),
        ("condicao", pa.string()),
        ("area_ha", pa.float64()),
        ("data_download", pa.date32()),
        ("geom_ewkb_hex", pa.string()),
        ("data_hora_ingestao", pa.timestamp("us", tz="UTC")),
        ("origem_ingestao", pa.string()),
        ("operacao_cdc", pa.string()),
        ("lsn_origem", pa.int64()),
    ]
)

# Diretorio padrao da tabela Delta Lake de imovel_car
DEFAULT_DELTA_PATH = os.getenv("DELTA_IMOVEL_PATH", "data/delta/imovel_car")
DEFAULT_SLOT_NAME = os.getenv("CDC_SLOT_NAME", "cdc_imovel")

log = logging.getLogger("cdc_consumer")


def lsn_para_int(lsn_str: str) -> int:
    """Converte LSN no formato 'X/Y' do PostgreSQL para um inteiro de 64 bits."""
    if not lsn_str or "/" not in lsn_str:
        return 0
    parte_alta, parte_baixa = lsn_str.strip().split("/", 1)
    return (int(parte_alta, 16) << 32) | int(parte_baixa, 16)


def conectar_postgres(
    host: str = "localhost",
    port: int = 5434,
    dbname: str = "corta-fogo-df",
    user: str = "corta-fogo",
    password: str = "corta-fogo",
    db_url: Optional[str] = None,
):
    """Cria conexao com o PostgreSQL."""
    if db_url:
        conn = psycopg2.connect(db_url)
    else:
        conn = psycopg2.connect(
            host=host,
            port=port,
            dbname=dbname,
            user=user,
            password=password,
        )
    conn.autocommit = False
    return conn


def garantir_slot(conn, slot_name: str = DEFAULT_SLOT_NAME) -> str:
    """
    Verifica se o slot logico existe; se nao, cria o slot usando test_decoding.
    Retorna o confirmed_flush_lsn ou LSN atual do banco.
    """
    with conn.cursor() as cur:
        cur.execute(
            "SELECT confirmed_flush_lsn::text FROM pg_replication_slots WHERE slot_name = %s",
            (slot_name,),
        )
        linha = cur.fetchone()
        if linha:
            lsn_retorno = linha[0]
            log.info("Slot logico '%s' ja existente. confirmed_flush_lsn: %s", slot_name, lsn_retorno)
        else:
            log.info("Criando slot logico '%s' com plugin test_decoding...", slot_name)
            cur.execute(
                "SELECT pg_create_logical_replication_slot(%s, 'test_decoding')",
                (slot_name,),
            )
            cur.execute("SELECT pg_current_wal_lsn()::text")
            lsn_retorno = cur.fetchone()[0]
            log.info("Slot '%s' criado com sucesso. LSN inicial: %s", slot_name, lsn_retorno)
    conn.commit()
    return lsn_retorno or "0/0"


def preparar_tabela_arrow(df: pd.DataFrame) -> pa.Table:
    """Garante que todas as colunas do contrato existam com tipos PyArrow compativeis."""
    arrays = {}
    for campo in SCHEMA_IMOVEL_DELTA:
        nome = campo.name
        if nome in df.columns:
            serie = df[nome]
            if campo.type == pa.date32():
                serie = pd.to_datetime(serie, errors="coerce").dt.date
            elif campo.type == pa.timestamp("us", tz="UTC"):
                serie = pd.to_datetime(serie, utc=True, errors="coerce")
            elif campo.type == pa.float64():
                serie = pd.to_numeric(serie, errors="coerce")
            elif campo.type == pa.int64():
                serie = pd.to_numeric(serie, errors="coerce").fillna(0).astype("int64")
            elif campo.type == pa.string():
                serie = serie.where(serie.notna(), None).astype(object)
            arrays[nome] = pa.array(serie, type=campo.type)
        else:
            arrays[nome] = pa.nulls(len(df), type=campo.type)
    return pa.Table.from_pydict(arrays, schema=SCHEMA_IMOVEL_DELTA)


def executar_snapshot_inicial(conn, delta_path: str = DEFAULT_DELTA_PATH, lsn_inicial: str = "0/0") -> int:
    """
    Executa snapshot completo de public.imovel_car para a tabela Delta Lake.
    Conforme Decisao D3 e docs/modelagem/contrato_tabela_aberta.yaml.
    """
    os.makedirs(Path(delta_path).parent, exist_ok=True)
    lsn_numerico = lsn_para_int(lsn_inicial)

    sql = """
    SELECT
        cod_imovel,
        situacao,
        condicao,
        area_ha::double precision AS area_ha,
        data_download,
        encode(ST_AsEWKB(geom), 'hex') AS geom_ewkb_hex,
        NOW() AT TIME ZONE 'UTC' AS data_hora_ingestao,
        'snapshot'::text AS origem_ingestao,
        'I'::text AS operacao_cdc,
        %s::bigint AS lsn_origem
    FROM public.imovel_car;
    """

    log.info("Extraindo snapshot completo de public.imovel_car do PostgreSQL...")
    with conn.cursor() as cur:
        cur.execute(sql, (lsn_numerico,))
        colunas = [desc[0] for desc in cur.description]
        linhas = cur.fetchall()

    df = pd.DataFrame(linhas, columns=colunas)
    if df.empty:
        log.warning("Tabela public.imovel_car esta vazia. Nenhum registro no snapshot.")
        return 0

    df["data_hora_ingestao"] = pd.to_datetime(df["data_hora_ingestao"], utc=True)
    df["data_download"] = pd.to_datetime(df["data_download"]).dt.date

    tabela_arrow = preparar_tabela_arrow(df)
    log.info("Gravando %d registros no snapshot Delta Lake em '%s'...", len(df), delta_path)
    write_deltalake(delta_path, tabela_arrow, mode="overwrite")
    log.info("Snapshot gravado com sucesso.")
    return len(df)


def parse_valores_tupla(dados_tupla: str) -> Dict[str, Any]:
    """
    Faz o parsing de tuplas do test_decoding nos formatos suportados pelo PostgreSQL:
    - Oficial: coluna[tipo]:'valor' ou coluna[tipo]:123 ou geom[tipo]:unchanged-toast-datum
    - Legado/mock: coluna['valor'] ou coluna[123]
    """
    resultado: Dict[str, Any] = {}
    padrao = re.compile(r"(\w+)\[([^\]]*)\](?::('(?:[^']|'')*'|\S+))?")
    for match in padrao.finditer(dados_tupla):
        col = match.group(1)
        tipo_ou_val = match.group(2)
        val_direto = match.group(3)
        val = val_direto if val_direto is not None else tipo_ou_val

        if val == "null":
            resultado[col] = None
        elif val == "unchanged-toast-datum":
            resultado[col] = "unchanged-toast-datum"
        elif val.startswith("'") and val.endswith("'"):
            resultado[col] = val[1:-1].replace("''", "'")
        else:
            resultado[col] = val
    return resultado


def parse_linha_test_decoding(data_str: str) -> Optional[Dict[str, Any]]:
    """
    Analisa uma mensagem de mudanca gerada pelo test_decoding.
    Retorna dicionario com operacao_cdc ('I', 'U', 'D') e dados da tupla,
    ou None caso a mensagem nao seja referente a public.imovel_car.
    """
    if not data_str.startswith("table public.imovel_car:"):
        return None

    # Exemplo: table public.imovel_car: INSERT: cod_imovel['...'] ...
    resto = data_str[len("table public.imovel_car:") :].strip()

    if resto.startswith("INSERT:"):
        dados_tupla = resto[len("INSERT:") :].strip()
        campos = parse_valores_tupla(dados_tupla)
        campos["operacao_cdc"] = "I"
        return campos

    elif resto.startswith("UPDATE:"):
        # Exemplo: UPDATE: old-key: cod_imovel['...'] new-tuple: cod_imovel['...'] ...
        # Ou: UPDATE: new-tuple: ...
        corpo = resto[len("UPDATE:") :].strip()
        cod_imovel_old = None

        if "old-key:" in corpo:
            partes = corpo.split("new-tuple:", 1)
            parte_old = partes[0].replace("old-key:", "").strip()
            old_campos = parse_valores_tupla(parte_old)
            cod_imovel_old = old_campos.get("cod_imovel")
            dados_new = partes[1].strip() if len(partes) > 1 else ""
        else:
            dados_new = corpo.replace("new-tuple:", "").strip()

        campos = parse_valores_tupla(dados_new)
        # O old-key sempre traz a PK real. No new-tuple a PK pode vir como
        # unchanged-toast-datum quando o valor esta fora de linha.
        if cod_imovel_old:
            campos["cod_imovel"] = cod_imovel_old

        campos["operacao_cdc"] = "U"
        return campos

    elif resto.startswith("DELETE:"):
        # Exemplo: DELETE: cod_imovel['...'] ou DELETE: old-key: cod_imovel['...']
        corpo = resto[len("DELETE:") :].replace("old-key:", "").strip()
        campos = parse_valores_tupla(corpo)
        campos["operacao_cdc"] = "D"
        return campos

    return None


def converter_evento_para_linha_delta(
    evento: Dict[str, Any], lsn_str: str, now_utc: datetime
) -> Optional[Dict[str, Any]]:
    """Normaliza o evento parseado para o esquema estrito de imovel_car_analitico."""
    cod_imovel = evento.get("cod_imovel")
    if not cod_imovel:
        return None

    op = evento.get("operacao_cdc", "I")
    area_ha = evento.get("area_ha")
    if area_ha is not None and area_ha != "unchanged-toast-datum":
        try:
            area_ha = float(area_ha)
        except (ValueError, TypeError):
            area_ha = None
    else:
        area_ha = None

    data_download = evento.get("data_download")
    if data_download and data_download != "unchanged-toast-datum":
        try:
            data_download = pd.to_datetime(data_download).date()
        except Exception:
            data_download = None
    else:
        data_download = None

    geom = evento.get("geom")
    geom_ewkb_hex = None
    if geom and geom != "unchanged-toast-datum":
        geom_ewkb_hex = str(geom)
    elif geom == "unchanged-toast-datum":
        geom_ewkb_hex = "unchanged-toast-datum"

    return {
        "cod_imovel": str(cod_imovel),
        "situacao": evento.get("situacao"),
        "condicao": evento.get("condicao"),
        "area_ha": area_ha,
        "data_download": data_download,
        "geom_ewkb_hex": geom_ewkb_hex,
        "data_hora_ingestao": now_utc,
        "origem_ingestao": "cdc",
        "operacao_cdc": op,
        "lsn_origem": lsn_para_int(lsn_str),
    }


def aplicar_merge_delta(df_mudancas: pd.DataFrame, delta_path: str = DEFAULT_DELTA_PATH) -> int:
    """
    Aplica MERGE idempotente na tabela Delta Lake garantindo:
    - matched com lsn_origem >= target.lsn_origem: atualiza
    - matched com lsn menor: ignora
    - unchanged-toast-datum preserva target.geom_ewkb_hex
    - delete: grava operacao_cdc='D' sem apagar a linha (soft-delete)
    """
    if df_mudancas.empty:
        return 0

    tabela_arrow = preparar_tabela_arrow(df_mudancas)

    if not DeltaTable.is_deltatable(delta_path):
        log.info("Tabela Delta '%s' nao existe. Criando com o lote atual...", delta_path)
        write_deltalake(delta_path, tabela_arrow, mode="error")
        return len(df_mudancas)

    dt = DeltaTable(delta_path)

    # Expressao de preservacao de geometria caso seja unchanged-toast-datum ou DELETE sem geometria
    atualizacao = {
        "situacao": "source.situacao",
        "condicao": "source.condicao",
        "area_ha": "source.area_ha",
        "data_download": "source.data_download",
        "geom_ewkb_hex": "CASE WHEN source.geom_ewkb_hex IS NOT NULL AND source.geom_ewkb_hex != 'unchanged-toast-datum' THEN source.geom_ewkb_hex ELSE target.geom_ewkb_hex END",
        "data_hora_ingestao": "source.data_hora_ingestao",
        "origem_ingestao": "source.origem_ingestao",
        "operacao_cdc": "source.operacao_cdc",
        "lsn_origem": "source.lsn_origem",
    }

    (
        dt.merge(
            source=tabela_arrow,
            predicate="target.cod_imovel = source.cod_imovel",
            source_alias="source",
            target_alias="target",
        )
        .when_matched_update(
            predicate="source.lsn_origem >= target.lsn_origem",
            updates=atualizacao,
        )
        .when_not_matched_insert_all()
        .execute()
    )

    return len(df_mudancas)


def processar_lote_cdc(
    conn, slot_name: str = DEFAULT_SLOT_NAME, delta_path: str = DEFAULT_DELTA_PATH, lote_max: int = 1000
) -> Tuple[int, Optional[str]]:
    """
    Executa uma rodada de consumo do slot logico:
    1. Faz peek das mudancas pendentes
    2. Filtra e processa as mutacoes de public.imovel_car
    3. Aplica o MERGE no Delta Lake
    4. Avanca o slot com confirmacao estrita
    """
    with conn.cursor() as cur:
        cur.execute(
            "SELECT lsn::text, xid, data FROM pg_logical_slot_peek_changes(%s, NULL, %s, 'skip-empty-xacts', '1')",
            (slot_name, lote_max),
        )
        linhas = cur.fetchall()

    if not linhas:
        return 0, None

    ultimo_lsn = linhas[-1][0]
    now_utc = datetime.now(timezone.utc)
    registros_cdc: List[Dict[str, Any]] = []

    for lsn_str, xid, data_str in linhas:
        evento = parse_linha_test_decoding(data_str)
        if not evento:
            continue
        linha_delta = converter_evento_para_linha_delta(evento, lsn_str, now_utc)
        if linha_delta:
            registros_cdc.append(linha_delta)

    if registros_cdc:
        df_mudancas = pd.DataFrame(registros_cdc)
        # Deduplica dentro do proprio micro-lote mantendo o maior LSN por imovel
        df_mudancas = df_mudancas.sort_values("lsn_origem").groupby("cod_imovel").last().reset_index()
        log.info("Aplicando MERGE de %d mutacoes de imovel_car no Delta Lake...", len(df_mudancas))
        aplicar_merge_delta(df_mudancas, delta_path)

    # Avanca o slot logico apenas apos a gravacao concluida no Delta Lake (At-Least-Once)
    with conn.cursor() as cur:
        cur.execute("SELECT pg_replication_slot_advance(%s, %s::pg_lsn)", (slot_name, ultimo_lsn))
    conn.commit()

    log.info("Slot '%s' avancado com sucesso ate o LSN %s.", slot_name, ultimo_lsn)
    return len(registros_cdc), ultimo_lsn


def executar_consumidor(
    host: str = "localhost",
    port: int = 5434,
    dbname: str = "corta-fogo-df",
    user: str = "corta-fogo",
    password: str = "corta-fogo",
    db_url: Optional[str] = None,
    delta_path: str = DEFAULT_DELTA_PATH,
    slot_name: str = DEFAULT_SLOT_NAME,
    modo_once: bool = False,
    snapshot_only: bool = False,
    intervalo: float = 2.0,
):
    """Orquestra o ciclo de vida completo do consumidor CDC."""
    conn = conectar_postgres(host, port, dbname, user, password, db_url)
    try:
        lsn_inicial = garantir_slot(conn, slot_name)

        # Se solicitado ou se a tabela Delta ainda nao existir, realiza o snapshot
        if snapshot_only or not DeltaTable.is_deltatable(delta_path):
            log.info("Tabela Delta nao encontrada ou --snapshot-only ativo. Iniciando snapshot inicial...")
            executar_snapshot_inicial(conn, delta_path, lsn_inicial)
            if snapshot_only:
                log.info("Snapshot finalizado com sucesso (--snapshot-only).")
                return

        log.info("Iniciando escuta de mudancas CDC no slot '%s'...", slot_name)
        while True:
            mutacoes, ultimo_lsn = processar_lote_cdc(conn, slot_name, delta_path)
            if mutacoes > 0:
                log.info("Processadas %d mutacoes nesta rodada.", mutacoes)
            if modo_once:
                if ultimo_lsn is None:
                    log.info("Nenhuma mudanca pendente no slot '%s'. Concluido (--once).", slot_name)
                    break
                continue
            time.sleep(intervalo)

    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(description="Consumidor CDC para sincronizacao continua de imovel_car no Delta Lake.")
    parser.add_argument("--db-url", default=os.getenv("DATABASE_URL"), help="URL de conexao com o PostgreSQL.")
    parser.add_argument("--host", default=os.getenv("DB_HOST", "localhost"))
    parser.add_argument("--port", type=int, default=int(os.getenv("DB_PORT", "5434")))
    parser.add_argument("--dbname", default=os.getenv("DB_NAME", "corta-fogo-df"))
    parser.add_argument("--user", default=os.getenv("DB_USER", "corta-fogo"))
    parser.add_argument("--password", default=os.getenv("DB_PASSWORD", "corta-fogo"))
    parser.add_argument("--delta-path", default=DEFAULT_DELTA_PATH, help="Caminho da tabela Delta Lake.")
    parser.add_argument("--slot", default=DEFAULT_SLOT_NAME, help="Nome do slot logico.")
    parser.add_argument("--once", action="store_true", help="Processa apenas as mudancas pendentes e finaliza.")
    parser.add_argument("--snapshot-only", action="store_true", help="Gera apenas o snapshot base e finaliza.")
    parser.add_argument("--interval", type=float, default=2.0, help="Intervalo de polling em segundos.")

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S%z",
    )

    executar_consumidor(
        host=args.host,
        port=args.port,
        dbname=args.dbname,
        user=args.user,
        password=args.password,
        db_url=args.db_url,
        delta_path=args.delta_path,
        slot_name=args.slot,
        modo_once=args.once,
        snapshot_only=args.snapshot_only,
        intervalo=args.interval,
    )


if __name__ == "__main__":
    main()
