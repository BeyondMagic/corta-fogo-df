#!/usr/bin/env python3
"""Garante que o lote e o CDC gravam Parquet com ZSTD, como declara o ADR 0002."""

import sys
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.pipeline.batch_ingest import preparar_dataframe, salvar_em_delta
from src.pipeline.cdc_consumer import aplicar_merge_delta


def codecs_parquet(delta_dir: str) -> set:
    arquivos = list(Path(delta_dir).rglob("*.parquet"))
    assert arquivos, "nenhum arquivo Parquet gravado"
    return {
        pq.ParquetFile(a).metadata.row_group(0).column(i).compression
        for a in arquivos
        for i in range(pq.ParquetFile(a).metadata.num_columns)
    }


def test_lote_grava_zstd():
    bruto = pd.DataFrame(
        {
            "latitude": [-15.7, -15.8],
            "longitude": [-47.9, -47.8],
            "data_hora_evento": ["2024-08-01 10:00:00", "2023-03-02 11:00:00"],
            "satelite": ["AQUA_M-T", "NOAA-20"],
        }
    )
    with tempfile.TemporaryDirectory() as d:
        salvar_em_delta(preparar_dataframe(bruto), f"{d}/foco_calor")
        assert codecs_parquet(f"{d}/foco_calor") == {"ZSTD"}


def test_cdc_grava_zstd_na_criacao_e_no_merge():
    agora = datetime.now(timezone.utc)

    def linha(cod, area, lsn):
        return {
            "cod_imovel": cod,
            "situacao": "AT",
            "condicao": "ok",
            "area_ha": area,
            "data_download": date(2026, 9, 27),
            "geom_ewkb_hex": "0106",
            "data_hora_ingestao": agora,
            "origem_ingestao": "cdc",
            "operacao_cdc": "I",
            "lsn_origem": lsn,
        }

    with tempfile.TemporaryDirectory() as d:
        caminho = f"{d}/imovel_car"
        aplicar_merge_delta(pd.DataFrame([linha("DF-1", 1.0, 10)]), caminho)
        aplicar_merge_delta(pd.DataFrame([linha("DF-1", 2.0, 20), linha("DF-2", 3.0, 21)]), caminho)
        assert codecs_parquet(caminho) == {"ZSTD"}
