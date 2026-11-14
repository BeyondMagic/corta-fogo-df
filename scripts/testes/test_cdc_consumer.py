#!/usr/bin/env python3
"""
Testes automatizados do consumidor CDC de imovel_car para a camada aberta Delta Lake.

Valida os requisitos da Tarefa #09 (GH #3):
- Conversao e ordenacao estrita de LSN (64-bit)
- Parser de tuplas e eventos do test_decoding (INSERT, UPDATE, DELETE, TOAST)
- Normalizacao de esquema conforme contrato de dados
- Merge Delta idempotente (reprocessamento de lote identico)
- Guarda contra eventos fora de ordem (LSN menor nao sobrescreve mais novo)
- Preservacao de geometria em tuplas TOAST (unchanged-toast-datum)
- Soft-delete de imoveis (operacao_cdc='D' sem expurgar linha)
"""

import os
import shutil
import sys
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd
import pytest
from deltalake import DeltaTable

# Garante importacao do modulo do pipeline
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.pipeline.cdc_consumer import (
    aplicar_merge_delta,
    converter_evento_para_linha_delta,
    eventos_para_linhas_delta,
    lsn_para_int,
    parse_linha_test_decoding,
    parse_valores_tupla,
    preparar_tabela_arrow,
    ressincronizar_snapshot,
)


@pytest.fixture
def temp_delta_dir():
    """Cria diretorio temporario isolado para testes com a tabela Delta."""
    tmp_path = tempfile.mkdtemp(prefix="test_delta_cdc_")
    yield tmp_path
    shutil.rmtree(tmp_path, ignore_errors=True)


def test_lsn_para_int():
    """Valida conversao de LSN do PostgreSQL para inteiros de 64 bits."""
    # Casos basicos e limites
    assert lsn_para_int("0/0") == 0
    assert lsn_para_int("") == 0
    assert lsn_para_int(None) == 0
    assert lsn_para_int("invalido") == 0

    # LSN real do PostgreSQL
    # "0/16B3748": parte alta 0x0, parte baixa 0x16B3748 = 23803720
    assert lsn_para_int("0/16B3748") == 23803720

    # "1/0": (1 << 32) = 4294967296
    assert lsn_para_int("1/0") == 4294967296

    # "1/10": 4294967296 + 16 = 4294967312
    assert lsn_para_int("1/10") == 4294967312

    # Monotonicidade estrita
    lsn1 = lsn_para_int("0/16B3748")
    lsn2 = lsn_para_int("0/16B3749")
    lsn3 = lsn_para_int("1/0")
    assert lsn1 < lsn2 < lsn3


def test_parse_valores_tupla():
    """Valida o extrator de pares chave[valor] emitidos pelo test_decoding."""
    linha_tupla = (
        "cod_imovel['DF-5300108-0001'] situacao['AT'] condicao['Ativo'] "
        "area_ha[150.50] data_download['2024-05-10'] geom['010300'] col_null[null] "
        "geom_toast[unchanged-toast-datum]"
    )
    dados = parse_valores_tupla(linha_tupla)
    assert dados["cod_imovel"] == "DF-5300108-0001"
    assert dados["situacao"] == "AT"
    assert dados["condicao"] == "Ativo"
    assert dados["area_ha"] == "150.50"
    assert dados["data_download"] == "2024-05-10"
    assert dados["geom"] == "010300"
    assert dados["col_null"] is None
    assert dados["geom_toast"] == "unchanged-toast-datum"


def test_parse_linha_test_decoding_insert():
    """Valida parsing de operacao INSERT no test_decoding."""
    msg = (
        "table public.imovel_car: INSERT: cod_imovel['DF-5300108-0001'] "
        "situacao['AT'] condicao['Aguardando analise'] area_ha[123.45] "
        "data_download['2024-05-10'] geom['0103000020E6100000...']"
    )
    evento = parse_linha_test_decoding(msg)
    assert evento is not None
    assert evento["operacao_cdc"] == "I"
    assert evento["cod_imovel"] == "DF-5300108-0001"
    assert evento["situacao"] == "AT"
    assert evento["condicao"] == "Aguardando analise"
    assert evento["area_ha"] == "123.45"
    assert evento["geom"] == "0103000020E6100000..."


