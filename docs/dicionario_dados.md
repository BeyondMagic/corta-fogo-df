---
icon: material/book-alphabet
---

# :material-book-alphabet: Dicionário de Dados

Catálogo técnico formal de entidades, atributos, tipos, restrições e regras de negócio da plataforma Corta-Fogo DF, estruturado segundo a arquitetura reversa: iniciando pela camada de consumo analítico (**Gold**), passando pelo armazenamento aberto em tabelas Delta (**Silver**) e concluindo nas estruturas transacionais e de entrada bruta (**Bronze**).

---

## Convenções Gerais e Padrões Arquiteturais

1. **Sistemas de Coordenadas (CRS):**
   - **`EPSG:31983` (SIRGAS 2000 / UTM zone 23S):** padrão métrico unificado de todo o banco de dados e dos cálculos espaciais. Permite avaliar distâncias euclidianas planas em metros (`ST_DWithin`) sem necessidade de projeções intermediárias ou custo de cálculo geodésico sobre esferoide.
   - **`EPSG:4326` (WGS 84):** padrão angular (graus decimais de latitude e longitude) utilizado exclusivamente no arquivo de intercâmbio do Leaflet e na ingestão original do INPE.
2. **Chaves Substitutas (Surrogate Keys):**
   - As dimensões analíticas adotam chaves substitutas determinísticas (`sk_*`), geradas via funções de resumo criptográfico (MD5) sobre chaves naturais ou representações textuais canônicas (WKT), garantindo estabilidade entre recargas do ambiente.
3. **Padrão Temporal Bitemporal:**
   - As tabelas de eventos distinguem formalmente o tempo válido (`data_hora_evento`, momento da detecção do satélite) do tempo de transação (`data_hora_ingestao`, momento em que o registro foi gravado na camada analítica ou banco de dados).

---

## 1. Camada Gold (Consumo Analítico e Pergunta de Gestão)

A camada Gold é responsável por alimentar diretamente as consultas analíticas, painéis geoespaciais e o cálculo de conformidade da pergunta de gestão declarada na E1. Seus modelos são gerenciados pelo dbt com motor DuckDB (`transformacao/models/marts/`) e pela visão materializada consolidada do PostgreSQL (`gold.mv_imoveis_reincidentes_areas_protegidas`).

### 1.1 `mart_reincidencia_imovel_ano`

Materializa as métricas anuais da pergunta de gestão por imóvel rural, identificando reincidência temporal e sobreposição a áreas protegidas.

- **Granularidade:** uma linha por imóvel rural por ano civil UTC (2015 a 2025) em que houve registro de foco dentro do imóvel e simultaneamente em área protegida (Reserva Legal do próprio imóvel, APP ou raio de amortecimento de 1.000 metros de Unidade de Conservação).
- **Tipo de Objeto:** Tabela física dbt (DuckDB / Delta Lake).

| Coluna | Tipo | Chave / Restrição | Descrição e Regra de Negócio | Origem / Linhagem |
| :--- | :--- | :--- | :--- | :--- |
| `cod_imovel` | `VARCHAR(60)` | PK composta / FK | Código identificador natural do imóvel no SICAR (padrão `DF-...`). | `dim_imovel_car.cod_imovel` |
| `ano` | `INTEGER` | PK composta / NOT NULL | Ano civil UTC do evento (entre 2015 e 2025). | `fato_foco_calor.ano` |
| `sk_imovel` | `VARCHAR(32)` | FK / NOT NULL | Chave substituta da versão cadastral SCD Tipo 2 do imóvel vigente na passagem do foco mais recente daquele ano. | `dim_imovel_car.sk_imovel` |
| `total_focos` | `BIGINT` | Medida / NOT NULL | Contagem de focos distintos registrados no perímetro do imóvel que incidiram em área protegida naquele ano. | `count(DISTINCT id_foco)` |
| `atinge_reserva_legal` | `BOOLEAN` | Flag / NOT NULL | Verdadeiro se ao menos um foco atingiu a Reserva Legal averbada ou declarada do próprio imóvel no ano. | `bool_or(em_reserva_legal)` |
| `atinge_app` | `BOOLEAN` | Flag / NOT NULL | Verdadeiro se ao menos um foco atingiu Área de Preservação Permanente (hidrografia, nascente ou encosta) no ano. | `bool_or(em_app)` |
| `atinge_uc_1km` | `BOOLEAN` | Flag / NOT NULL | Verdadeiro se ao menos um foco ocorreu dentro da faixa de amortecimento de 1.000 metros de Unidade de Conservação no ano. | `bool_or(ate_1km_uc)` |
| `anos_com_foco_protegido` | `INTEGER` | Métrica / NOT NULL | Quantidade acumulada de anos distintos em que o imóvel apresentou focos sob critérios de proteção em toda a série de 11 anos. | `count(DISTINCT ano) OVER (PARTITION BY cod_imovel)` |
| `lista_anos_protegidos` | `VARCHAR[]` | Métrica / NOT NULL | Vetor ordenado com os anos específicos em que foram constatadas queimadas incidentes no imóvel. | `array_agg(DISTINCT ano ORDER BY ano)` |
| `imovel_reincidente` | `BOOLEAN` | Regra / NOT NULL | Indicador de reincidência crítica: verdadeiro quando `anos_com_foco_protegido >= 2`. Núcleo da resposta à pergunta de gestão. | Expressão analítica booleana |

---

### 1.2 `fato_foco_calor`

Tabela fato atômica do modelo dimensional estrela. Não multiplica linhas por cruzamentos territoriais.

