---
icon: material/file-export
---

# :material-file-export: 0004. Publicar a camada semântica Gold como contrato dbt e retrato JSON versionado

- **Status:** Aceito
- **Data:** 2026-11-21
- **Decisores:** Cláudio H., Elias F., Gabriel F., Gabriel S., João V., Manoel F., Samuel R.

## Contexto

Com a camada dimensional Gold implementada em `dbt-duckdb` ([ADR 0003](03-modelagem-dimensional-e-ferramenta-de-transformacao.md)) e o ordenamento da fila de vistorias fechado pelo Índice de Prioridade de Vistoria ([ADR 0005](05-indice-de-prioridade-de-vistoria.md)), falta decidir como os dados tratados chegam ao consumo humano e analítico.

### Caracterização da carga e restrições

- **Volume da camada de consumo:** `gold.painel_imoveis_prioritarios` consolida os **1.593 imóveis rurais reincidentes** do DF (entre 21.047 cadastros do CAR) e agrega 37.693 focos protegidos. A fila exibida com geometrias no painel web cobre os **50 primeiros imóveis** (`TAMANHO_FILA = 50`), seus polígonos de Reserva Legal e os agregados do DF, enquanto todos os 1.593 registros ficam disponíveis para consulta tabular SQL no DuckDB.
- **Definição única de métrica:** os pesos do IPV (`0,4` recorrência, `0,3` recência, `0,3` intensidade), o piso de área (`14,1 ha`) e o corte temporal (`2015` a `2025`) devem viver em uma única fonte versionada (`transformacao/dbt_project.yml`), evitando divergência entre o painel e os relatórios SQL.
- **Restrições operacionais e ambientais:** a documentação e o dashboard rodam em hospedagem estática (GitHub Pages), sem servidor de aplicação nem banco permanente em produção. O carregamento inicial do painel visa resposta abaixo de `500 ms`, com SLA de frescor de até `30 horas` (`SLA_FRESCOR_HORAS = 30`). As tabelas carregadas descartam CPF e nome de proprietários do SICAR (`migrations/V2__cadastros_base.sql`), mantendo apenas o código público do imóvel (`cod_imovel` no padrão `DF-...`) e geometrias em `EPSG:31983`.

## Alternativas consideradas

### A. Opção nula: visões materializadas no PostGIS com exportação CSV agendada

Manter o consumo diretamente sobre a visão materializada `gold.mv_imoveis_reincidentes_areas_protegidas` (`V7`/`V9`) no PostgreSQL ou gerar um CSV tabular periódico com `psql \copy` para abertura em planilha ou QGIS.

- **Por que é viável:** reaproveita o banco PostGIS já existente no `docker-compose.yml` e elimina o script de exportação em JSON e as regras de contrato no DuckDB.
- **Por que não foi escolhida:** a consulta da MV no PostGIS leva `2.481,7 ms` na versão otimizada `V9` (`docs/explain/`), sem incluir o cálculo do IPV nem a associação histórica em SCD Tipo 2. Um CSV tabular simples (6,6 KB para os 50 primeiros) atende planilhas, mas não transporta os polígonos de imóvel e reserva legal nem os agregados por região administrativa e ano usados nos filtros cruzados do painel. Expor polígonos brutos do CAR chega a 54.373 vértices por feição.

### B. API ou federação de consultas sob demanda sobre DuckDB e PostGIS

Subir um serviço HTTP (FastAPI ou camada semântica acoplada) para executar SQL em tempo real no arquivo `corta_fogo.duckdb` e consultar camadas no PostgreSQL a cada abertura do dashboard.

- **O que oferece:** consistência imediata após cada execução do `dbt build` e filtros SQL livres sobre todos os 21.047 imóveis e 38.945 focos sem limitar polígonos no mapa.
- **O que cobra:** exige hospedar e manter servidor backend fora do GitHub Pages, expõe o arquivo local do DuckDB à contenção de leitura e escrita durante a execução diária do Dagster (`03:00` BRT) e repassa o custo de serialização GeoJSON e simplificação geométrica para a latência de rede do usuário.

### C. Contrato declarativo no dbt com retrato JSON estático e SLA de frescor (Alternativa Escolhida)

