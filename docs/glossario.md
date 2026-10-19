---
icon: material/book-open-page-variant
---

# :material-book-open-page-variant: Glossário Técnico e Referências

Termos, acrônimos e conceitos de engenharia de dados, cartografia e modelagem espacial adotados no projeto Corta-Fogo DF, acompanhados de suas definições formais e referências técnicas.

---

## 1. Georreferenciamento e Sistemas de Coordenadas

### SRID (Spatial Reference System Identifier)

Identificador numérico inteiro padronizado que referencia de forma unívoca um Sistema de Referência Espacial (CRS/SRS) no banco de dados[^1]. No PostGIS, o SRID define os parâmetros matemáticos de elipsoide, datum geodésico e projeção cartográfica associados a cada coluna do tipo `geometry`.

- **Uso no projeto:** nenhuma geometria é declarada sem SRID no esquema físico. Todas as tabelas têm seu SRID fixado em 31983.

### EPSG:31983 (SIRGAS 2000 / UTM zone 23S)

Código de autoridade do registro EPSG para o sistema de coordenadas projetadas baseado no datum geodésico SIRGAS 2000 (Sistema de Referência Geocêntrico para as Américas) e projeção Universal Transversa de Mercator (UTM) no fuso 23 Sul[^2]. Utiliza coordenadas planas métricas (X/Leste e Y/Norte em metros).

- **Uso no projeto:** projeção métrica padrão de todo o banco de dados. Permite avaliar distâncias exatas de amortecimento (raio de 1.000 metros via `ST_DWithin`) sem necessidade de projeções intermediárias ou cálculos em esferoide.

### UTM zone 23S (Universal Transversa de Mercator, Fuso 23 Sul)

Sistema de projeção cartográfica cilíndrica conforme e transversa que divide a Terra em 60 fusos longitudinais de 6 graus[^3]. O fuso 23 Sul estende-se da longitude 48° O a 42° O, com meridiano central em 45° O, cobrindo o hemisfério sul.

- **Uso no projeto:** o quadrilátero do Distrito Federal situa-se integralmente entre as longitudes 48° 12' O e 47° 20' O, permitindo o uso do fuso 23S com distorções de escala inferiores a 0,04% na medição de distâncias.

### EPSG:4326 (WGS 84, Coordenadas Geográficas)

Sistema geodésico global de referência (World Geodetic System 1984) expresso em coordenadas angulares de latitude e longitude sobre elipsoide de revolução (graus decimais)[^4].

- **Uso no projeto:** formato em que chegam as detecções brutas do BDQueimadas (INPE). As coordenadas são reprojetadas para EPSG:31983 na ingestão via função `ST_Transform`.

---

## 2. Estruturas Espaciais e Banco de Dados

### Arquitetura em Camadas: Bronze e Gold

Padrão de arquitetura de dados (medallion architecture) que organiza a ingestão em estágios sucessivos de qualidade: Bronze guarda o dado bruto exatamente como a fonte entregou, sem transformação; Gold guarda o dado já validado, tipado e pronto para consulta[^21].

