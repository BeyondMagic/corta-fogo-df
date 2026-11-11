#!/usr/bin/env python3
"""
Gera os snippets modulares em docs/snippets/mapa/ para inclusao
via pymdownx.snippets na pagina docs/mapa.md.

Gera 5 arquivos:
- metricas_gerais.md: cartoes e resumo das metricas consolidadas
- grafico_serie_anual.md: grafico xychart da serie anual 2015-2025 (Total vs Seca)
- grafico_sazonalidade_mensal.md: grafico xychart da distribuicao mensal (Jan-Dez)
- grafico_reincidencia_territorial.md: grafico xychart de sobreposicao protegida
- grafico_anos_reincidencia.md: histograma de anos com queima recorrente
"""

import csv
import os
from collections import defaultdict


def processar_focos_csv(csv_path):
    anos = list(range(2015, 2026))
    focos_por_ano = {ano: {"total": 0, "seca": 0, "ref": 0} for ano in anos}
    focos_por_mes = {mes: 0 for mes in range(1, 13)}

    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            ano = int(row["data_hora_evento"][:4])
            mes = int(row["data_hora_evento"][5:7])
            is_ref = (row["is_satelite_referencia"] == "True")
            is_seca = (5 <= mes <= 9)

            if ano in focos_por_ano:
                focos_por_ano[ano]["total"] += 1
                if is_seca:
                    focos_por_ano[ano]["seca"] += 1
                if is_ref:
                    focos_por_ano[ano]["ref"] += 1

            if 1 <= mes <= 12:
                focos_por_mes[mes] += 1

    return focos_por_ano, focos_por_mes


def gerar_metricas_gerais(output_dir, total_focos, total_seca, total_ref):
    pct_seca = (total_seca / total_focos * 100) if total_focos else 0
    pct_ref = (total_ref / total_focos * 100) if total_focos else 0

    fmt_total = f"{total_focos:,}".replace(",", ".")
    fmt_seca = f"{total_seca:,}".replace(",", ".")
    fmt_ref = f"{total_ref:,}".replace(",", ".")
    fmt_pct_seca = f"{pct_seca:.1f}".replace(".", ",")
    fmt_pct_ref = f"{pct_ref:.1f}".replace(".", ",")

    content = f"""<div class="cf-stats-grid">
  <div class="cf-stat-card">
    <span class="cf-stat-label">Série Histórica (11 anos)</span>
    <span class="cf-stat-val">{fmt_total} focos</span>
  </div>
  <div class="cf-stat-card">
    <span class="cf-stat-label">Concentração na Estiagem</span>
    <span class="cf-stat-val">{fmt_pct_seca}% ({fmt_seca})</span>
  </div>
  <div class="cf-stat-card">
    <span class="cf-stat-label">Satélite de Referência</span>
    <span class="cf-stat-val">{fmt_pct_ref}% ({fmt_ref})</span>
  </div>
  <div class="cf-stat-card">
    <span class="cf-stat-label">Imóveis CAR Reincidentes</span>
    <span class="cf-stat-val">1.593 cadastros</span>
  </div>
</div>

| Dimensão Analítica | Valor Consolidado | Proporção / Detalhe |
| :--- | ---: | :--- |
| **Total de focos no DF (2015 a 2025)** | {fmt_total} | 100% das detecções orbitais no território |
| **Focos na estação seca (maio a setembro)** | {fmt_seca} | {fmt_pct_seca}% de concentração no período crítico |
| **Focos do satélite de referência (AQUA_M-T)** | {fmt_ref} | {fmt_pct_ref}% para séries comparáveis sem viés |
| **Imóveis com foco em área protegida em algum ano** | 4.068 | 19,3% dos 21.047 imóveis rurais do CAR-DF |
| **Imóveis rurais reincidentes (2 anos ou mais)** | 1.593 | 7,6% do total cadastral do DF |
| **Focos vinculados a imóveis reincidentes** | 37.693 | 96,8% de todos os focos do período histórico |
"""

    filepath = os.path.join(output_dir, "metricas_gerais.md")
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)


