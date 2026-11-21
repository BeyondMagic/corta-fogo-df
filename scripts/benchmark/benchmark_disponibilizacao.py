#!/usr/bin/env python3
"""
Benchmark reproduzivel do mecanismo de disponibilizacao de dados (ADR 0004).

Compara as tres alternativas avaliadas sobre os dados reais do Distrito Federal:
- Alternativa A (Opcao nula): CSV tabular dos reincidentes + MV no PostGIS (V7/V9).
- Alternativa B: consulta direta em tempo real ao warehouse (DuckDB / API).
- Alternativa C (Escolhida): retrato JSON estatico versionado (gold.json + painel).

Funciona somente com biblioteca padrao sobre os artefatos versionados no repositorio
(docs/assets/dados_dashboard/, docs/explain/, data/raw/, data/processed/) e tambem
mede PostgreSQL e DuckDB ao vivo quando os servicos ou bibliotecas estiverem ativos.

Uso:
    python3 scripts/benchmark/benchmark_disponibilizacao.py
    python3 scripts/benchmark/benchmark_disponibilizacao.py --iteracoes 50
"""

from __future__ import annotations

import argparse
import csv
import gzip
import io
import json
import re
import statistics
import time
from pathlib import Path
from typing import Any, Dict, List, Optional


RAIZ = Path(__file__).resolve().parents[2]
DIR_PAINEL = RAIZ / "docs" / "assets" / "dados_dashboard"
DIR_EXPLAIN = RAIZ / "docs" / "explain"
DIR_RAW = RAIZ / "data" / "raw"
CSV_FOCOS = RAIZ / "data" / "processed" / "focos_df_2015_2025.csv"


def contar_vertices_geojson(geom: Optional[Dict[str, Any]]) -> int:
    """Conta vertices de um GeoJSON Polygon ou MultiPolygon."""
    if not geom:
        return 0
    coords = geom.get("coordinates")
    gtype = geom.get("type")
    if not coords:
        return 0
    if gtype == "Polygon":
        return sum(len(anel) for anel in coords)
    if gtype == "MultiPolygon":
        return sum(len(anel) for poli in coords for anel in poli)
    return 0


def extrair_tempo_explain(caminho: Path) -> Optional[float]:
    """Extrai Execution Time (ms) de um plano EXPLAIN ANALYZE salvo em docs/explain/."""
    if not caminho.exists():
        return None
    texto = caminho.read_text(encoding="utf-8")
    m = re.search(r"Execution Time:\s*([0-9]+(?:\.[0-9]+)?)\s*ms", texto)
    return float(m.group(1)) if m else None


def medir_retrato_json(iteracoes: int) -> Dict[str, Any]:
    """Mede tamanho em disco, gzip, vertices e latencia de parse de gold.json."""
    caminho_gold = DIR_PAINEL / "gold.json"
    if not caminho_gold.exists():
        raise FileNotFoundError(f"Arquivo nao encontrado: {caminho_gold}")

    tempos_gold_ms: List[float] = []
    dados_gold: Dict[str, Any] = {}
    for _ in range(iteracoes):
        t0 = time.perf_counter()
        raw = caminho_gold.read_bytes()
        dados_gold = json.loads(raw)
        tempos_gold_ms.append((time.perf_counter() - t0) * 1000.0)

    raw_gold = caminho_gold.read_bytes()
    gzip_gold = gzip.compress(raw_gold, compresslevel=6)

    geoms = dados_gold.get("car_top50_geoms", {})
    vertices_imoveis = sum(contar_vertices_geojson(v.get("imovel")) for v in geoms.values())
    vertices_rl = sum(
        sum(contar_vertices_geojson(rl) for rl in v.get("reserva_legal", []))
        for v in geoms.values()
    )

    arquivos_painel = ["gold.json", "resumo.json", "geometrias.json", "focos.json"]
    tamanhos_painel: Dict[str, int] = {}
    tempos_lote_ms: List[float] = []
    for _ in range(iteracoes):
        t0 = time.perf_counter()
        for nome in arquivos_painel:
            arq = DIR_PAINEL / nome
            if arq.exists():
                b = arq.read_bytes()
                tamanhos_painel[nome] = len(b)
                json.loads(b)
        tempos_lote_ms.append((time.perf_counter() - t0) * 1000.0)

    tempos_sorted = sorted(tempos_gold_ms)
    p95_idx = min(len(tempos_sorted) - 1, int(0.95 * len(tempos_sorted)))
    lote_sorted = sorted(tempos_lote_ms)
    lote_p95_idx = min(len(lote_sorted) - 1, int(0.95 * len(lote_sorted)))

    return {
        "gold_bytes": len(raw_gold),
        "gold_gzip_bytes": len(gzip_gold),
        "gold_media_ms": statistics.mean(tempos_gold_ms),
        "gold_p95_ms": tempos_sorted[p95_idx],
        "lote_total_bytes": sum(tamanhos_painel.values()),
        "lote_arquivos_bytes": tamanhos_painel,
        "lote_media_ms": statistics.mean(tempos_lote_ms),
        "lote_p95_ms": lote_sorted[lote_p95_idx],
        "top50_len": len(dados_gold.get("car_top50", [])),
        "vertices_imoveis_top50": vertices_imoveis,
        "vertices_rl_top50": vertices_rl,
        "dados_gold": dados_gold,
    }


