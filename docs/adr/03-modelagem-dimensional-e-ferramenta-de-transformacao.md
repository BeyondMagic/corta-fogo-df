---
icon: material/database-cog
---

# :material-database-cog: 0003. Modelagem dimensional da camada analítica e ferramenta declarativa de transformação

- **Status:** Aceito
- **Data:** 2026-11-09
- **Decisores:** Cláudio H., Elias F., Gabriel F., Gabriel S., João V., Manoel F., Samuel R.

## Contexto

Nas etapas anteriores, estruturamos o banco transacional no PostgreSQL com PostGIS (ADR 0001) e estabelecemos o fluxo de ingestão para tabelas abertas Delta Lake em formato Parquet comprimido com Zstandard (ADR 0002). Esse desenho isolou a aplicação operacional do custo das varreduras colunares, mas deixou em aberto como organizar o dado para consumo analítico final.

Na Entrega 3, a plataforma precisa responder de forma definitiva à pergunta de gestão do projeto:

> Quais imóveis rurais do Distrito Federal tiveram focos de calor reincidentes em áreas de reserva legal, de preservação permanente ou a até 1 km de unidades de conservação entre 2015 e 2025?

Para responder a essa pergunta com reprodutibilidade e confiança, precisamos resolver dois problemas arquiteturais:

1. **Padrão de modelagem analítica:** definir a estrutura de tabelas, o grão da fato e o tratamento de alterações cadastrais históricas nos imóveis rurais.
2. **Ferramenta de transformação e orquestração:** selecionar a ferramenta para executar as transformações em camadas (staging, intermediate e marts), aplicar testes de qualidade automáticos e orquestrar as execuções com tolerância a falhas e reprocessamento histórico (*backfill*).

## Alternativas de modelagem analítica avaliadas

### A. Esquema Estrela com Fato Atômica e Data Mart Agregado (Alternativa Escolhida)

Organizar os dados em um modelo dimensional composto por uma tabela fato de granularidade fina (`fato_foco_calor`), quatro dimensões conformadas (`dim_tempo`, `dim_satelite`, `dim_territorio`, `dim_imovel_car`) e um data mart agregado (`mart_reincidencia_imovel_ano`).

- **Granularidade da fato atômica:** uma linha por detecção de foco de calor no tempo e no espaço por sensor orbital (`id_foco`).
- **Dimensão de variação lenta (SCD Tipo 2):** a dimensão `dim_imovel_car` registra o histórico de alterações cadastrais e retificações de área dos imóveis rurais via snapshots do dbt sobre as mutações capturadas pelo CDC, expondo chave substituta (`sk_imovel`), data de início (`dbt_valid_from`), data de fim (`dbt_valid_to`) e indicador de versão atual (`is_current`).
- **Data mart de gestão:** agrega os cruzamentos espaciais na granularidade de uma linha por imóvel rural por ano civil UTC em que houve foco em área protegida, calculando se o imóvel atingiu reincidência histórica (pelo menos 2 anos distintos entre 2015 e 2025).
- **O que oferece:** preserva o detalhe atômico de cada passagem de satélite, permitindo consultas flexíveis (como filtrar apenas o satélite de referência AQUA_M-T ou analisar sazonalidade diária), enquanto entrega uma tabela final enxuta e pré-calculada para os analistas de fiscalização.
- **O que cobra:** exige uma camada intermediária de junção espacial para resolver relacionamentos N:N entre focos e polígonos sobrepostos do CAR.

### B. Tabela Única Desnormalizada (One Big Table - OBT)

Consolidar todas as colunas de focos, satélites, dados cadastrais do CAR e feições territoriais em uma única tabela horizontalmente ampla e totalmente desnormalizada.

- **O que oferece:** simplifica as consultas dos usuários analíticos ao eliminar completamente a necessidade de operações de `JOIN`.
- **O que cobra:** explosão de armazenamento e inconsistência histórica. Como o DF possui polígonos de reserva legal e imóveis com até 54 mil vértices, replicar essas geometrias pesadas a cada detecção de foco multiplicaria o volume físico por ordens de grandeza. Além disso, se um imóvel for retificado no CAR, a atualização retroativa na OBT exigiria reescrever centenas de milhares de linhas passadas, violando a integridade temporal.

### C. Modelagem Data Vault 2.0 (Hubs, Links e Satellites)

Adotar a metodologia Data Vault, decompondo os dados em tabelas de chaves de negócio (Hubs), relacionamentos associativos (Links) e atributos descritivos temporais (Satellites).

