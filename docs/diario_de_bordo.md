---
icon: material/calendar-clock
---

# :material-calendar-clock: Diário de Bordo

Registro cronológico reverso das atividades, decisões técnicas, entregas e marcos executados pela equipe do projeto Corta-Fogo DF, ordenado da semana mais recente até o início dos ciclos de desenvolvimento.

---

## 1. Entrega 4: Disponibilização, Arquitetura, Metodologia e Painel Operacional

A etapa final consolidou a arquitetura de consumo estático ([ADR 0004](adr/04-disponibilizacao-contrato-dbt-e-retrato-estatico.md)), a visualização interativa de linhagem de dados, a documentação metodológica e a revisão de usabilidade do dashboard operacional ([`docs/entrega/04/README.md`](entrega/04/README.md)).

### Semanas 15 e 16 (14/11 a 21/11/2026): Contrato de Consumo, Usabilidade do Painel e Fechamento

- **Arquitetura e Linhagem (`Gabriel Souza` e `Manoel Felipe`):** substituição do diagrama Mermaid estático por componente interativo em colunas com rastreamento upstream/downstream e busca de modelos (`docs/javascripts/arquitetura_diagrama.js`), compartilhado via snippet entre Entrega 3, Entrega 4, Metodologia e Esquema Gold.
- **Metodologia (`Elias F.` e `Gabriel Fernando`):** reorganização da nota metodológica para página dedicada ([Metodologia](metodologia.md)), separando explicações conceituais e fontes da interface operacional do painel.
- **Dashboard Operacional (`Samuel Ribeiro` e `João V. Farias`):** redesenho do [Dashboard](dashboard.md) para abrir diretamente com a pergunta, resposta e mapas, filtros abaixo do palco espacial, remoção de termos de infraestrutura da tela, seletores por checkbox na fila de vistoria (5 primeiros marcados por padrão) e correções de interação/zoom no Leaflet e no filtro de camadas.
- **ADRs e Fechamento do Portfólio (`João V. Farias`):** renumeração do Índice de Prioridade de Vistoria para [ADR 0005](adr/05-indice-de-prioridade-de-vistoria.md), fechamento do [ADR 0004](adr/04-disponibilizacao-contrato-dbt-e-retrato-estatico.md) com medições reproduzíveis em `scripts/benchmark/benchmark_disponibilizacao.py` e atualização do [Dicionário de Dados](dicionario_dados.md) com `dim_regiao_administrativa`, `fct_reincidencia_imovel`, `painel_imoveis_prioritarios` e `gold.json`.
- **Governança, SLA de Frescor e Reprodutibilidade (`Cláudio Henrique`):** consolidação da checagem horária do SLA de `30 h` no Dagster (`frescor_sla`), reprodutibilidade do ambiente conteinerizado em máquina limpa e registro dos limites em aberto da E4.

### Retrospectiva do Ciclo de Vida (E1 a E4)

- **Gatilho de revisão acionado:** na E1, o [ADR 0001](adr/01-adotar-postgresql-com-postgis-camada-gold.md) previu revisão caso consultas analíticas passassem de `5 s`. O join espacial bruto em `41,8 s` (e `4,6 s` na MV `V7`) disparou a transição planejada para Delta Lake + DuckDB (`5,0 ms` na tabela de consumo Gold e `187,0 KB` em `gold.json`).
- **O que sustentou a reprodutibilidade:** pipeline conteinerizado em perfis do `docker-compose.yml`, chaves substitutas determinísticas em MD5/SHA-256 sem dependência de sequência, 189 nós aprovados no `dbt build` (incluindo testes sazonais/espaciais contra erros silenciosos e reconciliação contra a MV do PostGIS) e verificação horária de frescor no Dagster.
- **Limites assumidos ao fim da E4:** não foram implementadas gravação reversa automatizada em tabela transacional do PostgreSQL nem políticas de controle de acesso `ROLE`/RLS no warehouse, e o recorte de polígonos do mapa estático cobre os 50 primeiros imóveis priorizados pelo IPV. Esses pontos estão documentados com limiares claros nos gatilhos do [ADR 0004](adr/04-disponibilizacao-contrato-dbt-e-retrato-estatico.md).

---

## 2. Entrega 3: Modelagem Dimensional, Transformação e Orquestração

