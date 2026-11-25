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

## 2. [Metodologia](../../metodologia.md) e [Decisões de Negócio](../../decisoes_descartes.md)

<p class="apresentador"><em>Apresentação: Elias F. e Gabriel Fernando</em></p>

- **Base métrica e histórico sem reescrever o passado:** padronização em `EPSG:31983` (`ST_IsValid`), cruzando cada foco com a versão cadastral vigente na data do evento (`dim_imovel_car` em SCD Tipo 2) sobre Reserva Legal do próprio imóvel, APP ou `1.000 m` de UC.
- **Sensores e separação de grãos (sobreposição SICAR):** tendência interanual usa o sensor `AQUA_M-T` (`1 km²`), enquanto a cobertura fundiária usa 20 satélites; `fato_foco_calor` preserva `38.944` focos únicos do DF e `fct_reincidencia_imovel` absorve a relação N:N de matrículas sobrepostas sem inflar o total distrital.
- **Priorização acionável (IPV) e recorte gestão vs. campo:** `dias_com_foco` por `100 ha` (piso `14,1 ha` = 1 pixel VIIRS) reduz a área mediana do Top 10 de `25.808 ha` para `114,2 ha` (9 ativos); a camada Gold mantém `1.593` reincidentes (incluindo `CA`/`SU`/`PE` para auditoria de passivo) e a RLS em `operacional.fila_vistoria` entrega `1.413` ativos ao fiscal de campo.
- **Camada semântica única e validação cruzada:** parâmetros centralizados em `dbt_project.yml` e contrato `enforced` alimentam `gold.json`, consultas SQL e ETL reverso sem divergência, com `0` diferenças frente ao PostGIS (`V9`) e `259` testes aprovados.

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
| B. API / Federação DuckDB | Sob demanda | `5,0 ms` (SQL tabular) | Servidor ativo; lock na transformação diária |
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
| Reprodutibilidade e SLA | `docker compose up` e *asset check* horário `frescor_sla` no Dagster | Transformação diária (dbt e ETL reverso) às `03:00` BRT; limite de `30 h` ([`frescor.py`](https://github.com/BeyondMagic/corta-fogo-df/blob/main/src/pipeline/frescor.py)) |
| Métrica única | Parâmetros em `dbt_project.yml` e contrato em `painel_imoveis_prioritarios` | Reconciliado com PostGIS; alimenta `gold.json` e `analyses/` |
| Catálogo e linhagem | Bronze, Silver, Gold e consumo documentados | [Dicionário de Dados](../../dicionario_dados.md) e diagrama da Seção 1 |
| LGPD: dado pessoal | O arquivo público do SICAR não traz CPF, nome nem contato do titular; o banco guarda só `cod_imovel`, situação, condição, área e geometria | Risco residual: o `cod_imovel` permite chegar ao titular consultando o portal público do SICAR |
| LGPD: base legal, retenção e descarte | Base legal: dado de acesso público tratado conforme a finalidade, a boa-fé e o interesse público (LGPD, art. 7º, §§ 3º e 4º). Retenção: enquanto o projeto existir. Descarte: `docker compose down -v` apaga os volumes | Base legal a validar com o grupo. Os arquivos do SICAR continuam no histórico do Git |
| ETL reverso | Asset `operacional/fila_vistoria` no `job_transformacao`: a fila (1.593 imóveis) volta ao PostgreSQL, idempotente | `operacional.fila_vistoria`, lida e atualizada por quem vistoria; preserva `status_vistoria` ([ETL reverso e acesso](../../etl_reverso_e_acesso.md)) |
| Controle de acesso | Papéis `etl_reverso`, `fiscal_vistoria` e `analista_leitura`; RLS na fila e privilégio por coluna | `fiscal_vistoria` vê 1.413 de 1.593 (cadastro ativo); `analista_leitura` não lê `geom` (migração `V10`) |
| Limites assumidos | Fila entregue via `gold.json` no painel ([Diário de Bordo](../../diario_de_bordo.md)) | Papéis sem login nem segredos; sem controle de acesso por papel no warehouse DuckDB |

### 5.1. ETL reverso e controle de acesso

A fila de vistoria calculada no analítico volta ao PostgreSQL operacional (`operacional.fila_vistoria`), e cada papel só tem o privilégio de que precisa. O ETL empurra por *upsert* em uma transação: rodar duas vezes deixa a tabela igual, e o `status_vistoria` que o fiscal registrou nunca é sobrescrito. Imóvel que sai da fila fica com `na_fila = FALSE`, sem apagar o histórico.

| Papel | Pode | Não pode |
| :--- | :--- | :--- |
| `etl_reverso` | Inserir a fila e atualizar as métricas | Alterar `status_vistoria` e `observacao` |
| `fiscal_vistoria` | Ler a fila ativa (RLS: `na_fila AND cadastro_ativo`) e alterar `status_vistoria` e `observacao` | Ver imóvel com cadastro não ativo, alterar métricas, apagar, ler `public.imovel_car` |
| `analista_leitura` | Ler `cod_imovel`, `situacao`, `condicao`, `area_ha` e `data_download` de `imovel_car` | Ler a geometria `geom`, usar `SELECT *`, entrar no schema `operacional` |

```bash
docker compose --profile transformacao run --rm etl_reverso
docker compose --profile transformacao --profile demonstracao run --rm demo_acesso
```

A demonstração exerce cada papel no banco real e reprova (exit 1) se algum privilégio falhar. Na última execução: 1.593 imóveis na fila, segunda carga insere 0; o fiscal vê 1.413 de 1.593 e é negado em `indice_prioridade`, `DELETE` e `imovel_car`; o analista é negado em `geom`, `SELECT *` e no schema `operacional`. Detalhes e limites em [ETL reverso e controle de acesso](../../etl_reverso_e_acesso.md).