- **Granularidade:** uma linha por detecção de foco de calor no tempo e no espaço por sensor orbital (`id_foco`).
- **Tipo de Objeto:** Tabela física dbt (DuckDB / Delta Lake).

| Coluna | Tipo | Chave / Restrição | Descrição e Regra de Negócio | Origem / Linhagem |
| :--- | :--- | :--- | :--- | :--- |
| `id_foco` | `VARCHAR(64)` | PK / NOT NULL | Hash SHA-256 determinístico derivado de latitude, longitude, data/hora do evento e nome do satélite. | `stg_focos_calor.id_foco` |
| `sk_tempo` | `INTEGER` | FK / NOT NULL | Chave para `dim_tempo` no formato numérico `YYYYMMDD`, calculada a partir da data no fuso horário local de Brasília. | `dim_tempo.sk_tempo` |
| `sk_satelite` | `VARCHAR(32)` | FK / NOT NULL | Chave substituta para `dim_satelite` (MD5 do nome do satélite em caixa alta). | `dim_satelite.sk_satelite` |
| `satelite` | `VARCHAR(40)` | Atributo degenerado | Nome do satélite detector (ex: `AQUA_M-T`, `NOAA-20`). | `stg_focos_calor.satelite` |
| `is_satelite_referencia` | `BOOLEAN` | Flag / NOT NULL | Verdadeiro quando captado pelo satélite de referência oficial do INPE (`AQUA_M-T`), usado para análises temporais livres de viés amostral. | `stg_focos_calor.is_satelite_referencia` |
| `data_hora_evento` | `TIMESTAMPTZ` | Temporal / NOT NULL | Carimbo UTC do instante exato de detecção térmica pela passagem orbital. | `stg_focos_calor.data_hora_evento` |
| `data_hora_ingestao` | `TIMESTAMPTZ` | Auditoria / NOT NULL | Carimbo UTC do momento de gravação do registro na camada analítica do Lakehouse. | `stg_focos_calor.data_hora_ingestao` |
| `data_evento_local` | `DATE` | Temporal / NOT NULL | Data civil convertida para o fuso local (`America/Sao_Paulo`). | Conversão temporal da passagem |
| `ano` | `INTEGER` | Partição / NOT NULL | Ano civil UTC do evento (2015 a 2025). | `date_part('year', data_hora_evento)` |
| `mes` | `INTEGER` | Partição / NOT NULL | Mês civil UTC do evento (1 a 12). | `date_part('month', data_hora_evento)` |
| `latitude` | `DOUBLE` | Espacial / NOT NULL | Latitude geográfica expressa em graus decimais (WGS 84, EPSG:4326), correspondendo ao centroide do pixel do sensor orbital. | `stg_focos_calor.latitude` |
| `longitude` | `DOUBLE` | Espacial / NOT NULL | Longitude geográfica expressa em graus decimais (WGS 84, EPSG:4326), correspondendo ao centroide do pixel do sensor orbital. | `stg_focos_calor.longitude` |
| `x_31983` | `DOUBLE` | Métrica / NOT NULL | Coordenada plana Leste (Easting) projetada em metros (SIRGAS 2000 UTM 23S). | `stg_focos_calor.x_31983` |
| `y_31983` | `DOUBLE` | Métrica / NOT NULL | Coordenada plana Norte (Northing) projetada em metros (SIRGAS 2000 UTM 23S). | `stg_focos_calor.y_31983` |
| `geom` | `GEOMETRY` | Espacial / NOT NULL | Ponto geométrico bidimensional com SRID fixo em EPSG:31983. Representa o centroide do pixel do satélite (pegada nominal de 375 m a 1.000 m no solo, e não o polígono contínuo da cicatriz de queima). | `ST_Point(x_31983, y_31983)` |
| `origem_ingestao` | `VARCHAR(20)` | Linhagem / NOT NULL | Identificador do canal de extração de origem (sempre `lote`). | Constante de pipeline |
| `operacao_cdc` | `VARCHAR(1)` | Linhagem / NOT NULL | Código de linhagem da operação (sempre `I` para inserção). | Constante de pipeline |
| `qtd_imoveis` | `INTEGER` | Métrica / NOT NULL | Quantidade de imóveis rurais cadastrados no CAR cujo perímetro contém o foco. | Junção espacial com `stg_imoveis_car` |
| `em_imovel_car` | `BOOLEAN` | Flag / NOT NULL | Verdadeiro se o ponto do foco intercepta ao menos um imóvel rural ativo do SICAR. | `qtd_imoveis > 0` |
| `em_reserva_legal` | `BOOLEAN` | Flag / NOT NULL | Verdadeiro se o ponto intercepta polígono cadastrado de Reserva Legal. | Interseção com `stg_reservas_legais` |
| `em_app` | `BOOLEAN` | Flag / NOT NULL | Verdadeiro se o ponto intercepta polígono de Área de Preservação Permanente. | Interseção com `stg_areas_preservacao_permanente` |
| `ate_1km_uc` | `BOOLEAN` | Flag / NOT NULL | Verdadeiro se o ponto situa-se a até 1.000 metros do limite de uma Unidade de Conservação. | Junção com `stg_unidades_conservacao` |
| `distancia_min_uc_m` | `DOUBLE` | Métrica | Menor distância euclidiana exata calculada em metros até a borda de uma UC (nulo se fora da faixa de 1 km). | `ST_Distance(geom, uc_geom)` |
| `em_area_protegida` | `BOOLEAN` | Regra / NOT NULL | Verdadeiro quando o foco atende a qualquer um dos três critérios de proteção ambiental (RL, APP ou UC a 1 km). | `em_reserva_legal OR em_app OR ate_1km_uc` |

