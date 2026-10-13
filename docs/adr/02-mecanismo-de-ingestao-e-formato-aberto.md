# 0002. Mecanismo de ingestão e formato aberto de tabela

- **Status:** Em Análise
- **Data:** 2026-10-13
- **Decisores:** Cláudio H., Elias F., Gabriel F., Gabriel S., João V., Manoel F., Samuel R.

## Contexto

O projeto Corta-Fogo DF consolida dois fluxos de dados com características operacionais e taxas de mutação distintas:

1. **Ocorrências de calor do [BDQueimadas (INPE)](../glossario.md#bdqueimadas-inpe):** série temporal contínua com detecções orbitais no Distrito Federal (38.945 focos entre 2015 e 2025). As linhas são imutáveis (apenas inserção no OLTP protegida por trigger), mas eventos de datas anteriores podem ser disponibilizados em remessas posteriores (dados atrasados ou *late-arriving data*).
2. **Cadastros territoriais do [SICAR](../glossario.md#sicar-car-sistema-nacional-de-cadastro-ambiental-rural) e do IBRAM/SISDIA:** malhas fundiárias e áreas protegidas (21.047 imóveis rurais, 13.499 reservas legais, 2.234 áreas de preservação permanente e 84 unidades de conservação). No sistema de origem, `imovel_car` é a tabela cadastral sujeita a inserções, retificações de área/condição e cancelamentos de registro (operações de `INSERT`, `UPDATE` e `DELETE`).

Na Entrega 1, essas bases foram estruturadas no PostgreSQL 16 com extensão PostGIS 3.4 ([ADR 0001](01-adotar-postgresql-com-postgis-camada-gold.md)), que valida regras topológicas e chaves relacionais. Executar consultas analíticas espaciais pesadas diretamente no PostgreSQL consome CPU, I/O e conexões do banco operacional.

A equipe precisa definir dois pontos arquiteturais para a Entrega 2:

- O mecanismo de propagação e sincronização dos dados do sistema de origem para o ambiente analítico desacoplado.
- O formato aberto de armazenamento colunar para persistência no lakehouse, permitindo consultas analíticas velozes via [DuckDB](../glossario.md#duckdb) sem dependência de um servidor de banco dedicado ou cluster distribuído.

## Alternativas de ingestão consideradas

### A. Opção nula: Ingestão agendada no PostgreSQL via scripts SQL ou pg_cron

Manter todo o processamento analítico dentro do próprio PostgreSQL, agendando rotinas de cópia periódica (`INSERT ... SELECT`), visões materializadas ou scripts SQL executados via extensão `pg_cron` ou cron do sistema operacional.

- **O que oferece:** dispensa ferramentas externas de pipeline, mantém toda a lógica em comandos SQL e utiliza a infraestrutura de banco de dados já instalada.
- **O que cobra:** consome recursos de CPU, memória e subsistema de I/O da mesma instância utilizada pelo sistema transacional durante as rotinas de agregação. Mantém os dados presos na estrutura relacional em páginas de 8 KB do PostgreSQL, sem gerar arquivos colunares abertos para processamento analítico desacoplado. Não oferece suporte nativo a versionamento temporal aberto (*time-travel*) nem compressão colunar avançada.

### B. Captura de mudanças de dados (CDC) via decodificação lógica do WAL

Configurar a leitura contínua do log de transações do PostgreSQL (Write-Ahead Log - WAL) com nível lógico (`wal_level=logical`), extraindo eventos linha a linha por meio de slots de replicação com plugins de decodificação (`test_decoding`) para atualizar a camada analítica aberta.

- **O que oferece:** propaga modificações cadastrais com latência na escala de milissegundos (~31 ms), captura operações DML (`INSERT`, `UPDATE` e `DELETE`) sem sobrecarregar o banco com consultas de varredura periódica e registra a ordem exata das transações por meio do Log Sequence Number (LSN) de 64 bits.
- **O que cobra:** exige gerenciar slots de replicação lógica no PostgreSQL. Se o processo consumidor falhar ou ficar inativo por período prolongado, o banco retém os arquivos de WAL no disco até o limite configurado (`max_slot_wal_keep_size=2GB`), sob risco de esgotar o armazenamento da instância operacional (`pgdata`).

### C. Ingestão periódica em lote (Batch)

Executar scripts programados em Python que extraem dados das fontes públicas (INPE) ou processam arquivos em janelas temporais definidas, aplicando regras de limpeza, particionamento temporal e deduplicação no momento da escrita.

- **O que oferece:** arquitetura simples e robusta sem processos residentes em segundo plano, sem sockets abertos contínuos ou filas de mensageria. Alinha o processamento à periodicidade das publicações públicas de satélite. Permite controle determinístico de idempotência e roteamento automático de registros atrasados (*late-arriving data*) para suas respectivas partições físicas.
- **O que cobra:** a latência de atualização fica vinculada ao intervalo de disparo do agendador (minutos ou horas). Exige controle explícito de deduplicação entre execuções para evitar inserção de registros duplicados em períodos já consolidados.

## Comparação de formatos abertos de tabela

Para o armazenamento analítico colunar (lakehouse), avaliamos duas especificações de tabela aberta baseadas em Apache Parquet:

### Delta Lake

Especificação aberta de tabela com controle transacional ACID, versionamento de dados e log de operações mantido no diretório `_delta_log/` em formato JSON e checkpoints compactados.

- **O que oferece:** biblioteca nativa em Python (`deltalake`, desenvolvida em Rust pelo projeto delta-rs) que lê e grava tabelas Delta diretamente com PyArrow e Pandas, sem necessidade de JVM ou cluster Apache Spark. Suporta nativamente operações de `MERGE INTO`, evolução controlada de esquema, particionamento em diretórios padrão Hive (`ano=YYYY/mes=MM/`) e integração com ferramentas de consulta colunar como DuckDB via extensão `delta_scan`.
- **O que cobra:** o ecossistema delta-rs implementa um subconjunto da especificação do Delta Lake do ecossistema Spark (sem suporte nativo a catálogos centralizados complexos fora do ecossistema Databricks/Unity), embora cubra plenamente escrita em lote, `MERGE`, deleção lógica e histórico de commits ACID para ambientes locais e conteinerizados.

### Apache Iceberg

Especificação de tabela aberta voltada para grandes volumes analíticos, com controle de metadados em camadas (arquivos de metadados JSON, listas de manifestos e arquivos de manifesto individuais).

- **O que oferece:** abstração completa de particionamento (particionamento oculto, sem expor colunas artificiais na consulta), evolução de esquema sem reescrita de dados e isolamento transacional estrito.
- **O que cobra:** requer obrigatoriamente um serviço de catálogo de metadados externo ativo (REST Catalog, Apache Polaris, Nessie, JDBC ou Hive Metastore) para registrar commits concorrentes com segurança. A biblioteca Python oficial (PyIceberg) apresenta menor maturidade para operações avançadas de escrita transacional com mesclagem espacial (`MERGE`) e exigiria contêineres adicionais de catálogo na composição do Docker Compose, elevando a complexidade operacional da equipe.

## Critérios de avaliação

A decisão entre os mecanismos de ingestão e os formatos abertos considera cinco critérios técnicos:

1. **Latência de propagação:** intervalo de tempo entre o commit na origem e a sua disponibilidade para consulta na camada analítica.
2. **Custo operacional:** quantidade de serviços adicionais no ambiente (contêineres, brokers de mensageria, JVM, catálogo de metadados) e esforço de manutenção contínua.
3. **Impacto no OLTP:** nível de interferência da rotina de extração sobre os recursos do PostgreSQL operacional (consumo de CPU, I/O de disco, concorrência de travas e retenção de WAL).
4. **Complexidade de schema evolution:** esforço necessário para adicionar ou evoluir colunas nas tabelas analíticas sem corromper partições históricas ou exigir reprocessamento total.
5. **Tolerância a falhas e idempotência:** capacidade de recuperar execuções interrompidas, reprocessar remessas duplicadas e absorver dados fora de ordem temporal (*late-arriving data*) sem gerar duplicatas.

---

## Medição Empírica

Todas as métricas apresentadas nesta seção foram colhidas com scripts automatizados reproduzíveis no repositório, utilizando dados reais do Distrito Federal (38.945 focos do INPE e 21.047 imóveis do CAR).

### 1. Benchmark de Latência Comparativa: CDC vs Lote vs Opção Nula

Script de reprodução: [`scripts/benchmark/benchmark_ingestao.py`](https://github.com/BeyondMagic/corta-fogo-df/blob/main/scripts/benchmark/benchmark_ingestao.py)  
Relatório estruturado: [`scripts/benchmark/resultados_latencia.md`](https://github.com/BeyondMagic/corta-fogo-df/blob/main/scripts/benchmark/resultados_latencia.md)

| Mecanismo de Ingestão | Latência de Propagação | Frequência Típica | Granularidade | Impacto no OLTP |
| :--- | :--- | :--- | :--- | :--- |
| **B. CDC (Decodificação Lógica)** | **~31,97 ms** | Contínua / Near-Real-Time | Por transação (tupla a tupla) | **Baixo:** leitura assíncrona do WAL via slot lógico nativo |
| **C. Lote (Delta Lake MERGE)** | **~52,69 ms (0,053 s)** | Agendada (Diária / Mensal) | Bloco temporal (`ano/mes`) | **Nulo:** processamento desacoplado fora do SGBD |
| **A. Opção Nula (In-database ELT)** | **~14,27 ms (0,014 s)** | Agendada via `pg_cron` / Trigger | Global ou relacional | **Alto:** disputa concorrência de CPU, lock e I/O com escrita |

#### Análise quantitativa da Opção Nula vs CDC
- **Onde a Opção Nula é viável:** em bancos com baixa concorrência de escrita, onde tabelas analíticas intermediárias ou visões materializadas podem ser recalculadas na madrugada sem impactar transações de usuários.
- **Onde a Opção Nula falha e justifica o CDC:** à medida que consultas espaciais e agregações de malha fundiária crescem, o comando `INSERT ... SELECT` concorre diretamente pelos buffers compartilhados (*shared_buffers*) e I/O de disco com os processos de carga. O conector CDC desacopla totalmente a camada analítica: a leitura de eventos ocorre sequencialmente no WAL em segundo plano, entregando latência de **31,97 ms** sem bloquear tabelas ou saturar o planejador relacional.

---

### 2. Benchmark de Compressão Colunar: Snappy vs ZSTD

Script de reprodução: [`scripts/benchmark/benchmark_compressao.py`](https://github.com/BeyondMagic/corta-fogo-df/blob/main/scripts/benchmark/benchmark_compressao.py)  
Relatório estruturado: [`scripts/benchmark/resultados_compressao.md`](https://github.com/BeyondMagic/corta-fogo-df/blob/main/scripts/benchmark/resultados_compressao.md)  
Amostra avaliada: partição real de focos de calor do DF (`ano=2024/mes=08`, 1.183 registros normalizados).

| Algoritmo de Compressão | Tamanho em Disco (MB) | Taxa de Redução vs Raw (%) | Tempo de Escrita (ms) | Query Agregada DuckDB (ms) |
| :--- | :--- | :--- | :--- | :--- |
| **UNCOMPRESSED** | 0,1439 MB | 43,93% | 2,17 ms | 2,783 ms |
| **SNAPPY** | 0,1359 MB | 47,04% | 2,13 ms | 2,535 ms |
| **ZSTD (Zstandard)** | **0,0918 MB** | **64,21%** | 2,80 ms | 2,906 ms |

#### Justificativa da escolha de compressão
- **Eficiência física:** o algoritmo **Zstandard (ZSTD)** proporcionou **taxa de redução de 64,21%** contra o formato bruto em memória, gerando arquivos **32,4% menores do que o Snappy** (0,0918 MB vs 0,1359 MB na partição).
- **Desempenho de leitura no DuckDB:** o tempo de resposta em consultas analíticas de agregação vetorizada (`COUNT(*)`, `AVG(risco_fogo)` agrupado por satélite) permaneceu estatisticamente idêntico entre ZSTD (2,90 ms) e Snappy (2,53 ms), com diferença inferior a 0,4 ms.
- **Conclusão:** para uma série histórica de 11 anos com 38.945 registros de satélite, a economia cumulativa de armazenamento viabilizada pelo ZSTD supera amplamente o custo desprezível de descompressão pelo DuckDB.

---

### 3. Validação de Semântica At-Least-Once e Reprocessamento Forçado

Script de validação: [`scripts/testes/test_reprocessamento_cdc.py`](https://github.com/BeyondMagic/corta-fogo-df/blob/main/scripts/testes/test_reprocessamento_cdc.py)

1. **Semântica At-Least-Once no CDC comprovada na prática:**
   - O teste simulou queda e reconexão do consumidor forçando o offset a recuar para um LSN anterior (`0/2000`), reenviando mutações já processadas e mutações desordenadas com LSN obsoleto (`0/800`).
   - A guarda de LSN no Delta Lake (`source.lsn_origem >= target.lsn_origem`) descartou 100% dos eventos obsoletos e evitou regresso de estado.
   - A unicidade de `cod_imovel` foi estritamente preservada (zero duplicações), confirmando que a semântica de entrega at-least-once com deduplicação no destino produz efeito observável de *processamento exatamente-uma-vez* (*effectively-once*).

2. **Idempotência no Lote:**
   - A reexecução do pipeline em lote sobre o mesmo conjunto anual de focos de calor processou 20 registros, inseriu exatamente 0 novos registros e ignorou 20 duplicatas via `MERGE ... WHEN NOT MATCHED INSERT`, mantendo a contagem total invariante.

3. **Divergência Estrutural em Cenário de Falha:**
   - **Falha no Lote:** isolada à partição/job em execução. Custo no OLTP é nulo. A recuperação consiste na simples reexecução pontual do job idempotente.
   - **Falha no CDC:** cumulativa no stream. O PostgreSQL retém arquivos de WAL no diretório `pgdata` enquanto o slot `cdc_imovel` não avançar seu `confirmed_flush_lsn`. Exige monitoramento ativo para evitar esgotamento de disco antes de atingir `max_slot_wal_keep_size`.

---

## Decisão

Adotamos formalmente uma **arquitetura híbrida de ingestão** associada ao formato aberto **Delta Lake**:

1. **Ingestão em Lote (Batch) para `foco_calor`:**
   - Executada por [`src/pipeline/batch_ingest.py`](https://github.com/BeyondMagic/corta-fogo-df/blob/main/src/pipeline/batch_ingest.py).
   - Armazenada em `data/delta/foco_calor` com particionamento temporal `ano=YYYY/mes=MM/` baseado em `data_hora_evento` (UTC).
   - Idempotência assegurada por chave primária sintética `id_foco` (SHA-256 de coordenadas, timestamp e satélite) via operação `MERGE INTO`.

2. **Captura de Mudanças (CDC) para `imovel_car`:**
   - Executada por [`src/pipeline/cdc_consumer.py`](https://github.com/BeyondMagic/corta-fogo-df/blob/main/src/pipeline/cdc_consumer.py).
   - Consome continuamente alterações do slot lógico nativo `cdc_imovel` com plugin `test_decoding`, sem brokers externos (sem Kafka) e sem dependência de JVM.
   - Armazenada em `data/delta/imovel_car` sem particionamento (dimensão cadastral leve).
   - Regra de `MERGE` orientada por `cod_imovel` e guarda estrita `source.lsn_origem >= target.lsn_origem`.
   - Suporte a soft-delete (`operacao_cdc='D'`) e preservação de geometrias TOAST (`unchanged-toast-datum`).

3. **Formato Aberto de Tabela e Compressão:**
   - **Delta Lake** gerenciado via biblioteca `deltalake` (delta-rs).
   - Compressão colunar **Zstandard (ZSTD)** recomendada para dados históricos consolidados, admitindo Snappy como formato padrão Parquet.
   - Leitura analítica direta vetorizada via **DuckDB** (`delta_scan`).

---

## Consequências

**O que ganhamos:**

- **Isolamento de Carga:** cruzamentos espaciais analíticos e consultas temporais pesadas rodam no DuckDB sobre arquivos colunares sem onerar a CPU ou as transações do PostgreSQL operacional.
- **Stack Leve e Autocontida:** todo o ciclo de ingestão e consumo opera em contêineres Python leves via `deltalake` e `psycopg2`, sem necessidade de Spark, Hadoop, JVM ou brokers de mensagens.
- **Idempotência e Tolerância a Falhas:** reprocessamentos de arquivos em lote e retransmissões de eventos CDC no modelo At-Least-Once não corrompem o estado nem duplicam registros na camada analítica.
- **Roteamento Automático de Dados Atrasados:** focos de satélite antigos recebidos em lotes recentes são alocados deterministicamente em suas partições históricas de ano e mês sem exigir regravação das partições vigentes.
- **Economia Volumétrica:** compressão colunar com redução superior a 64% em relação aos dados brutos em memória.

**O que perdemos:**

- **Gestão de Slots WAL:** o consumidor CDC precisa permanecer em execução para drenar o slot de replicação, exigindo governança para que o PostgreSQL não acumule arquivos WAL no volume `pgdata`.
- **Limitações do ecossistema delta-rs:** recursos avançados da especificação completa do Spark (como catálogos federados centralizados Unity/Hive) não estão presentes, sendo suficiente para o escopo local/conteinerizado do projeto.

**O que se torna irreversível:**

- A camada analítica passa a depender da especificação do Delta Lake e de seus logs de transação ACID no diretório `_delta_log/`. Substituir o formato por Apache Iceberg no futuro exigirá ferramentas de conversão de metadados ou reingestão integral dos dados físicos.

---

## Gatilho de revisão

Esta decisão será revisada caso:

1. O volume de detecções de focos de calor exija ingestão contínua em tempo real (subminuto com streaming direto de satélites), tornando a janela em lote insuficiente.
2. A organização exija governança distribuída com catálogo de metadados corporativo multi-motor (ex: Trino, Spark, Flink e DuckDB operando simultaneamente em nuvem), momento em que o **Apache Iceberg com catálogo REST** deverá ser reavaliado.
3. O volume retido de WAL no PostgreSQL atinja frequentemente o patamar de alerta (`max_slot_wal_keep_size`), exigindo migração para ferramenta externa de captura como Debezium com Kafka intermediário.
