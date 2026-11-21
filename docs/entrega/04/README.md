---
icon: material/numeric-4-box
---

# :material-numeric-4-box: Entrega 4: Arquitetura, Metodologia e Painel Operacional (25/11)

> Consolidação da arquitetura em camadas (Bronze, Silver e Gold), definição única de métricas com contrato dbt, revisão do painel para decisão de vistoria e fechamento do portfólio de ADRs.

## O que a plataforma resolve na prática

Para alinhar a defesa final (8 a 12 minutos) entre decisão de fiscalização e engenharia de dados:

| Perspectiva | Antes (listas sem ordenação / consulta bruta) | Agora (Entrega 4 consolidada) |
| :--- | :--- | :--- |
| **Gestão e Fiscalização** | A contagem simples de focos colocava no Top 10 perímetros com mediana de `25.808 ha` (7 acima de `10.000 ha` e apenas 1 ativo), misturando áreas gigantes com ocorrência real. | A fila priorizada pelo [IPV](../../adr/05-indice-de-prioridade-de-vistoria.md) entrega 1.593 imóveis reincidentes (402 em prioridade crítica); o Top 10 tem mediana de `114,2 ha` e 9 cadastros ativos, com os 5 primeiros selecionados por padrão no painel e comparadores frente à média do DF. |
| **Engenharia e Dados** | Junção espacial direta no PostGIS levava `41,8 s` e cada consulta repetia critérios em scripts separados. | O pipeline separa CDC/Lote em Delta Lake (`ADR 0002`), modela em estrela com SCD Tipo 2 (`ADR 0003`), centraliza regras em `dbt_project.yml` e expõe `painel_imoveis_prioritarios` com contrato estrito e retrato estático `gold.json` (`187,0 KB`, parse em `2,29 ms`, SLA `30 h`) no [`ADR 0004`](../../adr/04-disponibilizacao-contrato-dbt-e-retrato-estatico.md). |

---

## Divisão de Responsabilidades (25/11)

| Frente | Responsáveis | Escopo na apresentação |
| :--- | :--- | :--- |
| **Arquitetura (Bronze, Silver e Gold)** | Gabriel Souza, Manoel Felipe | Linhagem interativa ponta a ponta da fonte ao consumo e papel de cada camada |
| **Metodologia** | Elias F., Gabriel Fernando | Fontes, padronização `EPSG:31983`, definição única de reincidência, testes e validação contra o PostGIS |
| **Dashboard Operacional e ADR 0004** | João V. Farias, Samuel Ribeiro | Novo fluxo do painel (mapa + fila selecionável + comparadores), fechamento do [ADR 0004](../../adr/04-disponibilizacao-contrato-dbt-e-retrato-estatico.md) e portfólio de ADRs |

---

## 1. Arquitetura em Camadas (Bronze, Silver e Gold)

<p class="apresentador"><em>Apresentação: Gabriel Souza e Manoel Felipe</em></p>

O diagrama abaixo substitui o fluxograma anterior por uma visão em colunas com linhagem interativa. Passe o cursor ou clique em qualquer tabela para inspecionar sua origem (*upstream*), destino (*downstream*), tipo de materialização e volume de linhas da fonte ao consumo:

--8<-- "docs/snippets/arquitetura_camadas.md"

---

## 2. Metodologia

<p class="apresentador"><em>Apresentação: Elias F. e Gabriel Fernando</em></p>

A documentação metodológica detalha como cada número do painel é construído sem ambiguidade:

- **Base territorial única:** conversão obrigatória para `EPSG:31983`, definição de área protegida (Reserva Legal do próprio imóvel, APP ou faixa de `1.000 m` de UC) e preservação do perímetro vigente na data do foco por SCD Tipo 2 (`dim_imovel_car`).
- **Série histórica e viés de sensores:** distinção entre volume total de focos (`38.945`, 20 satélites) e tendência temporal no satélite de referência (`AQUA_M-T`), além de contagem por dias com foco na densidade do IPV para neutralizar satélites recentes de `375 m`.
- **Reconciliação dupla:** o teste `reconcilia_fato_imovel_com_mv_postgis` confere os 1.593 imóveis reincidentes e os 37.693 focos entre a camada Gold no DuckDB e a visão materializada no PostGIS.

Texto completo em [Metodologia](../../metodologia.md).

---

## 3. Dashboard Interativo

<p class="apresentador"><em>Apresentação: João V. Farias e Samuel Ribeiro</em></p>

O [Dashboard](../../dashboard.md) foi redesenhado para reduzir densidade visual e acelerar a triagem de vistorias:

