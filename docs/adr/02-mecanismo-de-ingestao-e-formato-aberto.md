---
icon: material/database-sync
---

# :material-database-sync: 0002. Mecanismo de ingestão e formato aberto de tabela

- **Status:** Aceito
- **Data:** 2026-10-13
- **Decisores:** Cláudio H., Elias F., Gabriel F., Gabriel S., João V., Manoel F., Samuel R.

## Contexto

No ADR 0001, colocamos todas as tabelas no PostgreSQL com PostGIS. Isso resolveu a validação geométrica e a integridade referencial, mas a medição da pergunta de gestão mostrou o custo dessa escolha: a junção espacial completa entre os 38.945 focos e os 21.047 imóveis levou 41,8 segundos no banco operacional. Manter esse tipo de consulta analítica rodando direto no PostgreSQL consome CPU, conexões e disco, competindo com as cargas normais do sistema.

Para a Entrega 2, precisamos levar esses dados para uma camada analítica colunar em formato aberto (lakehouse), consultável por ferramentas como o DuckDB. Só que as duas fontes principais do projeto se comportam de maneiras opostas:

1. **Focos de calor do [BDQueimadas (INPE)](../glossario.md#bdqueimadas-inpe):** chegam em arquivos de satélite com 38.945 detecções entre 2015 e 2025. O foco é um fato histórico: depois de gravado, ele nunca sofre alteração nem exclusão (a tabela tem trigger bloqueando UPDATE e DELETE). Porém, ocorrem dados atrasados (*late-arriving data*): um arquivo processado hoje pode conter detecções de meses ou anos anteriores, e esse dado precisa cair na partição do ano do evento, sem sobrepor as partições atuais.
2. **Imóveis rurais do [SICAR](../glossario.md#sicar-car-sistema-nacional-de-cadastro-ambiental-rural):** a tabela `imovel_car` representa um cadastro vivo. Imóveis podem ser inseridos, retificados em área ou cancelados. É a única tabela do projeto que sofre `INSERT`, `UPDATE` e `DELETE`.

Diante disso, precisamos decidir como propagar esses dados para o lakehouse sem sobrecarregar o PostgreSQL e qual formato aberto de tabela adotar no armazenamento.

## Alternativas de ingestão consideradas

### A. Opção nula: Ingestão agendada no PostgreSQL via scripts SQL ou pg_cron

Manter todo o processamento dentro do próprio PostgreSQL, criando tabelas analíticas ou visões materializadas atualizadas por scripts agendados com `pg_cron` ou pelo cron do sistema operacional.

- **O que oferece:** não adiciona nenhum componente à infraestrutura. Toda a lógica continua em SQL puro e usa o PostgreSQL que já está no ar.
- **O que cobra:** as consultas analíticas continuam disputando os mesmos recursos de CPU, memória e disco com a aplicação. O PostgreSQL guarda dados em páginas de 8 KB orientadas a linha, o que é ineficiente para varreduras de colunas em milhões de registros. Também não entrega arquivos abertos para ferramentas externas nem suporta viagens no tempo (*time-travel*) sem duplicação manual de tabelas.

### B. Captura de mudanças de dados (CDC) via decodificação lógica do WAL

Configurar o PostgreSQL com `wal_level=logical` e ler as alterações direto do log de transações (Write-Ahead Log) por meio de um slot de replicação com plugin nativo (`test_decoding`). Um consumidor em Python lê o stream de eventos e reflete as mutações na tabela aberta.

- **O que oferece:** propaga alterações cadastrais com latência de milissegundos (~32 ms no nosso teste). Captura inserções, atualizações e exclusões sem fazer consultas periódicas de varredura no banco. A ordem das operações é garantida pelo número sequencial de log (LSN), o que elimina incertezas de relógio.
- **O que cobra:** exige monitorar o slot de replicação. Se o consumidor parar e o slot ficar aberto, o PostgreSQL acumula arquivos de WAL em disco até o limite de `max_slot_wal_keep_size` (definido em 2 GB), podendo esgotar o espaço da partição de dados do banco.

### C. Ingestão periódica em lote (Batch)

Executar scripts em Python que leem arquivos das fontes públicas ou do banco em horários definidos, aplicando regras de particionamento e mesclagem idempotente na escrita.

- **O que oferece:** processo simples que roda, faz o trabalho e encerra. Não mantém serviços adicionais em segundo plano, não ocupa conexões permanentes e não depende de brokers de mensageria como Kafka. Combina com a natureza das fontes públicas, que publicam arquivos em lotes diários ou anuais. Trata dados atrasados de forma determinística, gravando cada registro na sua pasta de partição correspondente.
- **O que cobra:** a novidade dos dados fica limitada ao intervalo de agendamento (horas ou dias). Exige um identificador estável para que reexecuções não gerem duplicatas.

## Comparação de formatos abertos de tabela

Para armazenar os arquivos colunares Parquet com suporte a transações ACID e controle de versão, comparamos duas opções:

### Delta Lake

Formato de tabela aberta que armazena os dados em arquivos Parquet e o histórico de transações em uma pasta `_delta_log/` com arquivos JSON e checkpoints compactados.

- **O que oferece:** a biblioteca `deltalake` (delta-rs, escrita em Rust com bindings para Python) permite ler e gravar tabelas Delta diretamente com PyArrow e Pandas, sem precisar de Java, JVM ou cluster Spark. Suporta `MERGE INTO`, particionamento no padrão Hive (`ano=YYYY/mes=MM/`) e é lida nativamente pelo DuckDB.
- **O que cobra:** a biblioteca em Rust cobre as operações locais de escrita, merge e deleção, mas não implementa todos os recursos de catálogos corporativos avançados que o ecossistema Databricks oferece. Para o nosso ambiente conteinerizado, essa limitação não tem impacto prático.

### Apache Iceberg

Formato de tabela analítica voltado para grandes volumes de dados, com metadados estruturados em árvores de manifestos e arquivos de dados.

- **O que oferece:** isolamento transacional rigoroso, evolução de esquema sem reescrever dados e particionamento oculto (as consultas filtram por data sem precisar conhecer a estrutura de pastas).
- **O que cobra:** exige um serviço de catálogo ativo (como REST Catalog, Nessie ou Hive Metastore) para coordenar escritas concorrentes, o que adicionaria mais contêineres e memória ao Compose. A biblioteca Python (`pyiceberg`) ainda tem limitações para operações complexas de escrita e mesclagem comparada à sua implementação em Java, o que exigiria trazer a JVM para o pipeline.

## Critérios de avaliação

Comparamos as opções usando cinco critérios técnicos:

1. **Latência de propagação:** tempo que uma alteração na origem leva para aparecer nas consultas analíticas.
2. **Custo operacional:** quantidade de serviços no Docker Compose, consumo de memória RAM, dependência de JVM e complexidade de manutenção.
3. **Impacto no OLTP:** quanto a ingestão consome de CPU, disco, conexões e espaço de WAL do PostgreSQL.
4. **Evolução de esquema:** facilidade para adicionar ou alterar colunas sem quebrar cargas antigas nem reprocessar a base inteira.
5. **Tolerância a falhas e idempotência:** garantia de que reexecuções de jobs, quedas de conexão ou eventos fora de ordem cronológica não gerem linhas duplicadas nem corrompam dados.

---

## Medição Empírica

Todas as medições desta seção foram obtidas com os scripts de benchmark do repositório, usando dados reais do Distrito Federal (38.945 focos do INPE e 21.047 imóveis do CAR).

### 1. Benchmark de Latência: CDC vs Lote vs Opção Nula

- Script: [`scripts/benchmark/benchmark_ingestao.py`](https://github.com/BeyondMagic/corta-fogo-df/blob/main/scripts/benchmark/benchmark_ingestao.py)
- Relatório detalhado: [`scripts/benchmark/resultados_latencia.md`](https://github.com/BeyondMagic/corta-fogo-df/blob/main/scripts/benchmark/resultados_latencia.md)

| Mecanismo | Latência medida | Frequência típica | Granularidade | Impacto no OLTP |
| :--- | :--- | :--- | :--- | :--- |
| **CDC (Decodificação Lógica)** | **~31,97 ms** | Contínua (quase tempo real) | Tupla a tupla | Baixo (leitura assíncrona do WAL via slot) |
| **Lote (Delta Lake MERGE)** | **~52,69 ms** | Agendada (diária ou periódica) | Bloco temporal (`ano/mes`) | Nulo (processamento fora do banco) |
| **Opção Nula (SQL no PostgreSQL)** | **~14,27 ms** | Agendada (`pg_cron` ou trigger) | Conjunto relacional | Alto (concorre por CPU, I/O e travas) |

À primeira vista, a opção nula parece a mais rápida (14,27 ms), mas esse número esconde o problema real: ela roda dentro do próprio PostgreSQL, disputando memória compartilhada (*shared_buffers*) e bloqueios de tabela com as transações da aplicação. Conforme o volume de cruzamentos espaciais cresce, essa disputa degrada o banco inteiro.

O CDC entrega uma latência de 31,97 ms lendo o WAL de forma assíncrona, sem travar tabelas nem concorrer com o planejador de consultas. Já o lote demora 52,69 ms para mesclar blocos de dados fora do banco, sem gerar impacto no OLTP.

---

### 2. Benchmark de Compressão: Snappy vs ZSTD

- Script: [`scripts/benchmark/benchmark_compressao.py`](https://github.com/BeyondMagic/corta-fogo-df/blob/main/scripts/benchmark/benchmark_compressao.py)
- Relatório detalhado: [`scripts/benchmark/resultados_compressao.md`](https://github.com/BeyondMagic/corta-fogo-df/blob/main/scripts/benchmark/resultados_compressao.md)
- Amostra: partição real de focos do DF (`ano=2024/mes=08`, com 1.183 registros).

| Algoritmo | Tamanho em disco | Redução vs bruto em memória | Tempo de escrita | Consulta no DuckDB |
| :--- | :--- | :--- | :--- | :--- |
| **Sem compressão** | 0,1439 MB | 43,9% | 2,17 ms | 2,78 ms |
| **Snappy** | 0,1359 MB | 47,0% | 2,13 ms | 2,53 ms |
| **ZSTD (Zstandard)** | **0,0918 MB** | **64,2%** | 2,80 ms | 2,90 ms |

O Zstandard (ZSTD) gerou arquivos 32,4% menores que o Snappy (0,0918 MB contra 0,1359 MB), reduzindo o volume em 64,2% em relação aos dados brutos em memória.

Na leitura pelo DuckDB, uma consulta analítica agregada (`COUNT(*)`, `AVG(risco_fogo)` por satélite) levou 2,90 ms no ZSTD e 2,53 ms no Snappy. A diferença de 0,37 ms é imperceptível na prática e compensa amplamente pela economia de armazenamento em uma série histórica de 11 anos.

---

### 3. Semântica de Entrega e Testes de Falha

- Script: [`scripts/testes/test_reprocessamento_cdc.py`](https://github.com/BeyondMagic/corta-fogo-df/blob/main/scripts/testes/test_reprocessamento_cdc.py)

1. **At-least-once com deduplicação no destino:**
   No teste de reprocessamento do CDC, forçamos o consumidor a recuar o offset para um LSN anterior (`0/2000`) e reenviamos mutações antigas misturadas com eventos fora de ordem (`0/800`). A cláusula de guarda no `MERGE` do Delta Lake (`source.lsn_origem >= target.lsn_origem`) descartou todos os eventos com LSN inferior ao já armazenado. A tabela manteve unicidade em `cod_imovel` com zero duplicações, confirmando que a reentrega de eventos não corrompe o estado.

2. **Idempotência no lote:**
   A reexecução do script de lote sobre os mesmos focos processou 20 registros, inseriu zero linhas e ignorou 20 duplicatas por meio do `MERGE ... WHEN NOT MATCHED INSERT`. A contagem total da tabela permaneceu inalterada.

3. **Comportamento em caso de falha:**
   Se o lote falhar, o impacto fica restrito àquele job: basta corrigir o problema e rodar o lote de novo. Se o consumidor CDC falhar, o efeito se acumula no PostgreSQL: os arquivos de WAL não são descartados enquanto o slot `cdc_imovel` não avançar. Isso reforça a necessidade de manter o consumidor ativo ou monitorar o tamanho do WAL retido.

---

## Decisão

Adotamos uma abordagem híbrida de ingestão com **Delta Lake** como formato de tabela aberta:

1. **Ingestão em lote para `foco_calor`:**
   Executada por [`src/pipeline/batch_ingest.py`](https://github.com/BeyondMagic/corta-fogo-df/blob/main/src/pipeline/batch_ingest.py). Os focos do INPE são gravados em `data/delta/foco_calor`, particionados no padrão `ano=YYYY/mes=MM/` a partir de `data_hora_evento`. A idempotência é garantida gerando um identificador determinístico `id_foco` (hash SHA-256 das coordenadas, data/hora e satélite), aplicando `MERGE INTO` para gravar apenas detecções novas. Dados com datas anteriores caem direto na partição do ano correspondente, sem alterar as demais.

2. **Captura de mudanças (CDC) para `imovel_car`:**
   Executada por [`src/pipeline/cdc_consumer.py`](https://github.com/BeyondMagic/corta-fogo-df/blob/main/src/pipeline/cdc_consumer.py). O script consome o slot de replicação lógica `cdc_imovel` com o plugin nativo `test_decoding` e `psycopg2`, sem intermediários como Kafka ou Debezium. Os dados vão para `data/delta/imovel_car` sem partição, aplicando `MERGE` por `cod_imovel` com a guarda `source.lsn_origem >= target.lsn_origem`. Exclusões no banco são refletidas como exclusão lógica (`operacao_cdc='D'`), preservando geometrias compactadas pelo mecanismo TOAST.

3. **Formato de tabela e compressão:**
   Usamos a biblioteca `deltalake` (delta-rs) em Python, sem JVM e sem catálogo externo. Os dados históricos usam compressão Zstandard (ZSTD), e as consultas analíticas rodam no DuckDB por meio da função `delta_scan`.

---

## Consequências

**O que ganhamos:**

- As consultas espaciais analíticas saem do PostgreSQL e rodam no DuckDB sobre arquivos Parquet, liberando o banco operacional para transações normais.
- O pipeline inteiro roda em Python leve com `deltalake` e `psycopg2`, sem exigir Spark, Hadoop, JVM ou contêineres de mensageria no Docker Compose.
- Reprocessamentos de lote e retransmissões do CDC não duplicam linhas. O hash `id_foco` protege os focos e a guarda de LSN protege os imóveis.
- Focos antigos recebidos em lotes recentes são direcionados automaticamente para suas partições históricas de ano e mês.
- A compressão ZSTD entrega mais de 64% de redução em relação ao tamanho bruto em memória, com velocidade de leitura equivalente ao Snappy no DuckDB.

**O que perdemos:**

- O slot de replicação do CDC exige monitoramento. Se o consumidor parar e ficar inativo por muito tempo, o PostgreSQL acumula arquivos de WAL até o limite de 2 GB.
- A biblioteca `deltalake` em Python não traz recursos de catálogos corporativos distribuídos que existem no Spark, embora atenda com folga o escopo local e conteinerizado do projeto.

**O que se torna irreversível:**

- A camada analítica passa a depender da especificação do Delta Lake e dos seus logs em `_delta_log/`. Migrar para Apache Iceberg no futuro exigirá ferramentas de conversão de metadados ou reprocessamento dos dados físicos.

---

## Gatilho de revisão

Revisaremos esta decisão caso:

1. O INPE passe a disponibilizar focos em fluxo contínuo de tempo real (subminuto por streaming), tornando a janela em lote insuficiente.
2. O projeto passe a exigir um catálogo corporativo compartilhado por múltiplos motores analíticos concorrentes em nuvem (como Trino, Spark e Flink operando juntos), cenário em que o Apache Iceberg com catálogo REST deverá ser avaliado.
3. A retenção de WAL no PostgreSQL atinja com frequência o limite de 2 GB por inatividade do consumidor, justificando adotar uma infraestrutura externa de mensageria com Debezium e Kafka.
