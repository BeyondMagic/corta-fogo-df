#!/usr/bin/env python3
"""
Demonstracao ponta a ponta do SCD Tipo 2 de imoveis rurais (Issue #19).

Roda dentro do contêiner do Dagster, sobre uma copia descartavel da tabela Delta
imovel_car e um DuckDB temporario: nada do lakehouse ou do warehouse reais e tocado.
As mudancas cadastrais passam pelo codigo de producao do CDC
(cdc_consumer.converter_evento_para_linha_delta e aplicar_merge_delta).

Passos:
  1. Constroi stg_imoveis_car, snp_imovel_car e dim_imovel_car sobre a copia.
  2. Retifica um imovel (area e condicao) e roda o snapshot de novo.
  3. Reentrega a mesma retificacao (mesmo LSN, como no at-least-once do CDC).
  4. Cancela o imovel (exclusao logica) e roda o snapshot de novo.
  5. Cruza focos ficticios de cada periodo com a dimensao pela validade e confere
     que cada foco recebe a versao do cadastro vigente na data do evento.

Uso: docker compose --profile orquestracao exec dagster_webserver python /opt/dagster/app/demo_scd2_imovel.py
Sai com codigo 1 se alguma verificacao falhar.
"""

import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import duckdb
import pandas as pd
from deltalake import DeltaTable

DELTA_DIR = Path(os.getenv("DELTA_DIR", "/app/data/delta"))
PROJETO_DBT = Path(os.getenv("DBT_PROJECT_DIR", "/app/transformacao"))
sys.path.insert(0, os.getenv("PIPELINE_DIR", "/app/src/pipeline"))

import cdc_consumer as cdc  # noqa: E402

FOCO_ANTIGO = datetime(2020, 8, 15, 15, 0, tzinfo=timezone.utc)
CONDICAO_RETIFICADA = "Retificacao de teste SCD Tipo 2 (demo_scd2_imovel)"
falhas = []


def checar(ok, descricao):
    print(f"  [{'OK' if ok else 'FALHA'}] {descricao}")
    if not ok:
        falhas.append(descricao)


def lsn_texto(lsn: int) -> str:
    return f"{lsn >> 32:X}/{lsn & 0xFFFFFFFF:X}"


class Ambiente:
    def __init__(self, base: Path):
        self.delta = base / "delta"
        self.imovel = self.delta / "imovel_car"
        self.duckdb = base / "demo.duckdb"
        self.base = base
        shutil.copytree(DELTA_DIR / "imovel_car", self.imovel)

    def dbt(self, *selecao):
        env = {**os.environ, "DELTA_DIR": str(self.delta), "DUCKDB_PATH": str(self.duckdb)}
        comando = [
            "dbt", "build", "--project-dir", str(PROJETO_DBT),
            "--target-path", str(self.base / "target"), "--log-path", str(self.base / "logs"),
            "--indirect-selection", "cautious",
            "--select", *selecao,
        ]
        saida = subprocess.run(comando, env=env, capture_output=True, text=True)
        if saida.returncode != 0:
            raise SystemExit(f"dbt build falhou:\n{saida.stdout}\n{saida.stderr}")

    def mudar(self, evento: dict) -> datetime:
        lsn = int(DeltaTable(str(self.imovel)).to_pandas()["lsn_origem"].max()) + 1
        agora = datetime.now(timezone.utc)
        linha = cdc.converter_evento_para_linha_delta(evento, lsn_texto(lsn), agora)
        cdc.aplicar_merge_delta(pd.DataFrame([linha]), str(self.imovel))
        return agora

    def reentregar(self, cod_imovel: str) -> None:
        """Regrava a linha atual com o mesmo LSN e novo carimbo, como faz uma reentrega do slot."""
        linha = DeltaTable(str(self.imovel)).to_pandas().query("cod_imovel == @cod_imovel").iloc[0].to_dict()
        linha["data_hora_ingestao"] = datetime.now(timezone.utc)
        cdc.aplicar_merge_delta(pd.DataFrame([linha]), str(self.imovel))

    def consultar(self, sql: str, params=None) -> pd.DataFrame:
        con = duckdb.connect(str(self.duckdb), read_only=True)
        try:
            con.load_extension("spatial")
            return con.execute(sql, params or []).df()
        finally:
            con.close()