- **Pergunta e mapa no topo:** abertura direta com a pergunta de gestão, resposta consolidada e alternância entre `Mapa Analítico` e `Mapa Satélite / Ruas` logo abaixo, com filtros compactos reposicionados sob o mapa.
- **Fila de Vistoria (50) acoplada ao mapa:** seleção por checkbox por imóvel com os **5 primeiros marcados por padrão**, recalculando mapas, contadores e séries para os imóveis selecionados em vez de sobrecarregar a leitura com tudo ao mesmo tempo.
- **Comparadores e linguagem de negócio:** remoção de jargões de armazenamento e inclusão de indicadores relativos frente ao histórico do DF (`gold.json` exportado via `scripts/exportar_painel_gold.py`).

---

## 4. Portfólio de ADRs e Gatilhos de Revisão

Consolidação das cinco decisões estruturais do projeto ao longo das entregas E1 a E4:

| ADR | Decisão | Gatilho de revisão definido | Situação na E4 |
| :--- | :--- | :--- | :--- |
| [**0001**](../../adr/01-adotar-postgresql-com-postgis-camada-gold.md) | PostgreSQL 16 com PostGIS em `EPSG:31983` como banco principal | Carga `> 1 h` ou consulta analítica `> 5 s` | **Gatilho disparado na E1** (`41,8 s` no join espacial bruto e `4,6 s` na MV `V7`): motivou o descarregamento analítico para Lakehouse + DuckDB na E2/E3. |
| [**0002**](../../adr/02-mecanismo-de-ingestao-e-formato-aberto.md) | Ingestão híbrida (Lote para focos + CDC WAL para CAR) em Delta Lake (`ZSTD`) | INPE subminuto, catálogo multi-motor ou WAL próximo de `2 GB` | Ativo dentro dos limites; partições `ano/mes` com `ZSTD` a `0,09 MB` na partição de referência. |
| [**0003**](../../adr/03-modelagem-dimensional-e-ferramenta-de-transformacao.md) | Esquema estrela (`fato_foco_calor` + SCD2) em `dbt-duckdb` com Dagster | Volume `> 50 GB`, mais de 10 domínios ou stream `< 10 s` | Ativo (`1,8 MB` na fato atômica em Parquet, `5,0 ms` na consulta SQL Gold). |
| [**0004**](../../adr/04-disponibilizacao-contrato-dbt-e-retrato-estatico.md) | Contrato dbt (`painel_imoveis_prioritarios`) + retrato JSON estático (`gold.json`) | `gold.json > 2 MB`, SLA `< 6 h` ou consumidor transacional externo | **Aceito na E4** (`187,0 KB`, parse em `2,29 ms`, SLA monitorado de `30 h`). |
| [**0005**](../../adr/05-indice-de-prioridade-de-vistoria.md) | Índice de Prioridade de Vistoria (`0,4 / 0,3 / 0,3`, piso `14,1 ha`) | Mudança de pesos pela fiscalização ou entrada de dado de cicatriz de fogo | Ativo e versionado em `transformacao/dbt_project.yml`. |

---

## 5. Governança, Escopo de Dados (LGPD) e Limites Assumidos

Alinhamento objetivo aos critérios de governança da E4 com base estrita no que existe no repositório:

- **Métrica única e consumo duplo:** todas as regras do índice e cortes temporais residem em `transformacao/dbt_project.yml` e no contrato enforçado de `painel_imoveis_prioritarios` (`_marts.yml`), alimentando tanto o painel web (`gold.json`) quanto as análises SQL (`consulta_pergunta_gestao.sql` e `resumo_pergunta_gestao.sql`), sem divergência frente ao PostGIS.
- **Catálogo e linhagem:** documentação completa das camadas Bronze, Silver, Gold e consumo no [Dicionário de Dados](../../dicionario_dados.md) e no diagrama interativo da Seção 1.
- **LGPD e dados públicos:** o esquema operacional (`migrations/V2__cadastros_base.sql`) e os scripts de carga (`src/pipeline/load_camadas.py`) descartam CPF, nome e dados de contato do proprietário presentes em formulários originais do SICAR, persistindo apenas o identificador público do imóvel (`cod_imovel` no padrão `DF-...`), `situacao`, `condicao`, `area_ha` e geometrias, cruzados com detecções orbitais sem pessoas do INPE. Mantém-se como cautela documental o risco de reidentificação indireta caso terceiros cruzem o `cod_imovel` ou o perímetro com consultas públicas externas no SICAR.
- **Retorno operacional e controle de acesso (limites em aberto):** hoje a métrica tratada retorna à operação via `gold.json` consumido no [Dashboard](../../dashboard.md) para seleção de vistorias de campo. O projeto **não** grava uma tabela de fila de volta no PostgreSQL operacional (ETL reverso em banco) nem cria perfis `ROLE` ou *Row-Level Security* no warehouse; ambos estão registrados como limites assumidos e gatilhos de evolução no [ADR 0004](../../adr/04-disponibilizacao-contrato-dbt-e-retrato-estatico.md).
- **Retrospectiva do ciclo:** consolidada em [Diário de Bordo](../../diario_de_bordo.md).
