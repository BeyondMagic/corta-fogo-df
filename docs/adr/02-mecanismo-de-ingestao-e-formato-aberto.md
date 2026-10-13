# 0002. Mecanismo de ingestão e formato aberto de tabela

- **Status:** Proposto
- **Data:** 2026-10-13
- **Decisores:** Cláudio H., Elias F., Gabriel F., Gabriel S., João V., Manoel F., Samuel R.

## Contexto

O projeto Corta-Fogo DF consolida dois fluxos de dados com características operacionais distintas:

1. **Ocorrências de calor do [BDQueimadas (INPE)](../glossario.md#bdqueimadas-inpe):** série temporal contínua com detecções orbitais no Distrito Federal (38.945 focos entre 2015 e 2025). As linhas são imutáveis (apenas inserção), mas eventos de datas anteriores podem ser disponibilizados em remessas posteriores (dados atrasados ou *late-arriving data*).
2. **Cadastros territoriais do [SICAR](../glossario.md#sicar-car-sistema-nacional-de-cadastro-ambiental-rural) e do IBRAM/SISDIA:** malhas fundiárias e áreas protegidas (21.047 imóveis rurais, 13.499 reservas legais, 2.234 áreas de preservação permanente e 84 unidades de conservação). No sistema de origem, `imovel_car` é a tabela cadastral sujeita a inserções, atualizações de perímetro e cancelamentos de registro (operações de INSERT, UPDATE e DELETE).

Na Entrega 1, essas bases foram estruturadas no PostgreSQL 16 com extensão PostGIS 3.4 ([ADR 0001](01-adotar-postgresql-com-postgis-camada-gold.md)), que valida regras topológicas e chaves relacionais. Executar consultas analíticas espaciais pesadas diretamente no PostgreSQL consome CPU e memória do banco operacional.

A equipe precisa definir dois pontos arquiteturais para a Entrega 2:

- O mecanismo de propagação dos dados do sistema de origem para o ambiente analítico.
- O formato aberto de armazenamento colunar para persistência no lakehouse, permitindo consultas analíticas sem dependência de um servidor de banco dedicado.

## Alternativas de ingestão consideradas

### A. Opção nula: Ingestão agendada no PostgreSQL via scripts SQL ou pg_cron

Manter o processamento analítico dentro do próprio PostgreSQL, agendando rotinas de cópia periódica (`INSERT ... SELECT`), visões materializadas ou scripts SQL executados via extensão `pg_cron` ou cron do sistema operacional.

- **O que oferece:** dispensa ferramentas externas de pipeline, mantém toda a lógica em comandos SQL e utiliza a infraestrutura de banco de dados já instalada.
- **O que cobra:** consome recursos de CPU, memória e I/O da mesma instância utilizada pelo sistema transacional durante as rotinas de carga. Mantém os dados presos na estrutura relacional do PostgreSQL, sem gerar arquivos colunares abertos para processamento analítico desacoplado.

### B. Captura de mudanças de dados (CDC) via decodificação lógica do WAL

Configurar a leitura contínua do log de transações do PostgreSQL (Write-Ahead Log - WAL) com nível lógico (`wal_level=logical`), extraindo eventos linha a linha por meio de slots de replicação com plugins de decodificação (`test_decoding` ou `pgoutput`) para atualizar a camada analítica.

- **O que oferece:** propaga modificações com baixa latência, captura operações DML (INSERT, UPDATE e DELETE) sem sobrecarregar o banco com consultas de varredura periódica e registra a ordem exata das transações por meio do Log Sequence Number (LSN).
- **O que cobra:** exige gerenciar slots de replicação lógica no PostgreSQL. Se o processo consumidor falhar ou ficar inativo, o banco retém os arquivos de WAL no disco até o limite configurado (`max_slot_wal_keep_size`), sob risco de esgotar o armazenamento da instância operacional.

### C. Ingestão periódica em lote (Batch)

Executar scripts programados em Python que extraem dados das fontes públicas (INPE) ou exportam lotes do banco de dados em janelas de tempo definidas, aplicando regras de limpeza, particionamento e deduplicação no momento da escrita.

- **O que oferece:** arquitetura simples sem processos residentes em segundo plano ou filas de mensageria. Alinha o processamento à periodicidade das publicações públicas de satélite e cadastros rurais. Permite controle determinístico de idempotência e ordenação de registros atrasados (*late-arriving data*).
- **O que cobra:** a latência de atualização fica vinculada ao intervalo de disparo do agendador. Exige controle explícito de estado entre execuções para evitar reprocessamento integral de períodos já consolidados.

## Comparação de formatos abertos de tabela

Para o armazenamento analítico colunar (lakehouse), avaliamos duas especificações de tabela aberta baseadas em Parquet:

### Delta Lake

Especificação aberta de tabela com controle transacional ACID, versionamento de dados e log de operações mantido no diretório `_delta_log/` em formato JSON e checkpoints compactados.

- **O que oferece:** biblioteca nativa em Python (`deltalake`, desenvolvida em Rust pelo projeto delta-rs) que lê e grava tabelas Delta diretamente com PyArrow e Pandas, sem necessidade de JVM ou cluster Apache Spark. Suporta operações de `MERGE INTO`, particionamento em diretórios padrão Hive (`ano=YYYY/mes=MM/`) e integração com ferramentas de consulta colunar como DuckDB.
- **O que cobra:** o ecossistema delta-rs implementa um subconjunto da especificação completa do Delta Lake do ecossistema Spark, embora cubra plenamente escrita em lote, `MERGE`, deleção lógica e histórico de commits.

### Apache Iceberg

Especificação de tabela aberta voltada para grandes volumes analíticos, com controle de metadados em camadas (arquivos de metadados JSON, listas de manifestos e arquivos de manifesto individuais).

- **O que oferece:** abstração completa de particionamento (particionamento oculto, sem expor colunas artificiais na consulta), evolução de esquema sem reescrita de dados e isolamento transacional estrito.
- **O que cobra:** requer um catálogo de metadados externo ativo (serviço REST Catalog, Nessie, JDBC ou Hive Metastore) para registrar commits concorrentes. A biblioteca Python oficial (PyIceberg) tem maturidade menor para operações avançadas de escrita e mesclagem espacial comparada ao ecossistema Java.

## Critérios de avaliação

A decisão entre os mecanismos de ingestão e os formatos abertos considera cinco critérios técnicos:

1. **Latência de propagação:** intervalo de tempo entre a publicação ou alteração do registro na origem e a sua disponibilidade para consulta na camada analítica.
2. **Custo operacional:** quantidade de serviços adicionais no ambiente (contêineres, brokers de mensageria, memória alocada, runtime Java) e esforço de manutenção contínua.
3. **Impacto no OLTP:** nível de interferência da rotina de extração sobre os recursos do PostgreSQL operacional (consumo de CPU, I/O de disco, concorrência de travas e retenção de WAL).
4. **Complexidade de schema evolution:** esforço necessário para adicionar, renomear ou tipar colunas nas tabelas analíticas sem corromper partições históricas ou exigir reprocessamento total.
5. **Tolerância a falhas e idempotência:** capacidade de recuperar execuções interrompidas, reprocessar remessas duplicadas e organizar dados recebidos fora de ordem temporal (*late-arriving data*) sem gerar duplicatas.

## Medição planejada

A validação das alternativas na Entrega 2 contempla três medições práticas:

- **Idempotência e dados atrasados no lote:** verificação automatizada via script `scripts/testes/test_idempotencia_lote.py`, avaliando a reexecução do lote de focos e a alocação de registros em partições temporais históricas.
- **Consumo e retenção do WAL no CDC:** monitoramento do volume de WAL retido e tempo de confirmação do LSN via `scripts/testes/test_cdc_consumer.py`.
- **Desempenho de consulta no formato aberto:** medição do tempo de varredura e cruzamento analítico dos arquivos Parquet via DuckDB contra a tabela materializada do PostGIS.

## Decisão

Adotamos uma abordagem híbrida de ingestão combinada ao formato aberto **Delta Lake**:

1. **Ingestão em lote (Batch) para `foco_calor`:** executada pelo script `src/pipeline/batch_ingest.py`, gravando em Parquet particionado no padrão `ano=YYYY/mes=MM/` derivado de `data_hora_evento`. Idempotência garantida por chave determinística `id_foco` e operação `MERGE INTO`.
2. **Captura de mudanças (CDC) para `imovel_car`:** executada pelo consumidor `src/pipeline/cdc_consumer.py`, lendo alterações do slot lógico `cdc_imovel` via decodificação nativa do PostgreSQL (`test_decoding`) com `psycopg2`, sem serviços intermediários de mensageria ou JVM.
3. **Formato aberto de tabela: Delta Lake via biblioteca `deltalake`:** dispensa catálogo de metadados externo e executa em processo Python leve, com controle ACID local e leitura via DuckDB.

## Consequências

**O que ganhamos:**

- Desacoplamento da carga analítica: consultas OLAP pesadas rodam sobre arquivos Parquet/Delta via DuckDB sem onerar o PostgreSQL operacional.
- Ausência de dependências pesadas: todo o pipeline opera em Python com `deltalake`, sem exigência de runtime Java, cluster Spark ou brokers como Kafka.
- Idempotência ponta a ponta: reexecuções em lote e reentregas de eventos CDC não geram duplicatas graças às guardas de `id_foco` e `lsn_origem`.
- Roteamento correto de dados atrasados: focos históricos recebidos fora de ordem temporal são alocados diretamente em suas respectivas partições de ano e mês.

**O que perdemos:**

- O CDC requer monitoramento do slot de replicação no PostgreSQL para evitar retenção de WAL caso o consumidor permaneça inativo.
- A biblioteca `deltalake` (delta-rs) não possui suporte a catálogos centralizados de múltiplos motores como o ecossistema Iceberg oferece.

**O que se torna irreversível:**

- A camada analítica passa a depender da estrutura de logs de transação do Delta Lake (`_delta_log/`). A substituição futura por Apache Iceberg demandará ferramentas de conversão de metadados ou reescrita dos dados físicos.

## Gatilho de revisão

Esta decisão será revisada caso:

1. O volume de detecções de focos de calor exija ingestão contínua em tempo real (subminuto), tornando o lote insuficiente.
2. O catálogo de tabelas analíticas precise ser compartilhado concorrentemente por múltiplos motores distribuídos em nuvem, momento em que o Apache Iceberg com catálogo REST deverá ser reavaliado.

