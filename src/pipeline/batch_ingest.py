#!/usr/bin/env python3
"""
Pipeline de ingestao em lote para a tabela aberta Delta Lake (formato Parquet).
Garante idempotencia e suporta eventos fora de ordem temporal (late-arriving data).
"""

import argparse
import hashlib
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import pandas as pd
from deltalake import DeltaTable, WriterProperties, write_deltalake
from pyproj import Transformer

# Diretorio padrao para a tabela Delta Lake
DEFAULT_DELTA_PATH = os.getenv("DELTA_TABLE_PATH", "data/delta/foco_calor")
DEFAULT_CSV_PATH = "data/processed/focos_df_2015_2025.csv"

# ZSTD gerou arquivos 32,4% menores que Snappy no benchmark de compressao (ADR 0002).
WRITER_PROPERTIES = WriterProperties(compression="ZSTD")

_TRANSFORM_4326_31983 = Transformer.from_crs("EPSG:4326", "EPSG:31983", always_xy=True)


def calcular_id_foco(lat: float, lon: float, data_hora_evento: str, satelite: str) -> str:
    """
    Gera um identificador deterministico unico baseado no conteudo do foco.
    Utiliza hash SHA-256 das coordenadas arredondadas, timestamp e satelite.
    """
    lat_fmt = f"{float(lat):.5f}"
    lon_fmt = f"{float(lon):.5f}"
    dt_fmt = str(data_hora_evento).strip()
    sat_fmt = str(satelite).upper().strip()
    payload = f"{lat_fmt}|{lon_fmt}|{dt_fmt}|{sat_fmt}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def preparar_dataframe(df_orig: pd.DataFrame) -> pd.DataFrame:
    """
    Normaliza colunas, gera id_foco deterministico e deriva as particoes ano e mes.
    Remove duplicatas no lote antes da persistencia.
    """
    if df_orig.empty:
        return pd.DataFrame()

    df = df_orig.copy()

    # Normaliza nomes de colunas
    df.columns = [str(c).lower().strip() for c in df.columns]

    # Converte timestamp de evento
    col_evento = next((c for c in df.columns if c in ["data_hora_evento", "data_pas", "data_hora"]), None)
    if not col_evento:
        raise ValueError("Coluna de data/hora do evento nao encontrada no lote.")

    df["data_hora_evento"] = pd.to_datetime(df[col_evento], errors="coerce")
    df = df.dropna(subset=["data_hora_evento"]).copy()

    # Deriva colunas de particao (ano=YYYY, mes=MM)
    df["ano"] = df["data_hora_evento"].dt.strftime("%Y")
    df["mes"] = df["data_hora_evento"].dt.strftime("%m")

    # Garante carimbo de ingestao
    if "data_hora_ingestao" not in df.columns or df["data_hora_ingestao"].isna().all():
        now_utc = datetime.now(timezone.utc)
        df["data_hora_ingestao"] = now_utc
    else:
        df["data_hora_ingestao"] = pd.to_datetime(df["data_hora_ingestao"], errors="coerce")

    # Coordenadas numericas (WGS84) e metricas (31983)
    df["latitude"] = pd.to_numeric(df["latitude"], errors="coerce")
    df["longitude"] = pd.to_numeric(df["longitude"], errors="coerce")
    df = df.dropna(subset=["latitude", "longitude"]).copy()

    x_m, y_m = _TRANSFORM_4326_31983.transform(
        df["longitude"].to_numpy(),
        df["latitude"].to_numpy(),
    )
    df["x_31983"] = x_m
    df["y_31983"] = y_m

    # Linhagem do lote (foco_calor fora do CDC: sempre lote / I)
    df["origem_ingestao"] = "lote"
    df["operacao_cdc"] = "I"

    # Satelite e atributos analiticos
    if "satelite" not in df.columns:
        df["satelite"] = "DESCONHECIDO"
    else:
        df["satelite"] = df["satelite"].fillna("DESCONHECIDO").astype(str).str.strip()

    if "is_satelite_referencia" not in df.columns:
        df["is_satelite_referencia"] = df["satelite"].str.upper().str.contains("AQUA_M-T")
    else:
        df["is_satelite_referencia"] = df["is_satelite_referencia"].astype(bool)

    if "municipio" not in df.columns:
        df["municipio"] = "Brasília"
    else:
        df["municipio"] = df["municipio"].fillna("Brasília").astype(str)

    if "bioma" not in df.columns:
        df["bioma"] = "Cerrado"
    else:
        df["bioma"] = df["bioma"].fillna("Cerrado").astype(str)

    if "risco_fogo" in df.columns:
        df["risco_fogo"] = pd.to_numeric(df["risco_fogo"], errors="coerce")
    else:
        df["risco_fogo"] = None

    # Gera id_foco deterministico caso nao exista
    if "id_foco" not in df.columns or df["id_foco"].isna().any():
        df["id_foco"] = [
            calcular_id_foco(lat, lon, dt, sat)
            for lat, lon, dt, sat in zip(
                df["latitude"],
                df["longitude"],
                df["data_hora_evento"],
                df["satelite"],
            )
        ]
    else:
        df["id_foco"] = df["id_foco"].astype(str)

    # Ordenacao das colunas do contrato docs/modelagem/contrato_tabela_aberta.yaml
    colunas_finais = [
        "id_foco",
        "latitude",
        "longitude",
        "x_31983",
        "y_31983",
        "data_hora_evento",
        "data_hora_ingestao",
        "satelite",
        "is_satelite_referencia",
        "municipio",
        "bioma",
        "risco_fogo",
        "ano",
        "mes",
        "origem_ingestao",
        "operacao_cdc",
    ]

    df_final = df[colunas_finais].copy()

    # Deduplicacao no proprio lote por chave primaria deterministica
    df_final = df_final.drop_duplicates(subset=["id_foco"], keep="first")
    return df_final