---

### 1.3 `dim_imovel_car`

Dimensão com suporte a Histórico de Variação Lenta (SCD Tipo 2), derivada do snapshot dbt (`snp_imovel_car`).

- **Granularidade:** uma linha por versão cadastral de imóvel rural do SICAR/DF (`cod_imovel`, `dbt_valid_from`).
- **Tipo de Objeto:** Tabela física dbt (DuckDB / Delta Lake).

| Coluna | Tipo | Chave / Restrição | Descrição e Regra de Negócio | Origem / Linhagem |
| :--- | :--- | :--- | :--- | :--- |
| `sk_imovel` | `VARCHAR(32)` | PK / NOT NULL | Chave substituta determinística da versão: MD5 de `cod_imovel` concatenado a `lsn_origem`. | `md5(cod_imovel \|\| lsn_origem)` |
| `cod_imovel` | `VARCHAR(60)` | Chave Natural / NOT NULL | Código identificador oficial do imóvel rural no padrão SICAR (`DF-...`). | `stg_imoveis_car.cod_imovel` |
| `numero_versao` | `INTEGER` | Sequencial / NOT NULL | Número incremental da versão dentro do ciclo de vida do imóvel (1 para a versão inicial). | `row_number() OVER (PARTITION BY cod_imovel ORDER BY dbt_valid_from)` |
| `situacao` | `VARCHAR(40)` | Atributo | Situação cadastral do imóvel (`AT` = Ativo, `PE` = Pendente, `CA` = Cancelado, `SU` = Suspenso). | `stg_imoveis_car.situacao` |
| `condicao` | `VARCHAR(200)` | Atributo | Condição descritiva da análise cadastral pelo órgão ambiental. | `stg_imoveis_car.condicao` |
| `area_ha` | `NUMERIC(14,4)` | Métrica | Área total do imóvel rural declarada no cadastro em hectares. | `stg_imoveis_car.area_ha` |
| `data_download` | `DATE` | Metadado | Data em que o lote original foi extraído junto ao repositório de dados abertos do SICAR. | `stg_imoveis_car.data_download` |
| `geom_ewkb_hex` | `VARCHAR` | Serialização / NOT NULL | Perímetro do imóvel serializado em formato EWKB hexadecimal com SRID 31983. | `stg_imoveis_car.geom_ewkb_hex` |
| `geom` | `GEOMETRY` | Espacial / NOT NULL | Polígono ou multipolígono métrico reprojetado em EPSG:31983. | Conversão de `geom_ewkb_hex` |
| `is_excluido` | `BOOLEAN` | Lógica / NOT NULL | Verdadeiro quando a versão registra a inativação ou exclusão lógica do imóvel via evento de CDC. | `operacao_cdc = 'D'` |
| `operacao_cdc` | `VARCHAR(1)` | Linhagem / NOT NULL | Operação capturada no log de transações do PostgreSQL (`I` = Insert, `U` = Update, `D` = Delete). | Consumidor CDC / Debezium |
| `lsn_origem` | `BIGINT` | Linhagem / NOT NULL | Log Sequence Number (LSN) do PostgreSQL, garantindo ordenação estrita e idempotência contra reentregas. | Consumidor CDC |
| `data_hora_ingestao` | `TIMESTAMPTZ` | Auditoria / NOT NULL | Carimbo UTC do momento de inserção da linha na tabela analítica. | Timestamp de escrita |
| `dbt_valid_from` | `TIMESTAMPTZ` | Vigência / NOT NULL | Início da vigência da versão cadastral (inclusivo). Para a primeira versão histórica, adota data aberta (`1900-01-01`). | Mecanismo de Snapshot dbt |
| `dbt_valid_to` | `TIMESTAMPTZ` | Vigência / NOT NULL | Fim da vigência da versão (exclusivo). Na versão corrente, preenchido com data aberta futura (`9999-12-31`). | Mecanismo de Snapshot dbt |
| `is_current` | `BOOLEAN` | Flag / NOT NULL | Verdadeiro exclusivamente na versão cadastral corrente do imóvel rural (exatamente uma linha ativa por `cod_imovel`). | `dbt_valid_to = '9999-12-31'` |

---

### 1.4 `dim_territorio`

Dimensão consolidada de feições territoriais especialmente protegidas no Distrito Federal.

- **Granularidade:** uma linha por feição protegida: Unidade de Conservação, APP ou Reserva Legal (`sk_territorio`).
- **Tipo de Objeto:** Tabela física dbt (DuckDB / Delta Lake).

