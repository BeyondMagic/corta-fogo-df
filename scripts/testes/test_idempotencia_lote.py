#!/usr/bin/env python3
"""
Testes automatizados de idempotencia e tratamento de dados atrasados (late-arriving data)
para a tabela Delta Lake de focos de calor.
Suporta execucao direta via python e execucao atraves do pytest.
"""

import shutil
import tempfile
from pathlib import Path
import pandas as pd
import pytest
from deltalake import DeltaTable

# Garante importacao do modulo do pipeline
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.pipeline.batch_ingest import executar_ingestao_lote, preparar_dataframe


@pytest.fixture
def temp_delta_dir():
    """Cria um diretorio temporario isolado para testes com a tabela Delta."""
    tmp_path = tempfile.mkdtemp(prefix="test_delta_")
    yield tmp_path
    shutil.rmtree(tmp_path, ignore_errors=True)


def criar_lote_exemplo(ano: int = 2024, mes: int = 8, quantidade: int = 5, offset: int = 0) -> pd.DataFrame:
    """Gera um DataFrame sintetico controlado com colunas padrao de focos."""
    registros = []
    for i in range(quantidade):
        idx = offset + i
        registros.append({
            "latitude": -15.70000 + (idx * 0.01),
            "longitude": -47.80000 - (idx * 0.01),
            "data_hora_evento": f"{ano}-{mes:02d}-15 14:{idx:02d}:00",
            "satelite": "AQUA_M-T" if i % 2 == 0 else "NOAA-20",
            "municipio": "Brasília",
            "bioma": "Cerrado",
            "risco_fogo": 0.5,
        })
    return pd.DataFrame(registros)


def test_ingestao_inicial_e_particionamento(temp_delta_dir):
    """Valida a criacao inicial da tabela e o padrao de particionamento ano=YYYY/mes=MM/."""
    df_lote = criar_lote_exemplo(ano=2024, mes=8, quantidade=4)

    resultado = executar_ingestao_lote(df_input=df_lote, delta_path=temp_delta_dir)

    assert resultado["status"] == "criada"
    assert resultado["inseridos"] == 4
    assert resultado["total_final"] == 4

    dt = DeltaTable(temp_delta_dir)
    arquivos = dt.file_uris()
    assert len(arquivos) > 0

    # Verifica se os arquivos estao dentro da estrutura de diretorios particionada
    particao_esperada = "ano=2024/mes=08"
    assert any(particao_esperada in arq for arq in arquivos), (
        f"Estrutura de particao '{particao_esperada}' nao encontrada nos arquivos: {arquivos}"
    )


def test_idempotencia_reexecucao_mesmo_lote(temp_delta_dir):
    """
    Criterio de Aceite: Execucao repetida sobre o mesmo conjunto de dados
    nao duplica nenhuma linha e mantem a contagem identica.
    """
    df_lote = criar_lote_exemplo(ano=2024, mes=9, quantidade=10)

    # Execucao 1: Carga inicial
    res_1 = executar_ingestao_lote(df_input=df_lote, delta_path=temp_delta_dir)
    assert res_1["status"] == "criada"
    assert res_1["inseridos"] == 10
    assert res_1["total_final"] == 10

    # Execucao 2: Reexecucao identica (deve ser estritamente idempotente)
    res_2 = executar_ingestao_lote(df_input=df_lote, delta_path=temp_delta_dir)
    assert res_2["status"] == "mesclada"
    assert res_2["inseridos"] == 0, "Nenhum novo registro deveria ter sido inserido"
    assert res_2["ignorados"] == 10, "Todos os 10 registros repetidos deveriam ser ignorados"
    assert res_2["total_final"] == 10, "A contagem total da tabela deve permanecer rigorosamente 10"

    # Execucao 3: Terceira execucao consecutiva
    res_3 = executar_ingestao_lote(df_input=df_lote, delta_path=temp_delta_dir)
    assert res_3["inseridos"] == 0
    assert res_3["total_final"] == 10

    # Verificacao direta no dataset lido da tabela Delta
    dt = DeltaTable(temp_delta_dir)
    df_delta = dt.to_pandas()
    assert len(df_delta) == 10
    assert df_delta["id_foco"].nunique() == 10