def main():
    if not DeltaTable.is_deltatable(str(DELTA_DIR / "imovel_car")):
        raise SystemExit(f"Tabela Delta {DELTA_DIR / 'imovel_car'} nao encontrada: rode o cdc_consumer antes.")

    base = Path(tempfile.mkdtemp(prefix="demo_scd2_"))
    try:
        amb = Ambiente(base)
        atual = DeltaTable(str(amb.imovel)).to_pandas()
        alvo = atual[atual["operacao_cdc"] != "D"].sort_values("cod_imovel").iloc[0]
        cod, area_original = alvo["cod_imovel"], float(alvo["area_ha"])
        area_retificada = round(area_original * 1.25, 4)
        print(f"Imovel de teste: {cod} (area {area_original} ha); copia Delta em {base}")

        print("1. Carga inicial do snapshot")
        amb.dbt("+dim_imovel_car")
        n_imoveis = len(atual)
        dim = amb.consultar("select count(*) as n, count(*) filter (where is_current) as c from gold.dim_imovel_car")
        checar(int(dim.n[0]) == n_imoveis and int(dim.c[0]) == n_imoveis, f"uma versao corrente por imovel ({n_imoveis})")

        print("2. Retificacao de area e condicao")
        t_retificacao = amb.mudar({
            "cod_imovel": cod, "operacao_cdc": "U", "situacao": alvo["situacao"],
            "condicao": CONDICAO_RETIFICADA, "area_ha": str(area_retificada),
            "data_download": str(alvo["data_download"]), "geom": "unchanged-toast-datum",
        })
        amb.dbt("snp_imovel_car", "dim_imovel_car")

        print("3. Reentrega da retificacao (mesmo LSN)")
        amb.reentregar(cod)
        amb.dbt("snp_imovel_car", "dim_imovel_car")
        snap = amb.consultar("select count(*) as n from snapshots.snp_imovel_car where cod_imovel = ?", [cod])
        checar(int(snap.n[0]) == 3, "snapshot registrou a reentrega como linha propria (3 linhas)")

        print("4. Cancelamento do cadastro (exclusao logica)")
        t_cancelamento = amb.mudar({"cod_imovel": cod, "operacao_cdc": "D"})
        amb.dbt("snp_imovel_car", "dim_imovel_car")

        versoes = amb.consultar(
            "select numero_versao, area_ha, condicao, is_excluido, is_current, dbt_valid_from, dbt_valid_to "
            "from gold.dim_imovel_car where cod_imovel = ? order by numero_versao", [cod],
        )
        print(versoes.to_string(index=False))
        checar(len(versoes) == 3, "dimensao com 3 versoes (original, retificada, cancelada): reentrega descartada")
        checar(versoes.is_current.tolist() == [False, False, True], "apenas a ultima versao e corrente")
        checar(versoes.dbt_valid_from[0].year == 1900, "primeira versao vale para focos anteriores a carga inicial")

        print("5. Cruzamento temporal de focos com a dimensao")
        t_meio = t_retificacao + (t_cancelamento - t_retificacao) / 2
        t_depois = t_cancelamento + timedelta(seconds=1)
        focos = amb.consultar(
            """
            with focos(rotulo, data_hora_evento) as (
                values ('antigo', ?::timestamptz), ('meio', ?::timestamptz), ('depois', ?::timestamptz)
            )
            select f.rotulo, d.numero_versao, d.area_ha, d.is_excluido
            from focos f
            join gold.dim_imovel_car d
              on d.cod_imovel = ?
             and f.data_hora_evento >= d.dbt_valid_from
             and f.data_hora_evento <  d.dbt_valid_to
            """,
            [FOCO_ANTIGO, t_meio, t_depois, cod],
        ).set_index("rotulo")
        checar(len(focos) == 3, "cada foco casa com exatamente uma versao")
        checar(
            focos.loc["antigo", "numero_versao"] == 1 and focos.loc["antigo", "area_ha"] == area_original,
            f"foco de {FOCO_ANTIGO:%Y-%m-%d} usa a versao original ({area_original} ha), nao a retificada",
        )
        checar(focos.loc["meio", "area_ha"] == area_retificada, f"foco apos a retificacao usa a area nova ({area_retificada} ha)")
        checar(bool(focos.loc["depois", "is_excluido"]), "foco apos o cancelamento casa com a versao cancelada")
    finally:
        shutil.rmtree(base, ignore_errors=True)

    print("SCD Tipo 2 demonstrado sem falhas." if not falhas else f"{len(falhas)} verificacao(oes) falharam.")
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main())