- **O que oferece:** rastreabilidade completa e alta flexibilidade para sistemas com dezenas de fontes corporativas heterogêneas e esquemas que mudam com frequência imprevisível.
- **O que cobra:** complexidade estrutural excessiva para o escopo do projeto. O Corta-Fogo DF integra apenas duas fontes principais (INPE e SICAR/SISDIA) com esquemas estáveis e definidos em contrato. Implementar Data Vault adicionaria dezenas de tabelas intermediárias e consultas com múltiplos joins complexos, prejudicando o tempo de resposta sem trazer benefício proporcional.

## Alternativas de ferramenta de transformação e orquestração

### 1. Opção Nula: Scripts SQL agendados via cron do sistema operacional

Manter arquivos SQL com comandos `CREATE TABLE AS SELECT` ou `INSERT ... SELECT` executados periodicamente pelo cron do Linux.

- **O que oferece:** custo zero de dependências de software adicionais.
- **O que cobra:** ausência de linhagem de dados (*data lineage*), falta de testes de dados automatizados antes da publicação, impossibilidade de modularização em camadas e ausência de mecanismos nativos de reexecução (*retry*) e reprocessamento (*backfill*). Se um script falha no meio, o estado das tabelas fica corrompido ou inconsistente.

### 2. SQLMesh com Apache Airflow

Utilizar o SQLMesh como motor de transformação declarativa e o Apache Airflow como orquestrador corporativo de tarefas.

- **O que oferece:** ambientes virtuais de dados (*virtual data environments*) nativos no SQLMesh e agendamento robusto com rica interface gráfica no Airflow.
- **O que cobra:** alto consumo de infraestrutura local. O Apache Airflow exige múltiplos contêineres permanentes (webserver, scheduler, triggerer, metastore PostgreSQL dedicado), consumindo mais de 2 GB de memória RAM apenas para manter a infraestrutura de agendamento ativa, violando o princípio de execução leve e reprodutível da equipe.

### 3. dbt (com adapter dbt-duckdb) e Dagster (Alternativa Escolhida)

Adotar o `dbt-core` com o adapter `dbt-duckdb` para transformações declarativas em SQL modular, e o `Dagster` integrado via `dagster-dbt` para orquestração em grafo de dependências (*Software-Defined Assets*).

- **O que oferece:**
  - **Desempenho e simplicidade:** o `dbt-duckdb` lê diretamente as pastas Delta Lake e arquivos Parquet no volume local via `delta_scan` e consulta camadas do PostGIS em modo somente leitura sem exigir JVM ou clusters Spark.
  - **Camadas estruturadas:** organização limpa do pipeline em `staging`, `intermediate`, `snapshots` e `marts`.
  - **Suíte de testes de dados:** execução nativa de testes de unicidade, nulidade, integridade referencial, limites de volume e testes de distribuição estatística e espacial para prevenção de erros silenciosos.
  - **Orquestração visual com retry e backfill:** o Dagster mapeia os modelos do dbt como ativos de dados, provê interface gráfica da DAG, aplica políticas de reexecução automática (*RetryPolicy*) com recuo exponencial e permite executar backfills de partições temporais históricas sem duplicar registros.
- **O que cobra:** necessidade de configurar o perfil de conexão DuckDB e sincronizar o ciclo de snapshots com as cargas incrementais.

## Medições práticas e evidências do projeto

Para fundamentar as escolhas, realizamos medições empíricas com a totalidade dos dados do Distrito Federal (38.945 focos entre 2015 e 2025, 21.047 imóveis do CAR e 84 unidades de conservação):

| Critério de Avaliação | PostGIS Original (E1) | Opção Nula (Cron + SQL) | dbt-duckdb + Dagster (E3) |
| :--- | :---: | :---: | :---: |
| **Tempo de resposta da pergunta de gestão** | 41,8 s (join espacial bruto) | ~14 ms (tabela interna no OLTP) | **2,9 ms** (consulta colunar no DuckDB) |
| **Impacto no banco operacional (OLTP)** | Alto (concorrência de CPU e disco) | Alto (disputa locks e memória) | **Zero** (isolado em volume analítico) |
| **Preservação de histórico cadastral (SCD)** | Sobrescrita manual | Risco de perda retroativa | **Garantida** (SCD Tipo 2 via snapshots) |
| **Testes automáticos de qualidade** | Restrições `CHECK` relacionais | Nenhum teste automatizado | **Suíte completa** (esquema, volume, distribuição) |
| **Tolerância a falhas na execução** | Falha interrompe transação | Falha deixa dado truncado | **Recuperação automática** (RetryPolicy no Dagster) |
| **Reprocessamento histórico (Backfill)** | Manual via scripts SQL | Manual sujeito a duplicatas | **Determinístico** por partição temporal |

