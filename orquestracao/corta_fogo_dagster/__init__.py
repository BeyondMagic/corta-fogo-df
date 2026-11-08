from dagster import (
    AssetSelection,
    DefaultScheduleStatus,
    Definitions,
    ScheduleDefinition,
    define_asset_job,
)
from dagster_dbt import DbtCliResource

from .lote import PARTICOES_MENSAIS, foco_calor_delta, imovel_car_delta
from .transformacao import PROJETO_DBT, modelos_dbt

job_lote_mensal = define_asset_job(
    "job_lote_mensal",
    selection=AssetSelection.assets(foco_calor_delta),
    partitions_def=PARTICOES_MENSAIS,
    description="Ingestao em lote dos focos para o Delta, uma particao mensal por execucao (alvo do backfill).",
)

job_transformacao = define_asset_job(
    "job_transformacao",
    selection=AssetSelection.assets(modelos_dbt),
    description="dbt build de todos os modelos, apos as tabelas Delta de origem.",
)

agenda_transformacao = ScheduleDefinition(
    job=job_transformacao,
    cron_schedule="0 3 * * *",
    execution_timezone="America/Sao_Paulo",
    default_status=DefaultScheduleStatus.RUNNING,
)

defs = Definitions(
    assets=[foco_calor_delta, imovel_car_delta, modelos_dbt],
    jobs=[job_lote_mensal, job_transformacao],
    schedules=[agenda_transformacao],
    resources={"dbt": DbtCliResource(project_dir=PROJETO_DBT)},
)