def test_parse_linha_test_decoding_update_com_toast():
    """Valida parsing de operacao UPDATE com geom inalterada (unchanged-toast-datum)."""
    msg = (
        "table public.imovel_car: UPDATE: old-key: cod_imovel['DF-5300108-0001'] "
        "new-tuple: cod_imovel['DF-5300108-0001'] situacao['PE'] condicao['Pendente'] "
        "area_ha[123.45] data_download['2024-05-10'] geom[unchanged-toast-datum]"
    )
    evento = parse_linha_test_decoding(msg)
    assert evento is not None
    assert evento["operacao_cdc"] == "U"
    assert evento["cod_imovel"] == "DF-5300108-0001"
    assert evento["situacao"] == "PE"
    assert evento["geom"] == "unchanged-toast-datum"


def test_parse_update_pk_toast_usa_old_key():
    """Captura real do PG16: a PK do new-tuple vem como unchanged-toast-datum, a PK real esta no old-key."""
    msg = (
        "table public.imovel_car: UPDATE: old-key: "
        "cod_imovel[character varying]:'DF-5300108-A55B9407F4DD45ECBCBCE09C1AFAE947' "
        "new-tuple: cod_imovel[character varying]:unchanged-toast-datum "
        "situacao[character varying]:'PE' condicao[character varying]:'debug2' "
        "area_ha[numeric]:886.1151 data_download[date]:'2026-09-27' "
        "geom[geometry]:unchanged-toast-datum"
    )
    evento = parse_linha_test_decoding(msg)
    assert evento["operacao_cdc"] == "U"
    assert evento["cod_imovel"] == "DF-5300108-A55B9407F4DD45ECBCBCE09C1AFAE947"
    assert evento["condicao"] == "debug2"


def test_parse_linha_test_decoding_formato_oficial_postgis():
    """Valida parsing de formato oficial emitido pelo plugin test_decoding no PostgreSQL 16."""
    msg = (
        "table public.imovel_car: UPDATE: cod_imovel[character varying]:'DF-5300108-C0489' "
        "situacao[character varying]:'AT' condicao[character varying]:'Analisado (PRA)' "
        "area_ha[numeric]:999.9900 data_download[date]:'2026-09-27' "
        "geom[geometry]:unchanged-toast-datum data_hora_ingestao[timestamp with time zone]:'2026-10-12 22:00:00+00'"
    )
    evento = parse_linha_test_decoding(msg)
    assert evento is not None
    assert evento["operacao_cdc"] == "U"
    assert evento["cod_imovel"] == "DF-5300108-C0489"
    assert evento["situacao"] == "AT"
    assert evento["condicao"] == "Analisado (PRA)"
    assert evento["area_ha"] == "999.9900"
    assert evento["geom"] == "unchanged-toast-datum"


def test_parse_linha_test_decoding_delete():
    """Valida parsing de operacao DELETE contendo apenas old-key da PK."""
    msg = "table public.imovel_car: DELETE: old-key: cod_imovel['DF-5300108-0001']"
    evento = parse_linha_test_decoding(msg)
    assert evento is not None
    assert evento["operacao_cdc"] == "D"
    assert evento["cod_imovel"] == "DF-5300108-0001"


def test_parse_linha_test_decoding_tabela_irrelevante():
    """Ignora mensagens de tabelas que nao sejam public.imovel_car."""
    msg = "table public.foco_calor: INSERT: id_foco['123'] latitude[-15.7]"
    assert parse_linha_test_decoding(msg) is None


def test_converter_evento_para_linha_delta():
    """Valida normalizacao do evento para colunas e tipos estritos do Delta Lake."""
    evento = {
        "operacao_cdc": "U",
        "cod_imovel": "DF-5300108-0002",
        "situacao": "AT",
        "condicao": "Ativo",
        "area_ha": "87.65",
        "data_download": "2024-06-01",
        "geom": "010300ABCDEF",
    }
    now = datetime(2024, 6, 1, 10, 0, 0, tzinfo=timezone.utc)
    linha = converter_evento_para_linha_delta(evento, "0/16B3800", now)

    assert linha is not None
    assert linha["cod_imovel"] == "DF-5300108-0002"
    assert linha["situacao"] == "AT"
    assert linha["area_ha"] == 87.65
    assert isinstance(linha["area_ha"], float)
    assert linha["data_download"] == date(2024, 6, 1)
    assert linha["geom_ewkb_hex"] == "010300ABCDEF"
    assert linha["origem_ingestao"] == "cdc"
    assert linha["operacao_cdc"] == "U"
    assert linha["lsn_origem"] == lsn_para_int("0/16B3800")
    assert linha["data_hora_ingestao"] == now


