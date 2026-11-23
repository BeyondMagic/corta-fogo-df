---
icon: material/compass-outline
---

# :material-compass-outline: Metodologia

<p class="apresentador"><em>Responsáveis: Elias F. e Gabriel Fernando</em></p>

A metodologia diz **como** medimos. A Gold é onde isso vira tabela e alimenta o [Dashboard](dashboard.md). Guia completo, em português simples: [esquema dimensional Gold](modelagem/esquema_dimensional_gold.md). Índice: [ADR 0005](adr/05-indice-de-prioridade-de-vistoria.md). Frescor: [SLA](frescor_sla.md).

## O que a Gold entrega

Em quatro frases:

1. Conta só foco em **Reserva Legal do imóvel**, **APP** ou a até **1 km de UC**.
2. **Reincidente** = isso em **2 anos ou mais** (2015–2025).
3. A fila de vistoria ordena esses imóveis pelo **IPV** e sai no `gold.json` ([ADR 0004](adr/04-disponibilizacao-contrato-dbt-e-retrato-estatico.md)).
4. Cada foco usa o **perímetro da época** do evento, não o mapa de hoje.

## Arquitetura em Camadas (Bronze, Silver e Gold)

<p class="apresentador"><em>Arquitetura: Gabriel Souza e Manoel Felipe</em></p>

--8<-- "docs/snippets/arquitetura_camadas.md"

## Tópicos previstos

### 1. Fontes de dados e pegada espacial dos sensores

- Escopo temporal (`2015-2025`), satélites considerados e protocolo de referência (`AQUA_M-T`).
- Diferença entre centroide do pixel orbital, detecções múltiplas no mesmo dia e área queimada (cicatriz).

### 2. Padronização cartográfica e cruzamentos espaciais

- Projeção oficial adotada (`EPSG:31983`, SIRGAS 2000 / UTM zona 23S) para cálculo de áreas e distâncias.
- Critérios de interseção com Reserva Legal, Área de Preservação Permanente (APP) e faixa de amortecimento de `1.000 m` em torno das Unidades de Conservação.
- Associação histórica com versões do imóvel no SICAR via SCD Tipo 2.

### 3. Reincidência e Índice de Prioridade de Vistoria (IPV)

- Regra de elegibilidade (`>= 2` anos civis distintos com foco em área protegida).
- Formulação de recorrência, recência e intensidade diária por `100 ha` com piso de `14,1 ha` ([ADR 0005](adr/05-indice-de-prioridade-de-vistoria.md)).

### 4. Limitações, defasagens e validação

- Sobreposição entre perímetros declarados no SICAR e cadastros cancelados/suspensos.
- Reconciliação entre a camada Gold (`dbt-duckdb`) e a visão materializada no PostGIS.

<!--
## Nota Metodológica: Pegada Espacial vs. Cicatriz de Queimada

Cada coordenada exibida no painel não representa apenas um ponto infinitesimal de ignição, nem corresponde diretamente à área contínua destruída pelo fogo: trata-se do **centroide do pixel orbital** (célula de resolução) onde o sensor termal identificou energia radiativa compatível com combustão ativa no instante da passagem.

Sensores distintos cobrem resoluções diferentes em uma mesma série histórica:

| Família / Sensor | Exemplos na série do DF | Dimensão do pixel no solo | Área nominal do pixel | Órbita típica |
| :--- | :--- | :--- | :--- | :--- |
| **VIIRS** (`I-Band`) | `NPP-375`, `NOAA-20`, `NOAA-21` | `375 m x 375 m` | `~14,1 ha` (`~0,14 km²`) | Polar (alta resolução) |
| **MODIS** (`AQUA_M-T`, Referência) | `AQUA_M-T`, `TERRA_M-M` | `1.000 m x 1.000 m` | `~100,0 ha` (`1,00 km²`) | Polar (série climatológica) |
| **AVHRR / Outros** | `NOAA-18`, `NOAA-19`, `METOP-B/C` | `1.100 m x 1.100 m` | `~121,0 ha` (`~1,21 km²`) | Polar |
| **ABI / SEVIRI** (Geoestacionário) | `GOES-16`, `GOES-19`, `MSG-03` | `2.000 m x 2.000 m` | `~400,0 ha` (`4,00 km²`) | Geoestacionária (passagens a cada 10–15 min) |

