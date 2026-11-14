#!/usr/bin/env python3
"""
Frescor e SLA da tabela de consumo do painel (gold.painel_imoveis_prioritarios).

Duas verificacoes, as duas com o mesmo limite (SLA_FRESCOR_HORAS, padrao 30 horas):

1. Processamento: idade da tabela, agora - max(gerado_em). gerado_em e o instante da
   execucao do dbt que gerou a tabela.
2. Fonte: ha quanto tempo existe no lago Delta (foco_calor e imovel_car) uma linha
   gravada depois de gerado_em, ou seja, um dado que o painel ainda nao processou.

Sai com codigo 1 se alguma passa do SLA. Detalhes e justificativa do limite em
docs/frescor_sla.md.

Uso (no compose): docker compose --profile transformacao run --rm frescor
"""

import argparse
import os
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import List, Optional

SLA_HORAS_PADRAO = 30.0
TABELA_CONSUMO = "gold.painel_imoveis_prioritarios"
TABELAS_DELTA = ("foco_calor", "imovel_car")


@dataclass
class Verificacao:
    nome: str
    ok: bool
    horas: float
    detalhe: str

    def linha(self, sla_horas: float) -> str:
        estado = "OK  " if self.ok else "FORA"
        return f"{estado} {self.nome}: {self.horas:.1f} de {sla_horas:g} horas ({self.detalhe})"


def _horas(intervalo: timedelta) -> float:
    return max(intervalo.total_seconds(), 0.0) / 3600.0


def avaliar_processamento(gerado_em: Optional[datetime], agora: datetime, sla_horas: float) -> Verificacao:
    """Idade da tabela de consumo. Tabela vazia ou ausente viola o SLA."""
    nome = f"processamento ({TABELA_CONSUMO})"
    if gerado_em is None:
        return Verificacao(nome, False, float("inf"), "tabela vazia ou ausente")
    horas = _horas(agora - gerado_em)
    return Verificacao(nome, horas <= sla_horas, horas, f"gerada em {gerado_em:%d/%m/%Y %H:%M} UTC")


def avaliar_fonte(
    tabela: str, pendente_desde: Optional[datetime], agora: datetime, sla_horas: float
) -> Verificacao:
    """
    Dado do lago ainda nao processado. pendente_desde e a gravacao mais antiga posterior
    a gerado_em; None quando o painel ja processou tudo o que esta no lago.
    """
    nome = f"fonte (delta {tabela})"
    if pendente_desde is None:
        return Verificacao(nome, True, 0.0, "tudo o que esta no lago ja foi processado")
    horas = _horas(agora - pendente_desde)
    return Verificacao(
        nome, horas <= sla_horas, horas, f"dado pendente desde {pendente_desde:%d/%m/%Y %H:%M} UTC"
    )


def _utc(valor) -> Optional[datetime]:
    if valor is None:
        return None
    if valor.tzinfo is None:
        return valor.replace(tzinfo=timezone.utc)
    return valor.astimezone(timezone.utc)


def _conectar(duckdb_path: str, tentativas: int = 5, espera_s: float = 3.0):
    """Abre o DuckDB em modo leitura. Se um dbt build estiver gravando, tenta de novo."""
    import duckdb

    for tentativa in range(1, tentativas + 1):
        try:
            return duckdb.connect(duckdb_path, read_only=True)
        except duckdb.IOException:
            if tentativa == tentativas:
                raise
            time.sleep(espera_s)


def medir(
    duckdb_path: str,
    delta_dir: Optional[str],
    sla_horas: float = SLA_HORAS_PADRAO,
    agora: Optional[datetime] = None,
) -> List[Verificacao]:
    """Le o warehouse e o lago e devolve as verificacoes de frescor."""
    agora = agora or datetime.now(timezone.utc)
    con = _conectar(duckdb_path)
    try:
        try:
            gerado_em = _utc(con.execute(f"SELECT max(gerado_em) FROM {TABELA_CONSUMO}").fetchone()[0])
        except Exception:
            gerado_em = None

        verificacoes = [avaliar_processamento(gerado_em, agora, sla_horas)]
        if gerado_em is None or not delta_dir:
            return verificacoes

        con.execute("LOAD delta")
        for tabela in TABELAS_DELTA:
            caminho = os.path.join(delta_dir, tabela)
            pendente = con.execute(
                f"SELECT min(data_hora_ingestao::timestamp AT TIME ZONE 'UTC') "
                f"FROM delta_scan('{caminho}') "
                f"WHERE (data_hora_ingestao::timestamp AT TIME ZONE 'UTC') > ?",
                [gerado_em],
            ).fetchone()[0]
            verificacoes.append(avaliar_fonte(tabela, _utc(pendente), agora, sla_horas))
        return verificacoes
    finally:
        con.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Verifica o SLA de frescor da tabela de consumo do painel.")
    parser.add_argument("--duckdb", default=os.getenv("DUCKDB_PATH", "data/warehouse/corta_fogo.duckdb"))
    parser.add_argument("--delta-dir", default=os.getenv("DELTA_DIR", "data/delta"))
    parser.add_argument(
        "--sla-horas", type=float, default=float(os.getenv("SLA_FRESCOR_HORAS", SLA_HORAS_PADRAO))
    )
    parser.add_argument("--sem-fonte", action="store_true", help="So a idade da tabela, sem ler o lago Delta.")
    args = parser.parse_args()

    verificacoes = medir(args.duckdb, None if args.sem_fonte else args.delta_dir, args.sla_horas)
    for verificacao in verificacoes:
        print(verificacao.linha(args.sla_horas))

    violadas = [v for v in verificacoes if not v.ok]
    if violadas:
        print(f"SLA de frescor VIOLADO ({len(violadas)} de {len(verificacoes)} verificacao(oes)).")
        return 1
    print(f"SLA de frescor cumprido ({len(verificacoes)} verificacao(oes)).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