- **Uso no projeto:** a camada Bronze é o arquivo bruto em `data/raw` e `data/processed` (CSV do INPE, GeoJSON do IBRAM/SISDIA, shapefile zipado do SICAR), fora do banco. A camada Gold é o schema `public` do PostgreSQL: as tabelas finais com SRID fixo, chaves, restrições `ST_IsValid` e índices GiST, onde a consulta da pergunta de gestão roda direto. Só os focos passam por um estágio intermediário dentro do banco (`staging.foco_calor_raw`), porque chegam como coordenadas soltas em vez de geometria pronta. Diagrama completo na seção "Pipeline: da fonte pública à camada Gold" da [Entrega 1](../entrega/01/README.md#pipeline-da-fonte-publica-a-camada-gold).

### PostGIS

Extensão espacial de código aberto para o SGBD PostgreSQL que adiciona suporte a tipos de dados geográficos (Point, LineString, Polygon, MultiPolygon) em conformidade com as especificações da Open Geospatial Consortium (OGC)[^5].

- **Uso no projeto:** motor principal da camada transacional e consolidada (Gold da Entrega 1), responsável pela validação topológica e execução de junções espaciais.

### Índice GiST (Generalized Search Tree / R-Tree)

Estrutura de indexação extensível do PostgreSQL que implementa árvores balanceadas de pesquisa[^6]. Para dados espaciais no PostGIS, o GiST implementa o algoritmo R-Tree, organizando as feições por meio de suas caixas mínimas envolventes (Bounding Boxes - BBOX)[^7].

- **Uso no projeto:** todas as colunas geométricas contêm índices GiST (`idx_*_geom`). O índice filtra pares viáveis por BBOX antes da execução do algoritmo topológico exato (`ST_Intersects` ou `ST_DWithin`), reduzindo a complexidade de varredura sequencial $O(N \times M)$ para tempo logarítmico.

### EWKB (Extended Well-Known Binary)

Extensão proprietária do PostGIS sobre o formato padrão OGC WKB (Well-Known Binary) para serialização binária de geometrias[^8]. O EWKB embute o SRID e dimensões extras (Z, M) diretamente no cabeçalho do fluxo de bytes.

- **Uso no projeto:** formato interno de persistência em disco das geometrias nas tabelas físicas do PostgreSQL.

### GEOS (Geometry Engine, Open Source)

Biblioteca em C++ que implementa os algoritmos de geometria computacional e predicados topológicos da especificação OpenGIS Simple Features for SQL (como DE-9IM, interseção de polígonos e cálculo de distância)[^9].

- **Uso no projeto:** motor interno acionado pelo PostGIS ao executar funções analíticas (`ST_Intersects`, `ST_DWithin`, `ST_MakeValid` e `ST_SimplifyPreserveTopology`).

---

## 3. Modelagem Temporal e Histórico

### Modelo Temporal Bitemporal

Abordagem de modelagem que registra duas dimensões ortogonais de tempo para cada fato: o tempo válido (quando o evento ocorreu no mundo real) e o tempo de transação (quando o registro foi gravado no sistema de banco de dados)[^10].

- **Uso no projeto:** implementado em `foco_calor` pelas colunas `data_hora_evento` (tempo válido da passagem orbital do satélite) e `data_hora_ingestao` (tempo de transação no banco). Desde a migração `V6`, as quatro tabelas territoriais (`imovel_car`, `reserva_legal`, `area_preservacao_permanente`, `unidade_conservacao`) também têm `data_hora_ingestao`, ao lado de `data_download` (ver "Snapshot de Limites Territoriais"). `data_download` e `data_hora_ingestao` não são o mesmo tempo: o arquivo pode ter sido baixado numa data e carregado neste banco bem depois, por exemplo ao reexecutar `docker compose up` em outra máquina.

### Snapshot de Limites Territoriais

Estratégia de captura periódica de dados cadastrais em que uma versão consolidada e estática da fonte de origem é armazenada com registro de seu momento de extração[^11].

- **Uso no projeto:** aplicado às tabelas `imovel_car`, `reserva_legal`, `area_preservacao_permanente` e `unidade_conservacao` por meio da coluna `data_download`, que registra quando o arquivo foi obtido na fonte (IBRAM/SISDIA ou SICAR), não quando a carga rodou. Para as camadas baixadas em tempo de execução (UCs e APPs do IBRAM), `extract_camadas.py` grava essa data num arquivo `.meta.json` ao lado do GeoJSON; para os zips do SICAR, versionados no repositório, é uma constante documentada em `load_camadas.py`. Delimita formalmente que a consulta espacial avalia o impacto dos focos contra o perímetro registrado no momento do snapshot, sem presumir vigências retroativas.

### SCD Tipo 2 (Slowly Changing Dimensions Type 2)

Padrão de modelagem dimensional de variação lenta que preserva o histórico integral de alterações em cadastros mediante o versionamento de linhas, controlando a vigência por datas de início e fim (`vigencia_inicio` e `vigencia_fim`)[^12].

- **Uso no projeto:** arquitetura planejada para etapas posteriores à Entrega 1 para versionar retificações de limites de imóveis e reservas legais do SICAR, caso seja exigido responder se o foco estava na reserva legal na data exata da emissão do título.

---

## 4. Motores Analíticos e Formatos Abertos

### DuckDB

Sistema de gerenciamento de banco de dados relacional analítico (OLAP) colunar em processo (_in-process_)[^13]. Otimizado para execução vetorizada de consultas analíticas sem demandar servidor dedicado em segundo plano.

- **Uso no projeto:** alternativa arquitetural definida no gatilho de revisão do ADR 0001 para processamento analítico a partir da Entrega 3, caso consultas espaciais densas excedam os limites de latência do PostGIS.

### GeoParquet

Extensão geoespacial da especificação Apache Parquet mantida pela Open Geospatial Consortium (OGC)[^14]. Adiciona metadados padronizados para colunas com dados vetoriais serializados em WKB, permitindo compressão colunar por blocos, estatísticas de BBOX por linha e leitura paralela de geometrias.

- **Uso no projeto:** formato aberto de armazenamento colunar planejado para as camadas analíticas da Entrega 2 e 3.

### CDC (Change Data Capture)

Conjunto de padrões de software para identificar e capturar alterações (inserções, atualizações e exclusões) em um banco transacional de origem e disponibilizá-las em tempo quase-real para sistemas analíticos a jusante[^15].

- **Uso no projeto:** requisito central da Entrega 2 (Semana 10) para captura de mudanças via decodificação lógica do Write-Ahead Log (WAL) do PostgreSQL (Debezium/pgoutput).

---

## 5. Domínio Territorial e Ambiental

### SICAR / CAR (Sistema Nacional de Cadastro Ambiental Rural)

Registro público eletrônico de âmbito nacional, obrigatório para todos os imóveis rurais do Brasil, instituído pela Lei Federal nº 12.651/2012 (Código Florestal)[^16]. Integra as informações ambientais das propriedades rurais para composição de base de dados para controle, monitoramento e combate ao desmatamento.

- **Uso no projeto:** base de dados da tabela `imovel_car` e `reserva_legal`, recortada para o Distrito Federal.

### APP (Área de Preservação Permanente)

Área protegida, coberta ou não por vegetação nativa, com a função ambiental de preservar os recursos hídricos, a paisagem, a estabilidade geológica e a biodiversidade (art. 3º, II, da Lei Federal nº 12.651/2012)[^17].

- **Uso no projeto:** camada `area_preservacao_permanente` obtida do IBRAM/SISDIA (nascentes, cursos d'água, reservatórios e bordas de chapada do DF).

### Reserva Legal

Área localizada no interior de um imóvel rural delimitada com a função de assegurar o uso econômico de modo sustentável dos recursos naturais e auxiliar a conservação da vegetação nativa (art. 3º, III, da Lei Federal nº 12.651/2012)[^18]. No bioma Cerrado dentro do DF, a exigência é de 20% da área do imóvel.

- **Uso no projeto:** camada `reserva_legal`, associada relacionalmente ao imóvel rural do SICAR.

### UC (Unidade de Conservação)

Espaço territorial e seus recursos ambientais, com características naturais relevantes, legalmente instituído pelo Poder Público com objetivos de conservação e limites definidos, sob regime especial de administração (Lei Federal nº 9.985/2000 - Sistema Nacional de Unidades de Conservação - SNUC)[^19].

- **Uso no projeto:** base da tabela `unidade_conservacao` (parques, reservas biológicas, florestas e APAs do DF). Serve de centro para a zona de amortecimento de 1.000 metros calculada pela consulta de gestão.

### BDQueimadas (INPE)

Banco de Dados de Queimadas mantido pelo Instituto Nacional de Pesquisas Espaciais (INPE), que processa imagens de satélites meteorológicos e de observação da Terra (como AQUA, TERRA, NOAA e GOES) para detecção térmica de focos de vegetação[^20].

- **Uso no projeto:** fonte da tabela `foco_calor`, abrangendo a série histórica de 2015 a 2025 para o recorte do Distrito Federal.

---

## Referências

[^1]: Open Geospatial Consortium (OGC). _OpenGIS Implementation Standard for Geographic information - Simple feature access - Part 1: Common architecture (OGC 06-103r4)_. Wayland: OGC, 2011.
[^2]: International Association of Oil & Gas Producers (IOGP). _EPSG Geodetic Parameter Dataset: Coordinate Reference System EPSG:31983 (SIRGAS 2000 / UTM zone 23S)_. Disponível em: <https://epsg.io/31983>.
[^3]: Snyder, John P. _Map Projections: A Working Manual (US Geological Survey Professional Paper 1395)_. Washington, D.C.: U.S. Government Printing Office, 1987.
[^4]: National Geospatial-Intelligence Agency (NGA). *Department of Defense World Geodetic System 1984: Its Definition and Relationships with Local Geodetic Systems (NGA.STND.0036_1.0.0_WGS84)*. Bethesda: NGA, 2014.
[^5]: PostGIS Project Steering Committee. _PostGIS 3.4.0 Manual_. Disponível em: <https://postgis.net/docs/>.
[^6]: Hellerstein, Joseph M.; Kuntz, Jeffrey F.; Kohout, Corey A. _Generalized Search Trees for Database Systems_. In: Proceedings of the 21st International Conference on Very Large Data Bases (VLDB '95), Zurich, p. 562-573, 1995.
[^7]: Guttman, Antonin. _R-Trees: A Dynamic Index Structure for Spatial Searching_. In: Proceedings of the 1984 ACM SIGMOD International Conference on Management of Data, Boston, p. 47-57, 1984.
[^8]: Obe, Regina O.; Hsu, Leo S. _PostGIS in Action_. 3. ed. Shelter Island: Manning Publications, 2021.
[^9]: GEOS Development Team. _GEOS: Geometry Engine, Open Source (C++ Port of the Java Topology Suite)_. Open Source Geospatial Foundation, 2023. Disponível em: <https://libgeos.org/>.
[^10]: Snodgrass, Richard T. _Developing Time-Oriented Database Applications in SQL_. San Francisco: Morgan Kaufmann Publishers, 1999.
[^11]: Kleppmann, Martin. _Designing Data-Intensive Applications: The Big Ideas Behind Reliable, Scalable, and Maintainable Systems_. Sebastopol: O'Reilly Media, 2017.
[^12]: Kimball, Ralph; Ross, Margy. _The Data Warehouse Toolkit: The Definitive Guide to Dimensional Modeling_. 3. ed. Indianapolis: John Wiley & Sons, 2013.
[^13]: Raasveldt, Mark; Mühleisen, Hannes. _DuckDB: an Embeddable Analytical Database_. In: Proceedings of the 2019 International Conference on Management of Data (SIGMOD '19), Amsterdam, p. 1981-1984, 2019.
[^14]: Open Geospatial Consortium (OGC). _OGC GeoParquet 1.1.0 Standard (OGC 22-044r1)_. Wayland: OGC, 2024. Disponível em: <https://geoparquet.org/>.
[^15]: Reis, Joe; Housley, Matt. _Fundamentals of Data Engineering: Plan and Build Robust Data Systems_. Sebastopol: O'Reilly Media, 2022.
[^16]: Brasil. _Lei nº 12.651, de 25 de maio de 2012. Dispõe sobre a proteção da vegetação nativa (Código Florestal)_. Diário Oficial da União, Brasília, DF, 28 maio 2012.
[^17]: Brasil. _Decreto nº 7.830, de 17 de outubro de 2012. Cria o Sistema de Cadastro Ambiental Rural (SICAR)_. Diário Oficial da União, Brasília, DF, 18 out. 2012.
[^18]: Instituto Brasília Ambiental (IBRAM). _Geoportal do Distrito Federal / Sistema Distrital de Informações Ambientais (SISDIA)_. Brasília: IBRAM, 2024. Disponível em: <https://sisdia.df.gov.br/>.
[^19]: Brasil. _Lei nº 9.985, de 18 de julho de 2000. Institui o Sistema Nacional de Unidades de Conservação da Natureza (SNUC)_. Diário Oficial da União, Brasília, DF, 19 jul. 2000.
[^20]: Instituto Nacional de Pesquisas Espaciais (INPE). _Programa Queimadas: Monitoramento dos Focos Ativos por Satélite_. São José dos Campos: INPE, 2024. Disponível em: <https://queimadas.dgi.inpe.br/queimadas/bdqueimadas>.
[^21]: Databricks. _What is a Medallion Architecture?_. Databricks Glossary, 2024. Disponível em: <https://www.databricks.com/glossary/medallion-architecture>.
