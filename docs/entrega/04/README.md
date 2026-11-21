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
| **Dashboard Operacional** | Samuel Ribeiro | Novo fluxo do painel (mapa + fila selecionável + comparadores) para priorização em campo |
| **ADRs (0001 a 0005)** | João V. Farias | Fechamento do [ADR 0004](../../adr/04-disponibilizacao-contrato-dbt-e-retrato-estatico.md), medições de consumo e revisão dos gatilhos do ciclo |
| **Governança, SLA e Reprodutibilidade** | Cláudio Henrique | Execução via Docker Compose, monitoramento de frescor no Dagster (`<= 30 h`), catálogo, dados públicos e limites assumidos |

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

<p class="apresentador"><em>Apresentação: Samuel Ribeiro</em></p>

O [Dashboard](../../dashboard.md) foi redesenhado para reduzir densidade visual e acelerar a triagem de vistorias:

- **Pergunta e mapa no topo:** abertura direta com a pergunta de gestão, resposta consolidada e alternância entre `Mapa Analítico` e `Mapa Satélite / Ruas` logo abaixo, com filtros compactos reposicionados sob o mapa.
- **Fila de Vistoria (50) acoplada ao mapa:** seleção por checkbox por imóvel com os **5 primeiros marcados por padrão**, recalculando mapas, contadores e séries para os imóveis selecionados em vez de sobrecarregar a leitura com tudo ao mesmo tempo.
- **Comparadores e linguagem de negócio:** remoção de jargões de armazenamento e inclusão de indicadores relativos frente ao histórico do DF (`gold.json` exportado via `scripts/exportar_painel_gold.py`).

---

## 4. Portfólio de ADRs e Gatilhos de Revisão

<p class="apresentador"><em>Apresentação: João V. Farias</em></p>

**ADR 0004 (Disponibilização):** publicar `painel_imoveis_prioritarios` via retrato estático `gold.json` (`187,0 KB`, top 50 simplificado) sob SLA de `30 h`, sem backend em produção.

| Alternativa | Entrega | Latência medida | Limite |
| :--- | :--- | :--- | :--- |
| **A. Opção nula** (PostGIS `V9` / CSV) | `6,6 KB` (CSV) | `2.481,7 ms` (`V9`) / `0,17 ms` (CSV) | Sem geometrias no CSV; exige PostGIS |
| **B. API / Federação DuckDB** | Sob demanda | `5,0 ms` (tabular SQL) | Servidor ativo; lock na carga diária |
| **C. Contrato dbt + `gold.json`** | **187,0 KB** (`35,9 KB` gzip) | **2,29 ms** (parse JSON) | Fila no mapa limitada ao top 50 |

### Gatilhos de revisão dos 5 ADRs

| ADR | Decisão | Gatilho de revisão | Estado |
| :--- | :--- | :--- | :--- |
| [**0001**](../../adr/01-adotar-postgresql-com-postgis-camada-gold.md) | PostGIS (`EPSG:31983`) | Carga `> 1 h` ou consulta `> 5 s` | **Disparado na E1** (`41,8 s` -> DuckDB) |
| [**0002**](../../adr/02-mecanismo-de-ingestao-e-formato-aberto.md) | Lote + CDC em Delta (`ZSTD`) | INPE `< 1 min` ou WAL `> 2 GB` | Nos limites (`0,09 MB`/partição) |
| [**0003**](../../adr/03-modelagem-dimensional-e-ferramenta-de-transformacao.md) | Estrela + SCD2 (`dbt-duckdb`) | Volume `> 50 GB` ou `> 10` domínios | Nos limites (`5,0 ms` na Gold) |
| [**0004**](../../adr/04-disponibilizacao-contrato-dbt-e-retrato-estatico.md) | Contrato dbt + `gold.json` | `gold.json > 2 MB` ou SLA `< 6 h` | **Aceito na E4** (`187,0 KB`, `2,29 ms`) |
| [**0005**](../../adr/05-indice-de-prioridade-de-vistoria.md) | IPV (`0,4 / 0,3 / 0,3`, piso `14,1 ha`) | Novos pesos ou dado de cicatriz | Ativo em `dbt_project.yml` |

---

## 5. Governança, SLA de Frescor e Limites Assumidos

<p class="apresentador"><em>Apresentação: Cláudio Henrique</em></p>

| Critério | Implementação | Evidência / Limite |
| :--- | :--- | :--- |
| **Reprodutibilidade e SLA** | Ambiente sobe via `docker compose up` com *asset check* horário `frescor_sla` no Dagster | Ciclo diário `03:00` BRT; limite de `30 h` ([`frescor.py`](https://github.com/BeyondMagic/corta-fogo-df/blob/main/src/pipeline/frescor.py)) |
| **Métrica única** | Regras em `dbt_project.yml` + contrato `painel_imoveis_prioritarios` | Reconciliado com MV PostGIS; alimenta `gold.json` e `analyses/` |
| **Catálogo e linhagem** | Bronze, Silver, Gold e consumo documentados ponta a ponta | [Dicionário de Dados](../../dicionario_dados.md) e diagrama da Seção 1 |
| **LGPD (dados públicos)** | Carga descarta CPF, nome e contato do SICAR; persiste só `cod_imovel` e geometria | Cautela de reidentificação indireta via portal público do SICAR |
| **Limites assumidos** | Retorno à operação via `gold.json` no painel ([Diário de Bordo](../../diario_de_bordo.md)) | Sem gravação reversa no PostgreSQL nem `ROLE` / RLS no warehouse |
