# Alinhamento da Arquitetura da E2

## 1. Decisões arquiteturais definidas

### D1. Formato aberto: Delta Lake via `deltalake`

- Já implementado e testado. Sem JVM e sem catálogo.
- Iceberg exigiria `pyiceberg`, catálogo (SQL ou REST) e reescrita de `batch_ingest.py` e dos testes.
- Escrita via `write_deltalake` e `DeltaTable.merge`.

### D2. Conector CDC: Debezium Server (sink Kafka) + Redpanda

Opções discutidas em grupo: 

- Debezium Connector for PostgreSQL em Kafka Connect sobre Redpanda
- Debezium Server

Proposta do grupo: Debezium Server publicando em Redpanda. Redpanda não executa Kafka Connect. A primeira opção exige um contêiner `debezium/connect` e um passo de registro do conector via REST, que complica o processo de orquestração. Debezium Server é configurado por arquivo de propriedades montado no contêiner.

Serviços novos no Compose: `redpanda`, `debezium-server`, `cdc-consumer`. Parâmetros mínimos:

| Parâmetro | Valor |
| --- | --- |
| `plugin.name` | `pgoutput` |
| `publication.name` | `cdc_publication` (criada no Flyway), `publication.autocreate.mode=disabled` |
| `slot.name` | nome fixo, único |
| `topic.prefix` | `oltp`, gerando `oltp.public.foco_calor` e `oltp.public.imovel_car` |
| `snapshot.mode` | `initial`. Eventos `r` são tratados como upsert e absorvidos pela deduplicação |
| `decimal.handling.mode` | `double` (`risco_fogo`) |
| Serialização | JSON |

Geometria: o Debezium entrega colunas PostGIS como struct `{wkb, srid}`. O consumidor decodifica com `shapely.wkb`.