Centralizar regras de métrica em `transformacao/dbt_project.yml` (`vars`), aplicar contrato de esquema estrito em `painel_imoveis_prioritarios` (`_marts.yml`), reconciliar totais contra o PostGIS via teste automático (`reconcilia_fato_imovel_com_mv_postgis.sql`) e materializar a entrega operacional em `docs/assets/dados_dashboard/gold.json` por meio de [`scripts/exportar_painel_gold.py`](https://github.com/BeyondMagic/corta-fogo-df/blob/main/scripts/exportar_painel_gold.py).

- **O que oferece:** entrega ao navegador um único arquivo pré-agregado com polígonos simplificados em `EPSG:4326` (`ST_SimplifyPreserveTopology(..., 60)` e 4 casas decimais), sem servidor em produção. O *asset check* horário `frescor_sla` no Dagster monitora a coluna `gerado_em` contra `30 horas`. O mesmo contrato alimenta tanto o dashboard quanto as consultas declarativas `consulta_pergunta_gestao.sql` e `resumo_pergunta_gestao.sql`.

## Medição

Script reproduzível sem dependências externas sobre os artefatos do repositório: [`scripts/benchmark/benchmark_disponibilizacao.py`](https://github.com/BeyondMagic/corta-fogo-df/blob/main/scripts/benchmark/benchmark_disponibilizacao.py). Os tempos de execução do PostGIS vêm dos planos em [`docs/explain/`](https://github.com/BeyondMagic/corta-fogo-df/tree/main/docs/explain) e a leitura tabular do DuckDB vem da medição registrada na Entrega 3 (`dbt show --select consulta_pergunta_gestao --limit 20`).

```bash
python3 scripts/benchmark/benchmark_disponibilizacao.py --iteracoes 30
```

| Mecanismo de disponibilização | Tamanho entregue | Latência medida | Geometrias na entrega | Servidor em produção |
| :--- | :---: | :---: | :--- | :--- |
| **A. Opção nula: MV PostGIS (`V9`) / CSV (top 50)** | 6,6 KB (CSV tabular) | `2.481,7 ms` (`V9` DB) / `0,17 ms` (CSV) | Ausentes no CSV; até 54.373 vértices no banco | PostGIS ativo para consulta SQL |
| **B. Warehouse DuckDB direto (consulta tabular)** | Sob demanda | `5,0 ms` (`painel_imoveis_prioritarios`) | Exige `ST_AsGeoJSON` por requisição | API Python / DuckDB contínua |
| **C. Contrato dbt + `gold.json` estático (escolhida)** | **187,0 KB** (`35,9 KB` gzip; redução de **99,46%** frente aos 34,11 MiB brutos) | **2,29 ms** média (`2,79 ms` p95 de parse em Python) | **7.177 vértices** totais no top 50 (1.222 de imóveis + 5.955 de RL) | **Nenhum** (GitHub Pages) |

O lote completo lido pelo dashboard (`gold.json`, `resumo.json`, `geometrias.json` e `focos.json`) soma `2,49 MiB`, com parse médio de `38,04 ms` (`p95` de `41,52 ms`).

## Decisão

Adotamos **contrato declarativo de consumo no dbt (`painel_imoveis_prioritarios`) exportado em retrato JSON estático versionado (`gold.json`)**, com definição única de parâmetros em `transformacao/dbt_project.yml` e verificação horária de frescor em `src/pipeline/frescor.py` (`SLA <= 30 h`).

## Consequências

**O que ganhamos:**

- Hospedagem estática em GitHub Pages com carga de `187,0 KB` para toda a camada Gold no painel (`35,9 KB` comprimido em HTTP).
- Consistência garantida entre SQL e interface: o teste `reconcilia_fato_imovel_com_mv_postgis` confere os mesmos 1.593 imóveis reincidentes e 37.693 focos frente ao PostGIS, enquanto `contract: enforced: true` barra alterações silenciosas de tipo ou coluna antes da exportação.
- Isolamento total do banco OLTP e do arquivo DuckDB contra acessos simultâneos de leitura do público final.

**O que perdemos:**

- **Recorte geométrico da fila limitada no mapa:** `car_top50_geoms` exporta polígonos apenas dos 50 primeiros colocados por IPV; imóveis das posições 51 a 1.593 são consultados via `consulta_pergunta_gestao.sql` no DuckDB, sem renderização individual no mapa web.
- **Atraso inerente ao ciclo em retrato (até 30 horas):** alterações recém-ingeridas pelo CDC só chegam ao usuário publicado após novo `dbt build`, execução de `exportar_painel_gold.py` e atualização do artefato estático.
- **Escrita reversa e controle de acesso no banco fora do escopo atual:** `gold.json` entrega a fila pronta para triagem humana no navegador, mas não grava de volta uma tabela operacional no PostgreSQL nem aplica perfis `ROLE` ou *Row-Level Security* no warehouse.

**O que se torna irreversível:**

- Os scripts visuais em `docs/javascripts/dashboard_corta_fogo.js` ficam acoplados ao esquema de chaves de `gold.json` (`gold_referencia`, `car_cruzamento`, `car_top50`, `car_top50_geoms`). Migrar para API dinâmica ou alterar nomes de campos exige atualizar o contrato `_marts.yml`, `scripts/exportar_painel_gold.py` e o frontend no mesmo ciclo.

## Gatilho de revisão

Revisaremos esta decisão caso ocorra ao menos uma das condições abaixo:

1. O arquivo `gold.json` ultrapassar `2 MB` (ou o conjunto de JSONs do painel passar de `5 MB`) devido à expansão da fila para além de 50 imóveis, elevando o carregamento inicial acima de `2 s`.
2. A equipe de fiscalização exigir atualização em tempo sub-diário (SLA inferior a `6 horas`) ou filtragem geométrica livre sobre todos os 21.047 imóveis em campo, justificando substituir o retrato estático por uma API sobre DuckDB/PostGIS.
3. Um sistema operacional externo passar a consumir diretamente os resultados da fila, exigindo gravação de volta no PostgreSQL (ETL reverso em tabela transacional) e restrição de acesso por linha ou região administrativa (`ROLE` / RLS).
