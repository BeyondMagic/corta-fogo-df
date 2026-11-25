---
icon: material/compass-outline
---

# :material-compass-outline: Metodologia

<p class="apresentador"><em>Responsáveis: Elias F. e Gabriel Fernando</em></p>

A metodologia define **como** o projeto mede ocorrências térmicas, cruza limites territoriais e prioriza imóveis rurais para fiscalização. A materialização dessas regras vive no [esquema dimensional Gold](modelagem/esquema_dimensional_gold.md) (`dbt-duckdb`) e alimenta o [Dashboard](dashboard.md). Os recortes de escopo, tratamentos de anomalias e alternativas descartadas estão documentados de forma espelhada em [Decisões e Descartes](decisoes_descartes.md).

## O que a Gold entrega

Em quatro frases:

1. Conta só foco em **Reserva Legal do imóvel**, **APP** ou a até **1 km de UC**.
2. **Reincidente** = isso em **2 anos ou mais** (2015 a 2025).
3. A fila de vistoria ordena esses imóveis pelo **IPV** ([ADR 0005](adr/05-indice-de-prioridade-de-vistoria.md)) e sai no `gold.json` ([ADR 0004](adr/04-disponibilizacao-contrato-dbt-e-retrato-estatico.md)).
4. Cada foco usa o **perímetro da época** do evento, não o mapa de hoje.

**Intermediate vs Gold:** intermediate calcula (`int_*`); Gold publica (`fato_*`, `fct_*`, `painel_*`). O dashboard só lê a Gold.

## Arquitetura em Camadas (Bronze, Silver e Gold)

<p class="apresentador"><em>Arquitetura: Gabriel Souza e Manoel Felipe</em></p>

--8<-- "docs/snippets/arquitetura_camadas.md"

---

## 1. Origens de Dados e Pegada Espacial dos Sensores

O pipeline cruza a série histórica de detecções orbitais de calor (`2015 a 2025`, cobrindo 11 estações secas completas) com quatro malhas territoriais oficiais do Distrito Federal:

