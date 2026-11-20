# Esquema dimensional Gold

Camada `gold` no dbt-duckdb (`transformacao/models/marts/`). Estrela em torno da fato atômica de focos, com um fato no grão do imóvel para a pergunta de gestão e uma tabela larga de consumo para o painel.

## Decisões de modelagem

| Pergunta | Decisão |
| :--- | :--- |
| Qual o grão da fato atômica? | Uma linha por `id_foco` (detecção = tempo + espaço + satélite). |
| A fato atômica explode por imóvel? | Não. Há sobreposição no SICAR (um foco em N imóveis). A relação N:N fica em `int_focos_imoveis`. |
| Onde está o sujeito da pergunta de gestão? | Em `fct_reincidencia_imovel`, uma linha por imóvel. A pergunta é sobre imóveis, e a decisão (ordem das vistorias) também. |
| Como ordenar os imóveis reincidentes? | Índice de Prioridade de Vistoria ([ADR 0005](../adr/05-indice-de-prioridade-de-vistoria.md)). |
| Tempo: dia ou mês? | Dia civil local (`data_evento_local`). Estação seca do DF: maio a setembro. |
| `dim_territorio`: chave estável? | `sk_territorio = md5(tipo_area, cod_imovel, WKT da geometria)`. Não usa o IDENTITY do PostGIS. |
| Região Administrativa | `dim_regiao_administrativa`, ligada ao foco (ponto) e ao imóvel (ponto interno do perímetro). |
| SCD2 no cruzamento | O foco cruza com a **geometria** da versão do imóvel vigente na data do evento (`dbt_valid_from <= data_hora_evento < dbt_valid_to`). Geometria e atributos vêm da mesma versão. |
| Reincidência | Imóvel com foco em área protegida em pelo menos 2 anos distintos entre 2015 e 2025. |

## Diagrama lógico

```text
dim_tempo   dim_satelite   dim_regiao_administrativa   dim_territorio
    \            |              /          \                 |
     \           |             /            \                | (int_focos_areas_protegidas)
      +---> fato_foco_calor <-+              \               |
                 |                            \              |
                 | (int_focos_imoveis: versao  \             |
                 |  vigente na data do foco)    \            |
                 v                               v           |
          dim_imovel_car <-------------- fct_reincidencia_imovel <--+
                 |                               |
                 v                               v
   mart_reincidencia_imovel_ano       painel_imoveis_prioritarios
        (tendencia por ano)           (fila de vistoria, consumo)
```

## Granularidades

| Modelo | Granularidade | Linhas (14/11/2026) |
| :--- | :--- | ---: |
| `dim_tempo` | Uma linha por data civil de 2015-01-01 a 2025-12-31. | 4.018 |
| `dim_satelite` | Uma linha por satélite detector. | 20 |
| `dim_regiao_administrativa` | Uma linha por Região Administrativa do DF. | 37 |
| `dim_territorio` | Uma linha por feição protegida: UC, APP ou Reserva Legal. | 15.814 |
| `dim_imovel_car` | Uma linha por versão cadastral do imóvel (SCD Tipo 2). | 21.049 |
| `fato_foco_calor` | Uma linha por detecção de foco no tempo e no espaço por sensor orbital. | 38.944 |
| `fct_reincidencia_imovel` | Uma linha por imóvel com ao menos um foco em área protegida entre 2015 e 2025. | 4.068 |
| `mart_reincidencia_imovel_ano` | Uma linha por imóvel por ano civil UTC com foco em área protegida. | 8.271 |
| `painel_imoveis_prioritarios` | Uma linha por imóvel reincidente ainda presente no cadastro, na ordem da fila de vistoria. | 1.593 |

## Modelos

### `dim_imovel_car`

- PK: `sk_imovel = md5(cod_imovel, lsn_origem)`, uma por versão.
- Uma versão só existe quando o conteúdo do imóvel muda (atributos, geometria ou exclusão). Reentregas do CDC e recargas do OLTP com os mesmos dados não abrem versão.
- A lógica de versões fica em `int_imoveis_versoes`, que também alimenta o cruzamento espacial. A dimensão só a apresenta.

### `fato_foco_calor`

Lê `int_focos_territorio`. Chaves: `id_foco` (natural), `sk_tempo` (data local), `sk_satelite`, `sk_regiao_administrativa`. Medidas e marcas degeneradas: `em_imovel_car`, `em_reserva_legal`, `em_app`, `ate_1km_uc`, `em_area_protegida`, `qtd_imoveis`, `distancia_min_uc_m`, coordenadas e carimbos.

### `fct_reincidencia_imovel`

1. `int_focos_imoveis`: pares foco e imóvel, com a versão vigente na data do foco.
2. `int_focos_protegidos_imovel`: só os pares em Reserva Legal do próprio imóvel, APP ou a até 1 km de UC (a regra da pergunta, em um lugar só).
3. `int_metricas_imovel`: contagens por imóvel (anos, dias, focos por critério e por satélite de referência).
4. `int_indice_prioridade_imovel`: componentes, índice e quartis, só para reincidentes.

Contagens são aditivas entre imóveis, com a ressalva de que um foco sobre imóveis sobrepostos conta em cada um. Densidade, componentes e índice não são aditivos.

### `painel_imoveis_prioritarios`

Tabela larga de consumo, com contrato de esquema. Junta o fato, a versão do imóvel e a RA. `posicao` 1 é o imóvel de maior índice. `gerado_em` sustenta a [métrica de frescor](../frescor_sla.md).

### `mart_reincidencia_imovel_ano`

Mesma regra do fato por imóvel, agregada por imóvel e ano. Serve à tendência ao longo da série.

## Reconciliação

`tests/reconcilia_fato_imovel_com_mv_postgis.sql` compara os imóveis reincidentes do fato com a `gold.mv_imoveis_reincidentes_areas_protegidas` do PostGIS (anos, focos e critérios atingidos). Na carga de 14/11/2026, zero divergências. O teste tem severidade `warn`: os dois lados leem o cadastro em momentos diferentes (a MV no último `REFRESH`, o fato na versão vigente de cada foco).