| Coluna | Tipo | Chave / Restrição | Descrição e Regra de Negócio | Origem / Linhagem |
| :--- | :--- | :--- | :--- | :--- |
| `sk_territorio` | `VARCHAR(32)` | PK / NOT NULL | Hash estável gerado a partir de `tipo_area` e representação WKT canônica da geometria, imune a recargas de contêineres. | `md5(tipo_area \|\| '\|' \|\| ST_AsText(geom))` |
| `tipo_area` | `VARCHAR(30)` | Categoria / NOT NULL | Tipo da feição protegida: `unidade_conservacao`, `app` ou `reserva_legal`. | Identificador de camada de origem |
| `id_feicao_origem` | `BIGINT` | Auditoria / NOT NULL | Chave primária numérica original da tabela de origem no PostgreSQL (uso exclusivo para rastreabilidade de carga). | PK da tabela transacional |
| `nome_area` | `VARCHAR(200)` | Atributo | Nome oficial da Unidade de Conservação ou descrição tipológica da APP (nulo para Reserva Legal). | Fonte IBRAM / SICAR |
| `categoria_area` | `VARCHAR(100)` | Atributo | Categoria formal de manejo da UC (ex: Parque, ESEC), tipo de APP ou situação da RL. | Fonte IBRAM / SICAR |
| `grupo_area` | `VARCHAR(30)` | Atributo | Classificação conforme SNUC: `protecao_integral` ou `uso_sustentavel` (nulo em APP e RL). | `stg_unidades_conservacao.grupo` |
| `cod_imovel` | `VARCHAR(60)` | Atributo | Código do imóvel CAR proprietário da feição (presente em RL e APP individualizada; nulo em UCs). | Código SICAR do imóvel |
| `area_ha` | `NUMERIC(14,4)` | Métrica | Extensão territorial da feição expressa em hectares. | Atributo oficial da camada |
| `raio_amortecimento_m`| `DOUBLE` | Parâmetro / NOT NULL | Distância de amortecimento estipulada para a feição: 1.000 metros para UCs; 0 metros (interseção estrita) para RL e APP. | Regra de negócio do projeto |
| `data_download` | `DATE` | Metadado | Data do carimbo de download do pacote de dados brutos na fonte governamental. | Metadado de extração |
| `geom` | `GEOMETRY` | Espacial / NOT NULL | Polígono ou multipolígono métrico da área protegida em EPSG:31983. | Geometria reprojetada |

---

### 1.5 `dim_tempo`

Dimensão calendário gerada dinamicamente para o intervalo completo da série de dados (2015 a 2025).

- **Granularidade:** uma linha por data civil local no calendário de 2015-01-01 a 2025-12-31.
- **Tipo de Objeto:** Tabela física dbt (DuckDB / Delta Lake).

| Coluna | Tipo | Chave / Restrição | Descrição e Regra de Negócio | Origem / Linhagem |
| :--- | :--- | :--- | :--- | :--- |
| `sk_tempo` | `INTEGER` | PK / NOT NULL | Chave substituta numérica inteira no padrão `YYYYMMDD` (ex: `20240905`). | `ano * 10000 + mes * 100 + dia` |
| `data` | `DATE` | Temporal / NOT NULL | Data civil correspondente. | Série de datas gerada |
| `ano` | `INTEGER` | Atributo / NOT NULL | Ano civil de quatro dígitos (2015 a 2025). | `date_part('year', data)` |
| `mes` | `INTEGER` | Atributo / NOT NULL | Número do mês no ano (1 a 12). | `date_part('month', data)` |
| `dia` | `INTEGER` | Atributo / NOT NULL | Dia do mês civil (1 a 31). | `date_part('day', data)` |
| `nome_mes` | `VARCHAR(20)` | Atributo / NOT NULL | Nome por extenso do mês em língua portuguesa (ex: `Janeiro`, `Setembro`). | Formatação da data |
| `is_estacao_seca` | `BOOLEAN` | Regra / NOT NULL | Verdadeiro quando o mês situa-se entre maio e setembro (período oficial de estiagem severa no Cerrado do DF). | `mes BETWEEN 5 AND 9` |

---

### 1.6 `dim_satelite`

Dimensão dos sensores orbitais que operam na captação de anomalias térmicas espaciais.

- **Granularidade:** uma linha por sensor/satélite detector identificado na série histórica.
- **Tipo de Objeto:** Tabela física dbt (DuckDB / Delta Lake).

| Coluna | Tipo | Chave / Restrição | Descrição e Regra de Negócio | Origem / Linhagem |
| :--- | :--- | :--- | :--- | :--- |
| `sk_satelite` | `VARCHAR(32)` | PK / NOT NULL | Chave substituta gerada pelo hash MD5 do nome padronizado do satélite. | `md5(satelite)` |
| `satelite` | `VARCHAR(40)` | Chave Natural / NOT NULL | Nome oficial do satélite em letras maiúsculas (ex: `AQUA_M-T`, `TERRA_M-T`). | `stg_focos_calor.satelite` |
| `is_referencia` | `BOOLEAN` | Flag / NOT NULL | Verdadeiro exclusivamente para o satélite de referência padrão do INPE (`AQUA_M-T`). | Comparação nominal estrita |

---

### 1.7 `gold.mv_imoveis_reincidentes_areas_protegidas` (PostgreSQL / PostGIS)

Visão materializada relacional na camada Gold do banco PostgreSQL (migração `V7`).

- **Granularidade:** uma linha por imóvel rural reincidente (focos em área protegida em pelo menos 2 anos distintos entre 2015 e 2025).
- **Tipo de Objeto:** Tabela materializada relacional com índice espacial GiST.

