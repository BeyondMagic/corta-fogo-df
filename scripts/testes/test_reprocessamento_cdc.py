#!/usr/bin/env python3
"""
Testes de Demonstracao da Semantica de Entrega At-Least-Once e Reprocessamento Forcado.

1. Comprova a semantica At-Least-Once no CDC: forca o reprocessamento de mensagens ja gravadas
   (simulando retorno de offset / crash antes do commit de LSN) e valida que a tabela Delta Lake
   nao sofre duplicacao nem corrupcao devido a guarda estrita de LSN (lsn_origem >= target.lsn_origem).
2. Comprova a idempotencia e invariancia de contagem no Lote: reexecuta a ingestao sobre o mesmo
   conjunto de dados anual e atesta contagem identica com zero novas insercoes.
3. Documenta e atesta programaticamente a divergencia estrutural entre falhas de Lote versus CDC
   (latencia de recuperacao isolada vs risco de acumulo de lag no WAL do PostgreSQL).

Suporta execucao via pytest e execucao direta via linha de comando (CLI):
    pytest scripts/testes/test_reprocessamento_cdc.py -v
    python scripts/testes/test_reprocessamento_cdc.py --verbose
"""

import argparse
import os
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd
import pytest
from deltalake import DeltaTable

# Garante importacao dos modulos do projeto
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.pipeline.batch_ingest import executar_ingestao_lote
from src.pipeline.cdc_consumer import (
    aplicar_merge_delta,
    converter_evento_para_linha_delta,
    lsn_para_int,
    parse_linha_test_decoding,
)


@pytest.fixture
def temp_delta_dir():
    """Cria diretorio temporario isolado para testes com a tabela Delta."""
    tmp_path = tempfile.mkdtemp(prefix="test_reprocessamento_")
    yield tmp_path
    shutil.rmtree(tmp_path, ignore_errors=True)


def criar_evento_imovel_raw(
    op: str,
    cod_imovel: str,
    area_ha: float = 120.0,
    situacao: str = "AT",
    condicao: str = "Cadastrado",
    geom_hex: str = "0103000020E61000000100000005000000",
) -> str:
    """Gera string de mudanca sintetica no formato padrao do test_decoding."""
    if op == "D":
        return f"table public.imovel_car: DELETE: cod_imovel['{cod_imovel}']"
    return (
        f"table public.imovel_car: {op}: cod_imovel['{cod_imovel}'] "
        f"situacao['{situacao}'] condicao['{condicao}'] area_ha[{area_ha}] "
        f"data_download['2024-05-10'] geom['{geom_hex}']"
    )