def test_tratamento_dados_atrasados_late_arriving(temp_delta_dir):
    """
    Criterio de Aceite: Tratamento explicito de dados atrasados.
    Se um registro com data de 2024 for processado em lote tardio, ele deve ser
    depositado na particao correspondente a 2024, sem perturbar particoes atuais.
    """
    # 1. Ingestao inicial com dados recentes de 2025
    df_2025 = criar_lote_exemplo(ano=2025, mes=7, quantidade=5, offset=0)
    executar_ingestao_lote(df_input=df_2025, delta_path=temp_delta_dir)

    dt_inicial = DeltaTable(temp_delta_dir)
    assert dt_inicial.to_pandas().shape[0] == 5

    # 2. Lote tardio (late-arriving) contendo:
    # - 2 focos atrasados com data de 2024 (ano=2024/mes=03)
    # - 1 foco atrasado com data de 2023 (ano=2023/mes=09)
    # - 1 foco repetido de 2025 (duplicado)
    # - 1 foco novo de 2025
    df_tardio_2024 = criar_lote_exemplo(ano=2024, mes=3, quantidade=2, offset=10)
    df_tardio_2023 = criar_lote_exemplo(ano=2023, mes=9, quantidade=1, offset=20)
    df_duplicado_2025 = df_2025.iloc[[0]].copy()
    df_novo_2025 = criar_lote_exemplo(ano=2025, mes=7, quantidade=1, offset=30)

    lote_misto = pd.concat(
        [df_tardio_2024, df_tardio_2023, df_duplicado_2025, df_novo_2025],
        ignore_index=True,
    )

    res_tardio = executar_ingestao_lote(df_input=lote_misto, delta_path=temp_delta_dir)

    # Dos 5 registros do lote misto: 4 sao novos (2 de 2024, 1 de 2023, 1 de 2025) e 1 e duplicado
    assert res_tardio["inseridos"] == 4
    assert res_tardio["ignorados"] == 1
    assert res_tardio["total_final"] == 9  # 5 originais + 4 novos

    # 3. Verificacao das particoes fisicas no Delta Lake
    dt_final = DeltaTable(temp_delta_dir)
    arquivos = dt_final.file_uris()

    # Confirma que os dados atrasados foram roteados para suas respectivas particoes
    assert any("ano=2024/mes=03" in arq for arq in arquivos), (
        "Particao ano=2024/mes=03 para dados atrasados nao foi criada corretamente"
    )
    assert any("ano=2023/mes=09" in arq for arq in arquivos), (
        "Particao ano=2023/mes=09 para dados atrasados nao foi criada corretamente"
    )
    assert any("ano=2025/mes=07" in arq for arq in arquivos), (
        "Particao ano=2025/mes=07 nao foi mantida"
    )

    df_resultado = dt_final.to_pandas()
    assert len(df_resultado[df_resultado["ano"] == "2024"]) == 2
    assert len(df_resultado[df_resultado["ano"] == "2023"]) == 1
    assert len(df_resultado[df_resultado["ano"] == "2025"]) == 6


def test_deduplicacao_no_proprio_lote():
    """Valida que registros duplicados dentro do proprio lote de entrada sao higienizados."""
    df_base = criar_lote_exemplo(ano=2024, mes=5, quantidade=3)
    # Duplica os mesmos registros
    df_duplicado = pd.concat([df_base, df_base], ignore_index=True)
    assert len(df_duplicado) == 6

    df_limpo = preparar_dataframe(df_duplicado)
    assert len(df_limpo) == 3
    assert df_limpo["id_foco"].nunique() == 3


def main():
    """Permite execucao direta do script de teste via CLI sem necessidade de chamar o pytest."""
    print("=== Executando testes automatizados de idempotencia e particionamento Delta Lake ===")
    with tempfile.TemporaryDirectory() as tmp_dir:
        print("\n1. Testando ingestao inicial e particionamento ano=YYYY/mes=MM/...")
        test_ingestao_inicial_e_particionamento(tmp_dir)
        print("-> OK!")

    with tempfile.TemporaryDirectory() as tmp_dir:
        print("\n2. Testando garantia de idempotencia na reexecucao do mesmo lote...")
        test_idempotencia_reexecucao_mesmo_lote(tmp_dir)
        print("-> OK!")

    with tempfile.TemporaryDirectory() as tmp_dir:
        print("\n3. Testando roteamento e isolamento de dados atrasados (late-arriving)...")
        test_tratamento_dados_atrasados_late_arriving(tmp_dir)
        print("-> OK!")

    print("\n4. Testando higienizacao de duplicatas dentro do proprio lote...")
    test_deduplicacao_no_proprio_lote()
    print("-> OK!")

    print("\nTodos os 4 testes foram executados e APROVADOS com sucesso!")


if __name__ == "__main__":
    main()