| Camada / Componente | Fonte Oficial / Biblioteca | Abrangência no Banco | Papel na Metodologia |
| :--- | :--- | :--- | :--- |
| **Focos de Calor (2015 a 2025)** | [INPE BDQueimadas](https://terrabrasilis.dpi.inpe.br/queimadas/bdqueimadas/) | `38.944` focos únicos no Delta Lake (`38.945` brutos no CSV) | Eventos térmicos pontuais com carimbo UTC e identificação de sensor |
| **Malha Fundiária (CAR e Reserva Legal)** | [SICAR Federal](https://consultapublica.car.gov.br/publico/imoveis/index) | `21.047` imóveis e `13.499` Reservas Legais (`13.496` distintas na Gold) | Sujeito da pergunta de gestão, situação cadastral e área de Reserva Legal declarada |
| **Unidades de Conservação e APPs** | [SISDIA / IBRAM-DF](https://sisdia.df.gov.br/server/rest/services/01_AMBIENTAL) | `84` Unidades de Conservação e `2.234` polígonos de APP | Áreas públicas protegidas e cálculo da faixa de amortecimento de `1.000 m` |
| **Regiões Administrativas** | [IDE-DF / SEDUH (`Publico/LIMITES`)](https://www.geoservicos.ide.df.gov.br/arcgis/rest/services/Publico/LIMITES/FeatureServer) | `37` Regiões Administrativas oficiais | Agregação territorial e filtro operacional no painel |
| **Visualização Cartográfica** | [D3.js v7](https://d3js.org/) (`d3-geo`) e [Leaflet 1.9](https://leafletjs.com/) | Projeção vetorial local e camadas de satélite/ruas | Palco espacial duplo com filtros cruzados sobre `gold.json` |

### Centroide do pixel orbital vs. cicatriz de queimada

Cada coordenada registrada pelo INPE corresponde ao **centroide do pixel orbital** (célula de resolução do sensor termal) onde foi detectada emissão infravermelha compatível com combustão ativa no instante da passagem. O ponto indica presença de fogo dentro da área nominal do pixel, sem delimitar o polígono contínuo consumido pelas chamas (cicatriz de queimada, cuja medição requer imagens ópticas multiespectrais como Landsat de `30 m` ou Sentinel-2 de `10 a 20 m`).

A base de 2015 a 2025 reúne 20 sensores com resoluções espaciais e frequências orbitais distintas:

| Família / Sensor | Exemplos na série do DF | Dimensão do pixel no solo | Área nominal do pixel | Órbita típica |
| :--- | :--- | :--- | :--- | :--- |
| **VIIRS** (`I-Band`) | `NPP-375`, `NPP-375D`, `NOAA-20`, `NOAA-21` | `375 m x 375 m` | `~14,1 ha` (`~0,14 km²`) | Polar (alta resolução espacial) |
| **MODIS** (`AQUA_M-T`, Referência) | `AQUA_M-T`, `TERRA_M-M`, `TERRA_M-T` | `1.000 m x 1.000 m` | `~100,0 ha` (`1,00 km²`) | Polar (série climatológica do INPE) |
| **AVHRR / Outros** | `NOAA-18`, `NOAA-19`, `METOP-B`, `METOP-C` | `1.100 m x 1.100 m` | `~121,0 ha` (`~1,21 km²`) | Polar |
| **ABI / SEVIRI** (Geoestacionário) | `GOES-16`, `GOES-19`, `MSG-03` | `2.000 m x 2.000 m` | `~400,0 ha` (`4,00 km²`) | Geoestacionária (varredura a cada 10 a 15 min) |

Para conciliar cobertura espacial com consistência histórica, o projeto separa dois usos:

- **Tendência temporal interanual:** utiliza a flag `is_satelite_referencia` (`AQUA_M-T`, passagem vespertina com pixel de `1 km²`), seguindo o protocolo do INPE para evitar que a entrada de sensores de `375 m` (a partir de 2016) infle a comparação entre anos.
- **Detecção em imóveis rurais:** utiliza todos os 20 satélites para cobrir propriedades menores, neutralizando múltiplas passagens no mesmo incêndio por meio da contagem de **dias distintos com foco** (`dias_com_foco`) e do piso de área de `14,1 ha` (1 pixel VIIRS) no cálculo de densidade.

Recortes de escopo e descartes de extração: [Decisões e Descartes, seção 1](decisoes_descartes.md#1-origens-escopo-e-extracao).

---

## 2. Padronização Cartográfica, Saneamento e Histórico Cadastral

### Referencial métrico (`EPSG:31983`) e saneamento geométrico

Todas as camadas vetoriais e coordenadas de focos são convertidas na entrada para o sistema projetado **SIRGAS 2000 / UTM zona 23S (`EPSG:31983`)**, referencial métrico oficial do Distrito Federal ([ADR 0001](adr/01-adotar-postgresql-com-postgis-camada-gold.md)). Operar diretamente em metros permite aplicar predicados de distância (`ST_DWithin`) e calcular áreas em hectares (`ST_Area / 10000`) sem distorções angulares de coordenadas geográficas (`EPSG:4326`).

Na carga para o PostGIS ([`src/pipeline/load_camadas.py`](https://github.com/BeyondMagic/corta-fogo-df/blob/main/src/pipeline/load_camadas.py)), cada polígono passa por validação topológica (`ST_IsValid`). Geometrias com autointerseções ou anéis abertos são corrigidas com `make_valid` e normalizadas para `MultiPolygon`, descartando artefatos lineares ou pontuais residuais. As tabelas recebem índice espacial `GiST` e restrição `CHECK (ST_IsValid(geom))`.

### Identidade determinística e separação de carimbos temporais

Na ingestão para o Delta Lake ([`src/pipeline/batch_ingest.py`](https://github.com/BeyondMagic/corta-fogo-df/blob/main/src/pipeline/batch_ingest.py), [ADR 0002](adr/02-mecanismo-de-ingestao-e-formato-aberto.md)), cada foco recebe chave primária determinística `id_foco` calculada via `SHA-256` sobre latitude e longitude arredondadas a 5 casas decimais (`~1,1 m`), timestamp UTC da passagem e nome do satélite. O contrato separa:

- `data_hora_evento`: instante UTC da passagem do satélite, usado para particionamento físico (`ano=YYYY/mes=MM`) e cruzamento histórico.
- `data_hora_ingestao`: instante de chegada na camada analítica, usado para controle de versão e auditoria de processamento.

### Histórico cadastral do imóvel (`SCD Tipo 2`)

Imóveis rurais no SICAR sofrem retificações de perímetro, alterações de área e mudanças de status (`AT`, `PE`, `SU`, `CA`) ou exclusão. Para evitar que uma alteração recente reescreva o passado, as mutações capturadas via replicação lógica do PostgreSQL ([`src/pipeline/cdc_consumer.py`](https://github.com/BeyondMagic/corta-fogo-df/blob/main/src/pipeline/cdc_consumer.py)) alimentam o snapshot [`snp_imovel_car`](https://github.com/BeyondMagic/corta-fogo-df/blob/main/transformacao/snapshots/snp_imovel_car.yml) e o modelo [`int_imoveis_versoes.sql`](https://github.com/BeyondMagic/corta-fogo-df/blob/main/transformacao/models/intermediate/int_imoveis_versoes.sql), materializados em `dim_imovel_car`:

- Cada versão distinta de conteúdo recebe `sk_imovel = md5(cod_imovel || '|' || lsn_origem)` e intervalo de vigência `[dbt_valid_from, dbt_valid_to)`.
- O cruzamento espacial em [`int_focos_imoveis.sql`](https://github.com/BeyondMagic/corta-fogo-df/blob/main/transformacao/models/intermediate/int_focos_imoveis.sql) exige simultaneamente interseção espacial (`ST_Intersects`) e vigência temporal na data do evento (`dbt_valid_from <= data_hora_evento < dbt_valid_to`, com `not is_excluido`).

Contagens de saneamento e regras de armazenamento: [Decisões e Descartes, seção 2](decisoes_descartes.md#2-saneamento-deduplicacao-e-armazenamento-bronze-e-silver).

---

## 3. Cruzamentos Espaciais, Reincidência e Priorização (IPV)

### Critérios espaciais de área protegida e Região Administrativa

Um foco ocorrido dentro do perímetro vigente de um imóvel rural ([`int_focos_protegidos_imovel.sql`](https://github.com/BeyondMagic/corta-fogo-df/blob/main/transformacao/models/intermediate/int_focos_protegidos_imovel.sql)) é contabilizado para a pergunta de gestão quando satisfaz ao menos uma das três condições espaciais em [`int_focos_areas_protegidas.sql`](https://github.com/BeyondMagic/corta-fogo-df/blob/main/transformacao/models/intermediate/int_focos_areas_protegidas.sql):

1. **Reserva Legal do próprio imóvel (`em_reserva_legal_do_imovel`):** `ST_Intersects(foco.geom, rl.geom)` combinado com a exigência de titularidade `rl.cod_imovel = imovel.cod_imovel`.
2. **Área de Preservação Permanente (`em_app`):** `ST_Intersects(foco.geom, app.geom)` contra as feições físicas mapeadas pelo IBRAM.
3. **Proximidade de Unidade de Conservação (`ate_1km_uc`):** `ST_DWithin(foco.geom, uc.geom, 1000)`, capturando focos internos à UC ou em sua faixa de amortecimento de `1.000 m`.

Para localização territorial ([`atribuir_regiao_administrativa.sql`](https://github.com/BeyondMagic/corta-fogo-df/blob/main/transformacao/macros/atribuir_regiao_administrativa.sql)), cada foco usa sua coordenada pontual e cada imóvel usa um ponto garantido no interior de seu polígono (`ST_PointOnSurface(geom)`), evitando duplicação quando uma fazenda atravessa a divisa entre duas Regiões Administrativas. Pontos na borda do DF são associados à RA mais próxima até o limite de `2.000 m`.

### Regra de reincidência e Índice de Prioridade de Vistoria (IPV)

No modelo [`int_metricas_imovel.sql`](https://github.com/BeyondMagic/corta-fogo-df/blob/main/transformacao/models/intermediate/int_metricas_imovel.sql), os eventos protegidos são agregados por `cod_imovel`. Como cadastros autodeclaratórios no SICAR podem se sobrepor geograficamente, a tabela fato atômica (`fato_foco_calor`, `38.944` linhas) mantém grão de 1 linha por foco sem multiplicar registros por imóvel, enquanto o fato por imóvel (`fct_reincidencia_imovel`, `4.068` imóveis atingidos) consolida a contagem de anos, dias e focos de cada cadastro ([esquema dimensional Gold](modelagem/esquema_dimensional_gold.md)).

- **Elegibilidade de reincidência:** `anos_com_foco >= 2` (foco em área protegida em pelo menos 2 anos civis distintos entre 2015 e 2025), resultando em **1.593 imóveis reincidentes**.
- **Ordenação da fila ([ADR 0005](adr/05-indice-de-prioridade-de-vistoria.md)):** para impedir que fazendas extensas (mediana de `25.808 ha` no top 10 por contagem bruta) ou chácaras minúsculas distorçam a priorização, [`int_indice_prioridade_imovel.sql`](https://github.com/BeyondMagic/corta-fogo-df/blob/main/transformacao/models/intermediate/int_indice_prioridade_imovel.sql) calcula o IPV de `0` a `100`:

```text
IPV = 100 x (0,4 x recorrência + 0,3 x recência + 0,3 x intensidade)
```

| Componente | Peso | Regra de cálculo e normalização (`0` a `1`) |
| :--- | :---: | :--- |
| **Recorrência** | `0,4` | `(anos_com_foco - 2) / (11 - 2)`: varia linearmente de 2 anos (`0,0`) a 11 anos (`1,0`). |
| **Recência** | `0,3` | `(ultimo_ano_com_foco - 2015) / (2025 - 2015)`: varia de 2015 (`0,0`) a 2025 (`1,0`). |
| **Intensidade** | `0,3` | `dias_com_foco / greatest(area_ha, 14,1) * 100`, truncada nos percentis 5 e 95 dos reincidentes e normalizada via min-max. |

Os imóveis reincidentes são divididos por quartis do IPV (`PRIORIDADE CRITICA`, `ALTA`, `MEDIA` e `BAIXA`) e ordenados em `gold.painel_imoveis_prioritarios` desempatando por `anos_com_foco DESC`, `dias_com_foco DESC` e `cod_imovel ASC`.

Regras de fuso horário, estação seca, situação cadastral e otimizações de consulta: [Decisões e Descartes, seção 3](decisoes_descartes.md#3-cruzamentos-espaciais-tempo-e-ordenacao-gold).

---

## 4. Validação Cruzada, Consumo e Limitações

### Reconciliação entre motores e testes de domínio

A camada analítica passa por três níveis de verificação a cada execução do `dbt build` (259 testes de dados e 1 teste unitário):

1. **Reconciliação PostGIS vs. DuckDB ([ADR 0006](adr/06-ingestao-seletiva-delta-e-leitura-postgis.md)):** o teste [`reconcilia_fato_imovel_com_mv_postgis.sql`](https://github.com/BeyondMagic/corta-fogo-df/blob/main/transformacao/tests/reconcilia_fato_imovel_com_mv_postgis.sql) compara os `1.593` imóveis reincidentes, contagens de focos, anos e flags territoriais calculados no `dbt-duckdb` contra a visão materializada independente `gold.mv_imoveis_reincidentes_areas_protegidas` (`V9`) no PostGIS (0 divergências na carga de referência).
2. **Testes singulares contra erros silenciosos:** verificam no repositório de testes [`transformacao/tests/`](https://github.com/BeyondMagic/corta-fogo-df/tree/main/transformacao/tests) se todo ano possui ao menos `500` focos totais e `80` no satélite `AQUA_M-T`, se a estação seca (maio a setembro) concentra ao menos `70%` dos focos e se todas as geometrias permanecem no retângulo envolvente do DF.
3. **Teste unitário de SCD Tipo 2 e SLA de frescor:** valida a preservação histórica de perímetros retificados e monitora de hora em hora no Dagster se a tabela de consumo foi atualizada dentro da janela de `30 horas` ([Frescor e SLA](frescor_sla.md)).

### De onde vêm os dados do painel e do banco operacional

O consumo analítico e operacional é desacoplado do processamento pesado por dois fluxos gerados após o `dbt build`:

| Artefato / Destino | Gerado por | Fonte de leitura | Conteúdo e Papel |
| :--- | :--- | :--- | :--- |
| `docs/assets/dados_dashboard/gold.json` | [`scripts/exportar_painel_gold.py`](https://github.com/BeyondMagic/corta-fogo-df/blob/main/scripts/exportar_painel_gold.py) | `gold.painel_imoveis_prioritarios` e `gold.fct_reincidencia_imovel` (DuckDB) | Resposta oficial à pergunta de gestão ([ADR 0004](adr/04-disponibilizacao-contrato-dbt-e-retrato-estatico.md)): totais, distribuições, fila de vistoria ordenada pelo IPV, carimbo `gerado_em` e polígonos simplificados (`60 m`) dos 50 primeiros imóveis |
| `operacional.fila_vistoria` (PostgreSQL) | [`src/pipeline/etl_reverso.py`](https://github.com/BeyondMagic/corta-fogo-df/blob/main/src/pipeline/etl_reverso.py) | `gold.painel_imoveis_prioritarios` (DuckDB) | Retorno idempotente dos 1.593 reincidentes ao banco operacional, com controle de acesso por papel e preservação de `status_vistoria` ([ETL Reverso e Acesso](etl_reverso_e_acesso.md)) |
| `resumo.json`, `geometrias.json`, `focos.json` | [`scripts/gerar_dados_dashboard.py`](https://github.com/BeyondMagic/corta-fogo-df/blob/main/scripts/gerar_dados_dashboard.py) | `data/processed/` e `data/raw/` | Séries auxiliares de exploração visual do mapa (histórico por sensor, malha de RAs e UCs) |

Para regenerar o retrato oficial do painel após executar a transformação:

```bash
docker compose --profile transformacao run --rm exportar_painel
```

Recortes de privacidade (LGPD), diferenças dos arquivos exploratórios e limitações conhecidas: [Decisões e Descartes, seções 4 e 5](decisoes_descartes.md#4-validacao-orquestracao-e-consumo-no-painel).
