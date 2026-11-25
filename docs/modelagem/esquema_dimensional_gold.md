# Esquema dimensional Gold

A Gold é a **camada semântica** do projeto: regras de negócio em tabelas com nome e grão claros, prontas para o painel e para SQL. O painel não recalcula: lê o `gold.json` ([ADR 0004](../adr/04-disponibilizacao-contrato-dbt-e-retrato-estatico.md)).

Implementação: dbt-duckdb em `transformacao/models/marts/`.

## Intermediate não é a camada semântica

São camadas diferentes no mesmo pipeline dbt:

| Camada | Pasta | Papel | Quem consome |
| :--- | :--- | :--- | :--- |
| **Staging** | `models/staging/` | Tipa e limpa a fonte (Silver) | Só o pipeline |
| **Intermediate** | `models/intermediate/` | Cozinha o dado: cruzamento espacial, versões SCD2, métricas, peças do IPV | Só o pipeline |
| **Gold (semântica)** | `models/marts/` | Responde a pergunta de gestão: fato, dimensões, fila | Painel, análises, entrega |

A intermediate **calcula** (ex.: `int_focos_imoveis`, `int_indice_prioridade_imovel`).  
A Gold **publica o significado** (ex.: `fct_reincidencia_imovel`, `painel_imoveis_prioritarios`).

No diagrama Bronze / Silver / Gold, a intermediate fica dentro da **Silver** (transformação). A camada semântica é a **Gold**.

## A pergunta

> Quais imóveis rurais do DF tiveram focos de calor **reincidentes** em Reserva Legal, APP ou a até 1 km de Unidade de Conservação, entre 2015 e 2025?

**Reincidente** = foco em área protegida em **2 anos ou mais**.

## O que importa na Gold (3 tabelas)

| Tabela | Pra quê | Cada linha é | Linhas |
| :--- | :--- | :--- | ---: |
| `fato_foco_calor` | Contar focos sem inflar o número | 1 detecção | 38.944 |
| `fct_reincidencia_imovel` | Imóvel na pergunta + IPV | 1 imóvel com foco protegido | 4.068 |
| `painel_imoveis_prioritarios` | Fila do dashboard | 1 reincidente, já ordenado | 1.593 |

```text
intermediate (cruzamentos, métricas, IPV)
        |
        v
fato_foco_calor --> fct_reincidencia_imovel --> painel_imoveis_prioritarios
   (cada foco)         (cada imóvel)              (fila / gold.json)
```

## Do foco à fila

1. Satélite detecta um **foco**.
2. Intermediate: caiu em imóvel e em área protegida (RL, APP ou 1 km de UC)?
3. Intermediate: usa o **perímetro da data do foco** (SCD2).
4. Gold: conta **anos** por imóvel; com 2 ou mais → reincidente.
5. Gold: ordena pelo **IPV** ([ADR 0005](../adr/05-indice-de-prioridade-de-vistoria.md)).
6. Painel lê a fila pronta.

## Duas regras anti-erro

1. **Um foco, uma linha** em `fato_foco_calor`. No SICAR imóveis se sobrepõem; repetir por imóvel infla o total.
2. **Mapa da época do foco** via `dim_imovel_car` (SCD Tipo 2).

## Glossário

| Termo | Significado |
| :--- | :--- |
| **Camada semântica** | A Gold: métricas e entidades com significado de negócio. |
| **Intermediate** | Etapa de transformação (Silver), não é consumo final. |
| **UC** | Unidade de Conservação. Conta a até 1 km. |
| **APP** | Área de Preservação Permanente. Conta se intersecta. |
| **Reserva Legal** | Parte do imóvel com vegetação obrigatória. |
| **SICAR** | Cadastro Ambiental Rural. |
| **IPV** | Índice que ordena a fila. |
| **SCD Tipo 2** | Guardar versões do cadastro. |

---

## Detalhe: demais tabelas da Gold

| Tabela | Em uma linha | Cada linha é | Linhas |
| :--- | :--- | :--- | ---: |
| `dim_tempo` | Calendário 2015–2025 | 1 dia | 4.018 |
| `dim_satelite` | Sensores do INPE | 1 satélite | 20 |
| `dim_regiao_administrativa` | RAs do DF | 1 RA | 37 |
| `dim_territorio` | Áreas protegidas | 1 UC, APP ou RL | 15.814 |
| `dim_imovel_car` | Histórico do cadastro | 1 versão de imóvel | 21.049 |
| `mart_reincidencia_imovel_ano` | Tendência ano a ano | 1 imóvel × 1 ano | 8.271 |

## Decisões de modelagem

| Pergunta | Decisão |
| :--- | :--- |
| Grão da fato atômica? | 1 linha por `id_foco`. |
| Explode por imóvel? | Não. N:N em `int_focos_imoveis`. |
| Sujeito da pergunta? | `fct_reincidencia_imovel`. |
| Ordem da fila? | IPV ([ADR 0005](../adr/05-indice-de-prioridade-de-vistoria.md)). |
| Tempo | Dia civil local. Seca no DF: maio a setembro. |
| Chave de território | `md5(tipo_area, cod_imovel, WKT)`. |
| SCD2 | `dbt_valid_from <= data_hora_evento < dbt_valid_to`. |
| Reincidência | ≥ 2 anos com foco em área protegida (2015–2025). |

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
- Nova versão só quando muda atributo, geometria ou exclusão.
- Lógica em `int_imoveis_versoes`; a dimensão só apresenta.

### `fato_foco_calor`

Lê `int_focos_territorio`. Chaves: `id_foco`, `sk_tempo`, `sk_satelite`, `sk_regiao_administrativa`.

### `fct_reincidencia_imovel`

Monta a partir da intermediate: pares protegidos, métricas e IPV. Uma linha por imóvel.

### `painel_imoveis_prioritarios`

Tabela que o painel consome. `posicao` 1 = maior IPV. `gerado_em` alimenta o [frescor](../frescor_sla.md).

### `mart_reincidencia_imovel_ano`

Mesma regra, por imóvel e ano.

## Reconciliação

`tests/reconcilia_fato_imovel_com_mv_postgis.sql` compara a Gold com a MV do PostGIS. Carga 14/11/2026: zero divergências. Severidade `warn`.