def test_merge_idempotente_reprocessamento(temp_delta_dir):
    """
    Criterio de Aceite: Reprocessamento de micro-lote CDC identico nao duplica linhas
    e mantem o estado final estritamente consistente.
    """
    now = datetime.now(timezone.utc)
    lote = pd.DataFrame([
        {
            "cod_imovel": "DF-5300108-0010",
            "situacao": "AT",
            "condicao": "Ativo",
            "area_ha": 100.0,
            "data_download": date(2024, 1, 1),
            "geom_ewkb_hex": "01030010",
            "data_hora_ingestao": now,
            "origem_ingestao": "cdc",
            "operacao_cdc": "I",
            "lsn_origem": 1000,
        },
        {
            "cod_imovel": "DF-5300108-0020",
            "situacao": "PE",
            "condicao": "Pendente",
            "area_ha": 250.0,
            "data_download": date(2024, 1, 1),
            "geom_ewkb_hex": "01030020",
            "data_hora_ingestao": now,
            "origem_ingestao": "cdc",
            "operacao_cdc": "I",
            "lsn_origem": 1000,
        },
    ])

    # 1. Primeira aplicacao
    aplicar_merge_delta(lote, delta_path=temp_delta_dir)
    dt1 = DeltaTable(temp_delta_dir)
    df1 = dt1.to_pandas().sort_values("cod_imovel").reset_index(drop=True)
    assert len(df1) == 2

    # 2. Re-execucao identica (simulando replay ou restart at-least-once)
    aplicar_merge_delta(lote, delta_path=temp_delta_dir)
    dt2 = DeltaTable(temp_delta_dir)
    df2 = dt2.to_pandas().sort_values("cod_imovel").reset_index(drop=True)

    assert len(df2) == 2
    assert df1["cod_imovel"].tolist() == df2["cod_imovel"].tolist()
    assert df1["situacao"].tolist() == df2["situacao"].tolist()
    assert df1["lsn_origem"].tolist() == df2["lsn_origem"].tolist()


def test_guarda_lsn_fora_de_ordem(temp_delta_dir):
    """
    Criterio de Aceite: Eventos com LSN anterior nao sobrescrevem registros ja
    atualizados por LSN mais recente (resiliencia a desordenacao).
    """
    now = datetime.now(timezone.utc)
    base = pd.DataFrame([
        {
            "cod_imovel": "DF-5300108-0030",
            "situacao": "AT",
            "condicao": "Ativo Recente",
            "area_ha": 300.0,
            "data_download": date(2024, 1, 1),
            "geom_ewkb_hex": "01030030",
            "data_hora_ingestao": now,
            "origem_ingestao": "cdc",
            "operacao_cdc": "I",
            "lsn_origem": 2000,
        }
    ])
    aplicar_merge_delta(base, delta_path=temp_delta_dir)

    # Tentativa de aplicar evento atrasado (LSN 1500 < LSN 2000) querendo alterar para CANCELADO
    evento_atrasado = pd.DataFrame([
        {
            "cod_imovel": "DF-5300108-0030",
            "situacao": "CA",
            "condicao": "Cancelado Antigo",
            "area_ha": 300.0,
            "data_download": date(2024, 1, 1),
            "geom_ewkb_hex": "01030030",
            "data_hora_ingestao": now,
            "origem_ingestao": "cdc",
            "operacao_cdc": "U",
            "lsn_origem": 1500,
        }
    ])
    aplicar_merge_delta(evento_atrasado, delta_path=temp_delta_dir)

    df_depois = DeltaTable(temp_delta_dir).to_pandas()
    assert len(df_depois) == 1
    # O valor do estado deve permanecer o mais recente (AT, LSN 2000)
    assert df_depois.iloc[0]["situacao"] == "AT"
    assert df_depois.iloc[0]["condicao"] == "Ativo Recente"
    assert df_depois.iloc[0]["lsn_origem"] == 2000

    # Agora aplica evento mais novo (LSN 2500 > LSN 2000)
    evento_novo = pd.DataFrame([
        {
            "cod_imovel": "DF-5300108-0030",
            "situacao": "PE",
            "condicao": "Pendente Novo",
            "area_ha": 300.0,
            "data_download": date(2024, 1, 1),
            "geom_ewkb_hex": "01030030",
            "data_hora_ingestao": now,
            "origem_ingestao": "cdc",
            "operacao_cdc": "U",
            "lsn_origem": 2500,
        }
    ])
    aplicar_merge_delta(evento_novo, delta_path=temp_delta_dir)

    df_final = DeltaTable(temp_delta_dir).to_pandas()
    assert df_final.iloc[0]["situacao"] == "PE"
    assert df_final.iloc[0]["condicao"] == "Pendente Novo"
    assert df_final.iloc[0]["lsn_origem"] == 2500


