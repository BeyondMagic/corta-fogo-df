# Orquestração com Dagster

O Dagster orquestra o pipeline analítico: a ingestão em lote dos focos para o Delta e o `dbt build` de `transformacao/`. Os modelos dbt viram *software-defined assets* (`dagster-dbt`), então o grafo da interface vem do `manifest` do dbt e novos modelos entram sozinhos.

## Como subir

```bash
docker compose --profile orquestracao up -d --build
```

Interface em <http://localhost:3000> (porta configurável por `DAGSTER_PORT`). São dois serviços, `dagster_webserver` e `dagster_daemon` (agenda e backfills), no perfil `orquestracao`: o `docker compose up` padrão não os inicia. O estado (execuções, backfills, agendas) fica em SQLite no volume `dagster_state`, removido pelo `docker compose down -v`.

Os modelos dbt leem as tabelas Delta e o PostGIS, então o `batch_ingest` e o `cdc_consumer` precisam ter rodado (`docker compose up`).

## Grafo de assets

| Asset | Grupo | Descrição |
| :--- | :--- | :--- |
| `foco_calor_delta` | `lote` | Focos no Delta, **132 partições mensais** (jan/2015 a dez/2025, mesmas `ano/mes` da tabela). |
| `imovel_car_delta` | `cdc` | Alimentado fora do Dagster pelo `cdc_consumer`. |
| `staging/*`, `intermediate/*`, `oltp/*` | `default` | Modelos e fontes do dbt. As fontes Delta do dbt apontam para os dois assets acima. |

| Job | Conteúdo | Agenda |
| :--- | :--- | :--- |
| `job_transformacao` | `dbt build` de todos os modelos | Diária, 03:00 (America/Sao_Paulo) |
| `job_lote_mensal` | Uma partição mensal de `foco_calor_delta` | Sob demanda (backfill) |

`dagster.yaml` limita a uma execução por vez (`max_concurrent_runs: 1`): o DuckDB aceita um único escritor por arquivo, e partições em paralelo travariam `corta_fogo.duckdb`.

## Retry com recuo exponencial

`politicas.py` define `RetryPolicy(max_retries=3, delay=2, backoff=EXPONENTIAL)`, aplicada a `foco_calor_delta` e aos modelos dbt. Para induzir falha de forma determinística, `FALHAS_INDUZIDAS=N` faz as N primeiras tentativas de `foco_calor_delta` falharem:

```bash
FALHAS_INDUZIDAS=3 docker compose --profile orquestracao up -d --force-recreate dagster_webserver dagster_daemon
docker compose --profile orquestracao exec dagster_webserver dagster job backfill -j job_lote_mensal \
  -w /opt/dagster/home/workspace.yaml --partitions 2024-08-01 --noprompt
```

Com `FALHAS_INDUZIDAS=3`, o log da execução mostra 4 tentativas, com pedidos de nova tentativa em 2 s, 6 s e 14 s, e sucesso na quarta. Com `FALHAS_INDUZIDAS=4` o recuo se esgota e a execução termina em falha. Sem a variável (ou com `0`) não há falha induzida.

## Backfill por partição

```bash
docker compose --profile orquestracao exec dagster_webserver python /opt/dagster/app/demo_backfill.py
```

O script reexecuta pelo Dagster as partições 2024-08 a 2024-10, remove a partição 2024-09 do Delta (3.079 linhas) e faz backfill só dela. Resultado da execução registrada:

| Etapa | Resultado |
| :--- | :--- |
| Backfill de 3 partições com o Delta íntegro | 0 linhas inseridas, 5.587 ignoradas por duplicidade; total continua em 38.944 |
| Perda da partição 2024-09 | Tabela cai para 35.865 linhas, 131 partições |
| Backfill só de 2024-09 | 3.079 linhas restauradas; 38.944 linhas, todas com `id_foco` único; as outras 131 partições idênticas às do início |

O reprocessamento é idempotente porque o `MERGE` de `batch_ingest.py` só insere `id_foco` ausente.

## Limitações

- O backfill por partição está na ingestão para o Delta. Os modelos dbt são `table` com recarga completa, sem partição.
- Ainda não há testes dbt (`dbt build` só materializa os modelos).
