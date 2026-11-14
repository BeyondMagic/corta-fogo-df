from dagster import (
    AssetSelection,
    DefaultScheduleStatus,
    Definitions,
    ScheduleDefinition,
    define_asset_job,
)
from dagster_dbt import DbtCliResource

from .frescor import frescor_sla
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
    description="dbt build de todos os modelos, apos as tabelas Delta de origem, e a verificacao de frescor.",
)

job_frescor = define_asset_job(
    "job_frescor",
    selection=AssetSelection.checks(frescor_sla),
    description="So a verificacao do SLA de frescor da tabela de consumo do painel, sem rodar o dbt.",
)

agenda_transformacao = ScheduleDefinition(
    job=job_transformacao,
    cron_schedule="0 3 * * *",
    execution_timezone="America/Sao_Paulo",
    default_status=DefaultScheduleStatus.RUNNING,
)

# A transformacao diaria deixa a tabela com no maximo 24 h. A verificacao de hora em hora
# acusa o atraso assim que o SLA de 30 h e ultrapassado (docs/frescor_sla.md).
agenda_frescor = ScheduleDefinition(
    job=job_frescor,
    cron_schedule="0 * * * *",
    execution_timezone="America/Sao_Paulo",
    default_status=DefaultScheduleStatus.RUNNING,
)

defs = Definitions(
    assets=[foco_calor_delta, imovel_car_delta, modelos_dbt],
    asset_checks=[frescor_sla],
    jobs=[job_lote_mensal, job_transformacao, job_frescor],
    schedules=[agenda_transformacao, agenda_frescor],
    resources={"dbt": DbtCliResource(project_dir=PROJETO_DBT)},
)