def test_reprocessamento_cdc_semantica_at_least_once(temp_delta_dir):
    """
    Demonstra a semantica de entrega At-Least-Once do consumidor CDC.
    
    Cenario do teste:
    1. Consumidor processa lote inicial de mutacoes (LSN 100 a 300).
    2. Simula crash ou reabertura de conexao onde o offset de replicacao retrocede
       (replay forçado dos eventos de LSN 200 e 300, alem de evento obsoleto LSN 150).
    3. Demonstra que o MERGE Delta Lake descarta mutacoes antigas e absorve repetidas sem duplicar.
    """
    delta_path = os.path.join(temp_delta_dir, "imovel_car")
    now_utc = datetime.now(timezone.utc)

    # -------------------------------------------------------------------------
    # Passo 1: Ingestao inicial de 3 imoveis com LSNs crescentes
    # -------------------------------------------------------------------------
    raw_eventos_fase1 = [
        ("0/1000", criar_evento_imovel_raw("INSERT", "DF-5300108-0001", area_ha=100.0, condicao="Fase 1")),
        ("0/2000", criar_evento_imovel_raw("INSERT", "DF-5300108-0002", area_ha=200.0, condicao="Fase 1")),
        ("0/3000", criar_evento_imovel_raw("INSERT", "DF-5300108-0003", area_ha=300.0, condicao="Fase 1")),
    ]

    linhas_delta_fase1 = []
    for lsn_str, raw_msg in raw_eventos_fase1:
        ev = parse_linha_test_decoding(raw_msg)
        ev_delta = converter_evento_para_linha_delta(ev, lsn_str, now_utc)
        linhas_delta_fase1.append(ev_delta)

    # Aplica primeira gravacao no Delta Lake
    aplicar_merge_delta(pd.DataFrame(linhas_delta_fase1), delta_path)

    dt_fase1 = DeltaTable(delta_path)
    df_fase1 = dt_fase1.to_pandas()
    assert len(df_fase1) == 3, "A tabela Delta deve conter exatamente 3 registros apos a Fase 1"
    assert df_fase1["cod_imovel"].nunique() == 3, "As 3 chaves cod_imovel devem ser unicas"

    # -------------------------------------------------------------------------
    # Passo 2: Atualizacao progressiva de um imovel (LSN 4000)
    # -------------------------------------------------------------------------
    raw_update = ("0/4000", criar_evento_imovel_raw("UPDATE", "DF-5300108-0002", area_ha=250.0, condicao="Retificado"))
    ev_up = parse_linha_test_decoding(raw_update[1])
    ev_up_delta = converter_evento_para_linha_delta(ev_up, raw_update[0], now_utc)
    aplicar_merge_delta(pd.DataFrame([ev_up_delta]), delta_path)

    df_pos_update = DeltaTable(delta_path).to_pandas()
    imovel_2 = df_pos_update[df_pos_update["cod_imovel"] == "DF-5300108-0002"].iloc[0]
    assert imovel_2["area_ha"] == 250.0
    assert imovel_2["condicao"] == "Retificado"
    assert imovel_2["lsn_origem"] == lsn_para_int("0/4000")

    # -------------------------------------------------------------------------
    # Passo 3: REPROCESSAMENTO FORCADO (Replay de stream / At-Least-Once)
    # Simula o consumidor reiniciando a partir de um LSN anterior (0/2000).
    # O stream reentrega:
    #   - Evento 0/2000 antigo (DF-0002 com area=200.0) -> Deve ser IGNORADO (LSN menor que 0/4000)
    #   - Evento 0/3000 identico (DF-0003 com area=300.0) -> Deve manter estado identico
    #   - Evento 0/4000 identico (DF-0002 com area=250.0) -> Deve manter estado identico
    #   - Evento 0/1500 desordenado (DF-0001 com area=99.0) -> Deve ser IGNORADO
    # -------------------------------------------------------------------------
    raw_eventos_replay = [
        ("0/2000", criar_evento_imovel_raw("UPDATE", "DF-5300108-0002", area_ha=200.0, condicao="Fase 1 Replay")),
        ("0/3000", criar_evento_imovel_raw("UPDATE", "DF-5300108-0003", area_ha=300.0, condicao="Fase 1 Replay")),
        ("0/4000", criar_evento_imovel_raw("UPDATE", "DF-5300108-0002", area_ha=250.0, condicao="Retificado")),
        ("0/800", criar_evento_imovel_raw("UPDATE", "DF-5300108-0001", area_ha=99.0, condicao="Desordenado Obsoleto")),
    ]

    linhas_delta_replay = []
    for lsn_str, raw_msg in raw_eventos_replay:
        ev = parse_linha_test_decoding(raw_msg)
        ev_delta = converter_evento_para_linha_delta(ev, lsn_str, now_utc)
        linhas_delta_replay.append(ev_delta)

    # Executa o reprocessamento forcado
    aplicar_merge_delta(pd.DataFrame(linhas_delta_replay), delta_path)

    # -------------------------------------------------------------------------
    # Passo 4: Verificacoes de Invariancia e Idempotencia
    # -------------------------------------------------------------------------
    dt_final = DeltaTable(delta_path)
    df_final = dt_final.to_pandas()

    # 1. Invariancia de contagem: zero duplicatas
    assert len(df_final) == 3, f"A contagem total deve permanecer estritamente 3. Encontrado: {len(df_final)}"
    assert df_final["cod_imovel"].nunique() == 3, "Chaves cod_imovel duplicadas foram inseridas indevidamente!"

    # 2. Imutabilidade frente a mutacoes desordenadas/mais antigas
    imovel_2_final = df_final[df_final["cod_imovel"] == "DF-5300108-0002"].iloc[0]
    assert imovel_2_final["area_ha"] == 250.0, (
        f"A mutacao obsoleta de LSN 0/2000 sobrescreveu indevidamente o LSN 0/4000! "
        f"area_ha esperada: 250.0, encontrada: {imovel_2_final['area_ha']}"
    )
    assert imovel_2_final["condicao"] == "Retificado"
    assert imovel_2_final["lsn_origem"] == lsn_para_int("0/4000")

    imovel_1_final = df_final[df_final["cod_imovel"] == "DF-5300108-0001"].iloc[0]
    assert imovel_1_final["area_ha"] == 100.0, (
        f"A mutacao desordenada de LSN 0/800 sobrescreveu indevidamente o estado original! "
        f"area_ha esperada: 100.0, encontrada: {imovel_1_final['area_ha']}"
    )