def gerar_grafico_serie_anual(output_dir, focos_por_ano):
    anos = sorted(focos_por_ano.keys())
    x_labels = ", ".join(f'"{ano}"' for ano in anos)
    totais = ", ".join(str(focos_por_ano[ano]["total"]) for ano in anos)
    secas = ", ".join(str(focos_por_ano[ano]["seca"]) for ano in anos)

    content = f"""```mermaid
xychart-beta
    title "Focos de Calor por Ano no Distrito Federal: Total vs Seca (2015 a 2025)"
    x-axis [{x_labels}]
    y-axis "Ocorrências de Calor" 0 --> 7000
    bar [{totais}]
    line [{secas}]
```

*Barras indicam o volume total de focos por ano (todos os sensores); a linha contínua indica os focos restritos aos meses de seca (maio a setembro). Em 2024, a estiagem prolongada provocou o ápice de 6.190 detecções no DF.*
"""

    filepath = os.path.join(output_dir, "grafico_serie_anual.md")
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)


def gerar_grafico_sazonalidade_mensal(output_dir, focos_por_mes):
    meses_nomes = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"]
    x_labels = ", ".join(f'"{m}"' for m in meses_nomes)
    valores = ", ".join(str(focos_por_mes[m]) for m in range(1, 13))

    content = f"""```mermaid
xychart-beta
    title "Sazonalidade Mensal Acumulada no DF (Soma de 2015 a 2025)"
    x-axis [{x_labels}]
    y-axis "Total de Focos Acumulados" 0 --> 18000
    bar [{valores}]
```

*Distribuição mensal consolidada. O mês de setembro sozinho concentra 17.348 ocorrências (44,5% do acumulado de 11 anos), evidenciando o momento mais severo de estiagem e risco de incêndios florestais no Cerrado.*
"""

    filepath = os.path.join(output_dir, "grafico_sazonalidade_mensal.md")
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)


def gerar_grafico_reincidencia_territorial(output_dir):
    content = """```mermaid
xychart-beta
    title "Imóveis Rurais Reincidentes por Categoria Territorial Protegida"
    x-axis ["Faixa de 1 km de UC", "Reserva Legal", "Área de Preservação Permanente (APP)"]
    y-axis "Quantidade de Imóveis" 0 --> 1400
    bar [1231, 958, 382]
```

*Total de imóveis reincidentes com detecções em cada categoria protegida. As categorias se sobrepõem: um mesmo imóvel pode ter focos em Reserva Legal e simultaneamente estar situado a menos de 1 km do limite de uma Unidade de Conservação.*
"""

    filepath = os.path.join(output_dir, "grafico_reincidencia_territorial.md")
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)


def gerar_grafico_anos_reincidencia(output_dir):
    content = """```mermaid
xychart-beta
    title "Distribuição dos 1.593 Imóveis por Quantidade de Anos com Queimada"
    x-axis ["2 anos", "3 anos", "4 anos", "5 anos", "6 anos", "7 anos", "8 anos", "9 anos", "10 anos", "11 anos"]
    y-axis "Imóveis Rurais" 0 --> 800
    bar [717, 331, 159, 120, 74, 47, 50, 31, 23, 41]
```

*Histograma de recorrência temporal. Embora a maioria dos reincidentes apresente focos em 2 a 3 anos distintos (1.048 imóveis), 41 propriedades no DF tiveram ocorrências de calor registradas em todos os 11 anos completos analisados (2015 a 2025).*
"""

    filepath = os.path.join(output_dir, "grafico_anos_reincidencia.md")
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)


def main():
    csv_path = "data/processed/focos_df_2015_2025.csv"
    output_dir = "docs/snippets/mapa"
    os.makedirs(output_dir, exist_ok=True)

    focos_por_ano, focos_por_mes = processar_focos_csv(csv_path)

    total_focos = sum(dados["total"] for dados in focos_por_ano.values())
    total_seca = sum(dados["seca"] for dados in focos_por_ano.values())
    total_ref = sum(dados["ref"] for dados in focos_por_ano.values())

    gerar_metricas_gerais(output_dir, total_focos, total_seca, total_ref)
    gerar_grafico_serie_anual(output_dir, focos_por_ano)
    gerar_grafico_sazonalidade_mensal(output_dir, focos_por_mes)
    gerar_grafico_reincidencia_territorial(output_dir)
    gerar_grafico_anos_reincidencia(output_dir)

    print(f"[OK] 5 snippets gerados com sucesso em {output_dir}/")


if __name__ == "__main__":
    main()
