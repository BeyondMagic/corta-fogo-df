#!/usr/bin/env python3
"""
Testes do SLA de frescor da tabela de consumo do painel (src/pipeline/frescor.py).

Cobrem a regra, sem banco: limite exato do SLA, tabela ausente, dado pendente no lago
dentro e fora do prazo, e a medicao ponta a ponta sobre um DuckDB temporario.
"""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.pipeline.frescor import (
    SLA_HORAS_PADRAO,
    avaliar_fonte,
    avaliar_processamento,
    medir,
)

AGORA = datetime(2026, 11, 14, 12, 0, 0, tzinfo=timezone.utc)


def test_tabela_dentro_do_sla_no_limite_exato():
    gerado_em = AGORA - timedelta(hours=SLA_HORAS_PADRAO)
    verificacao = avaliar_processamento(gerado_em, AGORA, SLA_HORAS_PADRAO)
    assert verificacao.ok
    assert verificacao.horas == SLA_HORAS_PADRAO


def test_tabela_um_minuto_alem_do_sla_viola():
    gerado_em = AGORA - timedelta(hours=SLA_HORAS_PADRAO, minutes=1)
    assert not avaliar_processamento(gerado_em, AGORA, SLA_HORAS_PADRAO).ok


def test_tabela_ausente_viola():
    verificacao = avaliar_processamento(None, AGORA, SLA_HORAS_PADRAO)
    assert not verificacao.ok
    assert "ausente" in verificacao.detalhe


def test_lago_sem_dado_pendente_cumpre():
    verificacao = avaliar_fonte("imovel_car", None, AGORA, SLA_HORAS_PADRAO)
    assert verificacao.ok
    assert verificacao.horas == 0.0


def test_dado_pendente_dentro_do_prazo_cumpre():
    pendente = AGORA - timedelta(hours=2)
    assert avaliar_fonte("imovel_car", pendente, AGORA, SLA_HORAS_PADRAO).ok


def test_dado_pendente_alem_do_prazo_viola():
    pendente = AGORA - timedelta(hours=SLA_HORAS_PADRAO + 1)
    verificacao = avaliar_fonte("foco_calor", pendente, AGORA, SLA_HORAS_PADRAO)
    assert not verificacao.ok
    assert "pendente" in verificacao.detalhe


def test_medir_sobre_duckdb_temporario(tmp_path):
    duckdb = pytest.importorskip("duckdb")
    caminho = str(tmp_path / "warehouse.duckdb")
    con = duckdb.connect(caminho)
    con.execute("CREATE SCHEMA gold")
    con.execute("CREATE TABLE gold.painel_imoveis_prioritarios (posicao INTEGER, gerado_em TIMESTAMPTZ)")
    con.execute(
        "INSERT INTO gold.painel_imoveis_prioritarios VALUES (1, ?)",
        [AGORA - timedelta(hours=5)],
    )
    con.close()

    dentro = medir(caminho, None, SLA_HORAS_PADRAO, agora=AGORA)
    assert [v.ok for v in dentro] == [True]
    assert round(dentro[0].horas, 1) == 5.0

    fora = medir(caminho, None, SLA_HORAS_PADRAO, agora=AGORA + timedelta(hours=SLA_HORAS_PADRAO))
    assert [v.ok for v in fora] == [False]


def test_medir_sem_a_tabela_viola(tmp_path):
    duckdb = pytest.importorskip("duckdb")
    caminho = str(tmp_path / "vazio.duckdb")
    duckdb.connect(caminho).close()

    verificacoes = medir(caminho, None, SLA_HORAS_PADRAO, agora=AGORA)
    assert [v.ok for v in verificacoes] == [False]
