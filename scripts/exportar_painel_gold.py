#!/usr/bin/env python3
"""
Exporta a camada Gold (dbt-duckdb) para docs/assets/dados_dashboard/gold.json, o arquivo
que o dashboard publicado le para responder a pergunta de gestao.

Tudo o que o painel mostra sobre imoveis reincidentes sai daqui: a fila de vistoria
(gold.painel_imoveis_prioritarios), os totais, as distribuicoes e as geometrias dos
imoveis da fila. O dashboard nao recalcula o cruzamento.

Uso (no compose): docker compose --profile transformacao run --rm exportar_painel
Uso (no host):    python scripts/exportar_painel_gold.py --duckdb data/warehouse/corta_fogo.duckdb
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import duckdb

TAMANHO_FILA = 50
SITUACOES = ["AT", "PE", "SU", "CA"]
FAIXAS_AREA = ["Até 20 ha", "20 a 100 ha", "100 a 500 ha", "500 a 5.000 ha", "Acima de 5.000 ha"]
CLASSIFICACOES = ["PRIORIDADE CRITICA", "PRIORIDADE ALTA", "PRIORIDADE MEDIA", "PRIORIDADE BAIXA"]
VARS_DO_INDICE = [
    "peso_recorrencia",
    "peso_recencia",
    "peso_intensidade",
    "area_minima_ha",
    "anos_minimos_reincidencia",
    "ano_inicio_serie",
    "ano_fim_serie",
]


def arredondar_coords(obj, casas=4):
    """Arredonda coordenadas recursivamente para reduzir o tamanho do JSON."""
    if isinstance(obj, float):
        return round(obj, casas)
    if isinstance(obj, list):
        return [arredondar_coords(x, casas) for x in obj]
    if isinstance(obj, dict):
        return {k: arredondar_coords(v, casas) for k, v in obj.items()}
    return obj


def ler_vars_do_indice(projeto_dbt: Path) -> dict:
    """Pesos e parametros do indice, lidos do dbt_project.yml (a fonte que o dbt usa)."""
    arquivo = projeto_dbt / "dbt_project.yml"
    if not arquivo.exists():
        return {}
    import yaml

    variaveis = (yaml.safe_load(arquivo.read_text(encoding="utf-8")) or {}).get("vars", {})
    return {nome: variaveis[nome] for nome in VARS_DO_INDICE if nome in variaveis}


def exportar(con, projeto_dbt: Path, sla_horas: float) -> dict:
    def linhas(sql, parametros=None):
        cur = con.execute(sql, parametros or [])
        colunas = [d[0] for d in cur.description]
        return [dict(zip(colunas, linha)) for linha in cur.fetchall()]

    def valor(sql):
        return con.execute(sql).fetchone()[0]

    gerado_em = valor("SELECT max(gerado_em) FROM gold.painel_imoveis_prioritarios")
    if gerado_em is None:
        raise SystemExit("gold.painel_imoveis_prioritarios esta vazia: rode o dbt build antes de exportar.")

    # --- Totais da pergunta de gestao -------------------------------------------------
    referencia = {
        "fonte": "gold.painel_imoveis_prioritarios e gold.fct_reincidencia_imovel (dbt-duckdb)",
        "imoveis_total_car": valor(
            "SELECT count(*) FROM gold.dim_imovel_car WHERE is_current AND NOT is_excluido"
        ),
        "imoveis_com_foco_protegido": valor("SELECT count(*) FROM gold.fct_reincidencia_imovel"),
        "imoveis_reincidentes": valor("SELECT count(*) FROM gold.painel_imoveis_prioritarios"),
        "focos_em_reincidentes": valor("SELECT coalesce(sum(total_focos), 0) FROM gold.painel_imoveis_prioritarios"),
        "reincidentes_por_categoria": linhas(
            """
            SELECT count(*) FILTER (WHERE atinge_uc_1km)        AS uc_1km,
                   count(*) FILTER (WHERE atinge_reserva_legal) AS reserva_legal,
                   count(*) FILTER (WHERE atinge_app)           AS app
            FROM gold.painel_imoveis_prioritarios
            """
        )[0],
        "distribuicao_anos": {
            str(l["anos_com_foco"]): l["n"]
            for l in linhas(
                "SELECT anos_com_foco, count(*) AS n FROM gold.painel_imoveis_prioritarios GROUP BY 1 ORDER BY 1"
            )
        },
        "situacao_cadastral": {
            l["situacao"]: l["n"]
            for l in linhas(
                "SELECT coalesce(situacao, 'ND') AS situacao, count(*) AS n "
                "FROM gold.painel_imoveis_prioritarios GROUP BY 1 ORDER BY 2 DESC"
            )
        },
    }

    # --- Distribuicoes para os graficos -----------------------------------------------
    por_situacao = {
        l["situacao"]: {"imoveis": l["imoveis"], "focos": l["focos"], "mediana_ha": l["mediana_ha"]}
        for l in linhas(
            """
            SELECT situacao, count(*) AS imoveis, sum(total_focos) AS focos,
                   round(median(area_ha), 1) AS mediana_ha
            FROM gold.painel_imoveis_prioritarios
            GROUP BY 1
            """
        )
    }
    por_faixa = {
        l["faixa"]: l["n"]
        for l in linhas(
            """
            SELECT CASE WHEN area_ha <= 20 THEN 'Até 20 ha'
                        WHEN area_ha <= 100 THEN '20 a 100 ha'
                        WHEN area_ha <= 500 THEN '100 a 500 ha'
                        WHEN area_ha <= 5000 THEN '500 a 5.000 ha'
                        ELSE 'Acima de 5.000 ha' END AS faixa,
                   count(*) AS n
            FROM gold.painel_imoveis_prioritarios
            GROUP BY 1
            """
        )
    }
    por_classificacao = {
        l["classificacao_prioridade"]: {
            "imoveis": l["imoveis"],
            "indice_min": l["indice_min"],
            "indice_max": l["indice_max"],
            "cadastro_ativo": l["ativos"],
        }
        for l in linhas(
            """
            SELECT classificacao_prioridade, count(*) AS imoveis,
                   min(indice_prioridade) AS indice_min, max(indice_prioridade) AS indice_max,
                   count(*) FILTER (WHERE cadastro_ativo) AS ativos
            FROM gold.painel_imoveis_prioritarios
            GROUP BY 1
            """
        )
    }
    por_ra = linhas(
        """
        SELECT codigo_regiao_administrativa AS codigo, regiao_administrativa AS nome,
               count(*) AS reincidentes,
               count(*) FILTER (WHERE classificacao_prioridade = 'PRIORIDADE CRITICA') AS criticos,
               sum(total_focos) AS focos
        FROM gold.painel_imoveis_prioritarios
        GROUP BY 1, 2
        ORDER BY reincidentes DESC, nome
        """
    )

    cruzamento = {
        "nota": "Numeros da camada Gold (Reserva Legal propria, APP ou ate 1 km de UC).",
        "imoveis_com_foco_prot": referencia["imoveis_com_foco_protegido"],
        "total_reincidentes": referencia["imoveis_reincidentes"],
        "reincidentes_rl": referencia["reincidentes_por_categoria"]["reserva_legal"],
        "reincidentes_uc1km": referencia["reincidentes_por_categoria"]["uc_1km"],
        "reincidentes_app": referencia["reincidentes_por_categoria"]["app"],
        "por_situacao": {
            s: por_situacao.get(s, {"imoveis": 0, "focos": 0, "mediana_ha": 0.0}) for s in SITUACOES
        },
        "por_faixa_area": {f: por_faixa.get(f, 0) for f in FAIXAS_AREA},
        "distribuicao_anos": {str(a): referencia["distribuicao_anos"].get(str(a), 0) for a in range(2, 12)},
        "por_classificacao": {
            c: por_classificacao.get(c, {"imoveis": 0, "indice_min": None, "indice_max": None, "cadastro_ativo": 0})
            for c in CLASSIFICACOES
        },
        "por_ra": por_ra,
    }

    # --- Fila de vistoria (primeiras posicoes) ----------------------------------------
    fila = linhas(
        f"""
        WITH fila AS (
            SELECT * FROM gold.painel_imoveis_prioritarios WHERE posicao <= {TAMANHO_FILA}
        ),
        focos_no_imovel AS (
            SELECT cod_imovel, count(DISTINCT id_foco) AS focos_no_imovel
            FROM intermediate.int_focos_imoveis
            WHERE cod_imovel IN (SELECT cod_imovel FROM fila)
            GROUP BY 1
        ),
        por_ano AS (
            SELECT cod_imovel, map_from_entries(list((ano::varchar, total_focos) ORDER BY ano)) AS por_ano
            FROM gold.mart_reincidencia_imovel_ano
            WHERE cod_imovel IN (SELECT cod_imovel FROM fila)
            GROUP BY 1
        ),
        centro AS (
            SELECT d.cod_imovel,
                   ST_Transform(ST_PointOnSurface(d.geom), 'EPSG:31983', 'EPSG:4326', always_xy := true) AS ponto
            FROM gold.dim_imovel_car d
            WHERE d.is_current AND d.cod_imovel IN (SELECT cod_imovel FROM fila)
        )
        SELECT f.posicao AS rank, f.cod_imovel, f.situacao, f.cadastro_ativo, f.condicao,
               f.regiao_administrativa AS ra, f.codigo_regiao_administrativa AS ra_codigo,
               f.regiao_administrativa AS municipio,
               round(f.area_ha, 1) AS area_ha,
               round(ST_Y(c.ponto), 4) AS lat, round(ST_X(c.ponto), 4) AS lon,
               f.lista_anos AS anos, f.anos_com_foco AS anos_qtd, f.ultimo_ano_com_foco AS ultimo_ano,
               coalesce(n.focos_no_imovel, f.total_focos) AS focos_total,
               f.total_focos AS focos_prot, f.dias_com_foco, f.dias_com_foco_por_100ha AS dias_por_100ha,
               f.focos_satelite_referencia AS focos_ref,
               f.indice_prioridade AS indice, f.classificacao_prioridade AS classificacao,
               f.componente_recorrencia AS comp_recorrencia, f.componente_recencia AS comp_recencia,
               f.componente_intensidade AS comp_intensidade,
               f.atinge_reserva_legal AS atinge_rl, f.atinge_uc_1km AS atinge_uc1km, f.atinge_app,
               p.por_ano
        FROM fila f
        LEFT JOIN focos_no_imovel n USING (cod_imovel)
        LEFT JOIN por_ano p USING (cod_imovel)
        LEFT JOIN centro c USING (cod_imovel)
        ORDER BY f.posicao
        """
    )
    for item in fila:
        item["por_ano"] = dict(item["por_ano"] or {})

    # --- Geometrias da fila (perimetro e Reservas Legais), simplificadas, em WGS84 -----
    def geojson(expressao_geom):
        return (
            f"ST_AsGeoJSON(ST_Transform(ST_SimplifyPreserveTopology({expressao_geom}, 60), "
            "'EPSG:31983', 'EPSG:4326', always_xy := true))"
        )

    geoms = {item["cod_imovel"]: {"imovel": None, "reserva_legal": []} for item in fila}
    for l in linhas(
        f"""
        SELECT d.cod_imovel, {geojson('d.geom')} AS gj
        FROM gold.dim_imovel_car d
        WHERE d.is_current
          AND d.cod_imovel IN (SELECT cod_imovel FROM gold.painel_imoveis_prioritarios WHERE posicao <= {TAMANHO_FILA})
        """
    ):
        geoms[l["cod_imovel"]]["imovel"] = arredondar_coords(json.loads(l["gj"]))
    for l in linhas(
        f"""
        SELECT t.cod_imovel, {geojson('t.geom')} AS gj
        FROM gold.dim_territorio t
        WHERE t.tipo_area = 'reserva_legal'
          AND t.cod_imovel IN (SELECT cod_imovel FROM gold.painel_imoveis_prioritarios WHERE posicao <= {TAMANHO_FILA})
        ORDER BY t.cod_imovel, t.id_feicao_origem
        """
    ):
        geometria = json.loads(l["gj"])
        if geometria.get("coordinates"):
            geoms[l["cod_imovel"]]["reserva_legal"].append(arredondar_coords(geometria))

    return {
        "fonte": "gold.painel_imoveis_prioritarios (camada Gold, dbt-duckdb)",
        "gerado_em": gerado_em.astimezone(timezone.utc).isoformat(),
        "exportado_em": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "sla_frescor_horas": sla_horas,
        "indice": {
            "nome": "Indice de Prioridade de Vistoria (IPV)",
            "adr": "docs/adr/04-indice-de-prioridade-de-vistoria.md",
            "parametros": ler_vars_do_indice(projeto_dbt),
        },
        "gold_referencia": referencia,
        "car_cruzamento": cruzamento,
        "car_top50": fila,
        "car_top50_geoms": geoms,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Exporta a camada Gold para o JSON do dashboard.")
    parser.add_argument("--duckdb", default=os.getenv("DUCKDB_PATH", "data/warehouse/corta_fogo.duckdb"))
    parser.add_argument("--saida", default=os.getenv("SAIDA_DIR", "/app/saida"))
    parser.add_argument("--projeto-dbt", default=os.getenv("DBT_PROJECT_DIR", "/app/transformacao"))
    parser.add_argument("--sla-horas", type=float, default=float(os.getenv("SLA_FRESCOR_HORAS", "30")))
    args = parser.parse_args()

    con = duckdb.connect(args.duckdb, read_only=True)
    try:
        con.execute("LOAD spatial")
        dados = exportar(con, Path(args.projeto_dbt), args.sla_horas)
    finally:
        con.close()

    saida = Path(args.saida)
    saida.mkdir(parents=True, exist_ok=True)
    destino = saida / "gold.json"
    with open(destino, "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, separators=(",", ":"), default=str)

    ref = dados["gold_referencia"]
    print(f"[OK] {destino} ({destino.stat().st_size / 1024:.1f} KB)")
    print(
        f"     {ref['imoveis_reincidentes']} imoveis reincidentes, {ref['focos_em_reincidentes']} focos, "
        f"fila com {len(dados['car_top50'])} imoveis, gold gerada em {dados['gerado_em']}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