def medir_csv_nulo(dados_gold: Dict[str, Any], iteracoes: int) -> Dict[str, Any]:
    """Mede serializacao e tamanho da opcao nula em CSV tabular (fila sem geometrias)."""
    fila = dados_gold.get("car_top50", [])
    if not fila:
        return {"csv_bytes": 0, "csv_media_ms": 0.0}

    colunas = [
        "rank",
        "cod_imovel",
        "ra",
        "situacao",
        "cadastro_ativo",
        "area_ha",
        "indice",
        "classificacao",
        "anos_qtd",
        "ultimo_ano",
        "focos_prot",
        "dias_com_foco",
        "dias_por_100ha",
        "atinge_rl",
        "atinge_app",
        "atinge_uc1km",
    ]
    tempos_ms: List[float] = []
    csv_bytes = 0
    for _ in range(iteracoes):
        t0 = time.perf_counter()
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=colunas, extrasaction="ignore")
        writer.writeheader()
        for item in fila:
            writer.writerow(item)
        csv_bytes = len(buf.getvalue().encode("utf-8"))
        tempos_ms.append((time.perf_counter() - t0) * 1000.0)

    return {
        "csv_bytes": csv_bytes,
        "csv_media_ms": statistics.mean(tempos_ms),
    }


def medir_fontes_brutas() -> Dict[str, int]:
    """Soma o tamanho dos arquivos de origem brutos para comparacao de escala."""
    brutos: Dict[str, int] = {}
    if DIR_RAW.exists():
        for arq in sorted(DIR_RAW.iterdir()):
            if arq.is_file():
                brutos[arq.name] = arq.stat().st_size
    if CSV_FOCOS.exists():
        brutos[CSV_FOCOS.name] = CSV_FOCOS.stat().st_size
    return brutos


def tentar_medir_duckdb(duckdb_path: Path) -> Optional[Dict[str, Any]]:
    """Mede consulta SQL direta se duckdb e o arquivo .duckdb estiverem disponiveis."""
    if not duckdb_path.exists():
        return None
    try:
        import duckdb  # type: ignore
    except ImportError:
        return None

    con = duckdb.connect(str(duckdb_path), read_only=True)
    try:
        t0 = time.perf_counter()
        rows = con.execute(
            "SELECT posicao, cod_imovel, indice_prioridade "
            "FROM gold.painel_imoveis_prioritarios ORDER BY posicao"
        ).fetchall()
        ms = (time.perf_counter() - t0) * 1000.0
        return {"linhas": len(rows), "consulta_ms": ms}
    finally:
        con.close()


