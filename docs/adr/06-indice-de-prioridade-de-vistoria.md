---
icon: material/sort-numeric-descending
---

# :material-sort-numeric-descending: 0006. Índice de Prioridade de Vistoria para ordenar os imóveis reincidentes

- **Status:** Proposto (pesos aguardam validação do grupo)
- **Data:** 2026-11-14
- **Decisores:** Cláudio H., Elias F., Gabriel F., Gabriel S., João V., Manoel F., Samuel R.

Fora das cinco decisões previstas no plano de ensino: complementa o ADR 0003 na definição da camada Gold.

## Contexto

A pergunta de gestão diz quais imóveis rurais tiveram foco reincidente em área protegida. A decisão que ela apoia é a ordem das vistorias em campo antes da estiagem. Até a E3, a camada Gold devolvia 1.593 imóveis reincidentes sem uma ordem que servisse a essa decisão. O relatório e o dashboard ordenavam pelo total de focos.

O total de focos favorece imóvel grande. Na carga de 14/11/2026, os 10 primeiros por total de focos têm mediana de 25.808 ha, sete passam de 10.000 ha e só um está com cadastro ativo. São perímetros declarados que cobrem áreas inteiras de UC e somam milhares de detecções por estarem expostos a mais pixels de satélite, não por reincidência mais grave.

Outra distorção vem da série: a entrada de sensores de 375 m a partir de 2016 multiplica as detecções do mesmo fogo. Contar detecções mistura o fogo com a cobertura orbital do ano.

## Alternativas

Cada alternativa ordena os 1.593 reincidentes. A tabela mostra o perfil dos 10 primeiros de cada uma (`gold.fct_reincidencia_imovel`, carga de 14/11/2026):

| Alternativa | Cadastro ativo | Área mediana | Área máxima | Acima de 10.000 ha | Anos com foco (média) |
| :--- | ---: | ---: | ---: | ---: | ---: |
| A. Total de focos (situação até a E3) | 1 | 25.808 ha | 103.415 ha | 7 | 10,3 |
| B. Dias com foco por 100 ha, sem piso de área | 10 | 2,0 ha | 4,6 ha | 0 | 3,2 |
| C. Dias com foco por 100 ha, piso de 14,1 ha | 10 | 19,9 ha | 113,7 ha | 0 | 4,7 |
| D. Focos só do satélite de referência (AQUA_M-T) | 0 | 25.808 ha | 103.415 ha | 7 | 11,0 |
| **E. Índice composto (escolhida)** | **9** | **114,2 ha** | **1.563 ha** | **0** | **9,1** |

- **A** repete o problema descrito no contexto.
- **B** corrige o tamanho, mas exagera no sentido oposto: chácaras de 2 ha com 2 ou 3 anos de foco viram as primeiras, porque um único foco num imóvel minúsculo gera densidade alta. O pixel do sensor mais fino tem 14,1 ha, então nenhuma detecção localiza o fogo com essa precisão.
- **C** aplica o piso de 14,1 ha e melhora B, mas ainda ignora recorrência e recência: um imóvel com 2 anos de foco em 2021 pode passar à frente de outro com foco todo ano até 2025.
- **D** elimina a distorção dos sensores novos, mas 1.022 dos 1.593 reincidentes não têm nenhuma detecção do AQUA_M-T. A ordem desses imóveis vira empate.

## Decisão

Ordenar os reincidentes pelo **Índice de Prioridade de Vistoria (IPV)**, de 0 a 100:

```text
IPV = 100 × (0,4 × recorrência + 0,3 × recência + 0,3 × intensidade)
```

| Componente | Medida | Normalização (0 a 1) |
| :--- | :--- | :--- |
| Recorrência | Anos distintos com foco em área protegida | 2 anos = 0, 11 anos = 1 |
| Recência | Último ano com foco em área protegida | 2015 = 0, 2025 = 1 |
| Intensidade | Dias distintos com foco por 100 ha, com área mínima de 14,1 ha | Saturada nos percentis 5 e 95 dos reincidentes e normalizada min-max |

- **Dias, e não detecções:** um fogo captado por vários satélites no mesmo dia conta uma vez. Isso neutraliza a entrada de sensores na série sem descartar 1.022 imóveis, como em D.
- **Recorrência com o maior peso:** é o critério da pergunta de gestão (reincidência).
- **Classificação:** quartis do IPV entre os reincidentes (`PRIORIDADE CRITICA`, `ALTA`, `MEDIA`, `BAIXA`).
- **Imóvel com cadastro cancelado, suspenso ou pendente** continua na fila, marcado em `situacao` e `cadastro_ativo`. A pergunta não filtra a situação cadastral, e um cadastro cancelado com fogo recorrente também é alvo de fiscalização. Imóvel excluído do cadastro (exclusão lógica no CDC) sai da fila.

Os pesos e o piso de área são variáveis do dbt (`transformacao/dbt_project.yml`). Mudar um peso não exige mudar SQL.

## Consequências

- A fila passa a ter imóveis menores e ativos no topo: 9 dos 10 primeiros com cadastro ativo, área máxima de 1.563 ha. Os 9 imóveis acima de 10.000 ha continuam na lista; o primeiro deles está na posição 61, e 8 ficam no quartil crítico.
- Os pesos são uma escolha de valor do grupo, não um resultado estatístico. Esta decisão fica como **Proposta** até o grupo validá-los.
- A intensidade depende da distribuição dos reincidentes (percentis 5 e 95). Uma carga nova pode mudar o índice de um imóvel sem que os focos dele mudem. A classificação por quartil tem o mesmo efeito.
- A área declarada no CAR é a do imóvel inteiro. Focos dentro do imóvel, mas fora de área protegida, não entram na intensidade: só contam focos em Reserva Legal própria, APP ou a até 1 km de UC.

## Implementação

| Arquivo | Papel |
| :--- | :--- |
| `transformacao/models/intermediate/int_metricas_imovel.sql` | Contagens por imóvel (anos, dias, focos por critério) |
| `transformacao/models/intermediate/int_indice_prioridade_imovel.sql` | Componentes, IPV e quartis |
| `transformacao/models/marts/fct_reincidencia_imovel.sql` | Fato no grão do imóvel, com o índice |
| `transformacao/models/marts/painel_imoveis_prioritarios.sql` | Fila de vistoria (tabela de consumo do painel) |

## Gatilho de revisão

- O grupo ou o usuário da fiscalização propõe outros pesos.
- Chegada de dado de área queimada (cicatriz), que mede o fogo diretamente e substitui a contagem de dias.
- Mudança na série de sensores que altere a contagem de dias com foco.