O ciclo da Entrega 3 (Semanas 11 a 14) transformou a plataforma em uma estrutura analítica de consumo com modelo dimensional em estrela, histórico cadastral em SCD Tipo 2, transformações declarativas no dbt-duckdb, testes de dados focados em erros silenciosos, orquestração com Dagster e exploração geoespacial interativa.

```
Semanas 13 e 14 (03/11 a 11/11/2026): Testes, Orquestração, Mapa e Consolidação
Semanas 11 e 12 (19/10 a 02/11/2026): Modelagem Dimensional, Camadas dbt e SCD2
```

---

### Semanas 13 e 14 (03/11 a 11/11/2026): Validação, Orquestração, Painel e Entrega

Etapa final da Entrega 3, dedicada à integração entre o dbt e o Dagster, execução real de testes de resiliência e backfill, desenvolvimento do mapa interativo e redação do relatório consolidado.

#### Issue #17: Coordenação Geral e Pergunta de Gestão
- **Responsável:** Gabriel Souza
- **Link da Issue:** [#17](https://github.com/BeyondMagic/corta-fogo-df/issues/17)
- **Atividades executadas:**
  - Coordenação das frentes de trabalho da equipe e validação cruzada entre os modelos do dbt e a consulta analítica final.
  - Redação do relatório consolidado da Entrega 3 ([`docs/entrega/03/README.md`](entrega/03/README.md)), cobrindo linhagem ponta a ponta, resultados da pergunta de gestão e comparativo de desempenho.
  - Auditoria dos 8 critérios do checklist oficial da disciplina contra o repositório e execução completa do pipeline em 10/11/2026.
  - Apuração do resultado central: 1.593 imóveis rurais reincidentes em áreas protegidas no DF entre 2015 e 2025, concentrando 37.692 focos (96,8% de todos os focos no território distrital).

#### Issue #22: Orquestração com Dagster (Retry e Backfill)
- **Responsável:** Cláudio Henrique
- **Link da Issue:** [#22](https://github.com/BeyondMagic/corta-fogo-df/issues/22)
- **Atividades executadas:**
  - Configuração do Dagster via Docker Compose no perfil `orquestracao` sem dependência de JVM, lendo o manifesto do dbt para instanciar ativos gerenciados por software (*Software-Defined Assets*).
  - Configuração do agendamento diário (`job_transformacao` às 03:00 em fuso de Brasília) e do job de carga particionado mensal (`job_lote_mensal` em 132 partições históricas).
  - Implementação de política de retentativas (`RetryPolicy`) com até 3 tentativas e recuo exponencial, exercitada em 10/11/2026 com falhas induzidas (`FALHAS_INDUZIDAS=3`) recuperadas na quarta execução.
  - Execução de backfill real via [`orquestracao/demo_backfill.py`](https://github.com/BeyondMagic/corta-fogo-df/blob/main/orquestracao/demo_backfill.py), simulando a perda intencional da partição `2024-09` (queda de 3.079 linhas) e sua recomposição idempotente via MERGE, restaurando as 38.944 linhas originais sem duplicidades.

#### Issue #21: Testes de Dados e Detecção de Erros Silenciosos
- **Responsável:** Elias F.
- **Link da Issue:** [#21](https://github.com/BeyondMagic/corta-fogo-df/issues/21)
- **Atividades executadas:**
  - Implementação de bateria com 173 testes de dados e 1 teste unitário no projeto dbt-duckdb, atingindo 189 de 189 nós aprovados no `dbt build`.
  - Configuração de testes estruturais de chave e nulidade (126 `not_null`, 13 `unique`, 4 `unique_combination_of_columns`, 16 `accepted_values` e 8 `relationships`).
  - Criação de 3 testes singulares em SQL projetados especificamente para capturar erros silenciosos de domínio:
    - *Volume anual:* valida se todo ano entre 2015 e 2025 possui ao menos 500 focos totais e 80 do sensor de referência (medido: menor ano foi 2018 com 948 focos e 88 de referência).
    - *Distribuição sazonal:* valida se a concentração de fogo no período de estiagem (maio a setembro) atinge pelo menos 70% da série (medido: 84,4% no total; pior ano foi 2020 com 70,1%).
    - *Distribuição espacial:* valida se 100% das coordenadas e geometrias situam-se no quadrilátero geográfico do DF com topologia válida.

#### Issue #23: Decisão de Arquitetura (ADR 0003) e Dashboard Interativo
- **Responsável:** João V. Farias
- **Link da Issue:** [#23](https://github.com/BeyondMagic/corta-fogo-df/issues/23)
- **Atividades executadas:**
  - Redação da Decisão Arquitetural [ADR 0003](adr/03-modelagem-dimensional-e-ferramenta-de-transformacao.md), comparando o modelo estrela contra alternativas (OBT e Data Vault) e dbt-duckdb com Dagster contra opções nulas (cron com SQL) e pesadas (SQLMesh/Airflow).
  - Medição de ganhos de desempenho: cálculo do mart em 9,9 s no dbt e leitura da pergunta final em 5,0 ms no DuckDB, contra 41,8 s da junção espacial direta no PostGIS.
  - Desenvolvimento do [Dashboard do DF](dashboard.md) em D3.js (`d3-geo`) e Leaflet com linha do tempo de 11 anos (2015 a 2025), filtros cruzados e inspeção de UCs, RAs e imóveis CAR.
  - Implementação de polígonos reais das 84 Unidades de Conservação oficiais (SISDIA/IBRAM), camada independente de buffer métrico de 1.000 m (EPSG:31983) e polígonos cadastrais sob demanda para os 10 imóveis com maior histórico de fogo no CAR.
  - Mapeamento da pegada espacial do sensor orbital (VIIRS 375 m, MODIS 1 km, GOES 2 km e AVHRR 1.1 km) e integração do modo tela cheia.

---

### Semanas 11 e 12 (19/10 a 02/11/2026): Modelagem Dimensional, Camadas dbt e SCD2

Fase inicial da Entrega 3, focada em desenhar o esquema analítico, configurar o motor colunar DuckDB e isolar a camada de processamento analítico do banco operacional.

#### Issue #20: Projeto dbt-duckdb, Staging e Camada Intermediate
- **Responsável:** Gabriel Fernando
- **Link da Issue:** [#20](https://github.com/BeyondMagic/corta-fogo-df/issues/20)
- **Atividades executadas:**
  - Estruturação do projeto dbt com o adaptador `dbt-duckdb`, conectando as tabelas Delta Lake da E2 via `delta_scan` e anexando o PostGIS em modo estritamente somente leitura.
  - Criação dos 5 modelos de staging (`stg_focos_calor`, `stg_imoveis_car`, `stg_unidades_conservacao`, `stg_areas_preservacao_permanente` e `stg_reservas_legais`).
  - Implementação da camada intermediate com cruzamentos espaciais métricos:
    - `int_focos_imoveis`: resolve a relação N:N de imóveis sobrepostos no SICAR, gerando 76.115 pares foco-imóvel a partir dos 38.944 focos atômicos.
    - `int_focos_areas_protegidas`: identifica focos incidentes em Reserva Legal (`ST_Intersects`), APP (`ST_Intersects`) ou faixa de amortecimento de 1.000 m de UCs (`ST_DWithin`), totalizando 32.778 ocorrências protegidas.
    - `int_focos_territorio`: agrega as flags espaciais em nível atômico de foco para alimentar a tabela fato.

#### Issue #18: Modelagem Dimensional Gold e Esquema Estrela
- **Responsável:** Manoel Felipe
- **Link da Issue:** [#18](https://github.com/BeyondMagic/corta-fogo-df/issues/18)
- **Atividades executadas:**
  - Projeto e implementação do esquema estrela com granularidades declaradas por extenso na documentação ([`docs/modelagem/esquema_dimensional_gold.md`](modelagem/esquema_dimensional_gold.md)).
  - Construção da dimensão calendário `dim_tempo` (4.018 dias de 2015 a 2025 com o atributo `is_estacao_seca`).
  - Construção da dimensão `dim_satelite` (20 sensores orbitais com flag `is_referencia` para o AQUA_M-T).
  - Construção da dimensão unificada de feições protegidas `dim_territorio` (15.814 feições com chaves substitutas estáveis geradas via MD5 de tipo e geometria WKT).
  - Construção da tabela fato atômica `fato_foco_calor` (38.944 linhas) e do mart consolidado `mart_reincidencia_imovel_ano` (8.271 linhas no grão imóvel por ano).

#### Issue #19: Dimensão de Variação Lenta (SCD Tipo 2) para Imóveis Rurais
- **Responsável:** Samuel Ribeiro
- **Link da Issue:** [#19](https://github.com/BeyondMagic/corta-fogo-df/issues/19)
- **Atividades executadas:**
  - Modelagem do mecanismo de controle histórico para retificações de área, mudanças de perímetro e cancelamentos de cadastros no SICAR, evitando sobrescrita de dados históricos.
  - Implementação do snapshot dbt [`transformacao/snapshots/snp_imovel_car.yml`](https://github.com/BeyondMagic/corta-fogo-df/blob/main/transformacao/snapshots/snp_imovel_car.yml) com estratégia `timestamp` sobre `data_hora_ingestao`.
  - Construção do modelo `dim_imovel_car`, gerando chave substituta de versão `sk_imovel = md5(cod_imovel || lsn_origem)` para descartar reentregas repetidas do CDC.
  - Definição do intervalo de vigência temporal aberta (`dbt_valid_from <= data_hora_evento < dbt_valid_to`), associando cada foco histórico à versão cadastral vigente no dia exato do evento.
  - Criação do teste unitário `dim_imovel_car_preserva_versao_anterior_para_focos_antigos` e do script demonstrativo [`orquestracao/demo_scd2_imovel.py`](https://github.com/BeyondMagic/corta-fogo-df/blob/main/orquestracao/demo_scd2_imovel.py).

---

## 3. Entrega 2: Ingestão em Formato Aberto, Lakehouse e CDC

O ciclo da Entrega 2 (Semanas 7 a 10) estabeleceu o armazenamento analítico em Delta Lake desacoplado do banco de dados relacional, implementou a ingestão em lote idempotente de dados climáticos e construiu o consumidor de Change Data Capture para dados cadastrais mutáveis.

---

### Semana 10 (10/10 a 11/10/2026): Captura Contínua de Mudanças e Resiliência CDC

A décima semana focou na captura contínua de mudanças cadastrais no SICAR e na validação da resiliência do pipeline contra falhas de rede e reprocessamento.

- **10/10/2026:** finalização do consumidor CDC [`src/pipeline/cdc_consumer.py`](https://github.com/BeyondMagic/corta-fogo-df/blob/main/src/pipeline/cdc_consumer.py), capaz de realizar a carga inicial de snapshot e passar a consumir o slot de replicação lógica de forma ininterrupta.
- **10/10/2026:** criação do gerador de mutações [`scripts/cdc/gerar_mutacoes_oltp.py`](https://github.com/BeyondMagic/corta-fogo-df/blob/main/scripts/cdc/gerar_mutacoes_oltp.py) para simular inserções, retificações de área e cancelamentos no PostgreSQL, comprovando a propagação para a tabela Delta em tempo real.
- **11/10/2026:** implementação da suíte de resiliência em [`scripts/testes/test_reprocessamento_cdc.py`](https://github.com/BeyondMagic/corta-fogo-df/blob/main/scripts/testes/test_reprocessamento_cdc.py), forçando o recuo intencional do LSN confirmado para validar que reentregas de mensagens no log do PostgreSQL não geram duplicidades nem inconsistências no destino.
- **Decisões técnicas da semana:**
  - Exclusões cadastrais no banco operacional são registradas como exclusão lógica (*soft-delete*, `operacao_cdc='D'`) na tabela Delta, preservando o histórico para auditoria.
  - A confirmação de avanço do LSN (*flush LSN*) no PostgreSQL só é enviada após a confirmação de escrita em disco do lote Parquet/Delta, garantindo semântica de entrega *at-least-once* com deduplicação segura no destino.

---

### Semana 9 (05/10 a 09/10/2026): Lakehouse Delta e Ingestão em Lote de Focos

A nona semana estruturou as fundações do Lakehouse e o pipeline de ingestão da série histórica de focos de calor do INPE.

- **05/10/2026:** consolidação formal da arquitetura técnica da E2 e implementação do script de ingestão em lote [`src/pipeline/batch_ingest.py`](https://github.com/BeyondMagic/corta-fogo-df/blob/main/src/pipeline/batch_ingest.py), gravando os focos do BDQueimadas em arquivos Delta Lake particionados por ano e mês.
- **06/10/2026:** criação dos testes automatizados de idempotência e dados atrasados em [`scripts/testes/test_idempotencia_lote.py`](https://github.com/BeyondMagic/corta-fogo-df/blob/main/scripts/testes/test_idempotencia_lote.py).
- **09/10/2026:** configuração dos parâmetros de replicação lógica no `docker-compose.yml` para o PostgreSQL (`wal_level=logical`, criação do slot `cdc_imovel` e limite de 2 GB de retenção de WAL para prevenir esgotamento de disco).
- **Decisões técnicas da semana:**
  - Descarte do Apache Iceberg devido à sobrecarga de catálogo externo (Hive Metastore/REST) e dependência de máquina virtual Java (JVM); adoção do Delta Lake via biblioteca nativa `deltalake` (delta-rs).
  - Adoção da decodificação lógica nativa do PostgreSQL (`test_decoding`) acoplada via `psycopg2`, dispensando infraestruturas adicionais de mensageria como Apache Kafka e Debezium Server.
  - Particionamento temporal estrito por `ano=YYYY/mes=MM` calculado a partir de `data_hora_evento`, garantindo que registros de anos anteriores caiam em suas respectivas partições sem regravação dos arquivos recentes.

---

### Semanas 7 e 8 (23/09 a 30/09/2026): Planejamento da E2 e Refinamentos da E1

Ciclo de transição dedicado a incorporar os apontamentos da banca da Entrega 1 e planejar a estratégia arquitetural da Entrega 2.

- **Semana 7:** revisão da documentação e das tabelas da Entrega 1 com base no retorno da professora em sala; consolidação formal da declaração de histórico das camadas territoriais e calibração dos índices espaciais GiST no PostGIS.
- **Semana 8 (30/09/2026):** reunião geral de planejamento da Entrega 2 com a equipe completa:
  - Definição da divisão técnica entre lote e streaming: os focos de calor foram classificados como dados imutáveis de série temporal histórica (insert-only), sendo direcionados para ingestão em lote; os imóveis rurais foram classificados como cadastros mutáveis sujeitos a retificação administrativa, sendo selecionados como o objeto exclusivo do pipeline de CDC.
  - Distribuição das frentes de trabalho entre os integrantes para o desenvolvimento conteinerizado dos scripts e testes.

---

## 4. Matriz de Contribuições por Integrante

Resumo das frentes de liderança técnica assumidas por cada membro da equipe nas Entregas 2, 3 e 4:

| Integrante | Entrega 2 (Lakehouse e CDC) | Entrega 3 (Dimensional, dbt e Dagster) | Entrega 4 (Arquitetura, Metodologia e Painel) | Issue E3 |
| :--- | :--- | :--- | :--- | :---: |
| **Gabriel Souza** | Coordenação e Arquitetura | Coordenação, Pergunta de Gestão e Checklist | Arquitetura em Camadas | [#17](https://github.com/BeyondMagic/corta-fogo-df/issues/17) |
| **Manoel Felipe** | Modelagem da Tabela Aberta (Delta) | Modelagem Dimensional Gold e Granularidades | Arquitetura em Camadas | [#18](https://github.com/BeyondMagic/corta-fogo-df/issues/18) |
| **Samuel Ribeiro** | Mutações OLTP e Artefatos de Teste | Dimensão SCD Tipo 2 e Snapshot Cadastral | Dashboard Operacional | [#19](https://github.com/BeyondMagic/corta-fogo-df/issues/19) |
| **Gabriel Fernando** | Consumidor CDC e Replicação Lógica | Projeto dbt-duckdb, Staging e Intermediate | Metodologia | [#20](https://github.com/BeyondMagic/corta-fogo-df/issues/20) |
| **Elias F.** | Benchmarks e Semântica de Entrega | Testes de Dados e Detecção de Erros Silenciosos | Metodologia | [#21](https://github.com/BeyondMagic/corta-fogo-df/issues/21) |
| **Cláudio Henrique** | Infraestrutura e Suporte ao Lakehouse | Orquestração com Dagster, Retry e Backfill | Governança, SLA de Frescor e Reprodutibilidade | [#22](https://github.com/BeyondMagic/corta-fogo-df/issues/22) |
| **João V. Farias** | Ingestão em Lote e ADR 0002 | ADR 0003, Dashboard e Dicionário de Dados | Portfólio de ADRs (ADR 0004) e Dicionário | [#23](https://github.com/BeyondMagic/corta-fogo-df/issues/23) |
