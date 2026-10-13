# Diário de Bordo: Entrega 2 (Semanas 7 a 10)

## Semana 7

A semana foi usada para corrigir a Entrega 1 (E1) de acordo com as observações da professora. Não houve entrega da E2 nesta semana.

## Semana 8

**30/09 -** O grupo se reuniu para se organizar para a próxima entrega (E2). Não houve entrega nesta semana. As entregas da E2 começaram na semana 9.

## Semana 9

**O que foi feito**

**05/10 -** Documento de arquitetura da E2 consolidado. </br>
**05/10 -** Ingestão em lote dos focos de calor do INPE para uma tabela Delta Lake (`batch_ingest.py`), com `MERGE` por `id_foco`. </br>
**06/10 -** Testes de idempotência, partição e dado atrasado do lote (`test_idempotencia_lote.py`). </br>
**09/10 -** PostgreSQL configurado para decodificação lógica (`wal_level=logical`, `max_replication_slots=4`, `max_slot_wal_keep_size=2GB`). </br>

**Decisões**

- **Formato aberto: Delta Lake via `deltalake`.** Parquet com log Delta, sem JVM e sem catálogo. Iceberg exigiria `pyiceberg`, catálogo e reescrita do lote e dos testes.
- **Dado atrasado no lote: partição `ano/mes` pelo `data_hora_evento` em UTC.** Registro atrasado cai na partição do evento sem tocar nas atuais. `data_hora_ingestao` é coluna, nunca partição. Reprocessar uma janela é reexecutar o arquivo do ano. O `MERGE` só insere, o que basta porque os focos do INPE são insert-only.
- **Escopo do CDC: só `imovel_car`.** É a única tabela com INSERT, UPDATE e DELETE. `foco_calor` fica no lote: o trigger bloqueia UPDATE e DELETE, e o OLTP não tem a chave de deduplicação do lote (`id_foco` é identity e reinicia a cada recarga).
- **CDC por decodificação lógica nativa com `psycopg2`.** Plugin `test_decoding` do próprio PostgreSQL, lido por `pg_logical_slot_peek_changes` e confirmado por `pg_replication_slot_advance`. Não adiciona serviço novo ao Compose e reaproveita a stack existente.

## Semana 10

**O que foi feito**

**10/10 -** Consumidor CDC (`cdc_consumer.py`) que grava `imovel_car` em uma tabela Delta. </br>
**10/10 -** Script de mutações no OLTP para provar que o CDC captura mudanças. </br>
**11/10 -** Testes do consumidor CDC (reprocessamento e idempotência). </br>

**Decisões**

- **Estado inicial e slot.** Ao iniciar, o consumidor cria o slot `cdc_imovel` se não existir e carrega um snapshot completo de `imovel_car`. Mudanças entre a criação do slot e o snapshot são reentregues e absorvidas pela guarda de `lsn_origem`.
- **Tabela Delta `imovel_car`.** Chave `cod_imovel`, sem partição. Guarda `geom_ewkb_hex` (hex repassado sem decodificar), `operacao_cdc` e `lsn_origem`. Exclusão é lógica (`operacao_cdc='D'`).
- **Dado atrasado no CDC: ordem por `lsn_origem`.** Evento só é aplicado se o `lsn_origem` for maior ou igual ao armazenado. Evento fora de ordem é ignorado, sem depender do relógio.
- **Semântica de entrega: at-least-once com deduplicação no destino.** O LSN só é confirmado depois do commit no Delta. Se o consumidor falhar no meio, o slot reentrega os eventos e `cod_imovel` mais a guarda de LSN impedem duplicata. No lote, `MERGE ... WHEN NOT MATCHED INSERT` por `id_foco` mantém a contagem em reexecuções.
