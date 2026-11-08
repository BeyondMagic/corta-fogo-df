# Esquema dimensional Gold (Issue #18)

Camada `gold` no dbt-duckdb (`transformacao/models/marts/`). Estrela em torno da fato atômica de focos, com mart agregado para a pergunta de gestão.

## Alinhamento /grill-me (decisões fechadas)

A skill `/grill-me` não tem runtime invocável neste ambiente; as perguntas abaixo foram respondidas contra o escopo da issue, o comentário da #20 e a `dim_imovel_car` da #19.

| Pergunta | Decisão |
| :--- | :--- |
| Qual a grain da fato? | Uma linha por `id_foco` (detecção = tempo + espaço + satélite). Igual a `int_focos_territorio`. |
| Fato explode por imóvel? | Não. Há sobreposição SICAR (um foco em N imóveis). Relação N:N fica em `int_focos_imoveis` e no mart. |
| Tempo: dia ou mês? | Dia civil local (`data_evento_local`). Estação seca do DF: maio a setembro. |
| Ano/mês da partição Delta? | Continuam na fato como atributos degenerados (`ano`, `mes` UTC do evento), além do `sk_tempo` pela data local. |
| `dim_territorio`: chave estável? | `sk_territorio = md5(tipo_area \|\| '|' \|\| ST_AsText(geom))`. Não usar IDENTITY do PostGIS. |
| Amortecimento 1 km | Atributo da feição UC (`raio_amortecimento_m = 1000`). RL e APP usam interseção (`raio_amortecimento_m = 0`). |
| SCD2 no mart | Join `dim_imovel_car` com `dbt_valid_from <= data_hora_evento < dbt_valid_to`. Atributos do imóvel no ano: versão do foco mais recente daquele ano. |
| Reincidência no mart | Grain = imóvel × ano com foco em área protegida. Flag `imovel_reincidente` se o imóvel tem ≥ 2 anos distintos nessa condição (2015–2025). |

## Diagrama lógico

```text
dim_tempo          dim_satelite       dim_territorio
    \                  |                    |
     \                 |                    | (consulta via int_focos_areas_protegidas)
      \                v                    |
       ------> fato_foco_calor <------------+
                     |
                     | (via int_focos_imoveis + SCD2)
                     v
              dim_imovel_car
                     |
                     v
         mart_reincidencia_imovel_ano
```

## Granularidades (por extenso)

| Modelo | Granularidade |
| :--- | :--- |
| `dim_tempo` | Uma linha por data civil no calendário 2015-01-01 a 2025-12-31 (`data`). |
| `dim_satelite` | Uma linha por nome de satélite detector (`satelite`). |
| `dim_territorio` | Uma linha por feição protegida: UC, APP ou Reserva Legal (`sk_territorio`). |
| `dim_imovel_car` | Uma linha por versão cadastral do imóvel (`sk_imovel`). Issue #19. |
| `fato_foco_calor` | Uma linha por detecção de foco no tempo e no espaço por sensor orbital (`id_foco`). |
| `mart_reincidencia_imovel_ano` | Uma linha por imóvel rural por ano civil UTC em que houve foco naquele imóvel em RL, APP ou faixa de 1 km de UC. |

## Modelos

### `dim_tempo`

- PK: `sk_tempo` (`YYYYMMDD` inteiro da data).
- Atributos: `data`, `ano`, `mes`, `dia`, `nome_mes`, `is_estacao_seca` (true se mês ∈ {5..9}).

### `dim_satelite`

- PK: `sk_satelite` (md5 do nome).
- Atributos: `satelite`, `is_referencia` (AQUA_M-T).

### `dim_territorio`

- PK: `sk_territorio` (hash estável tipo + WKT).
- `tipo_area`: `unidade_conservacao`, `app`, `reserva_legal`.
- `id_feicao_origem`: IDENTITY do ciclo atual (só auditoria intra-run).
- `raio_amortecimento_m`: 1000 para UC, 0 para APP/RL.
- Demais: nome, categoria, grupo, `cod_imovel`, `area_ha`, `geom`.

### `fato_foco_calor`

Lê `int_focos_territorio`. Chaves:

- `id_foco` (natural)
- `sk_tempo` ← `data_evento_local`
- `sk_satelite` ← nome do satélite

Medidas / flags degeneradas: `em_imovel_car`, `em_reserva_legal`, `em_app`, `ate_1km_uc`, `em_area_protegida`, `qtd_imoveis`, `distancia_min_uc_m`, coordenadas e carimbos.

### `mart_reincidencia_imovel_ano`

1. Pares foco×imóvel (`int_focos_imoveis`) com versão SCD2 vigente na `data_hora_evento`.
2. Só focos que também batem `int_focos_areas_protegidas` (mesma regra da `conferencia_mv_gold.sql`).
3. Agrega por `cod_imovel`, `ano`.
4. Marca `imovel_reincidente` se `count(anos distintos do imóvel) >= 2`.

Métricas: `total_focos`, `atinge_reserva_legal`, `atinge_app`, `atinge_uc_1km`, `sk_imovel` (versão do último evento do ano), `anos_com_foco_protegido`, `lista_anos_protegidos`.

## Arquivos

| Arquivo | Papel |
| :--- | :--- |
| `models/marts/dim_tempo.sql` | Dimensão calendário |
| `models/marts/dim_satelite.sql` | Dimensão satélite |
| `models/marts/dim_territorio.sql` | Dimensão feições protegidas |
| `models/marts/fato_foco_calor.sql` | Fato atômica |
| `models/marts/mart_reincidencia_imovel_ano.sql` | Mart da pergunta de gestão |
| `models/marts/_marts.yml` | Contratos e testes |