| Coluna | Tipo | Chave / Restrição | Descrição e Regra de Negócio | Origem / Linhagem |
| :--- | :--- | :--- | :--- | :--- |
| `cod_imovel` | `VARCHAR(60)` | PK / UNIQUE | Código do imóvel rural no CAR. | `public.imovel_car.cod_imovel` |
| `situacao` | `VARCHAR(40)` | Atributo | Situação cadastral do imóvel na data do snapshot. | `public.imovel_car.situacao` |
| `condicao` | `VARCHAR(200)` | Atributo | Condição do cadastro no SICAR. | `public.imovel_car.condicao` |
| `area_ha` | `NUMERIC(14,4)` | Métrica | Área total cadastrada em hectares. | `public.imovel_car.area_ha` |
| `anos_com_foco` | `INTEGER` | Métrica / NOT NULL | Total de anos civis distintos com focos em área protegida (`HAVING count >= 2`). | `count(DISTINCT ano_evento)` |
| `lista_anos` | `INTEGER[]` | Métrica / NOT NULL | Relação dos anos ordenados em que foram detectados focos no imóvel. | `array_agg(DISTINCT ano_evento)` |
| `total_focos` | `INTEGER` | Métrica / NOT NULL | Volume total de focos no imóvel sob as condições de sobreposição. | `count(DISTINCT id_foco)` |
| `atinge_reserva_legal`| `BOOLEAN` | Flag / NOT NULL | Verdadeiro se houve ao menos uma queima na Reserva Legal do imóvel. | `bool_or(r.id_reserva IS NOT NULL)` |
| `atinge_app` | `BOOLEAN` | Flag / NOT NULL | Verdadeiro se houve ao menos uma queima em Área de Preservação Permanente. | `bool_or(a.id_app IS NOT NULL)` |
| `atinge_uc_1km` | `BOOLEAN` | Flag / NOT NULL | Verdadeiro se houve foco no raio de 1.000 metros de Unidade de Conservação. | `bool_or(u.id_uc IS NOT NULL)` |
| `geom` | `GEOMETRY` | Espacial / NOT NULL | Polígono do imóvel em EPSG:31983 com índice GiST (`ix_mv_imoveis_reincidentes_geom`). | `public.imovel_car.geom` |

---

## 2. Camada Silver (Armazenamento Aberto em Formato Delta Lake)

A camada Silver consolida os dados na arquitetura Lakehouse aberta sob formato Delta Lake (`data/delta/`), desacoplando o armazenamento analítico do processamento transacional. Suas estruturas são regidas pelo contrato declarativo versionado [`contrato_tabela_aberta.yaml`](contrato_tabela_aberta.yaml).

### 2.1 `foco_calor_analitico` (Delta Lake)

Armazena a série temporal completa de focos de calor com tipagem estrita, coordenadas métricas e particionamento temporal.

- **Localização:** `data/delta/foco_calor`
- **Granularidade:** uma linha por detecção orbital de foco de calor no DF.
- **Particionamento:** particionado em diretórios por `ano=YYYY/mes=MM` com base em `data_hora_evento`.
- **Estratégia de Carga:** Ingestão em lote periódica com operação `MERGE ... WHEN NOT MATCHED INSERT` por `id_foco`.

| Coluna | Tipo Delta | Chave / Restrição | Descrição e Regra de Negócio | Origem / Linhagem |
| :--- | :--- | :--- | :--- | :--- |
| `id_foco` | `string` | PK lógica / NOT NULL | Hash SHA-256 de latitude, longitude, data/hora e satélite. Chave primária e critério de deduplicação idempotente. | Cálculo de ingestão em lote |
| `latitude` | `double` | Espacial / NOT NULL | Latitude WGS 84 (-16.05 a -15.45 no quadrilátero do DF), referente ao centroide do pixel do sensor. | BDQueimadas CSV |
| `longitude` | `double` | Espacial / NOT NULL | Longitude WGS 84 (-48.30 a -47.30 no quadrilátero do DF), referente ao centroide do pixel do sensor. | BDQueimadas CSV |
| `x_31983` | `double` | Métrica / NOT NULL | Coordenada Leste do centroide do pixel projetada em metros (SIRGAS 2000 UTM 23S). | Reprojeção via `pyproj` |
| `y_31983` | `double` | Métrica / NOT NULL | Coordenada Norte do centroide do pixel projetada em metros (SIRGAS 2000 UTM 23S). | Reprojeção via `pyproj` |
| `data_hora_evento` | `timestamp` | Temporal / NOT NULL | Momento de passagem do sensor orbital em UTC. Base da partição física e da apuração de anos. | BDQueimadas CSV |
| `data_hora_ingestao` | `timestamp` | Auditoria / NOT NULL | Momento de gravação do registro no arquivo Delta. Não é utilizado na partição para evitar regravação de dados históricos. | Carimbo de execução do job |
| `satelite` | `string` | Atributo / NOT NULL | Identificador do satélite detector. | BDQueimadas CSV |
| `is_satelite_referencia` | `boolean` | Flag / NOT NULL | Verdadeiro para o sensor `AQUA_M-T`. | Comparação nominal |
| `municipio` | `string` | Atributo | Município associado pelo INPE (geralmente `BRASÍLIA`). | BDQueimadas CSV |
| `bioma` | `string` | Atributo | Bioma de ocorrência (`Cerrado`). | BDQueimadas CSV |
| `risco_fogo` | `double` | Métrica | Estimativa de risco de fogo calculada pelo INPE (0.0 a 1.0). | BDQueimadas CSV |
| `ano` | `string` | Coluna de partição | Ano em quatro dígitos (`YYYY`) derivado de `data_hora_evento`. | Extração de ano |
| `mes` | `string` | Coluna de partição | Mês em dois dígitos (`MM`, 01 a 12) derivado de `data_hora_evento`. | Extração de mês |
| `origem_ingestao` | `string` | Linhagem / NOT NULL | Rastreabilidade da entrada de dados (sempre preenchido com `lote`). | Constante de pipeline |
| `operacao_cdc` | `string` | Linhagem / NOT NULL | Operação de linhagem estrutural (sempre `I` para novos focos). | Constante de pipeline |

---

### 2.2 `imovel_car_analitico` (Delta Lake)

Espelho dos imóveis rurais mantido sincronizado por eventos de Change Data Capture (CDC) e recargas de snapshot.