def tentar_medir_postgres(host: str, port: int, dbname: str, user: str, password: str) -> Optional[Dict[str, Any]]:
    """Mede consulta na MV gold do PostgreSQL se psycopg2 e o banco estiverem ativos."""
    try:
        import psycopg2  # type: ignore
    except ImportError:
        return None
    try:
        conn = psycopg2.connect(
            host=host, port=port, dbname=dbname, user=user, password=password, connect_timeout=2
        )
    except Exception:
        return None

    try:
        with conn.cursor() as cur:
            t0 = time.perf_counter()
            cur.execute("SELECT cod_imovel, anos_com_foco, total_focos FROM gold.mv_imoveis_reincidentes_areas_protegidas")
            rows = cur.fetchall()
            ms = (time.perf_counter() - t0) * 1000.0
            return {"linhas": len(rows), "consulta_mv_ms": ms}
    finally:
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark reproduzivel do ADR 0004.")
    parser.add_argument("--iteracoes", type=int, default=30)
    parser.add_argument("--duckdb", default=str(RAIZ / "data" / "warehouse" / "corta_fogo.duckdb"))
    parser.add_argument("--pg-host", default="localhost")
    parser.add_argument("--pg-port", type=int, default=5434)
    parser.add_argument("--pg-db", default="corta-fogo-df")
    parser.add_argument("--pg-user", default="corta-fogo")
    parser.add_argument("--pg-password", default="corta-fogo")
    args = parser.parse_args()

    json_res = medir_retrato_json(args.iteracoes)
    csv_res = medir_csv_nulo(json_res["dados_gold"], args.iteracoes)
    brutos = medir_fontes_brutas()
    t_v7 = extrair_tempo_explain(DIR_EXPLAIN / "antes_mv_imoveis_reincidentes.txt")
    t_v9 = extrair_tempo_explain(DIR_EXPLAIN / "depois_mv_imoveis_reincidentes.txt")
    duck_res = tentar_medir_duckdb(Path(args.duckdb))
    pg_res = tentar_medir_postgres(args.pg_host, args.pg_port, args.pg_db, args.pg_user, args.pg_password)

    total_bruto = sum(brutos.values())
    reducao_pct = (1.0 - (json_res["gold_bytes"] / total_bruto)) * 100.0 if total_bruto else 0.0

    print("=== Benchmark de Disponibilizacao (ADR 0004) ===")
    print(f"Iteracoes de parse/serializacao: {args.iteracoes}")
    print(
        f"gold.json: {json_res['gold_bytes']:,} bytes ({json_res['gold_bytes']/1024:.1f} KB) | "
        f"gzip: {json_res['gold_gzip_bytes']:,} bytes ({json_res['gold_gzip_bytes']/1024:.1f} KB)"
    )
    print(
        f"Parse gold.json: media {json_res['gold_media_ms']:.2f} ms | "
        f"p95 {json_res['gold_p95_ms']:.2f} ms"
    )
    print(
        f"Pacote completo do painel (4 JSONs): {json_res['lote_total_bytes']:,} bytes "
        f"({json_res['lote_total_bytes']/(1024*1024):.2f} MiB) | "
        f"parse medio {json_res['lote_media_ms']:.2f} ms (p95 {json_res['lote_p95_ms']:.2f} ms)"
    )
    print(
        f"Top {json_res['top50_len']} geometrias simplificadas (60 m): "
        f"{json_res['vertices_imoveis_top50']} vertices (imoveis) + "
        f"{json_res['vertices_rl_top50']} vertices (RL)"
    )
    print(
        f"Opcao nula CSV tabular (top {json_res['top50_len']} sem geometria): "
        f"{csv_res['csv_bytes']:,} bytes ({csv_res['csv_bytes']/1024:.1f} KB) | "
        f"geracao media {csv_res['csv_media_ms']:.2f} ms"
    )
    print(f"Fontes brutas em data/raw + processed: {total_bruto:,} bytes ({total_bruto/(1024*1024):.2f} MiB)")
    print(f"Reducao do gold.json frente as fontes brutas: {reducao_pct:.2f}%")
    if t_v7 is not None and t_v9 is not None:
        print(f"Planos EXPLAIN PostGIS (docs/explain/): V7 {t_v7:.1f} ms -> V9 {t_v9:.1f} ms")
    if duck_res:
        print(f"DuckDB ao vivo (painel_imoveis_prioritarios, {duck_res['linhas']} linhas): {duck_res['consulta_ms']:.2f} ms")
    else:
        print("DuckDB ao vivo: banco local ausente (usar --profile transformacao run --rm dbt show)")
    if pg_res:
        print(f"PostgreSQL MV ao vivo ({pg_res['linhas']} linhas): {pg_res['consulta_mv_ms']:.2f} ms")
    else:
        print("PostgreSQL MV ao vivo: servico inativo nesta sessao (dados de V7/V9 lidos de docs/explain/)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