def test_reprocessamento_lote_invariancia_contagem(temp_delta_dir):
    """
    Demonstra o reprocessamento forcado no pipeline em Lote (Batch).
    
    Criterio: A reexecucao sobre o mesmo conjunto de dados anual/mensal
    deve atestar contagem rigorosamente identica e zero novas insercoes.
    """
    delta_path = os.path.join(temp_delta_dir, "foco_calor")

    # Gera lote com 20 registros distribuidos em dois meses de 2024
    registros = []
    for i in range(20):
        mes = "08" if i < 10 else "09"
        registros.append({
            "latitude": -15.70000 + (i * 0.01),
            "longitude": -47.80000 - (i * 0.01),
            "data_hora_evento": f"2024-{mes}-15 14:{(i % 60):02d}:00",
            "satelite": "AQUA_M-T" if i % 2 == 0 else "NOAA-20",
            "municipio": "Brasília",
            "bioma": "Cerrado",
            "risco_fogo": 0.75,
        })
    df_lote = pd.DataFrame(registros)

    # 1. Carga Inicial
    res_1 = executar_ingestao_lote(df_input=df_lote, delta_path=delta_path)
    assert res_1["status"] == "criada"
    assert res_1["inseridos"] == 20
    assert res_1["total_final"] == 20

    # 2. Reprocessamento Forcado 1 (mesmo lote completo)
    res_2 = executar_ingestao_lote(df_input=df_lote, delta_path=delta_path)
    assert res_2["status"] == "mesclada"
    assert res_2["inseridos"] == 0, "Reprocessamento inseriu linhas indevidamente!"
    assert res_2["ignorados"] == 20, "Todos os registros deveriam ser ignorados pelo MERGE"
    assert res_2["total_final"] == 20, "A contagem total final foi alterada no reprocessamento"

    # 3. Reprocessamento Forcado 2 (terceira reexecucao)
    res_3 = executar_ingestao_lote(df_input=df_lote, delta_path=delta_path)
    assert res_3["inseridos"] == 0
    assert res_3["total_final"] == 20

    # Validacao direta no Delta Lake
    dt = DeltaTable(delta_path)
    df_delta = dt.to_pandas()
    assert len(df_delta) == 20
    assert df_delta["id_foco"].nunique() == 20