- **Localização:** `data/delta/imovel_car`
- **Granularidade:** uma linha por versão cadastral de imóvel rural transmitida pelo WAL do PostgreSQL.
- **Particionamento:** Sem partição (evita arquivos pequenos para volume em torno de 21 mil imóveis).
- **Estratégia de Carga:** MERGE condicionado: atualiza apenas quando `source.lsn_origem >= target.lsn_origem`.

| Coluna | Tipo Delta | Chave / Restrição | Descrição e Regra de Negócio | Origem / Linhagem |
| :--- | :--- | :--- | :--- | :--- |
| `cod_imovel` | `string` | Chave de busca / NOT NULL | Código natural do imóvel no SICAR (`DF-...`). | `imovel_car.cod_imovel` |
| `situacao` | `string` | Atributo | Situação do imóvel (`AT`, `PE`, `CA`, `SU`). | `imovel_car.situacao` |
| `condicao` | `string` | Atributo | Descrição da fase de análise do cadastro. | `imovel_car.condicao` |
| `area_ha` | `double` | Métrica | Área declarada em hectares. | `imovel_car.area_ha` |
| `data_download` | `date` | Metadado / NOT NULL | Data em que o pacote fundiário foi obtido na fonte governamental. | `imovel_car.data_download` |
| `geom_ewkb_hex` | `string` | Serialização / NOT NULL | Perímetro do imóvel em formato hexadecimal EWKB na projeção EPSG:31983. | Conversão `ST_AsHEXEWKB` |
| `data_hora_ingestao`| `timestamp` | Auditoria / NOT NULL | Carimbo UTC de entrada da versão no Delta Lake. | Momento da ingestão |
| `origem_ingestao` | `string` | Linhagem / NOT NULL | Canal de captura: `snapshot` (carga fria inicial) ou `cdc` (consumo de transações). | Pipeline de ingestão |
| `operacao_cdc` | `string` | Linhagem / NOT NULL | Indicador de operação no banco: `I` (inserção), `U` (atualização) ou `D` (exclusão lógica). | Mensagem do canal CDC |
| `lsn_origem` | `long` | Ordenação / NOT NULL | Log Sequence Number da transação de origem no PostgreSQL, assegurando idempotência e monotonicidade. | Consumidor CDC |

---

## 3. Camada Bronze (Ingestão Bruta e Transacional / PostgreSQL & PostGIS)

A camada Bronze compreende as tabelas de staging transitórias e as tabelas relacionais operacionais no PostgreSQL/PostGIS (esquemas `staging` e `public`), onde os dados espaciais são validados topologicamente e indexados com GiST na chegada.

### 3.1 `public.foco_calor`

Tabela operacional de armazenamento dos focos de calor com garantia de imutabilidade transacional.

- **Granularidade:** uma linha por detecção de calor aceita e validada topologicamente no quadrilátero do DF.
- **Tipo de Objeto:** Tabela relacional PostGIS com gatilho de proteção contra alteração (`tg_foco_calor_imutavel`).

| Coluna | Tipo | Chave / Restrição | Descrição e Regra de Negócio | Origem / Linhagem |
| :--- | :--- | :--- | :--- | :--- |
| `id_foco` | `BIGINT` | PK / IDENTITY | Identificador sequencial primário gerado pelo PostgreSQL. | Auto-incremento transacional |
| `id_satelite` | `SMALLINT` | FK / NOT NULL | Referência ao satélite detector em `public.satelite (id_satelite)`. | Mapeamento por nome do satélite |
| `data_hora_evento` | `TIMESTAMPTZ` | Temporal / NOT NULL | Carimbo UTC da detecção orbital. Critério estrito para contagem de anos distintos. | `staging.foco_calor_raw` |
| `data_hora_ingestao`| `TIMESTAMPTZ` | Auditoria / DEFAULT now() | Momento da inserção no banco. Restrição `ck_foco_calor_ingestao_apos_evento` exige `data_hora_ingestao >= data_hora_evento`. | Relógio do servidor |
| `municipio` | `VARCHAR(80)` | Atributo | Município atribuído pelo INPE. | `staging.foco_calor_raw` |
| `bioma` | `VARCHAR(40)` | Atributo | Bioma informado pela fonte pública. | `staging.foco_calor_raw` |
| `risco_fogo` | `NUMERIC(4,3)` | Métrica / CHECK (0 a 1) | Valor numérico adimensional de risco de fogo calculado pelo INPE. | `staging.foco_calor_raw` |
| `geom` | `geometry(Point, 31983)` | Espacial / NOT NULL | Ponto georreferenciado em EPSG:31983. Validado com `ST_IsValid` e indexado com GiST (`idx_foco_calor_geom`). | Reprojeção de lon/lat via `ST_Transform` |

---

### 3.2 `staging.foco_calor_raw`

Tabela de staging sem tipagem estrita para carga em alta velocidade via comando nativo `COPY FROM STDIN` do PostgreSQL.

- **Granularidade:** uma linha por registro de texto bruto do arquivo CSV disponibilizado pelo BDQueimadas.
- **Tipo de Objeto:** Tabela relacional temporária/transitória de staging.

