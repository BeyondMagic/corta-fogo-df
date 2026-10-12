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

### D3. Escopo de mutação: `foco_calor` e `imovel_car`

| Tabela | Operações esperadas | Observação |
| --- | --- | --- |
| `foco_calor` | `create` e `read` | O trigger impede `update` e `delete`. Exceção: `TRUNCATE` da recarga |
| `imovel_car` | `create`, `update`, `delete` | Única tabela com mutação real. Exige script de mutação |

Fora do CDC na E2: `reserva_legal`, `area_preservacao_permanente`, `unidade_conservacao`, `hidrografia`, `satelite`. A Gold continua em PostGIS.

Consumidor resolve `id_satelite` para nome por consulta via `psycopg2` com cache, sem incluir `satelite` na publicação.

### D4. Regra de dado atrasado

1. Partição `ano=YYYY/mes=MM` derivada de `data_hora_evento` em UTC. A coluna de origem é `TIMESTAMPTZ` e o CSV vem sem fuso, interpretado como UTC no contêiner.
2. `data_hora_ingestao` é coluna, nunca partição. A janela de ingestão fica consultável sem afetar o layout.
3. Registro atrasado cai na partição do evento, sem tocar nas partições atuais (já coberto por `test_tratamento_dados_atrasados_late_arriving`).
4. Reprocessamento de janela: o `MERGE` inclui predicado de partição (`target.ano = ... AND target.mes = ...`) para limitar a leitura às partições do lote.
5. `imovel_car_analitico`: um evento só é aplicado se `lsn_origem` for maior que o armazenado. Evita que um `update` antigo sobrescreva um mais novo.
6. O CDC não deriva partição do instante de commit nem de `ts_ms`. Usa `data_hora_evento` do payload.