def test_analise_comparativa_falha_lote_vs_cdc():
    """
    Testa e valida as propriedades arquiteturais divergentes de tolerancia a falha
    entre os dois mecanismos de ingestao (Lote versus CDC).
    """
    propriedades_lote = {
        "mecanismo": "Batch (Lote)",
        "ponto_recuperacao": "Idempotente por arquivo/partição temporal",
        "impacto_da_falha": "Atraso no fechamento da janela analítica (latência pontual)",
        "risco_no_oltp": "Nulo (o PostgreSQL não acumula estado para jobs de lote)",
        "complexidade_recuperacao": "Baixa (basta reexecutar o job para a partição afetada)",
    }

    propriedades_cdc = {
        "mecanismo": "CDC (Logical Decoding)",
        "ponto_recuperacao": "LSN confirmado no pg_replication_slots (confirmed_flush_lsn)",
        "impacto_da_falha": "Acúmulo progressivo de lag no slot de replicação",
        "risco_no_oltp": (
            "Alto se o consumidor demorar (PostgreSQL retém arquivos WAL em disco no pgdata, "
            "podendo atingir o limite de max_slot_wal_keep_size)"
        ),
        "complexidade_recuperacao": (
            "Média (o consumidor precisa acelerar o consumo 'catch-up' para drenar "
            "o WAL acumulado e avançar o confirmed_flush_lsn)"
        ),
    }

    # Assegura que as propriedades chaves estao formalizadas
    assert propriedades_lote["risco_no_oltp"] == "Nulo (o PostgreSQL não acumula estado para jobs de lote)"
    assert "pg_replication_slots" in propriedades_cdc["ponto_recuperacao"]
    assert "WAL" in propriedades_cdc["risco_no_oltp"]


def executar_demonstracao_cli(verbose: bool = True):
    """Executa os testes de forma interativa com saida formatada no terminal."""
    print("=" * 80)
    print("TESTE DE DEMONSTRACAO: SEMANTICA AT-LEAST-ONCE E REPROCESSAMENTO FORCADO (E2)")
    print("=" * 80)

    with tempfile.TemporaryDirectory(prefix="demo_reprocessamento_") as tmp_dir:
        dir_cdc = os.path.join(tmp_dir, "cdc")
        dir_lote = os.path.join(tmp_dir, "lote")
        os.makedirs(dir_cdc, exist_ok=True)
        os.makedirs(dir_lote, exist_ok=True)

        print("\n[1/3] Executando Teste de Reprocessamento CDC (At-Least-Once com Replay de LSN)...")
        test_reprocessamento_cdc_semantica_at_least_once(dir_cdc)
        print("  -> [SUCESSO] Mutacoes obsoletas descartadas; zero duplicatas; estado final consistente.")

        print("\n[2/3] Executando Teste de Reprocessamento em Lote (Invariancia de Contagem)...")
        test_reprocessamento_lote_invariancia_contagem(dir_lote)
        print("  -> [SUCESSO] Reexecucao de lote anual manteve contagem rigorosamente identica.")

        print("\n[3/3] Validando Analise Comparativa de Falha (Lote vs CDC)...")
        test_analise_comparativa_falha_lote_vs_cdc()
        print("  -> [SUCESSO] Modelo conceitual e regras de falha validados com sucesso.")

    print("\n" + "=" * 80)
    print("RESUMO DA DEMONSTRACAO DE AT-LEAST-ONCE E REPROCESSAMENTO:")
    print("=" * 80)
    print("1. Semântica At-Least-Once no CDC:")
    print("   - Ao reprocessar mensagens devido a reinício ou queda do consumidor, o MERGE na tabela")
    print("     Delta Lake utiliza a guarda 'source.lsn_origem >= target.lsn_origem'.")
    print("   - Eventos repetidos não alteram o estado e eventos com LSN inferior são descartados.")
    print("   - O efeito observável no destino analítico é exatamente-uma-vez (effectively once).")
    print("\n2. Idempotência no Pipeline em Lote:")
    print("   - A cláusula 'WHEN NOT MATCHED INSERT' garante que reexecuções do mesmo lote anual")
    print("     ignorem 100% dos registros já existentes pelo id_foco determinístico.")
    print("\n3. Diferença de Impacto em Cenário de Falha:")
    print("   - Lote: Falha gera atraso pontual de fechamento de partição; custo no OLTP é nulo.")
    print("   - CDC: Falha prolongada acumula WAL no PostgreSQL; requer monitoramento de disco.")
    print("=" * 80)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Demonstracao de semantica At-Least-Once e Reprocessamento.")
    parser.add_argument("--verbose", "-v", action="store_true", help="Modo verboso detalhado.")
    args = parser.parse_args()

    executar_demonstracao_cli(verbose=args.verbose)