| Coluna | Tipo | Chave / Restrição | Descrição |
| :--- | :--- | :--- | :--- |
| `data_hora_gmt` | `VARCHAR(30)` | Texto bruto | Carimbo de data e hora UTC como entregue no CSV. |
| `satelite` | `VARCHAR(50)` | Texto bruto | Nome do satélite detector. |
| `pais` | `VARCHAR(50)` | Texto bruto | País (`Brasil`). |
| `estado` | `VARCHAR(50)` | Texto bruto | Unidade federativa (`DISTRITO FEDERAL`). |
| `municipio` | `VARCHAR(100)` | Texto bruto | Nome do município (`BRASÍLIA`). |
| `bioma` | `VARCHAR(50)` | Texto bruto | Nome do bioma (`Cerrado`). |
| `dias_sem_chuva` | `VARCHAR(20)` | Texto bruto | Quantidade estimada de dias consecutivos sem chuva. |
| `precipitacao` | `VARCHAR(20)` | Texto bruto | Precipitação acumulada recente em milímetros. |
| `risco_fogo` | `VARCHAR(20)` | Texto bruto | Estimativa de risco de queimada. |
| `latitude` | `VARCHAR(30)` | Texto bruto | Latitude em formato textual decimal. |
| `longitude` | `VARCHAR(30)` | Texto bruto | Longitude em formato textual decimal. |
| `frp` | `VARCHAR(30)` | Texto bruto | Potência radiativa do fogo (Fire Radiative Power) em MW. |

---

### 3.3 `public.imovel_car`

Cadastros de imóveis rurais do DF obtidos junto ao Sistema Nacional de Cadastro Ambiental Rural (SICAR).

- **Granularidade:** uma linha por imóvel rural registrado na base pública do SICAR na data do snapshot.
- **Tipo de Objeto:** Tabela relacional PostGIS com índice espacial GiST (`idx_imovel_car_geom`).

| Coluna | Tipo | Chave / Restrição | Descrição e Regra de Negócio | Origem / Linhagem |
| :--- | :--- | :--- | :--- | :--- |
| `cod_imovel` | `VARCHAR(60)` | PK / CHECK (`DF-%`) | Código identificador oficial do imóvel no CAR (chave natural). | Shapefile SICAR (`AREA_IMOVEL`) |
| `situacao` | `VARCHAR(40)` | Atributo | Situação cadastral (`AT` = Ativo, `PE` = Pendente, `CA` = Cancelado, `SU` = Suspenso). | Atributo `ind_status` do SICAR |
| `condicao` | `VARCHAR(200)` | Atributo | Condição do cadastro perante análise técnica. | Atributo `des_condic` do SICAR |
| `area_ha` | `NUMERIC(14,4)` | Métrica / CHECK (> 0) | Área do imóvel em hectares. | Atributo `num_area` do SICAR |
| `data_download` | `DATE` | Metadado / NOT NULL | Data do snapshot em que o arquivo foi baixado da fonte pública. | Metadado de carga |
| `data_hora_ingestao`| `TIMESTAMPTZ` | Auditoria / DEFAULT now() | Momento da carga do registro na base local do PostgreSQL. | Relógio do servidor |
| `geom` | `geometry(MultiPolygon, 31983)` | Espacial / NOT NULL | Perímetro do imóvel rural validado com `ST_IsValid` e indexado com GiST. | Geometria reprojetada do shapefile |

---

### 3.4 `public.unidade_conservacao`

Polígonos de Unidades de Conservação do Distrito Federal gerenciados pelo IBRAM e ICMBio.

- **Granularidade:** uma linha por Unidade de Conservação oficial no DF.
- **Tipo de Objeto:** Tabela relacional PostGIS com índice espacial GiST (`idx_unidade_conservacao_geom`).

| Coluna | Tipo | Chave / Restrição | Descrição e Regra de Negócio | Origem / Linhagem |
| :--- | :--- | :--- | :--- | :--- |
| `id_uc` | `INTEGER` | PK / IDENTITY | Identificador numérico primário gerado pelo PostgreSQL. | Auto-incremento transacional |
| `nome` | `VARCHAR(200)` | Atributo / NOT NULL | Nome oficial da Unidade de Conservação. | SISDIA / IBRAM GeoJSON |
| `categoria` | `VARCHAR(100)` | Atributo | Categoria específica de manejo (Parque, ESEC, APA, etc.). | SISDIA / IBRAM GeoJSON |
| `grupo` | `VARCHAR(20)` | Categoria / CHECK | Grupo SNUC: `protecao_integral` ou `uso_sustentavel`. | Mapeamento de regras SNUC |
| `area_ha` | `NUMERIC(14,4)` | Métrica / CHECK (> 0) | Área oficial da Unidade de Conservação em hectares. | Atributo oficial da camada |
| `fonte` | `VARCHAR(80)` | Linhagem | Nome do órgão gestor de origem (`IBRAM`, `ICMBio`, `SISDIA`). | Metadado de extração |
| `data_download` | `DATE` | Metadado / NOT NULL | Data de obtenção da camada na API pública do SISDIA. | Metadado de extração |
| `data_hora_ingestao`| `TIMESTAMPTZ` | Auditoria / DEFAULT now() | Momento de carga no banco relacional. | Relógio do servidor |
| `geom` | `geometry(MultiPolygon, 31983)` | Espacial / NOT NULL | Limite territorial da UC com validação topológica estrita e índice GiST. | Geometria vetorial oficial |

---

### 3.5 `public.reserva_legal`

Polígonos de Reserva Legal declarados no SICAR no interior de imóveis rurais.

- **Granularidade:** uma linha por polígono de Reserva Legal associado a um imóvel rural.
- **Tipo de Objeto:** Tabela relacional PostGIS com índice espacial GiST (`idx_reserva_legal_geom`).

