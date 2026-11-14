#!/usr/bin/env python3
"""
Pipeline de extracao e download das camadas geograficas do DF.
Baixa camadas vetoriais abertas (UCs e APPs) do SISDIA/IBRAM
e organiza a pasta data/raw para ingestao no PostGIS.
"""

import argparse
import json
import os
import sys
import urllib.request
from datetime import datetime, timezone

RAW_DIR = os.path.join("data", "raw")

SISDIA_SERVICES = {
    "unidades_conservacao": {
        "url": "https://sisdia.df.gov.br/server/rest/services/01_AMBIENTAL/Unidades_de_Conservacao_Gestao_IBRAM/FeatureServer/0/query?where=1%3D1&outFields=*&f=geojson",
        "filename": "unidades_conservacao.geojson",
        "descricao": "Unidades de Conservacao de Gestao IBRAM (Distrital e Federal no DF)",
    },
    "app_nascentes": {
        "url": "https://sisdia.df.gov.br/server/rest/services/01_AMBIENTAL/APP_Nascente/FeatureServer/0/query?where=1%3D1&outFields=*&f=geojson",
        "filename": "app_nascentes.geojson",
        "descricao": "APPs de Nascentes do DF (IBRAM)",
    },
    "app_borda_chapada": {
        "url": "https://sisdia.df.gov.br/server/rest/services/01_AMBIENTAL/APP_Borda_de_Chapada/FeatureServer/0/query?where=1%3D1&outFields=*&f=geojson",
        "filename": "app_borda_chapada.geojson",
        "descricao": "APPs de Borda de Chapada do DF (IBRAM)",
    },
    "app_reservatorio": {
        "url": "https://sisdia.df.gov.br/server/rest/services/01_AMBIENTAL/APP_Reservatorio/FeatureServer/0/query?where=1%3D1&outFields=*&f=geojson",
        "filename": "app_reservatorio.geojson",
        "descricao": "APPs de Reservatorios do DF (IBRAM)",
    },
    # Fonte diferente das demais (IDE-DF / SEDUH), mesmo protocolo ArcGIS REST.
    "regioes_administrativas": {
        "url": "https://www.geoservicos.ide.df.gov.br/arcgis/rest/services/Publico/LIMITES/FeatureServer/1/query?where=1%3D1&outFields=*&outSR=4326&f=geojson",
        "filename": "regioes_administrativas.geojson",
        "descricao": "Regioes Administrativas do DF (IDE-DF / SEDUH)",
    },
}


def baixar_camada_geojson(nome: str, info: dict, output_dir: str = RAW_DIR) -> str:
    """
    Baixa uma camada vetorial em formato GeoJSON do endpoint REST do SISDIA.
    """
    os.makedirs(output_dir, exist_ok=True)
    destino = os.path.join(output_dir, info["filename"])

    print(f"Baixando {info['descricao']}...")
    req = urllib.request.Request(
        info["url"],
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
    )

    try:
        baixado_em = datetime.now(timezone.utc).isoformat()

        with urllib.request.urlopen(req, timeout=60) as resp:
            conteudo = resp.read()

        dados = json.loads(conteudo.decode("utf-8"))
        features = dados.get("features", [])

        with open(destino, "w", encoding="utf-8") as f:
            json.dump(dados, f, ensure_ascii=False)

        # Registra quando o download de fato aconteceu, separado do momento em
        # que a carga roda (load_camadas.py pode rodar bem depois disso).
        meta_path = destino + ".meta.json"
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump({"baixado_em": baixado_em, "fonte": info["url"]}, f)

        tamanho_kb = len(conteudo) / 1024
        print(f"  OK: {destino} ({len(features)} feicoes, {tamanho_kb:.1f} KB)")
        return destino
    except Exception as e:
        print(f"  Erro ao baixar {nome}: {e}", file=sys.stderr)
        return ""


def main():
    parser = argparse.ArgumentParser(
        description="Extrai dados abertos das camadas geograficas do DF (IBRAM/SISDIA)."
    )
    parser.add_argument(
        "--output-dir",
        default=RAW_DIR,
        help="Diretorio de saida para os arquivos brutos.",
    )
    parser.add_argument(
        "--camada",
        choices=list(SISDIA_SERVICES.keys()) + ["todas"],
        default="unidades_conservacao",
        help="Camada especifica para download.",
    )

    args = parser.parse_args()

    if args.camada == "todas":
        for k, v in SISDIA_SERVICES.items():
            baixar_camada_geojson(k, v, args.output_dir)
    else:
        baixar_camada_geojson(args.camada, SISDIA_SERVICES[args.camada], args.output_dir)


if __name__ == "__main__":
    main()
