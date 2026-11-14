# Benchmark Mínimo: MongoDB com Índices 2dsphere

Implementação isolada para medir a viabilidade e o desempenho do MongoDB na consulta da pergunta de gestão do [ADR 0001](../../../docs/adr/01-adotar-postgresql-com-postgis-camada-gold.md), usando o mesmo conjunto de dados reais do Distrito Federal.

## 1. Por que este benchmark existe

No ADR 0001, a alternativa C (MongoDB) foi avaliada conceitualmente. Este benchmark fornece o código reproduzível para comprovar na prática as características operacionais do MongoDB nessa carga:

1. **Ausência de junção espacial declarativa:** o MongoDB não possui equivalente a `ST_Intersects` ou `ST_DWithin` para relacionar coleções poligonais densas em uma única consulta. O operador `$lookup` não aceita predicados espaciais (`$geoIntersects`) dentro de expressões `$expr`.
2. **Processamento dirigido pela aplicação:** o cruzamento exige iterar sobre os documentos (por imóvel ou por foco) no código cliente, realizando milhares de requisições individuais ao banco.
3. **Restrição ao elipsoide WGS84:** os índices `2dsphere` trabalham com coordenadas esféricas em graus (EPSG:4326), enquanto a métrica oficial distrital utiliza a projeção métrica plana SIRGAS 2000 / UTM zone 23S (EPSG:31983).

## 2. Estrutura dos arquivos

- `docker-compose.mongo.yml`: define o contêiner do MongoDB 7.0 com os mesmos limites de recursos do PostgreSQL (2 CPUs e 2 GB de RAM) e o serviço que executa a carga e a medição.
- `carregar_mongo.py`: lê os arquivos de dados brutos e processados, converte as geometrias para GeoJSON WGS84 e cria os índices espaciais `2dsphere`.
- `benchmark_mongo.py`: executa a consulta da pergunta de gestão, demonstra a limitação do `$lookup` e mede o tempo de processamento por imóvel.
- `run_benchmark.sh`: script shell para executar o processo completo em um comando.

## 3. Como executar

### Opção A: Via Docker Compose (recomendado)

Com o Docker em execução, suba os contêineres:

```bash
docker compose -f scripts/benchmark/mongodb/docker-compose.mongo.yml up --build
```

Para encerrar e remover o volume de dados ao terminar:

```bash
docker compose -f scripts/benchmark/mongodb/docker-compose.mongo.yml down -v
```

### Opção B: Execução direta com Python local

Caso já tenha uma instância do MongoDB rodando na porta 27017:

```bash
pip install -r scripts/benchmark/mongodb/requirements.txt
python scripts/benchmark/mongodb/carregar_mongo.py
python scripts/benchmark/mongodb/benchmark_mongo.py
```

Argumentos opcionais aceitos:
- `--limite 1000`: avalia apenas os primeiros 1.000 imóveis para estimativa rápida.
- `--timeout 180`: define o limite de tempo em segundos (padrão de 180 s).

## 4. O que o script mede e compara

O script avalia:
1. Tempo de ingestão dos 38.945 focos e dos 21.047 imóveis do CAR-DF.
2. Tempo de criação dos índices `2dsphere`.
3. Tempo da consulta central da pergunta de gestão:
   - Identifica imóveis com focos em pelo menos 2 anos distintos entre 2015 e 2025.
   - Verifica se o foco atingiu reserva legal, APP ou faixa de 1.000 metros de Unidade de Conservação.
4. Comparativo direto com o tempo do PostgreSQL 16 + PostGIS 3.4 (41,8 s).
