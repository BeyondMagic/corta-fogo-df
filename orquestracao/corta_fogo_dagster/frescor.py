import os
import sys

from dagster import AssetCheckResult, AssetCheckSeverity, AssetKey, asset_check

sys.path.insert(0, os.getenv("PIPELINE_DIR", "/app/src/pipeline"))
from frescor import SLA_HORAS_PADRAO, medir  # noqa: E402

DUCKDB_PATH = os.getenv("DUCKDB_PATH", "/app/data/warehouse/corta_fogo.duckdb")
DELTA_DIR = os.getenv("DELTA_DIR", "/app/data/delta")

# Chave do modelo dbt no dagster-dbt: schema + nome. Sem o prefixo "gold", o check ficava preso a um
# asset fantasma (sem dependencias) em vez do modelo real do grafo.
PAINEL = AssetKey(["gold", "painel_imoveis_prioritarios"])


@asset_check(
    asset=PAINEL,
    name="frescor_sla",
    description=(
        "SLA de frescor da tabela de consumo do painel (docs/frescor_sla.md): idade da tabela "
        "e dado do lago Delta ainda nao processado, os dois ate SLA_FRESCOR_HORAS."
    ),
)
def frescor_sla() -> AssetCheckResult:
    sla_horas = float(os.getenv("SLA_FRESCOR_HORAS", SLA_HORAS_PADRAO))
    verificacoes = medir(DUCKDB_PATH, DELTA_DIR, sla_horas)
    return AssetCheckResult(
        passed=all(v.ok for v in verificacoes),
        severity=AssetCheckSeverity.ERROR,
        metadata={
            "sla_horas": sla_horas,
            **{v.nome: f"{'OK' if v.ok else 'FORA'}: {v.horas:.1f} h ({v.detalhe})" for v in verificacoes},
        },
    )