def test_soft_delete(temp_delta_dir):
    """
    Criterio de Aceite: Mutacao DELETE no Postgres atualiza operacao_cdc='D'
    sem excluir fisicamente o registro do lakehouse analitico.
    """
    now = datetime.now(timezone.utc)
    base = pd.DataFrame([
        {
            "cod_imovel": "DF-5300108-0040",
            "situacao": "AT",
            "condicao": "Ativo",
            "area_ha": 400.0,
            "data_download": date(2024, 1, 1),
            "geom_ewkb_hex": "01030040",
            "data_hora_ingestao": now,
            "origem_ingestao": "snapshot",
            "operacao_cdc": "I",
            "lsn_origem": 100,
        }
    ])
    aplicar_merge_delta(base, delta_path=temp_delta_dir)

    # Evento de exclusao do imovel (DELETE nao envia atributos exceto PK)
    evento_delete = pd.DataFrame([
        {
            "cod_imovel": "DF-5300108-0040",
            "situacao": None,
            "condicao": None,
            "area_ha": None,
            "data_download": None,
            "geom_ewkb_hex": None,
            "data_hora_ingestao": now,
            "origem_ingestao": "cdc",
            "operacao_cdc": "D",
            "lsn_origem": 200,
        }
    ])
    aplicar_merge_delta(evento_delete, delta_path=temp_delta_dir)

    df_resultado = DeltaTable(temp_delta_dir).to_pandas()
    assert len(df_resultado) == 1
    linha = df_resultado.iloc[0]
    assert linha["cod_imovel"] == "DF-5300108-0040"
    assert linha["operacao_cdc"] == "D"
    assert linha["lsn_origem"] == 200
    # A geometria anterior deve ter sido preservada pelo merge CASE
    assert linha["geom_ewkb_hex"] == "01030040"


def test_preservacao_unchanged_toast_datum(temp_delta_dir):
    """
    Criterio de Aceite: Mutacoes UPDATE que nao alteram a geometria recebem
    'unchanged-toast-datum' do Postgres; o Delta Lake deve manter a geometria original.
    """
    now = datetime.now(timezone.utc)
    geometria_original = "0103000020E61000000100000005000000ABCDEF123456"

    base = pd.DataFrame([
        {
            "cod_imovel": "DF-5300108-0050",
            "situacao": "AT",
            "condicao": "Ativo",
            "area_ha": 500.0,
            "data_download": date(2024, 1, 1),
            "geom_ewkb_hex": geometria_original,
            "data_hora_ingestao": now,
            "origem_ingestao": "snapshot",
            "operacao_cdc": "I",
            "lsn_origem": 500,
        }
    ])
    aplicar_merge_delta(base, delta_path=temp_delta_dir)

    # Mutacao que altera apenas situacao cadastral, emitindo unchanged-toast-datum para a geom
    evento_update_toast = pd.DataFrame([
        {
            "cod_imovel": "DF-5300108-0050",
            "situacao": "SU",
            "condicao": "Suspenso",
            "area_ha": 500.0,
            "data_download": date(2024, 1, 1),
            "geom_ewkb_hex": "unchanged-toast-datum",
            "data_hora_ingestao": now,
            "origem_ingestao": "cdc",
            "operacao_cdc": "U",
            "lsn_origem": 600,
        }
    ])
    aplicar_merge_delta(evento_update_toast, delta_path=temp_delta_dir)

    df_resultado = DeltaTable(temp_delta_dir).to_pandas()
    assert len(df_resultado) == 1
    linha = df_resultado.iloc[0]
    assert linha["cod_imovel"] == "DF-5300108-0050"
    assert linha["situacao"] == "SU"
    assert linha["condicao"] == "Suspenso"
    assert linha["lsn_origem"] == 600
    # Geometria continua sendo o binario original, e nao a string TOAST
    assert linha["geom_ewkb_hex"] == geometria_original