| Coluna | Tipo | Chave / Restrição | Descrição e Regra de Negócio | Origem / Linhagem |
| :--- | :--- | :--- | :--- | :--- |
| `id_reserva` | `INTEGER` | PK / IDENTITY | Identificador primário numérico da feição. | Auto-incremento transacional |
| `cod_imovel` | `VARCHAR(60)` | FK / NOT NULL | Referência ao imóvel proprietário em `public.imovel_car (cod_imovel)`. Exclusão em cascata. | Atributo do shapefile SICAR |
| `situacao` | `VARCHAR(40)` | Atributo | Situação cadastral da reserva legal no SICAR. | Shapefile SICAR (`RESERVA_LEGAL`) |
| `area_ha` | `NUMERIC(14,4)` | Métrica / CHECK (> 0) | Área da feição de Reserva Legal em hectares. | Atributo do shapefile |
| `data_download` | `DATE` | Metadado / NOT NULL | Data do snapshot da camada. Deve coincidir com a data do imóvel proprietário. | Metadado de carga |
| `data_hora_ingestao`| `TIMESTAMPTZ` | Auditoria / DEFAULT now() | Momento da ingestão no PostgreSQL. | Relógio do servidor |
| `geom` | `geometry(MultiPolygon, 31983)` | Espacial / NOT NULL | Polígono da reserva com SRID 31983, validado com `ST_IsValid` e indexado com GiST. | Geometria reprojetada |

---

### 3.6 `public.area_preservacao_permanente`

Mapeamento territorial de Áreas de Preservação Permanente no Distrito Federal.

- **Granularidade:** uma linha por feição poligonal de APP (nascentes, cursos d'água, encostas).
- **Tipo de Objeto:** Tabela relacional PostGIS com índice espacial GiST (`idx_app_geom`).

| Coluna | Tipo | Chave / Restrição | Descrição e Regra de Negócio | Origem / Linhagem |
| :--- | :--- | :--- | :--- | :--- |
| `id_app` | `INTEGER` | PK / IDENTITY | Identificador primário sequencial. | Auto-incremento transacional |
| `cod_imovel` | `VARCHAR(60)` | FK opcional | Referência a `public.imovel_car (cod_imovel)`. Preenchido se a APP vier do pacote individual do imóvel no SICAR; nulo se provier de camada distrital do IBRAM. | Relação fundiária SICAR |
| `tipo` | `VARCHAR(100)` | Atributo | Tipologia da APP (ex: curso d'água, nascente, reservatório artificial, topo de morro). | Camada temática de origem |
| `area_ha` | `NUMERIC(14,4)` | Métrica / CHECK (> 0) | Extensão em hectares da área preservada. | Atributo oficial da feição |
| `fonte` | `VARCHAR(80)` | Linhagem | Órgão ou base de dados fornecedora (`IBRAM`, `Geoportal DF`, `SICAR`). | Metadado de extração |
| `data_download` | `DATE` | Metadado / NOT NULL | Data em que a camada foi capturada na fonte oficial. | Metadado de extração |
| `data_hora_ingestao`| `TIMESTAMPTZ` | Auditoria / DEFAULT now() | Momento de carga no banco de dados. | Relógio do servidor |
| `geom` | `geometry(MultiPolygon, 31983)` | Espacial / NOT NULL | Polígono ou multipolígono métrico em EPSG:31983 validado e indexado com GiST. | Geometria reprojetada |

---

### 3.7 `public.satelite`

Catálogo dos sensores orbitais suportados na ingestão do BDQueimadas.

- **Granularidade:** uma linha por satélite detector registrado.
- **Tipo de Objeto:** Tabela relacional de referência com restrição de unicidade parcial.

| Coluna | Tipo | Chave / Restrição | Descrição e Regra de Negócio | Origem / Linhagem |
| :--- | :--- | :--- | :--- | :--- |
| `id_satelite` | `SMALLINT` | PK / IDENTITY | Chave primária substituta interna do PostgreSQL. | Auto-incremento transacional |
| `nome` | `VARCHAR(40)` | Chave Natural / NOT NULL | Nome do satélite em letras maiúsculas sem espaços vazios (`UNIQUE`). | BDQueimadas |
| `is_referencia` | `BOOLEAN` | Flag / NOT NULL | Verdadeiro para o sensor `AQUA_M-T`. O índice único parcial `uq_satelite_referencia` impede mais de um registro verdadeiro. | Configuração do BDQueimadas |

---

## 4. Matriz de Rastreabilidade e Linhagem Ponta a Ponta

A tabela a seguir resume o ciclo de transformação de cada dado entre os sistemas da plataforma:

| Dado / Conceito | Camada Bronze (PostgreSQL) | Camada Silver (Delta Lake) | Camada Gold (dbt / Dimensional) |
| :--- | :--- | :--- | :--- |
| **Focos de Calor** | `public.foco_calor` (somente inserção) | `foco_calor_analitico` (partição ano/mês) | `fato_foco_calor` (grão atômico com SKs) |
| **Imóveis Rurais** | `public.imovel_car` (snapshot fundiário) | `imovel_car_analitico` (CDC com LSN) | `dim_imovel_car` (SCD Tipo 2 com vigência) |
| **Áreas Protegidas** | `unidade_conservacao`, `reserva_legal`, `app` | Consultas federadas ao PostGIS / Delta | `dim_territorio` (UC, APP e RL unificadas) |
| **Tempo e Calendário** | `data_hora_evento` nas tabelas | `ano`, `mes` particionados em UTC | `dim_tempo` (grão diário com `is_estacao_seca`) |
| **Satélites** | `public.satelite` (com índice parcial) | Colunas `satelite`, `is_satelite_referencia` | `dim_satelite` (MD5 estável e flag) |
| **Resposta de Gestão** | `gold.mv_imoveis_reincidentes_areas_protegidas` | - | `mart_reincidencia_imovel_ano` (imóvel × ano) |
