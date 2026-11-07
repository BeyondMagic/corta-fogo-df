# Transformações dbt-duckdb

Pipeline declarativo em `dbt-core` com adapter `dbt-duckdb`. Consome as tabelas abertas Delta Lake (`foco_calor` e `imovel_car`) do volume `lakehouse` via `delta_scan` e anexa em modo somente leitura as camadas territoriais curadas no PostGIS (`unidade_conservacao`, `area_preservacao_permanente`, `reserva_legal`) via extensão `postgres` do DuckDB. O banco analítico resultante é persistido em `/app/data/warehouse/corta_fogo.duckdb` (volume nomeado `warehouse`).

## Como executar

Com o PostgreSQL e os serviços da Entrega 2 populados (`db`, `batch_ingest` e `cdc_consumer`):

```bash
docker compose --profile transformacao run --rm dbt debug
docker compose --profile transformacao run --rm dbt parse
docker compose --profile transformacao run --rm dbt run
```

Para execução fora do contêiner, instale `transformacao/requirements.txt` e ajuste as variáveis de ambiente aceitas pelo [`profiles.yml`](profiles.yml) e pelo [`_sources.yml`](models/staging/_sources.yml): `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DELTA_DIR` e `DUCKDB_PATH`.

## Camadas e granularidades

Descrições de colunas e contratos de cada modelo estão em [`models/staging/_staging.yml`](models/staging/_staging.yml) e [`models/intermediate/_intermediate.yml`](models/intermediate/_intermediate.yml).

| Camada | Modelo | Materialização | Granularidade |
| :--- | :--- | :--- | :--- |
| `staging` | `stg_focos_calor` | `view` | Uma linha por detecção de foco de calor no tempo e no espaço por sensor orbital (`id_foco`). |
| `staging` | `stg_imoveis_car` | `view` | Uma linha por imóvel rural cadastrado no SICAR/DF (`cod_imovel`), incluindo exclusões lógicas (`is_excluido`). |
| `staging` | `stg_unidades_conservacao` | `view` | Uma linha por polígono de Unidade de Conservação (`id_uc`). |
| `staging` | `stg_areas_preservacao_permanente` | `view` | Uma linha por polígono de Área de Preservação Permanente (`id_app`). |
| `staging` | `stg_reservas_legais` | `view` | Uma linha por feição de Reserva Legal (`id_reserva`). |
| `intermediate` | `int_focos_imoveis` | `table` | Uma linha por par (`id_foco`, `cod_imovel`) de imóvel ativo cujo polígono intersecta o foco. |
| `intermediate` | `int_focos_areas_protegidas` | `table` | Uma linha por par (`id_foco`, `tipo_area`, `id_feicao`) em Reserva Legal, APP ou faixa de 1 km de UC. |
| `intermediate` | `int_focos_territorio` | `table` | Uma linha por detecção de foco (`id_foco`), consolidando flags territoriais e contagem de imóveis atingidos. |

A consulta [`analyses/conferencia_mv_gold.sql`](analyses/conferencia_mv_gold.sql) reproduz a regra da `gold.mv_imoveis_reincidentes_areas_protegidas` (migração `V7`) sobre os modelos `int_focos_imoveis` e `int_focos_areas_protegidas` para conferência de contagem.

## Limitações

- Chaves `IDENTITY` das feições territoriais (`id_uc`, `id_app`, `id_reserva`) mudam a cada recarga completa do banco (`down -v`): ver descrição de `id_feicao` em [`models/intermediate/_intermediate.yml`](models/intermediate/_intermediate.yml).
- O cruzamento foco por imóvel utiliza o perímetro atual da tabela Delta `imovel_car` (a vinculação com a versão histórica depende do snapshot SCD Tipo 2): ver descrição de `int_focos_imoveis` em [`models/intermediate/_intermediate.yml`](models/intermediate/_intermediate.yml) e de `geom` em [`models/staging/_staging.yml`](models/staging/_staging.yml).
