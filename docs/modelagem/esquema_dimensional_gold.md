# Esquema dimensional Gold

A Gold é a camada pronta para consulta. Ela junta os dados já limpos e responde a pergunta do projeto sem o painel precisar recalcular nada.

Implementação: dbt-duckdb em `transformacao/models/marts/`. Consumo no painel: arquivo `gold.json` ([ADR 0004](../adr/04-disponibilizacao-contrato-dbt-e-retrato-estatico.md)).

## A pergunta que a Gold responde

> Quais imóveis rurais do DF tiveram focos de calor **reincidentes** em Reserva Legal, APP ou a até 1 km de Unidade de Conservação, entre 2015 e 2025?

**Reincidente** = foco em área protegida em **2 anos ou mais**.

## Do foco à fila (passo a passo)

1. O satélite detecta um **foco** (ponto no mapa, com data e sensor).
2. A gente pergunta: esse foco caiu em imóvel? Em Reserva Legal, APP ou perto de UC?
3. Cada foco é comparado com o **perímetro que o imóvel tinha naquela data** (não com o mapa de hoje).
4. Agrupamos por imóvel: em quantos anos isso aconteceu?
5. Quem tem 2 anos ou mais vira **reincidente**.
6. Os reincidentes entram numa **fila de vistoria**, ordenada pelo índice IPV ([ADR 0005](../adr/05-indice-de-prioridade-de-vistoria.md)).
7. O painel só lê essa fila pronta.

## Tabelas em português

| Tabela | Em uma linha | Cada linha é | Linhas (14/11/2026) |
| :--- | :--- | :--- | ---: |
| `fato_foco_calor` | Todas as detecções | 1 foco | 38.944 |
| `dim_tempo` | Calendário do projeto | 1 dia | 4.018 |
| `dim_satelite` | Sensores do INPE | 1 satélite | 20 |
| `dim_regiao_administrativa` | RAs do DF | 1 RA | 37 |
| `dim_territorio` | Áreas protegidas | 1 UC, APP ou Reserva Legal | 15.814 |
| `dim_imovel_car` | Histórico do cadastro | 1 versão de um imóvel | 21.049 |
| `fct_reincidencia_imovel` | Imóveis que já queimaram em área protegida | 1 imóvel | 4.068 |
| `mart_reincidencia_imovel_ano` | A mesma coisa, ano a ano | 1 imóvel em 1 ano | 8.271 |
| `painel_imoveis_prioritarios` | Fila de vistoria (o que o painel usa) | 1 imóvel reincidente, já ordenado | 1.593 |

### Três tabelas que mais importam

| Se você quer… | Olhe |
| :--- | :--- |
| Contar focos sem inflar número | `fato_foco_calor` |
| Saber se o imóvel é reincidente e o IPV dele | `fct_reincidencia_imovel` |
| Ver a fila que o dashboard mostra | `painel_imoveis_prioritarios` |

## Duas regras que evitam erro de contagem

**1. Um foco, uma linha na fato.**  
No SICAR (cadastro rural) os imóveis podem se sobrepor. Um foco pode cair em vários. Se a fato repetisse uma linha por imóvel, o total de focos cresceria artificialmente. A ligação foco↔imóvel fica à parte; a decisão fica no fato **por imóvel**.

**2. Usar o mapa da época do foco.**  
Um foco de 2017 cruza com o perímetro de 2017. Isso é o histórico SCD Tipo 2 em `dim_imovel_car`.

## Glossário rápido

| Termo | Significado aqui |
| :--- | :--- |
| **UC** | Unidade de Conservação (parque, APA etc.). Conta se o foco está a até 1 km. |
| **APP** | Área de Preservação Permanente (beira de rio, nascente etc.). Conta se o foco intersecta. |
| **Reserva Legal** | Parte do imóvel que a lei manda manter com vegetação. Conta se o foco intersecta a RL **daquele** imóvel. |
| **SICAR** | Sistema do Cadastro Ambiental Rural, origem dos perímetros. |
| **IPV** | Índice que ordena quem vistoriar primeiro (recorrência, recência, intensidade). |
| **Mart** | Tabela já agregada para uma pergunta (aqui: imóvel × ano). |
| **SCD Tipo 2** | Guardar versões antigas do cadastro em vez de apagar o passado. |

## Decisões de modelagem (referência)

| Pergunta | Decisão |
| :--- | :--- |
| Qual o grão da fato atômica? | Uma linha por `id_foco` (detecção = tempo + espaço + satélite). |
| A fato atômica explode por imóvel? | Não. Relação N:N em `int_focos_imoveis`. |
| Onde está o sujeito da pergunta? | `fct_reincidencia_imovel`, uma linha por imóvel. |
| Como ordenar os reincidentes? | IPV ([ADR 0005](../adr/05-indice-de-prioridade-de-vistoria.md)). |
| Tempo: dia ou mês? | Dia civil local. Estação seca no DF: maio a setembro. |
| Chave de `dim_territorio`? | `md5(tipo_area, cod_imovel, WKT)`. Sem IDENTITY do PostGIS. |
| Região Administrativa | Ligada ao foco (ponto) e ao imóvel (ponto interno). |
| SCD2 no cruzamento | `dbt_valid_from <= data_hora_evento < dbt_valid_to`. |
| Reincidência | ≥ 2 anos distintos com foco em área protegida (2015–2025). |

## Arquitetura em camadas (Bronze, Silver e Gold)

<p class="apresentador"><em>Responsáveis: Gabriel Souza e Manoel Felipe</em></p>

--8<-- "docs/snippets/arquitetura_camadas.md"

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

## Detalhe dos modelos

### `dim_imovel_car`

- PK: `sk_imovel = md5(cod_imovel, lsn_origem)`, uma por versão.
- Nova versão só quando muda atributo, geometria ou exclusão. Reentrega igual do CDC não abre versão.
- A lógica de versões está em `int_imoveis_versoes`; a dimensão só apresenta.

### `fato_foco_calor`

Lê `int_focos_territorio`. Chaves: `id_foco`, `sk_tempo`, `sk_satelite`, `sk_regiao_administrativa`. Marcas: `em_imovel_car`, `em_reserva_legal`, `em_app`, `ate_1km_uc`, `em_area_protegida`, `qtd_imoveis`, `distancia_min_uc_m`.

### `fct_reincidencia_imovel`

1. `int_focos_imoveis`: pares foco e imóvel na versão vigente.
2. `int_focos_protegidos_imovel`: só RL do próprio imóvel, APP ou 1 km de UC.
3. `int_metricas_imovel`: anos, dias, focos.
4. `int_indice_prioridade_imovel`: IPV e quartis, só reincidentes.

Contagem de focos soma entre imóveis, mas um foco em imóveis sobrepostos conta em cada um. Densidade e IPV não somam entre imóveis.

### `painel_imoveis_prioritarios`

Tabela que o painel consome. `posicao` 1 = maior IPV. `gerado_em` alimenta o [frescor](../frescor_sla.md).

### `mart_reincidencia_imovel_ano`

Mesma regra do fato por imóvel, por ano. Serve para ver a série no tempo.

## Reconciliação

`tests/reconcilia_fato_imovel_com_mv_postgis.sql` compara os reincidentes da Gold com a MV do PostGIS. Na carga de 14/11/2026, zero divergências. Severidade `warn`: cada lado lê o cadastro em momentos diferentes.
