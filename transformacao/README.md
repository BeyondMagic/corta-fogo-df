# Transformações dbt-duckdb

Pipeline declarativo em `dbt-core` com adapter `dbt-duckdb`. Consome as tabelas abertas Delta Lake (`foco_calor` e `imovel_car`) do volume `lakehouse` via `delta_scan` e anexa em modo somente leitura as camadas territoriais curadas no PostGIS (`unidade_conservacao`, `area_preservacao_permanente`, `reserva_legal`) via extensão `postgres` do DuckDB. O banco analítico resultante é persistido em `/app/data/warehouse/corta_fogo.duckdb` (volume nomeado `warehouse`).

## Como executar

Com o PostgreSQL e os serviços da Entrega 2 populados (`db`, `batch_ingest` e `cdc_consumer`):

```bash
docker compose --profile transformacao run --rm dbt debug
docker compose --profile transformacao run --rm dbt parse
docker compose --profile transformacao run --rm dbt run
docker compose --profile transformacao run --rm dbt snapshot
docker compose --profile transformacao run --rm dbt build
```

`dbt run` não executa snapshots: use `dbt snapshot` (ou `dbt build`, como faz o Dagster) para acumular o histórico de `snp_imovel_car`.

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
| `snapshots` | `snp_imovel_car` | `snapshot` | Uma linha por versão observada de cada imóvel (`cod_imovel`, `dbt_valid_from`), estratégia `timestamp` sobre `data_hora_ingestao`. |
| `gold` | `dim_imovel_car` | `table` | Uma linha por versão cadastral de imóvel (`sk_imovel`), com `dbt_valid_from`, `dbt_valid_to` (sempre preenchidos) e `is_current`. |
| `gold` | `dim_tempo` | `table` | Uma linha por data civil 2015–2025, com `is_estacao_seca` (maio–setembro). |
| `gold` | `dim_satelite` | `table` | Uma linha por satélite detector, com `is_referencia`. |
| `gold` | `dim_territorio` | `table` | Uma linha por feição UC/APP/RL; `sk_territorio` estável (hash tipo+WKT); amortecimento 1 km nas UCs. |
| `gold` | `fato_foco_calor` | `table` | Uma linha por detecção de foco (`id_foco`); chaves para tempo e satélite; flags territoriais. |
| `gold` | `mart_reincidencia_imovel_ano` | `table` | Uma linha por imóvel×ano com foco em área protegida; flag `imovel_reincidente` (≥ 2 anos). |

Especificação conceitual: [`docs/modelagem/esquema_dimensional_gold.md`](../docs/modelagem/esquema_dimensional_gold.md).

A consulta [`analyses/conferencia_mv_gold.sql`](analyses/conferencia_mv_gold.sql) reproduz a regra da `gold.mv_imoveis_reincidentes_areas_protegidas` (migração `V7`) sobre os modelos `int_focos_imoveis` e `int_focos_areas_protegidas` para conferência de contagem.

## Histórico de imóveis (SCD Tipo 2)

O snapshot [`snp_imovel_car`](snapshots/snp_imovel_car.yml) preserva retificações de área, alterações de perímetro e mudanças de situação cadastral (inclusive cancelamentos, via `is_excluido`) sem sobrescrever versões anteriores. A dimensão [`dim_imovel_car`](models/marts/dim_imovel_car.sql) é a interface de consumo:

- descarta versões idênticas geradas por reentrega do CDC (mesmo `lsn_origem`);
- `sk_imovel` é a chave substituta por versão (`md5(cod_imovel, lsn_origem)`);
- `dbt_valid_from` da primeira versão de cada imóvel é aberto em `var('inicio_vigencia_aberta')` (1900-01-01) e `dbt_valid_to` da versão corrente é fechado em `var('fim_vigencia_aberta')` (9999-12-31), para que o cruzamento com focos use sempre `dbt_valid_from <= data_hora_evento < dbt_valid_to`; o instante real em que cada versão foi gravada fica em `data_hora_ingestao`.