def salvar_em_delta(df: pd.DataFrame, delta_path: str) -> dict:
    """
    Grava ou atualiza os dados na tabela Delta Lake garantindo idempotencia e particionamento.
    Aplica MERGE INTO por id_foco quando a tabela ja existir.
    """
    os.makedirs(Path(delta_path).parent, exist_ok=True)

    if df.empty:
        return {
            "status": "vazio",
            "linhas_processadas": 0,
            "inseridos": 0,
            "ignorados": 0,
            "total_final": 0,
        }

    linhas_lote = len(df)

    if not DeltaTable.is_deltatable(delta_path):
        # Tabela nao existe: cria tabela particionada por ano e mes
        write_deltalake(
            delta_path,
            df,
            partition_by=["ano", "mes"],
            mode="error",
            writer_properties=WRITER_PROPERTIES,
        )
        return {
            "status": "criada",
            "linhas_processadas": linhas_lote,
            "inseridos": linhas_lote,
            "ignorados": 0,
            "total_final": linhas_lote,
        }

    # Tabela ja existe: realiza MERGE INTO idempotente por chave primaria
    dt = DeltaTable(delta_path)
    total_anterior = dt.to_pandas().shape[0]

    (
        dt.merge(
            source=df,
            predicate="target.id_foco = source.id_foco",
            source_alias="source",
            target_alias="target",
            writer_properties=WRITER_PROPERTIES,
        )
        .when_not_matched_insert_all()
        .execute()
    )

    # Recarrega a tabela para verificar contagem e integridade
    dt_atualizada = DeltaTable(delta_path)
    total_final = dt_atualizada.to_pandas().shape[0]
    novos_inseridos = total_final - total_anterior
    duplicados_ignorados = linhas_lote - novos_inseridos

    return {
        "status": "mesclada",
        "linhas_processadas": linhas_lote,
        "inseridos": novos_inseridos,
        "ignorados": duplicados_ignorados,
        "total_final": total_final,
    }


