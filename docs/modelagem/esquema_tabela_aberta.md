---
icon: material/table
---

# :material-table: Esquema da tabela aberta (E2)

Entrega da Issue #02 (Modelagem). Contrato máquina: [`contrato_tabela_aberta.yaml`](contrato_tabela_aberta.yaml).
Arquitetura: `arquitetura-E2/arquitetura.md`.

## Escopo

Duas tabelas Delta Lake. Não é cópia de todo o PostGIS.

| Tabela lógica | Caminho | Origem | Partição |
| :--- | :--- | :--- | :--- |
| `foco_calor_analitico` | `data/delta/foco_calor` | lote (`batch_ingest.py`) | `ano` + `mes` |
| `imovel_car_analitico` | `data/delta/imovel_car` | CDC / snapshot | nenhuma |

`foco_calor` fica fora do CDC: insert-only no OLTP e chave de dedupe do lote é o hash `id_foco`, não o identity do Postgres.

## `foco_calor_analitico`

### Colunas

| Coluna | Tipo | Papel |
| :--- | :--- | :--- |
| `id_foco` | string | PK lógica (SHA-256 de lat, lon, evento, satélite) |
| `latitude`, `longitude` | double | WGS84 (EPSG:4326) |
| `x_31983`, `y_31983` | double | metros em EPSG:31983 |
| `data_hora_evento` | timestamp | passagem do satélite; base da partição e da reincidência |
| `data_hora_ingestao` | timestamp | escrita na camada analítica |
| `satelite`, `is_satelite_referencia` | string / bool | sensor e flag AQUA_M-T |
| `municipio`, `bioma`, `risco_fogo` | string / double | atributos do CSV |
| `ano`, `mes` | string | partição (`YYYY`, `MM`) |
| `origem_ingestao` | string | sempre `lote` |
| `operacao_cdc` | string | sempre `I` (linhagem uniforme com `imovel_car`) |

### Particionamento temporal

- Derivado de `data_hora_evento` em UTC: `ano=YYYY/mes=MM`.
- `data_hora_ingestao` é só coluna, nunca partição.
- Registro atrasado (evento antigo num lote novo) cai na partição do evento. Partições recentes não são reescritas por causa disso.
- Granularidade mensal evita *small files*. Com ~39 mil focos no DF, partição diária ou por satélite só espalharia arquivos sem ganho.

### MERGE do lote

`MERGE ... WHEN NOT MATCHED INSERT` por `id_foco`. Reexecução do mesmo CSV não duplica linha. Correção de valores já gravados não é aplicada (aceitável: focos INPE são insert-only).

## `imovel_car_analitico`

Espelho analítico do imóvel CAR para o consumidor CDC. Sem partição.

| Coluna | Tipo | Papel |
| :--- | :--- | :--- |
| `cod_imovel` | string | chave |
| `situacao`, `condicao`, `area_ha`, `data_download` | string / double / date | atributos do OLTP |
| `geom_ewkb_hex` | string | MultiPolygon 31983 em EWKB hex |
| `data_hora_ingestao` | timestamp | entrada na camada analítica |
| `origem_ingestao` | string | `snapshot` ou `cdc` |
| `operacao_cdc` | string | `I`, `U` ou `D` (D = exclusão lógica) |
| `lsn_origem` | long | ordem e idempotência do WAL |

Regra de MERGE: atualiza só se `source.lsn_origem >= target.lsn_origem`.

## Metadados de auditoria e linhagem

| Campo | `foco_calor` | `imovel_car` |
| :--- | :--- | :--- |
| `origem_ingestao` | `lote` | `snapshot` / `cdc` |
| `operacao_cdc` | `I` | `I` / `U` / `D` |
| Extra | - | `lsn_origem` |

## Evolução de esquema

1. Permitido: adicionar coluna nullable (ou com default) sem reprocessar o histórico.
2. Proibido sem versão major: renomear, remover, mudar tipo, mudar chave ou layout de partição.
3. Atributos territoriais futuros no foco (`cod_imovel`, flags de RL/APP/UC) entram como colunas nullable. O lote INPE não precisa preenchê-las; um job espacial posterior preenche.
4. Nova versão major do contrato: atualizar `versao` no YAML e, se a mudança for incompatível, usar caminho Delta novo ou migrar com job explícito.

## Como usar o contrato

- Lote: `src/pipeline/batch_ingest.py` deve gravar exatamente as colunas de `foco_calor`.
- CDC: o consumidor grava `imovel_car` conforme este YAML e a seção D4 da arquitetura.
- Testes: particionamento e idempotência em `scripts/testes/test_idempotencia_lote.py`.

## Critérios da Issue #02

| Critério | Onde |
| :--- | :--- |
| Esquema de `foco_calor_analitico` (tipos, coords 4326+31983, carimbos) | YAML + tabela acima |
| Partição `ano`/`mes` por `data_hora_evento` | YAML + `batch_ingest.py` |
| `origem_ingestao` e `operacao_cdc` | ambas as tabelas no YAML |
| Regras de evolução | seção acima |
| Arquivo de contrato | `contrato_tabela_aberta.yaml` |