GEOM_A = "0103000020E61000000100000005000000AAAA"
GEOM_B = "0103000020E61000000100000005000000BBBB"
AGORA = datetime(2026, 11, 14, 12, 0, 0, tzinfo=timezone.utc)


def _linha(cod, lsn, op="I", geom=GEOM_A, situacao="AT", condicao="Ativo", area=100.0, origem="cdc"):
    return {
        "cod_imovel": cod,
        "situacao": situacao,
        "condicao": condicao,
        "area_ha": area,
        "data_download": date(2026, 9, 27),
        "geom_ewkb_hex": geom,
        "data_hora_ingestao": AGORA,
        "origem_ingestao": origem,
        "operacao_cdc": op,
        "lsn_origem": lsn,
    }


def _evento(msg, lsn):
    """Mensagem do test_decoding -> linhas do Delta, pelo mesmo caminho do consumidor."""
    return eventos_para_linhas_delta(parse_linha_test_decoding(msg), lsn, AGORA)


def _ler(delta_dir, cod):
    df = DeltaTable(delta_dir).to_pandas()
    return df[df["cod_imovel"] == cod].iloc[0]


def test_delete_real_preserva_atributos(temp_delta_dir):
    """O DELETE do test_decoding so traz a PK: os atributos do imovel nao podem virar NULL."""
    aplicar_merge_delta(pd.DataFrame([_linha("DF-1", 100, origem="snapshot")]), temp_delta_dir)

    linhas = _evento("table public.imovel_car: DELETE: cod_imovel[character varying]:'DF-1'", "0/C8")
    aplicar_merge_delta(pd.DataFrame(linhas), temp_delta_dir)

    linha = _ler(temp_delta_dir, "DF-1")
    assert linha["operacao_cdc"] == "D"
    assert linha["lsn_origem"] == lsn_para_int("0/C8")
    assert linha["situacao"] == "AT"
    assert linha["condicao"] == "Ativo"
    assert linha["area_ha"] == 100.0
    assert linha["data_download"] == date(2026, 9, 27)
    assert linha["geom_ewkb_hex"] == GEOM_A


def test_insert_e_update_toast_no_mesmo_lote_herdam_a_geometria(temp_delta_dir):
    """INSERT e UPDATE do mesmo imovel novo no mesmo micro-lote: o marcador TOAST nao vira geometria."""
    aplicar_merge_delta(pd.DataFrame([_linha("DF-0", 50)]), temp_delta_dir)

    lote = _evento(
        "table public.imovel_car: INSERT: cod_imovel[character varying]:'DF-2' situacao[character varying]:'AT' "
        f"condicao[character varying]:'x' area_ha[numeric]:10.0 data_download[date]:'2026-09-27' geom[geometry]:'{GEOM_B}'",
        "0/12C",
    ) + _evento(
        "table public.imovel_car: UPDATE: cod_imovel[character varying]:'DF-2' situacao[character varying]:'PE' "
        "condicao[character varying]:'y' area_ha[numeric]:11.0 data_download[date]:'2026-09-27' "
        "geom[geometry]:unchanged-toast-datum",
        "0/190",
    )
    aplicar_merge_delta(pd.DataFrame(lote), temp_delta_dir)

    linha = _ler(temp_delta_dir, "DF-2")
    assert linha["situacao"] == "PE"
    assert linha["area_ha"] == 11.0
    assert linha["geom_ewkb_hex"] == GEOM_B


def test_marcador_toast_nunca_e_gravado_como_geometria(temp_delta_dir):
    """UPDATE com geom TOAST inalterado de imovel que o Delta nao tem: geometria fica NULL, nunca o marcador."""
    aplicar_merge_delta(pd.DataFrame([_linha("DF-0", 50)]), temp_delta_dir)
    aplicar_merge_delta(pd.DataFrame([_linha("DF-9", 60, op="U", geom="unchanged-toast-datum")]), temp_delta_dir)

    assert pd.isna(_ler(temp_delta_dir, "DF-9")["geom_ewkb_hex"])
    assert "unchanged-toast-datum" not in DeltaTable(temp_delta_dir).to_pandas()["geom_ewkb_hex"].tolist()