### Evidências da Modelagem Dimensional

1. **Volume físico e ausência de explosão geométrica:** a fato atômica `fato_foco_calor` armazena as 38.945 ocorrências com coordenadas pontuais em apenas 1,8 MB de Parquet comprimido com Zstandard. Adotar a alternativa OBT com replicação dos polígonos de Reserva Legal elevaria o tamanho para mais de 180 MB.
2. **Eficácia dos testes de distribuição:** o teste singular `fato_foco_calor_distribuicao_sazonal_seca.sql` validou que 84,3% dos focos concentram-se no período de seca do DF (maio a setembro), atendendo com folga ao limiar de segurança de 70% e garantindo que não ocorreram inversões de calendário ou trocas de hemisfério. O teste `fato_foco_calor_distribuicao_espacial_df.sql` comprovou 100% de conformidade espacial dentro do envelope do DF.
3. **Resiliência do histórico:** a execução do script `demo_scd2_imovel.py` no contêiner do Dagster demonstrou que a retificação cadastral de um imóvel rural gerou uma nova versão (`dbt_valid_from` atualizado e `is_current = true`), preservando a versão histórica válida para associar os focos que ocorreram nos anos anteriores à alteração.

## Decisão

Decidimos adotar:

1. **Modelagem Dimensional em Esquema Estrela:**
   - Fato atômica `fato_foco_calor` em granularidade fina (uma linha por detecção de foco no tempo e espaço por sensor orbital).
   - Dimensões conformadas `dim_tempo`, `dim_satelite`, `dim_territorio` e `dim_imovel_car`.
   - Dimensão de variação lenta SCD Tipo 2 para `dim_imovel_car` gerenciada por dbt snapshots sobre o histórico do CDC.
   - Data mart agregado `mart_reincidencia_imovel_ano` com granularidade declarada de uma linha por imóvel rural por ano civil, respondendo diretamente à pergunta de gestão com identificação de reincidência histórica.
2. **Ferramenta de Transformação e Testes:** `dbt` com adapter `dbt-duckdb`, materializando modelos em camadas lógicas (staging, intermediate e marts) e executando bateria automatizada de testes de dados.
3. **Orquestrador de Pipeline:** `Dagster` com biblioteca `dagster-dbt`, provisionado em serviço dedicado no Docker Compose, provendo DAG visual de ativos, política de retry com recuo exponencial e capacidade de backfill demonstrável.

## Consequências

### Positivas

- **Isolamento e desempenho:** consultas analíticas e painéis de fiscalização rodam em milissegundos no DuckDB sem consumir recursos do banco de dados operacional.
- **Rastreabilidade e governança:** cada métrica exposta no mart final possui linhagem declarada no dbt, desde a ingestão da fonte pública até o relatório final.
- **Detecção precoce de erros silenciosos:** a inclusão obrigatória de testes de volume histórico e distribuição sazonal/espacial barra automaticamente cargas corrompidas ou dados anômalos antes que afetem as decisões de fiscalização.
- **Histórico cadastral confiável:** o uso de SCD Tipo 2 impede que a retificação recente de uma fazenda altere retroativamente a constatação de infração ambiental ocorrida anos antes.

### Negativas e Limitações Assumidas

- **Dependência do ciclo de snapshots:** a granularidade temporal da dimensão de imóveis fica restrita à frequência de execução do comando `dbt snapshot` ou `dbt build`. Alterações múltiplas no mesmo imóvel entre duas execuções são consolidadas em uma única versão mais recente.
- **Coordenação entre contêineres:** exige sincronizar o compartilhamento dos volumes `lakehouse` e `warehouse` entre os serviços de CDC, dbt e Dagster no Docker Compose.

## Gatilhos de revisão

Esta decisão será revisada caso ocorra ao menos uma das seguintes condições:

1. O volume de dados analíticos ultrapassar 50 GB ou exigir processamento distribuído entre múltiplos nós de computação em nuvem, justificando a migração do DuckDB local para Apache Spark com catálogo Apache Iceberg REST.
2. O projeto passar a integrar mais de dez domínios de negócio descentralizados mantidos por equipes distintas e autônomas, justificando a transição da modelagem dimensional clássica para Data Mesh com contratos federados de dados.
3. O INPE disponibilizar interface de eventos em tempo real com latência inferior a 10 segundos, exigindo a substituição do processamento em micro-lotes do dbt por streaming contínuo com Apache Flink.