O unit test `dim_imovel_car_preserva_versao_anterior_para_focos_antigos` ([`_marts.yml`](models/marts/_marts.yml)) cobre a lógica de versões. A demonstração ponta a ponta, sobre uma cópia descartável do Delta e com o código de produção do CDC, roda no contêiner do Dagster:

```bash
docker compose --profile orquestracao exec dagster_webserver python /opt/dagster/app/demo_scd2_imovel.py
```

## Bateria de testes de dados (Issue #21)

A suíte automatizada cobre testes de esquema, integridade referencial, volume histórico e distribuições estatística e espacial:

1. **Testes de esquema e chaves primárias:** testes `unique` e `not_null` em todas as PKs e surrogate keys das camadas Staging, Intermediate e Gold, além de testes genéricos de unicidade composta (`unique_combination_of_columns`) em tabelas associativas e agregadas (`int_focos_imoveis`, `int_focos_areas_protegidas`, `mart_reincidencia_imovel_ano`).
2. **Integridade referencial:** testes `relationships` entre fatos, modelos intermediários e dimensões conformadas (`fato_foco_calor` -> `dim_tempo`, `dim_satelite`; `int_focos_imoveis` -> `dim_imovel_car`, `fato_foco_calor`; `int_focos_areas_protegidas` -> `dim_territorio`, `fato_foco_calor`; `mart_reincidencia_imovel_ano` -> `dim_imovel_car`).
3. **Volume histórico anual:** [`tests/fato_foco_calor_volume_historico_anual.sql`](tests/fato_foco_calor_volume_historico_anual.sql) confere se cada ano da série (2015 a 2025) contém no mínimo 500 focos totais e 80 detecções no satélite de referência AQUA_M-T, prevenindo ingestão truncada.
4. **Distribuição sazonal:** [`tests/fato_foco_calor_distribuicao_sazonal_seca.sql`](tests/fato_foco_calor_distribuicao_sazonal_seca.sql) valida se pelo menos 70% dos focos concentram-se no período de seca do DF (maio a setembro via `is_estacao_seca`), tanto no acumulado da série quanto ano a ano.
5. **Distribuição espacial e integridade geométrica:** [`tests/fato_foco_calor_distribuicao_espacial_df.sql`](tests/fato_foco_calor_distribuicao_espacial_df.sql) valida que 100% dos focos e geometrias de imóveis e feições territoriais estão situados no envelope do Distrito Federal em EPSG:31983 e EPSG:4326, com validação topológica (`ST_IsValid` e não vazias).
6. **Integridade da dimensão temporal SCD2:** testes singulares [`tests/dim_imovel_car_uma_versao_corrente.sql`](tests/dim_imovel_car_uma_versao_corrente.sql) e [`tests/dim_imovel_car_vigencias_contiguas.sql`](tests/dim_imovel_car_vigencias_contiguas.sql).

Comando para execução dos testes:

```bash
docker compose --profile transformacao run --rm dbt test
```

## Limitações

- Chaves `IDENTITY` das feições territoriais (`id_uc`, `id_app`, `id_reserva`) mudam a cada recarga completa do banco (`down -v`): ver descrição de `id_feicao` em [`models/intermediate/_intermediate.yml`](models/intermediate/_intermediate.yml).
- O cruzamento foco por imóvel em `int_focos_imoveis` utiliza o perímetro atual da tabela Delta `imovel_car`; a vinculação com a versão histórica fica para a camada Gold (Issue #18), com `dim_imovel_car` e a validade descrita acima.
- A tabela Delta `imovel_car` guarda só o estado mais recente de cada imóvel. Várias mudanças do mesmo imóvel entre duas execuções do snapshot viram uma única versão nova (a última); a granularidade do histórico é a frequência de execução do `dbt build`.
- A primeira versão de cada imóvel é a observada na carga inicial do CDC e é assumida como vigente para todo o período anterior (focos desde 2015), pois não há histórico cadastral anterior à carga.
