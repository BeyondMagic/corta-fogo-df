import os
from pathlib import Path
from typing import Any, Mapping

from dagster import AssetExecutionContext, AssetKey
from dagster_dbt import DagsterDbtTranslator, DbtCliResource, DbtProject, dbt_assets

from .politicas import POLITICA_RETRY

PROJETO_DBT = DbtProject(project_dir=Path(os.getenv("DBT_PROJECT_DIR", "/app/transformacao")))


def _manifest_desatualizado() -> bool:
    """True se o manifest nao existe ou algum modelo/macro/config e mais novo que ele."""
    manifest = PROJETO_DBT.manifest_path
    if not manifest.exists():
        return True
    base = PROJETO_DBT.project_dir
    fontes = [*base.glob("models/**/*"), *base.glob("macros/**/*"), base / "dbt_project.yml", base / "profiles.yml"]
    return any(f.is_file() and f.stat().st_mtime > manifest.stat().st_mtime for f in fontes)


# prepare_if_dev() so age sob `dagster dev`; aqui o manifest e gerado explicitamente (dbt parse).
if _manifest_desatualizado():
    PROJETO_DBT.preparer.prepare(PROJETO_DBT)

# As fontes Delta do dbt (source('lakehouse', ...)) viram dependencias dos assets de ingestao.
FONTES_DELTA = {"foco_calor": "foco_calor_delta", "imovel_car": "imovel_car_delta"}


class TradutorCortaFogo(DagsterDbtTranslator):
    def get_asset_key(self, dbt_resource_props: Mapping[str, Any]) -> AssetKey:
        if dbt_resource_props["resource_type"] == "source" and dbt_resource_props["source_name"] == "lakehouse":
            return AssetKey(FONTES_DELTA[dbt_resource_props["name"]])
        return super().get_asset_key(dbt_resource_props)


@dbt_assets(
    manifest=PROJETO_DBT.manifest_path,
    dagster_dbt_translator=TradutorCortaFogo(),
    retry_policy=POLITICA_RETRY,
)
def modelos_dbt(context: AssetExecutionContext, dbt: DbtCliResource):
    yield from dbt.cli(["build"], context=context).stream()