O filtro **Satélite de referência (`AQUA_M-T`)** segue o protocolo oficial do INPE de série consistente desde 2002 (pixel nominal de 1 km²), eliminando distorções provocadas pela entrada de sensores polares de 375 m (`NPP-375`, `NOAA-20`) ou geoestacionários a partir de 2016–2018. Para medição física contínua de área queimada (**cicatrizes**), combinam-se séries multiespectrais ópticas (como `Landsat` 30 m ou `Sentinel-2` 10–20 m).

---

## De onde vêm os dados do painel

Dois arquivos alimentam a página, em `docs/assets/dados_dashboard/`:

| Arquivo | Gerado por | Conteúdo |
| :--- | :--- | :--- |
| `gold.json` | [`scripts/exportar_painel_gold.py`](https://github.com/BeyondMagic/corta-fogo-df/blob/main/scripts/exportar_painel_gold.py), lendo a camada Gold do dbt | Resposta à pergunta de gestão: totais de imóveis reincidentes, distribuições, os 50 primeiros da fila de vistoria e as geometrias deles, a data em que a Gold foi gerada |
| `resumo.json`, `geometrias.json`, `focos.json` | [`scripts/gerar_dados_dashboard.py`](https://github.com/BeyondMagic/corta-fogo-df/blob/main/scripts/gerar_dados_dashboard.py) | Exploração dos focos: série histórica, RAs, UCs, sensores e as malhas do mapa |

O painel não recalcula o cruzamento de imóveis: os números de reincidência são os de `gold.painel_imoveis_prioritarios` e `gold.fct_reincidencia_imovel`. Para regenerar `gold.json` depois de um `dbt build`:

```bash
docker compose --profile transformacao run --rm exportar_painel
```

A ordem da fila é a do Índice de Prioridade de Vistoria ([ADR 0005](adr/05-indice-de-prioridade-de-vistoria.md)). A data exibida no bloco de resposta é a da execução do dbt que gerou a tabela ([frescor e SLA](frescor_sla.md)).

---

## Origem Oficial dos Dados e Ferramentas

| Camada / Componente | Fonte Oficial / Biblioteca | Abrangência | Frequência / Uso |
| :--- | :--- | :--- | :--- |
| **Focos de Calor (`2015–2025`)** | [INPE BDQueimadas](https://terrabrasilis.dpi.inpe.br/queimadas/bdqueimadas/) | Todos os `38.945` registros no DF | Dados históricos reais em `focos.json` |
| **Regiões Administrativas e Limite do DF** | [IDE-DF / SEDUH (`Publico/LIMITES`)](https://www.geoservicos.ide.df.gov.br/arcgis/rest/services/Publico/LIMITES/FeatureServer) | `37` Regiões Administrativas oficiais | Malha base vetorial e coroplético por RA |
| **Unidades de Conservação e Faixa 1 km** | [IDE-DF / IBRAM](https://www.geoservicos.ide.df.gov.br/arcgis/rest/services) | `84` áreas protegidas e buffers de 1.000 m | Ranking dinâmico e filtro por UC |
| **Malha Fundiária (CAR e Reserva Legal)** | [SICAR Federal](https://consultapublica.car.gov.br/publico/imoveis/index), pela camada Gold | `21.047` imóveis e `13.499` Reservas Legais no PostGIS | Fila de vistoria, situação cadastral, porte e polígonos dos 50 primeiros |
| **Visualização Analítica e Cartográfica** | [D3.js v7](https://d3js.org/) (`d3-geo` + Canvas + SVG) & [Leaflet 1.9](https://leafletjs.com/) | Projeção vetorial local + tiles OSM / ESRI | Palco duplo com filtros cruzados em memória |
-->
