# Benchmark da consulta da pergunta de gestão

Mede o efeito do índice GiST sobre a consulta central do ADR 0001, com o dado real do Distrito Federal já carregado pelo `docker compose up` (nenhum dado sintético).

## Como reproduzir

```bash
docker compose up -d
docker cp scripts/benchmark/benchmark_pergunta_gestao.sql $(docker compose ps -q db):/tmp/benchmark_pergunta_gestao.sql
docker compose exec db psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -f /tmp/benchmark_pergunta_gestao.sql
```

Sem variáveis de ambiente definidas, use os valores padrão do `docker-compose.yml`: usuário `corta-fogo`, banco `corta-fogo-df`.

## O que o script mede

A mesma consulta (a do ADR 0001, seção "Medição") roda duas vezes na mesma sessão:

- **B**: comportamento padrão do PostgreSQL com PostGIS, usando o índice GiST das colunas de geometria (a alternativa adotada).
- **A**: a mesma consulta com `enable_indexscan` e `enable_bitmapscan` desligados, forçando varredura sequencial. Aproxima a alternativa "PostgreSQL puro sem índice R-tree" descrita no ADR, sem exigir uma segunda infraestrutura: isola o efeito real de ter (ou não) um índice espacial sobre o mesmo dado e a mesma consulta. Tem um `statement_timeout` de 5 minutos, porque sem índice a consulta não termina em tempo hábil.

## Resultado da última execução (dado real, 28/09/2026)

| Alternativa | Tempo de execução |
| :--- | :--- |
| B. PostgreSQL + PostGIS (índice GiST) | 41,8 s |
| A. Sem índice espacial (indexscan/bitmapscan desligados) | > 5 min (timeout, não terminou) |

## Alternativa C: MongoDB com índice 2dsphere

A implementação do benchmark mínimo para o MongoDB está disponível no diretório [`mongodb/`](mongodb/README.md), contendo o `docker-compose.mongo.yml` e scripts para:
1. Ingestão dos dados em WGS84 (GeoJSON) e criação de índices espaciais `2dsphere`.
2. Execução da consulta da pergunta de gestão via iteração por imóvel e verificação de predicados espaciais.
3. Demonstração prática da impossibilidade de junção espacial declarativa via `$lookup`.

Para executar o benchmark do MongoDB via Docker:

```bash
docker compose -f scripts/benchmark/mongodb/docker-compose.mongo.yml up --build
```

## Disponibilização e retrato de consumo (ADR 0004)

`benchmark_disponibilizacao.py` compara sobre os arquivos versionados do repositório (e contra DuckDB/PostgreSQL ao vivo quando ativos) o tamanho entregue, a contagem de vértices e a latência de leitura/serialização entre a opção nula em CSV + MV PostGIS (`docs/explain/`), consulta direta ao DuckDB e o retrato estático `docs/assets/dados_dashboard/gold.json`.

```bash
python3 scripts/benchmark/benchmark_disponibilizacao.py --iteracoes 30
```