def test_update_para_null_no_mesmo_lote_nao_herda_valor_anterior(temp_delta_dir):
    """Dois UPDATEs no mesmo micro-lote: vale a ultima linha inteira, inclusive os NULLs."""
    aplicar_merge_delta(pd.DataFrame([_linha("DF-3", 100)]), temp_delta_dir)

    lote = _evento(
        "table public.imovel_car: UPDATE: cod_imovel[character varying]:'DF-3' situacao[character varying]:'PE' "
        "condicao[character varying]:'pendencia X' area_ha[numeric]:100.0 data_download[date]:'2026-09-27' "
        "geom[geometry]:unchanged-toast-datum",
        "0/12C",
    ) + _evento(
        "table public.imovel_car: UPDATE: cod_imovel[character varying]:'DF-3' situacao[character varying]:'AT' "
        "condicao[character varying]:null area_ha[numeric]:100.0 data_download[date]:'2026-09-27' "
        "geom[geometry]:unchanged-toast-datum",
        "0/190",
    )
    aplicar_merge_delta(pd.DataFrame(lote), temp_delta_dir)

    linha = _ler(temp_delta_dir, "DF-3")
    assert linha["situacao"] == "AT"
    assert pd.isna(linha["condicao"])
    assert linha["geom_ewkb_hex"] == GEOM_A
    assert linha["lsn_origem"] == lsn_para_int("0/190")


def test_update_seguido_de_delete_no_mesmo_lote(temp_delta_dir):
    """UPDATE e DELETE no mesmo micro-lote: a linha excluida guarda o ultimo estado antes da exclusao."""
    aplicar_merge_delta(pd.DataFrame([_linha("DF-4", 100)]), temp_delta_dir)

    lote = [_linha("DF-4", 200, op="U", geom=GEOM_B, condicao="Retificado", area=120.0)] + _evento(
        "table public.imovel_car: DELETE: cod_imovel[character varying]:'DF-4'", "0/12C"
    )
    aplicar_merge_delta(pd.DataFrame(lote), temp_delta_dir)

    linha = _ler(temp_delta_dir, "DF-4")
    assert linha["operacao_cdc"] == "D"
    assert linha["lsn_origem"] == lsn_para_int("0/12C")
    assert linha["condicao"] == "Retificado"
    assert linha["area_ha"] == 120.0
    assert linha["geom_ewkb_hex"] == GEOM_B


def test_delete_seguido_de_reinsercao_no_mesmo_lote(temp_delta_dir):
    """DELETE e INSERT do mesmo imovel no mesmo micro-lote: o imovel termina vivo, com o estado novo."""
    aplicar_merge_delta(pd.DataFrame([_linha("DF-5", 100)]), temp_delta_dir)

    lote = _evento("table public.imovel_car: DELETE: cod_imovel[character varying]:'DF-5'", "0/C8") + [
        _linha("DF-5", 300, op="I", geom=GEOM_B, condicao="Recadastrado")
    ]
    aplicar_merge_delta(pd.DataFrame(lote), temp_delta_dir)

    linha = _ler(temp_delta_dir, "DF-5")
    assert linha["operacao_cdc"] == "I"
    assert linha["condicao"] == "Recadastrado"
    assert linha["geom_ewkb_hex"] == GEOM_B
    assert len(DeltaTable(temp_delta_dir).to_pandas()) == 1


