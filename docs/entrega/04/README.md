---
icon: material/numeric-4-box
---

# :material-numeric-4-box: Entrega 4: Arquitetura, Metodologia e Painel Operacional (25/11)

> Consolidação da arquitetura em camadas (Bronze, Silver e Gold), documentação metodológica e revisão de usabilidade do dashboard para apoio à vistoria em campo.

## Divisão de Responsabilidades (25/11)

| Frente | Responsáveis | Escopo |
| :--- | :--- | :--- |
| **Arquitetura (Bronze, Silver e Gold)** | Gabriel Souza, Manoel Felipe | Diagrama interativo de linhagem e camadas legível sem necessidade de zoom manual |
| **Metodologia** | Elias F., Gabriel Fernando | Consolidação dos critérios espaciais, sensores, amostragem temporal e cálculo de prioridade |
| **Dashboard Operacional** | João V. Farias, Samuel Ribeiro | Simplificação visual, fluxo mapa + fila de vistoria selecionável, comparadores e linguagem direta |

---

## 1. Arquitetura em Camadas (Bronze, Silver e Gold)

<p class="apresentador"><em>Apresentação: Gabriel Souza e Manoel Felipe</em></p>

Clique ou passe o cursor sobre qualquer tabela para inspecionar sua granularidade, volume de linhas, fontes de entrada e destinos na camada de consumo.

--8<-- "docs/snippets/arquitetura_camadas.md"

---

## 2. Metodologia

<p class="apresentador"><em>Apresentação: Elias F. e Gabriel Fernando</em></p>

A especificação completa das fontes, padronização cartográfica (`EPSG:31983`), regras de reincidência e validação contra o PostGIS está organizada em [Metodologia](../../metodologia.md).

---

## 3. Dashboard Interativo

<p class="apresentador"><em>Apresentação: João V. Farias e Samuel Ribeiro</em></p>

O [Dashboard](../../dashboard.md) foi reorganizado para priorizar a decisão de vistoria logo na abertura:

- Palco espacial (`Mapa Analítico` e `Mapa Satélite / Ruas`) acoplado à **Fila de Vistoria (50)** selecionável por checkbox, com os **5 primeiros marcados por padrão**.
- Barra de filtros compacta abaixo do mapa, com controles avançados e seletor de camadas recolhidos sob demanda.
- Indicadores de recorte com comparadores diretos frente à média histórica do Distrito Federal e remoção de termos internos de banco de dados da interface.
