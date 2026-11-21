---
icon: material/numeric-4-box
---

<!-- slides: level=3 -->

# :material-numeric-4-box: Entrega 4: Visualização e Metodologia

> Arquitetura em camadas, definição única de métricas no dbt e painel revisado para priorizar vistorias no DF.

## O que muda na prática

| Olhar | Antes | Agora |
| :--- | :--- | :--- |
| **Fiscalização** | Contagem bruta punha no topo fazendas de `25.808 ha` (só 1 ativa). | [IPV](../../adr/05-indice-de-prioridade-de-vistoria.md) ordena 1.593 reincidentes (402 críticos); o Top 10 cai para `114,2 ha` (9 ativos), com os 5 primeiros pré-marcados. |
| **Dados** | Join espacial direto no PostGIS levava `41,8 s`, com regras espalhadas. | Delta Lake + estrela SCD2 ([ADR 0002](../../adr/02-mecanismo-de-ingestao-e-formato-aberto.md), [ADR 0003](../../adr/03-modelagem-dimensional-e-ferramenta-de-transformacao.md)), regra única em `dbt_project.yml` e retrato `gold.json` (`187,0 KB`, `2,29 ms`, [ADR 0004](../../adr/04-disponibilizacao-contrato-dbt-e-retrato-estatico.md)). |

---

## Divisão de Responsabilidades

| Frente | Responsáveis | Na apresentação |
| :--- | :--- | :--- |
| Arquitetura | Gabriel Souza, Manoel Felipe | Fluxo interativo Bronze, Silver e Gold até o consumo |
| Metodologia | Elias F., Gabriel Fernando | Base `EPSG:31983`, sensores, reincidência e validação |
| Dashboard | Samuel Ribeiro | Mapa no topo, fila com seleção e comparadores do DF |
| ADRs (0001 a 0005) | João V. Farias | [ADR 0004](../../adr/04-disponibilizacao-contrato-dbt-e-retrato-estatico.md), medições e revisão de gatilhos |
| Governança e SLA | Cláudio Henrique | Docker Compose, frescor de `30 h`, dados públicos e limites |

---

## 1. Arquitetura em Camadas (Bronze, Silver e Gold)

<p class="apresentador"><em>Apresentação: Gabriel Souza e Manoel Felipe</em></p>

--8<-- "docs/snippets/arquitetura_camadas.md"

---

## 2. [Metodologia](../../metodologia.md)

<p class="apresentador"><em>Apresentação: Elias F. e Gabriel Fernando</em></p>

- Padronização em `EPSG:31983` e regra única de área protegida (Reserva Legal do próprio imóvel, APP ou `1.000 m` de UC), cruzando cada foco com a versão do cadastro vigente na data (`dim_imovel_car`).
- Separação entre a contagem total (`38.945` focos em 20 satélites) e a série comparável no `AQUA_M-T`, usando dias com foco no cálculo de densidade do IPV para não enviesar sensores de `375 m`.
- O teste `reconcilia_fato_imovel_com_mv_postgis` valida os 1.593 reincidentes e os 37.693 focos entre DuckDB e PostGIS a cada execução.

---

## 3. [Dashboard Interativo](../../dashboard.md)

<p class="apresentador"><em>Apresentação: Samuel Ribeiro</em></p>

- Abre direto com pergunta, resposta e os mapas (`Analítico` e `Satélite / Ruas`), deixando a barra de filtros abaixo do palco espacial.
- A **Fila de Vistoria (50)** inclui caixas de seleção por imóvel, com os 5 primeiros marcados por padrão para filtrar mapas e séries sem poluir a tela.
- Termos internos de banco saíram da interface, substituídos por comparadores frente à média histórica do DF a partir de `gold.json`.

---

## 4. Portfólio de ADRs e Gatilhos de Revisão

<p class="apresentador"><em>Apresentação: João V. Farias</em></p>

<!--Decisão do [ADR 0004](../../adr/04-disponibilizacao-contrato-dbt-e-retrato-estatico.md): publicar `painel_imoveis_prioritarios` no retrato estático `gold.json` (`187,0 KB`, top 50 simplificado) com SLA de `30 h` e sem backend. -->

| Alternativa | Entrega | Latência medida | Limite |
| :--- | :--- | :--- | :--- |
| A. Opção nula (PostGIS `V9` / CSV) | `6,6 KB` (CSV) | `2.481,7 ms` (`V9`) / `0,17 ms` (CSV) | Sem geometrias no CSV; exige PostGIS |
| B. API / Federação DuckDB | Sob demanda | `5,0 ms` (SQL tabular) | Servidor ativo; lock na carga diária |
| C. Contrato dbt + `gold.json` | **187,0 KB** (`35,9 KB` gzip) | **2,29 ms** (parse JSON) | Polígonos no mapa só para o top 50 |

### Gatilhos de revisão dos 5 ADRs

| ADR | Decisão | Gatilho de revisão | Estado |
| :--- | :--- | :--- | :--- |
| [0001](../../adr/01-adotar-postgresql-com-postgis-camada-gold.md) | PostGIS (`EPSG:31983`) | Carga `> 1 h` ou consulta `> 5 s` | **Disparado na E1** (`41,8 s` -> DuckDB) |
| [0002](../../adr/02-mecanismo-de-ingestao-e-formato-aberto.md) | Lote + CDC em Delta (`ZSTD`) | INPE `< 1 min` ou WAL `> 2 GB` | Nos limites (`0,09 MB`/partição) |
| [0003](../../adr/03-modelagem-dimensional-e-ferramenta-de-transformacao.md) | Estrela + SCD2 (`dbt-duckdb`) | Volume `> 50 GB` ou `> 10` domínios | Nos limites (`5,0 ms` na Gold) |
| [0004](../../adr/04-disponibilizacao-contrato-dbt-e-retrato-estatico.md) | Contrato dbt + `gold.json` | `gold.json > 2 MB` ou SLA `< 6 h` | **Aceito na E4** (`187,0 KB`, `2,29 ms`) |
| [0005](../../adr/05-indice-de-prioridade-de-vistoria.md) | IPV (`0,4 / 0,3 / 0,3`, piso `14,1 ha`) | Novos pesos ou dado de cicatriz | Ativo em `dbt_project.yml` |

---

## 5. Governança, SLA de Frescor e Limites Assumidos

<p class="apresentador"><em>Apresentação: Cláudio Henrique</em></p>

| Critério | O que roda | Evidência / Limite |
| :--- | :--- | :--- |
| Reprodutibilidade e SLA | `docker compose up` e *asset check* horário `frescor_sla` no Dagster | Carga diária às `03:00` BRT; limite de `30 h` ([`frescor.py`](https://github.com/BeyondMagic/corta-fogo-df/blob/main/src/pipeline/frescor.py)) |
| Métrica única | Parâmetros em `dbt_project.yml` e contrato em `painel_imoveis_prioritarios` | Reconciliado com PostGIS; alimenta `gold.json` e `analyses/` |
| Catálogo e linhagem | Bronze, Silver, Gold e consumo documentados | [Dicionário de Dados](../../dicionario_dados.md) e diagrama da Seção 1 |
| LGPD (dados públicos) | Carga descarta CPF, nome e contato do SICAR; guarda `cod_imovel` e geometria | Risco residual de reidentificação indireta via portal público do SICAR |
| Limites assumidos | Fila entregue via `gold.json` no painel ([Diário de Bordo](../../diario_de_bordo.md)) | Sem gravação reversa no PostgreSQL nem `ROLE` / RLS no warehouse |