def test_evento_sem_mudanca_de_conteudo_nao_regrava_a_linha(temp_delta_dir):
    """
    Recarga do OLTP com os mesmos dados ou reentrega do slot: o LSN avanca, mas o carimbo
    de ingestao fica, para o snapshot SCD Tipo 2 nao abrir uma versao identica.
    """
    antes = datetime(2026, 10, 1, tzinfo=timezone.utc)
    original = _linha("DF-6", 100, origem="snapshot")
    original["data_hora_ingestao"] = antes
    aplicar_merge_delta(pd.DataFrame([original]), temp_delta_dir)

    # Mesmo conteudo, LSN maior, geometria repetida por extenso.
    aplicar_merge_delta(pd.DataFrame([_linha("DF-6", 500, op="I")]), temp_delta_dir)
    linha = _ler(temp_delta_dir, "DF-6")
    assert linha["lsn_origem"] == 500
    assert linha["data_hora_ingestao"] == antes
    assert linha["origem_ingestao"] == "snapshot"

    # Mesmo conteudo, geometria como TOAST inalterado.
    aplicar_merge_delta(pd.DataFrame([_linha("DF-6", 600, op="U", geom="unchanged-toast-datum")]), temp_delta_dir)
    linha = _ler(temp_delta_dir, "DF-6")
    assert linha["lsn_origem"] == 600
    assert linha["data_hora_ingestao"] == antes

    # Conteudo diferente: a linha e regravada com o carimbo novo.
    aplicar_merge_delta(pd.DataFrame([_linha("DF-6", 700, op="U", area=101.0)]), temp_delta_dir)
    linha = _ler(temp_delta_dir, "DF-6")
    assert linha["area_ha"] == 101.0
    assert linha["data_hora_ingestao"] == AGORA
    assert linha["operacao_cdc"] == "U"


def test_parse_update_que_troca_a_pk():
    """old-key e new-tuple com chaves diferentes: a chave nova vale e a antiga fica registrada."""
    msg = (
        "table public.imovel_car: UPDATE: old-key: cod_imovel[character varying]:'DF-VELHO' "
        "new-tuple: cod_imovel[character varying]:'DF-NOVO' situacao[character varying]:'AT' "
        "geom[geometry]:unchanged-toast-datum"
    )
    evento = parse_linha_test_decoding(msg)
    assert evento["cod_imovel"] == "DF-NOVO"
    assert evento["cod_imovel_anterior"] == "DF-VELHO"


def test_troca_de_pk_exclui_a_chave_antiga_e_cria_a_nova(temp_delta_dir):
    """UPDATE que troca a PK: a chave antiga vira exclusao logica e a nova herda a geometria dela."""
    aplicar_merge_delta(pd.DataFrame([_linha("DF-VELHO", 100)]), temp_delta_dir)

    lote = _evento(
        "table public.imovel_car: UPDATE: old-key: cod_imovel[character varying]:'DF-VELHO' "
        "new-tuple: cod_imovel[character varying]:'DF-NOVO' situacao[character varying]:'AT' "
        "condicao[character varying]:'Ativo' area_ha[numeric]:100.0 data_download[date]:'2026-09-27' "
        "geom[geometry]:unchanged-toast-datum",
        "0/C8",
    )
    assert [l["operacao_cdc"] for l in lote] == ["D", "U"]
    aplicar_merge_delta(pd.DataFrame(lote), temp_delta_dir)

    velho, novo = _ler(temp_delta_dir, "DF-VELHO"), _ler(temp_delta_dir, "DF-NOVO")
    assert velho["operacao_cdc"] == "D"
    assert velho["geom_ewkb_hex"] == GEOM_A
    assert novo["operacao_cdc"] == "U"
    assert novo["geom_ewkb_hex"] == GEOM_A
    assert novo["lsn_origem"] == lsn_para_int("0/C8")