def carregar_dados_inpe(ano_inicio: int, ano_fim: int) -> pd.DataFrame:
    """
    Importa e executa a rotina de extracao do INPE para o intervalo de anos informado.
    """
    # Importacao sob demanda do modulo existente de extracao de focos
    script_dir = Path(__file__).resolve().parent
    if str(script_dir) not in sys.path:
        sys.path.insert(0, str(script_dir))

    try:
        from extract_focos import baixar_e_filtrar_ano
    except ImportError:
        raise RuntimeError("Modulo extract_focos nao encontrado em src/pipeline.")

    data_ingestao_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    partes = []

    for ano in range(ano_inicio, ano_fim + 1):
        df_ano = baixar_e_filtrar_ano(ano, data_ingestao_iso)
        if not df_ano.empty:
            partes.append(df_ano)

    if not partes:
        return pd.DataFrame()

    return pd.concat(partes, ignore_index=True)


def executar_ingestao_lote(
    input_path: Optional[str] = None,
    delta_path: str = DEFAULT_DELTA_PATH,
    df_input: Optional[pd.DataFrame] = None,
    ano_inicio: Optional[int] = None,
    ano_fim: Optional[int] = None,
) -> dict:
    """
    Funcao principal de orquestracao da ingestao em lote.
    """
    if df_input is not None:
        df_bruto = df_input
    elif input_path is not None:
        caminho = Path(input_path)
        if not caminho.exists():
            raise FileNotFoundError(f"Arquivo de entrada nao encontrado: {input_path}")
        if caminho.suffix.lower() == ".parquet":
            df_bruto = pd.read_parquet(caminho)
        else:
            df_bruto = pd.read_csv(caminho)
    elif ano_inicio is not None:
        fim = ano_fim if ano_fim is not None else ano_inicio
        print(f"Baixando dados do INPE para o periodo {ano_inicio} a {fim}...")
        df_bruto = carregar_dados_inpe(ano_inicio, fim)
    elif Path(DEFAULT_CSV_PATH).exists():
        print(f"Lendo arquivo de dados padrao: {DEFAULT_CSV_PATH}")
        df_bruto = pd.read_csv(DEFAULT_CSV_PATH)
    else:
        raise ValueError(
            "Nenhuma fonte de dados especificada e arquivo padrao nao encontrado. "
            "Informe --input-path ou --ano/--ano-inicio."
        )

    print(f"Preparando lote de {len(df_bruto)} registros brutos...")
    df_preparado = preparar_dataframe(df_bruto)

    print(f"Gravando na tabela Delta em: {delta_path} (particionado por ano=YYYY/mes=MM)...")
    resultado = salvar_em_delta(df_preparado, delta_path)

    print("\nResumo da Ingestao em Lote:")
    print(f"- Status: {resultado['status']}")
    print(f"- Registros processados: {resultado['linhas_processadas']}")
    print(f"- Novos registros inseridos: {resultado['inseridos']}")
    print(f"- Registros duplicados ignorados: {resultado['ignorados']}")
    print(f"- Total acumulado na tabela Delta: {resultado['total_final']}")

    return resultado


def main():
    parser = argparse.ArgumentParser(
        description="Ingestao em lote de focos de calor na tabela Delta Lake particionada."
    )
    parser.add_argument(
        "--input-path",
        type=str,
        default=None,
        help="Caminho do arquivo de entrada (CSV ou Parquet).",
    )
    parser.add_argument(
        "--delta-path",
        type=str,
        default=DEFAULT_DELTA_PATH,
        help=f"Caminho do diretorio da tabela Delta Lake (padrao: {DEFAULT_DELTA_PATH}).",
    )
    parser.add_argument(
        "--ano",
        type=int,
        default=None,
        help="Ano especifico para baixar do INPE (ex: 2024).",
    )
    parser.add_argument(
        "--ano-inicio",
        type=int,
        default=None,
        help="Ano inicial para baixar do INPE.",
    )
    parser.add_argument(
        "--ano-fim",
        type=int,
        default=None,
        help="Ano final para baixar do INPE.",
    )

    args = parser.parse_args()

    ano_inicio = args.ano if args.ano is not None else args.ano_inicio
    ano_fim = args.ano if args.ano is not None else args.ano_fim

    executar_ingestao_lote(
        input_path=args.input_path,
        delta_path=args.delta_path,
        ano_inicio=ano_inicio,
        ano_fim=ano_fim,
    )


if __name__ == "__main__":
    main()

