import os
import sys

from dagster import AssetExecutionContext, AssetKey, MaterializeResult, asset

from .politicas import POLITICA_RETRY

sys.path.insert(0, os.getenv("PIPELINE_DIR", "/app/src/pipeline"))
import etl_reverso as etl  # noqa: E402

DUCKDB_PATH = os.getenv("DUCKDB_PATH", "/app/data/warehouse/corta_fogo.duckdb")


@asset(
    key=AssetKey(["operacional", "fila_vistoria"]),
    deps=[AssetKey(["gold", "painel_imoveis_prioritarios"])],
    retry_policy=POLITICA_RETRY,
    group_name="etl_reverso",
    kinds={"postgres"},
    description=(
        "ETL reverso: publica a fila de vistoria da Gold no PostgreSQL operacional "
        "(operacional.fila_vistoria), com o papel etl_reverso. Idempotente: upsert que "
        "preserva o que a vistoria escreveu (docs/etl_reverso_e_acesso.md)."
    ),
)
def fila_vistoria_postgres(context: AssetExecutionContext) -> MaterializeResult:
    linhas = etl.ler_fila(DUCKDB_PATH)
    conn = etl.conectar()
    try:
        resumo = etl.publicar(conn, linhas)
    finally:
        conn.close()
    context.log.info(f"ETL reverso: {resumo}")
    return MaterializeResult(metadata=resumo)