def test_ressincronizacao_apos_slot_recriado(temp_delta_dir):
    """
    Slot recriado com a tabela Delta ja existente: o snapshot novo corrige o que o CDC
    perdeu, sem regravar o que nao mudou e sem apagar o historico de exclusoes.
    """
    antes = datetime(2026, 10, 1, tzinfo=timezone.utc)
    base = [_linha(cod, 100, origem="snapshot") for cod in ("DF-IGUAL", "DF-MUDOU", "DF-SUMIU", "DF-VOLTOU")]
    for linha in base:
        linha["data_hora_ingestao"] = antes
    base[3]["operacao_cdc"] = "D"
    aplicar_merge_delta(pd.DataFrame(base[:3]), temp_delta_dir)
    aplicar_merge_delta(pd.DataFrame(base[3:]), temp_delta_dir)

    snapshot = [
        _linha("DF-IGUAL", 900, origem="snapshot"),
        _linha("DF-MUDOU", 900, origem="snapshot", condicao="Retificado", area=150.0),
        _linha("DF-VOLTOU", 900, origem="snapshot"),
        _linha("DF-NOVO", 900, origem="snapshot", geom=GEOM_B),
    ]
    ressincronizar_snapshot(preparar_tabela_arrow(pd.DataFrame(snapshot)), temp_delta_dir, 900)

    df = DeltaTable(temp_delta_dir).to_pandas().set_index("cod_imovel")
    assert len(df) == 5

    assert df.loc["DF-IGUAL", "lsn_origem"] == 900
    assert df.loc["DF-IGUAL", "data_hora_ingestao"] == antes, "linha sem mudanca nao pode ganhar carimbo novo"

    assert df.loc["DF-MUDOU", "condicao"] == "Retificado"
    assert df.loc["DF-MUDOU", "area_ha"] == 150.0
    assert df.loc["DF-MUDOU", "data_hora_ingestao"] == AGORA

    assert df.loc["DF-SUMIU", "operacao_cdc"] == "D"
    assert df.loc["DF-SUMIU", "lsn_origem"] == 900
    assert df.loc["DF-SUMIU", "condicao"] == "Ativo", "exclusao logica preserva os atributos"
    assert df.loc["DF-SUMIU", "data_hora_ingestao"] > antes

    assert df.loc["DF-VOLTOU", "operacao_cdc"] == "I"
    assert df.loc["DF-NOVO", "geom_ewkb_hex"] == GEOM_B


def main():
    """Execucao direta dos testes sem dependencia estrita do CLI do pytest."""
    print("=== Executando suite de testes automatizados do Consumidor CDC (Tarefa #09 / GH #3) ===")

    print("\n1. Testando conversao de LSN para 64-bit e ordenacao...")
    test_lsn_para_int()
    print("-> OK!")

    print("\n2. Testando extrator de tuplas test_decoding...")
    test_parse_valores_tupla()
    print("-> OK!")

    print("\n3. Testando parser de mensagens test_decoding (INSERT, UPDATE TOAST, DELETE, tabelas externas)...")
    test_parse_linha_test_decoding_insert()
    test_parse_linha_test_decoding_update_com_toast()
    test_parse_linha_test_decoding_delete()
    test_parse_linha_test_decoding_tabela_irrelevante()
    print("-> OK!")

    print("\n4. Testando conversao de tipos para esquema Delta Lake...")
    test_converter_evento_para_linha_delta()
    print("-> OK!")

    with tempfile.TemporaryDirectory() as tmp_dir:
        print("\n5. Testando idempotencia de merge e replay de lote...")
        test_merge_idempotente_reprocessamento(tmp_dir)
        print("-> OK!")

    with tempfile.TemporaryDirectory() as tmp_dir:
        print("\n6. Testando guarda de LSN fora de ordem (rejeicao de mudanca antiga)...")
        test_guarda_lsn_fora_de_ordem(tmp_dir)
        print("-> OK!")

    with tempfile.TemporaryDirectory() as tmp_dir:
        print("\n7. Testando soft-delete de imovel no lakehouse...")
        test_soft_delete(tmp_dir)
        print("-> OK!")

    with tempfile.TemporaryDirectory() as tmp_dir:
        print("\n8. Testando preservacao de geometria em tuplas TOAST...")
        test_preservacao_unchanged_toast_datum(tmp_dir)
        print("-> OK!")

    print("\n9. Testando consolidacao do micro-lote, exclusao logica, troca de PK e ressincronizacao...")
    test_parse_update_que_troca_a_pk()
    for teste in (
        test_delete_real_preserva_atributos,
        test_insert_e_update_toast_no_mesmo_lote_herdam_a_geometria,
        test_marcador_toast_nunca_e_gravado_como_geometria,
        test_update_para_null_no_mesmo_lote_nao_herda_valor_anterior,
        test_update_seguido_de_delete_no_mesmo_lote,
        test_delete_seguido_de_reinsercao_no_mesmo_lote,
        test_evento_sem_mudanca_de_conteudo_nao_regrava_a_linha,
        test_troca_de_pk_exclui_a_chave_antiga_e_cria_a_nova,
        test_ressincronizacao_apos_slot_recriado,
    ):
        with tempfile.TemporaryDirectory() as tmp_dir:
            teste(tmp_dir)
    print("-> OK!")

    print("\nTodos os testes unitarios e de idempotencia CDC foram executados e APROVADOS com sucesso!")


if __name__ == "__main__":
    main()
