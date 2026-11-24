---
icon: material/database-export
---

# :material-database-export: 0006. Ingestão seletiva no Delta Lake e leitura direta no PostGIS

- **Status:** Aceito
- **Data:** 2026-11-22
- **Decisores:** Cláudio H., Elias F., Gabriel F., Gabriel S., João V., Manoel F., Samuel R.

Decisão adicional, fora das cinco previstas no plano de ensino: complementa os ADRs [0002](02-mecanismo-de-ingestao-e-formato-aberto.md) e [0003](03-modelagem-dimensional-e-ferramenta-de-transformacao.md) na organização das fontes lidas pela camada analítica.

## Contexto

No [ADR 0001](01-adotar-postgresql-com-postgis-camada-gold.md), todas as tabelas do projeto foram carregadas no PostgreSQL com PostGIS, incluindo a visão materializada `gold.mv_imoveis_reincidentes_areas_protegidas` (migração `V7`). Nas etapas seguintes, o [ADR 0002](02-mecanismo-de-ingestao-e-formato-aberto.md) introduziu o Lakehouse em Delta Lake e o [ADR 0003](03-modelagem-dimensional-e-ferramenta-de-transformacao.md) levou a camada Gold dimensional para o `dbt-duckdb`.

Essa transição deixou duas escolhas arquiteturais implícitas no código:

1. **Quais tabelas replicar para o Delta Lake:** o PostgreSQL mantém 6 tabelas espaciais carregadas (`foco_calor`, `imovel_car`, `unidade_conservacao`, `area_preservacao_permanente`, `reserva_legal` e `regiao_administrativa`), com comportamentos distintos. Apenas `foco_calor` (38.944 linhas, série histórica crescente em lote) e `imovel_car` (21.047 linhas, cadastro sujeito a mutações via CDC) foram levadas para o Delta Lake. As outras 4 camadas territoriais têm volume pequeno e atualização eventual (84 UCs, 2.234 APPs, 13.499 reservas legais e 37 Regiões Administrativas).
2. **O que fazer com a camada Gold original no PostGIS:** mesmo após construir `gold.fct_reincidencia_imovel` e `gold.painel_imoveis_prioritarios` no DuckDB, a visão materializada `gold.mv_imoveis_reincidentes_areas_protegidas` foi mantida e otimizada no PostGIS (migração `V9`).

## Alternativas consideradas

### A. Replicar todas as 6 tabelas espaciais para o Delta Lake

Criar pipelines em lote ou CDC para exportar `unidade_conservacao`, `area_preservacao_permanente`, `reserva_legal` e `regiao_administrativa` para tabelas Delta Lake em `data/delta/`, deixando o `dbt-duckdb` ler exclusivamente Parquet local e removendo a MV do PostGIS.

- **O que oferece:** desacoplamento completo do `dbt build` em relação ao PostgreSQL (o build rodaria só sobre o volume `lakehouse`, sem conexão com o banco) e uma única implementação da camada Gold.
- **O que cobra:** 4 pipelines extras de ingestão, contratos de esquema, testes de idempotência e versionamento para tabelas de referência pequenas e quase estáticas. Também remove a referência independente no PostGIS usada para conferir os cruzamentos espaciais executados no DuckDB.

### B. Manter toda a camada Gold apenas no PostGIS

Abandonar a construção dos modelos finais no `dbt-duckdb` e usar o PostgreSQL com PostGIS para responder diretamente à pergunta de gestão e alimentar o consumo via visões materializadas SQL.

- **O que oferece:** elimina a convivência entre dois motores analíticos (PostGIS e DuckDB) e remove o volume `warehouse` do Compose.
- **O que cobra:** viola o isolamento do OLTP estabelecido nos ADRs 0002 e 0003, dificulta manter o histórico cadastral em SCD Tipo 2 sobre o CDC do Delta Lake e concentra varreduras analíticas e testes de qualidade no banco operacional.

### C. Ingestão seletiva no Delta Lake, leitura direta no PostGIS e MV Gold paralela (Escolhida)

Replicar para o Delta Lake apenas `foco_calor` (lote particionado) e `imovel_car` (CDC sobre o WAL). Ler as 4 camadas territoriais diretamente do PostGIS em modo somente leitura pela extensão `postgres` do DuckDB (`transformacao/profiles.yml`), e manter `gold.mv_imoveis_reincidentes_areas_protegidas` otimizada (`V9`) no PostGIS como linha de base de reconciliação.

