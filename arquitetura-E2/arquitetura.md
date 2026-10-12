# Alinhamento da Arquitetura da E2

## 1. Decisões arquiteturais definidas

### D1. Formato aberto: Delta Lake via `deltalake`

- Já implementado e testado. Sem JVM e sem catálogo.
- Iceberg exigiria `pyiceberg`, catálogo (SQL ou REST) e reescrita de `batch_ingest.py` e dos testes.
- Escrita via `write_deltalake` e `DeltaTable.merge`.