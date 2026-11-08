import os
import sys
from pathlib import Path

import pandas as pd
from dagster import (
    AssetExecutionContext,
    AssetSpec,
    Failure,
    MaterializeResult,
    MonthlyPartitionsDefinition,
    asset,
)

from .politicas import POLITICA_RETRY

sys.path.insert(0, os.getenv("PIPELINE_DIR", "/app/src/pipeline"))
from batch_ingest import preparar_dataframe, salvar_em_delta  # noqa: E402

CSV_FOCOS = os.getenv("CSV_FOCOS", "/app/data/processed/focos_df_2015_2025.csv")
DELTA_FOCOS = os.path.join(os.getenv("DELTA_DIR", "/app/data/delta"), "foco_calor")

# 132 particoes mensais, jan/2015 a dez/2025: as mesmas ano=YYYY/mes=MM da tabela Delta.
PARTICOES_MENSAIS = MonthlyPartitionsDefinition(start_date="2015-01-01", end_date="2026-01-01")


@asset(
    partitions_def=PARTICOES_MENSAIS,
    retry_policy=POLITICA_RETRY,
    group_name="lote",
    compute_kind="deltalake",
    description=(
        "Focos de calor do INPE na tabela Delta, uma particao por mes do evento. "
        "Reexecutar uma particao e idempotente: o MERGE so insere id_foco ainda ausente."
    ),
)
def foco_calor_delta(context: AssetExecutionContext) -> MaterializeResult:
    # Falha induzida e deterministica: as N primeiras tentativas de cada no falham.
    # Com FALHAS_INDUZIDAS=2 o no passa na terceira tentativa, provando o retry.
    falhas = int(os.getenv("FALHAS_INDUZIDAS", "0"))
    if context.retry_number < falhas:
        raise Failure(
            description=f"Falha induzida {context.retry_number + 1}/{falhas} (FALHAS_INDUZIDAS={falhas})",
            allow_retries=True,
        )

    ano, mes = context.partition_key[:4], context.partition_key[5:7]
    preparado = preparar_dataframe(pd.read_csv(CSV_FOCOS))
    da_particao = preparado[(preparado["ano"] == ano) & (preparado["mes"] == mes)]
    resultado = salvar_em_delta(da_particao, DELTA_FOCOS)
    context.log.info(f"Particao ano={ano}/mes={mes}: {resultado}")

    return MaterializeResult(
        metadata={
            "particao": f"ano={ano}/mes={mes}",
            "linhas_do_lote": resultado["linhas_processadas"],
            "inseridas": resultado["inseridos"],
            "ignoradas_por_duplicidade": resultado["ignorados"],
            "total_na_tabela_delta": resultado["total_final"],
        }
    )


# Alimentada fora do Dagster pelo servico cdc_consumer (slot de replicacao logica).
imovel_car_delta = AssetSpec(
    key="imovel_car_delta",
    group_name="cdc",
    kinds={"deltalake"},
    description="Imoveis do SICAR na tabela Delta, mantidos pelo cdc_consumer.py a partir do WAL do PostgreSQL.",
)