- **O que oferece:** mantém o Lakehouse enxuto (2 tabelas Delta onde lote e CDC trazem ganho real), reaproveita o saneamento topológico (`ST_IsValid`) já garantido no PostGIS e fornece validação cruzada entre dois motores espaciais independentes (GEOS no PostGIS vs. DuckDB Spatial).
- **O que cobra:** acopla a execução do `dbt build` à disponibilidade do PostgreSQL e exige manter a regra da pergunta sincronizada entre [`V9__gold_consulta_otimizada.sql`](https://github.com/BeyondMagic/corta-fogo-df/blob/main/migrations/V9__gold_consulta_otimizada.sql) e [`int_focos_protegidos_imovel.sql`](https://github.com/BeyondMagic/corta-fogo-df/blob/main/transformacao/models/intermediate/int_focos_protegidos_imovel.sql).

## Evidências e medições

Medições registradas na carga completa de 14/11/2026 com a totalidade dos dados do DF:

| Aspecto | Medição real | Origem |
| :--- | :--- | :--- |
| **Volume das 4 camadas lidas do PostGIS** | 84 UCs, 2.234 APPs, 13.499 RLs, 37 RAs (15.854 feições no total) | [Entrega 1](../entrega/01/README.md#3-volumetria-real-do-distrito-federal) e `V8` |
| **Tempo do `dbt build` completo** | 14,3 s (18 tabelas, 6 views, 1 snapshot, 259 testes + 1 teste unitário) | [Entrega 3, seção 5](../entrega/03/README.md#5-transformacoes-declarativas-no-dbt-duckdb) |
| **Desempenho da MV no PostGIS (`V7` vs. `V9`)** | 4.656 ms -> 2.482 ms; ordenação em disco de 68,5 MB -> 2,9 MB (`REFRESH` total em 3,8 s) | [`docs/explain/`](https://github.com/BeyondMagic/corta-fogo-df/tree/main/docs/explain) |
| **Reconciliação entre os dois motores** | 0 divergências nos 1.593 imóveis reincidentes (mesmos anos, focos e critérios RL/APP/UC) | [`reconcilia_fato_imovel_com_mv_postgis.sql`](https://github.com/BeyondMagic/corta-fogo-df/blob/main/transformacao/tests/reconcilia_fato_imovel_com_mv_postgis.sql) |

A leitura das 4 camadas territoriais via `ATTACH ... (TYPE postgres, READ_ONLY)` no DuckDB não gera escrita nem bloqueio nas tabelas do PostGIS.

## Decisão

1. **Delta Lake seletivo:** manter apenas `foco_calor` (lote particionado por `ano/mes`) e `imovel_car` (CDC) em `data/delta/`, conforme [esquema da tabela aberta](../modelagem/esquema_tabela_aberta.md).
2. **Leitura direta somente leitura no PostGIS:** anexar `unidade_conservacao`, `area_preservacao_permanente`, `reserva_legal` e `regiao_administrativa` diretamente no `dbt-duckdb` via extensão `postgres` em modo `READ_ONLY` (`transformacao/profiles.yml`).
3. **Manutenção da MV Gold no PostGIS:** conservar `gold.mv_imoveis_reincidentes_areas_protegidas` (`V9`) como implementação independente no banco operacional, usada para o benchmark `EXPLAIN (ANALYZE, BUFFERS)` e para o teste automatizado `reconcilia_fato_imovel_com_mv_postgis` (severidade `warn`, pois a MV reflete o último `REFRESH` enquanto o fato no DuckDB reflete o estado SCD Tipo 2 vigente na data de cada foco).
4. **Fonte única do consumo analítico:** o [Dashboard](../dashboard.md), o contrato `gold.json` ([ADR 0004](04-disponibilizacao-contrato-dbt-e-retrato-estatico.md)) e o [SLA de frescor](../frescor_sla.md) consomem exclusivamente `gold.painel_imoveis_prioritarios` (DuckDB), nunca a MV do PostGIS.

## Consequências

**O que ganhamos:**

- Zero código de ingestão ou CDC redundante para 4 camadas de referência que somam menos de 16 mil feições.
- Validação cruzada automática entre PostGIS e DuckDB a cada `dbt build`, reduzindo o risco de erro silencioso nos predicados espaciais (`ST_Intersects` e `ST_DWithin`).
- Reuso direto da camada sanitizada e validada (`ST_IsValid`) já mantida pelo pipeline `load_camadas.py` no PostGIS.

**O que perdemos:**

- O `dbt build` depende do serviço `db` (PostgreSQL) em execução para anexar as camadas territoriais e a MV de reconciliação.
- Qualquer mudança na regra da pergunta de gestão exige atualizar dois arquivos (`V9` no PostGIS e `int_focos_protegidos_imovel.sql` no dbt), com o teste de reconciliação acusando divergências.
- Mutações cadastrais feitas via CDC em `imovel_car` geram divergência legítima contra a MV até o próximo `REFRESH` (motivo do `severity='warn'`).

## Gatilhos de revisão

Revisaremos esta decisão caso:

1. `reserva_legal` ou `area_preservacao_permanente` passem a sofrer mutações frequentes que exijam histórico SCD Tipo 2 próprio, justificando replicá-las para Delta Lake via CDC.
2. O pipeline `dbt` precise executar em ambiente isolado (como CI ou nuvem analítica) sem conectividade com o PostgreSQL operacional.
3. A MV do PostGIS deixe de ser necessária para auditoria ou consulta GIS direta, permitindo consolidar a regra da pergunta exclusivamente no `dbt-duckdb`.
