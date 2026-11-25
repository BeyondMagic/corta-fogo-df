---
icon: material/compass-outline
---

# :material-compass-outline: Metodologia

<p class="apresentador"><em>Responsáveis: Elias F. e Gabriel Fernando</em></p>

A metodologia define **como** o projeto mede ocorrências térmicas, cruza limites territoriais e prioriza imóveis rurais para fiscalização. A **Gold** é a **camada semântica** da plataforma: concentra entidades e métricas com significado de negócio, definição única em [`dbt_project.yml`](https://github.com/BeyondMagic/corta-fogo-df/blob/main/transformacao/dbt_project.yml) e contrato de esquema para consumo no [Dashboard](dashboard.md), em consultas SQL e no [ETL reverso](etl_reverso_e_acesso.md). Já a camada **intermediate** (`int_*`) não é semântica: atua apenas como etapa interna de cruzamentos espaciais e agregações dentro da Silver ([esquema dimensional Gold](modelagem/esquema_dimensional_gold.md)). Os recortes de escopo, tratamentos de anomalias e alternativas descartadas estão documentados de forma espelhada em [Decisões e Descartes](decisoes_descartes.md).

## O que a camada semântica Gold entrega

Em quatro regras:

1. Contabiliza apenas focos incidentes em **Reserva Legal do próprio imóvel**, **APP** ou a até **1 km de UC**.
2. Define **reincidente** como o imóvel com foco protegido em **2 anos civis ou mais** (`2015` a `2025`).
3. Ordena a fila de vistoria pelo **IPV** ([ADR 0005](adr/05-indice-de-prioridade-de-vistoria.md)) em `gold.painel_imoveis_prioritarios`, servindo simultaneamente `gold.json` ([ADR 0004](adr/04-disponibilizacao-contrato-dbt-e-retrato-estatico.md)) e `operacional.fila_vistoria`.
4. Cruza cada foco com o **perímetro vigente na época** do evento (`SCD Tipo 2`), sem reescrever o passado com retificações recentes.

**Separação Silver (`int_*`) vs. Gold (semântica):** modelos `int_*` executam junções espaciais e cálculos intermediários; apenas modelos Gold (`dim_*`, `fato_*`, `fct_*`, `mart_*`, `painel_*`) expõem métricas oficiais ao consumo.

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

### Ingestão seletiva no Delta Lake e leitura direta no PostGIS

O armazenamento aberto em Delta Lake ([ADR 0002](adr/02-mecanismo-de-ingestao-e-formato-aberto.md)) recebe seletivamente as duas tabelas com dinâmica temporal contínua: `foco_calor` (série histórica crescente ingerida em lote particionado) e `imovel_car` (cadastro fundiário sujeito a retificações e exclusões via CDC). As quatro camadas públicas de referência (`unidade_conservacao`, `area_preservacao_permanente`, `reserva_legal` e `regiao_administrativa`, somando `15.854` feições quase estáticas) permanecem no PostGIS e são anexadas pelo `dbt-duckdb` via extensão `postgres` em modo `READ_ONLY` ([`transformacao/profiles.yml`](https://github.com/BeyondMagic/corta-fogo-df/blob/main/transformacao/profiles.yml)). Essa divisão evita quatro pipelines redundantes de replicação, reaproveita a validação `ST_IsValid` da carga relacional e preserva o PostGIS como linha de base independente para reconciliação espacial.

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

### Sobreposição cadastral no SICAR, reincidência e Índice de Prioridade de Vistoria (IPV)

Cadastros autodeclaratórios no SICAR apresentam sobreposições geográficas frequentes: os `35.013` focos situados dentro da malha rural geram `76.115` pares foco-imóvel em [`int_focos_imoveis.sql`](https://github.com/BeyondMagic/corta-fogo-df/blob/main/transformacao/models/intermediate/int_focos_imoveis.sql). Para impedir inflação nas estatísticas do Distrito Federal e ainda responsabilizar cada matrícula atingida em áreas de litígio, a modelagem separa dois grãos ([esquema dimensional Gold](modelagem/esquema_dimensional_gold.md)):

- **Grão do evento térmico (`fato_foco_calor`, `38.944` linhas):** uma linha única por detecção orbital, usada em todos os totais anuais, sazonais e por Região Administrativa do DF.
- **Grão do sujeito fiscalizado (`fct_reincidencia_imovel`, `4.068` imóveis atingidos):** agrega em [`int_metricas_imovel.sql`](https://github.com/BeyondMagic/corta-fogo-df/blob/main/transformacao/models/intermediate/int_metricas_imovel.sql) os eventos protegidos de cada `cod_imovel`. Um foco sobre dois imóveis sobrepostos conta em ambos os cadastros para fins de vistoria, somando `37.693` ocorrências foco-imóvel nos reincidentes sem alterar o total de focos do DF.

A partir desse grão por imóvel aplicam-se as regras de negócio de seleção e priorização:

- **Elegibilidade de reincidência:** `anos_com_foco >= 2` (foco em área protegida em pelo menos 2 anos civis distintos entre 2015 e 2025), resultando em **1.593 imóveis reincidentes**.
- **Visão de gestão vs. visão operacional de campo (situação cadastral):** na camada Gold (`painel_imoveis_prioritarios` e `gold.json`), cadastros pendentes (`107 PE`), suspensos (`41 SU`) e cancelados (`32 CA`) permanecem visíveis ao lado dos ativos (`1.413 AT`), marcados por `cadastro_ativo = false`, pois cancelamento cadastral não extingue passivo ambiental. Apenas exclusões lógicas do CDC (`is_excluido = true`) saem da tabela. Já no retorno operacional ao PostgreSQL (`operacional.fila_vistoria`), uma política de *Row-Level Security* filtra a visão do papel `fiscal_vistoria` exclusivamente aos **1.413 imóveis ativos** (`na_fila AND cadastro_ativo`), direcionando equipes de campo apenas a matrículas vigentes.
- **Ordenação da fila ([ADR 0005](adr/05-indice-de-prioridade-de-vistoria.md)):** para impedir que fazendas extensas (mediana de `25.808 ha` no top 10 por contagem bruta) ou chácaras minúsculas distorçam a priorização, [`int_indice_prioridade_imovel.sql`](https://github.com/BeyondMagic/corta-fogo-df/blob/main/transformacao/models/intermediate/int_indice_prioridade_imovel.sql) calcula o IPV de `0` a `100` com parâmetros centralizados em `dbt_project.yml`:

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

## 4. Validação Cruzada, Consumo Duplo e Governança

### Reconciliação entre motores e testes de domínio

A camada analítica passa por três níveis de verificação a cada execução do `dbt build` (259 testes de dados e 1 teste unitário):

1. **Reconciliação PostGIS vs. DuckDB ([Decisões e Descartes, seção 2](decisoes_descartes.md#2-saneamento-deduplicacao-e-armazenamento-bronze-e-silver)):** o teste [`reconcilia_fato_imovel_com_mv_postgis.sql`](https://github.com/BeyondMagic/corta-fogo-df/blob/main/transformacao/tests/reconcilia_fato_imovel_com_mv_postgis.sql) compara os `1.593` imóveis reincidentes, contagens de focos, anos e flags territoriais calculados no `dbt-duckdb` (motor DuckDB Spatial) contra a visão materializada independente `gold.mv_imoveis_reincidentes_areas_protegidas` (`V9`, motor GEOS no PostGIS), registrando `0` divergências na carga de referência.
2. **Testes singulares contra erros silenciosos:** verificam em [`transformacao/tests/`](https://github.com/BeyondMagic/corta-fogo-df/tree/main/transformacao/tests) se todo ano possui ao menos `500` focos totais e `80` no satélite `AQUA_M-T`, se a estação seca (maio a setembro) concentra ao menos `70%` dos focos e se todas as geometrias permanecem no retângulo envolvente do DF.
3. **Teste unitário de SCD Tipo 2 e SLA de frescor:** valida a preservação histórica de perímetros retificados e monitora de hora em hora no Dagster se a tabela de consumo foi atualizada dentro da janela de `30 horas` ([Frescor e SLA](frescor_sla.md)).

### Camada semântica única, consumo duplo e retorno operacional

Para eliminar divergência de cálculo entre telas, relatórios e operação, todos os limiares da regra de negócio (`raio_uc_m`, `anos_minimos_reincidencia`, pesos do IPV e `area_minima_ha`) são versionados em um único arquivo ([`transformacao/dbt_project.yml`](https://github.com/BeyondMagic/corta-fogo-df/blob/main/transformacao/dbt_project.yml)) e materializados em `gold.painel_imoveis_prioritarios` sob contrato estrito de colunas e tipos (`contract: enforced: true`). Nenhum consumidor recalcula cruzamentos ou índices:

| Artefato / Destino | Gerado por | Fonte de leitura | Conteúdo e Papel |
| :--- | :--- | :--- | :--- |
| `docs/assets/dados_dashboard/gold.json` | [`scripts/exportar_painel_gold.py`](https://github.com/BeyondMagic/corta-fogo-df/blob/main/scripts/exportar_painel_gold.py) | `gold.painel_imoveis_prioritarios` e `gold.fct_reincidencia_imovel` (DuckDB) | Consumo analítico web ([ADR 0004](adr/04-disponibilizacao-contrato-dbt-e-retrato-estatico.md)): totais, distribuições, fila ordenada pelo IPV, carimbo `gerado_em` e polígonos simplificados (`60 m`) dos 50 primeiros imóveis |
| `analyses/consulta_pergunta_gestao.sql` e `resumo_pergunta_gestao.sql` | `dbt show` sobre a camada semântica | `gold.painel_imoveis_prioritarios` e `gold.fct_reincidencia_imovel` (DuckDB) | Consumo analítico tabular direto sobre os `1.593` reincidentes completos, sem limite de 50 posições |
| `operacional.fila_vistoria` (PostgreSQL) | [`src/pipeline/etl_reverso.py`](https://github.com/BeyondMagic/corta-fogo-df/blob/main/src/pipeline/etl_reverso.py) | `gold.painel_imoveis_prioritarios` (DuckDB) | Retorno operacional idempotente ao PostgreSQL (`V10`): preserva `status_vistoria` e `observacao` registrados pelo fiscal, aplica RLS (`1.413` ativos para `fiscal_vistoria`) e restringe `geom` em `analista_leitura` por minimização de LGPD ([ETL Reverso e Acesso](etl_reverso_e_acesso.md)) |
| `resumo.json`, `geometrias.json`, `focos.json` | [`scripts/gerar_dados_dashboard.py`](https://github.com/BeyondMagic/corta-fogo-df/blob/main/scripts/gerar_dados_dashboard.py) | `data/processed/` e `data/raw/` | Séries auxiliares de exploração visual do mapa (histórico geral por sensor, malha de RAs e UCs) |

Para regenerar o retrato do painel e atualizar a fila operacional após executar o `dbt build`:

```bash
docker compose --profile transformacao run --rm exportar_painel
docker compose --profile transformacao run --rm etl_reverso
```

Recortes de privacidade (LGPD), regras de privilégio mínimo, diferenças dos arquivos exploratórios e limitações conhecidas: [Decisões e Descartes, seções 4 e 5](decisoes_descartes.md#4-validacao-orquestracao-consumo-duplo-e-governanca).
