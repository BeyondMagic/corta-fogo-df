-- V9: reescreve a consulta da camada Gold (mesmo resultado, plano mais barato).
-- Medicao antes e depois com EXPLAIN (ANALYZE, BUFFERS) em docs/explain/.
--
-- O que muda em relacao a V7:
-- 1. APP e UC entram subdivididas (ST_Subdivide, ate 64 vertices por pedaco) em duas
--    Materialized Views de apoio com indice GiST. O teste ponto em poligono deixa de
--    abrir poligonos de ate 20 mil vertices a cada foco.
-- 2. As marcas "em APP" e "a ate 1 km de UC" sao calculadas uma vez por foco, e nao
--    uma vez por par foco e imovel (um foco sobre imoveis sobrepostos repetia o teste).
-- 3. A geometria do imovel sai da agregacao e so entra na juncao final. A ordenacao
--    do GROUP BY deixa de ir para disco.
--
-- As colunas, a ordem delas e o resultado sao os mesmos da V7. O teste dbt
-- reconcilia_fato_imovel_com_mv_postgis compara esta MV com o fato da camada dbt.

DROP MATERIALIZED VIEW gold.mv_imoveis_reincidentes_areas_protegidas;

CREATE MATERIALIZED VIEW gold.mv_app_subdividida AS
SELECT
    a.id_app,
    ST_Subdivide(a.geom, 64) AS geom
FROM public.area_preservacao_permanente a;

CREATE INDEX ix_mv_app_subdividida_geom
    ON gold.mv_app_subdividida USING gist (geom);

COMMENT ON MATERIALIZED VIEW gold.mv_app_subdividida IS
    'Apoio da camada Gold: poligonos de APP subdivididos em pedacos de ate 64 vertices para o teste ponto em poligono.';

CREATE MATERIALIZED VIEW gold.mv_uc_subdividida AS
SELECT
    u.id_uc,
    ST_Subdivide(u.geom, 64) AS geom
FROM public.unidade_conservacao u;

CREATE INDEX ix_mv_uc_subdividida_geom
    ON gold.mv_uc_subdividida USING gist (geom);

COMMENT ON MATERIALIZED VIEW gold.mv_uc_subdividida IS
    'Apoio da camada Gold: poligonos de UC subdivididos em pedacos de ate 64 vertices para o teste de distancia de 1 km.';

CREATE MATERIALIZED VIEW gold.mv_imoveis_reincidentes_areas_protegidas AS
WITH marcas_foco AS MATERIALIZED (
    SELECT
        f.id_foco,
        EXISTS (
            SELECT 1 FROM gold.mv_app_subdividida a
            WHERE ST_Intersects(f.geom, a.geom)
        ) AS em_app,
        EXISTS (
            SELECT 1 FROM gold.mv_uc_subdividida u
            WHERE ST_DWithin(f.geom, u.geom, 1000)
        ) AS ate_1km_uc
    FROM public.foco_calor f
    WHERE f.data_hora_evento >= '2015-01-01 00:00:00+00'
      AND f.data_hora_evento <= '2025-12-31 23:59:59+00'
),
pares AS (
    SELECT
        i.cod_imovel,
        f.id_foco,
        date_part('year', f.data_hora_evento)::int AS ano_evento,
        (r.id_reserva IS NOT NULL) AS em_reserva_legal
    FROM public.foco_calor f
    JOIN public.imovel_car i ON ST_Intersects(f.geom, i.geom)
    LEFT JOIN public.reserva_legal r
        ON r.cod_imovel = i.cod_imovel AND ST_Intersects(f.geom, r.geom)
    WHERE f.data_hora_evento >= '2015-01-01 00:00:00+00'
      AND f.data_hora_evento <= '2025-12-31 23:59:59+00'
),
agregado AS (
    SELECT
        p.cod_imovel,
        count(DISTINCT p.ano_evento)::int AS anos_com_foco,
        array_agg(DISTINCT p.ano_evento ORDER BY p.ano_evento) AS lista_anos,
        count(DISTINCT p.id_foco)::int AS total_focos,
        bool_or(p.em_reserva_legal) AS atinge_reserva_legal,
        bool_or(m.em_app) AS atinge_app,
        bool_or(m.ate_1km_uc) AS atinge_uc_1km
    FROM pares p
    JOIN marcas_foco m ON m.id_foco = p.id_foco
    WHERE p.em_reserva_legal OR m.em_app OR m.ate_1km_uc
    GROUP BY p.cod_imovel
    HAVING count(DISTINCT p.ano_evento) >= 2
)
SELECT
    i.cod_imovel,
    i.situacao,
    i.condicao,
    i.area_ha,
    a.anos_com_foco,
    a.lista_anos,
    a.total_focos,
    a.atinge_reserva_legal,
    a.atinge_app,
    a.atinge_uc_1km,
    i.geom
FROM agregado a
JOIN public.imovel_car i ON i.cod_imovel = a.cod_imovel;

COMMENT ON MATERIALIZED VIEW gold.mv_imoveis_reincidentes_areas_protegidas IS
    'Camada Gold: tabela materializada analitica que responde diretamente a pergunta de gestao da E1 em consulta unica.';
COMMENT ON COLUMN gold.mv_imoveis_reincidentes_areas_protegidas.cod_imovel IS
    'Codigo identificador do imovel rural no CAR (padrao DF-...).';
COMMENT ON COLUMN gold.mv_imoveis_reincidentes_areas_protegidas.anos_com_foco IS
    'Quantidade de anos distintos em que o imovel registrou focos em areas protegidas (reincidencia >= 2).';
COMMENT ON COLUMN gold.mv_imoveis_reincidentes_areas_protegidas.lista_anos IS
    'Array com a relacao cronologica dos anos distintos em que ocorreram os focos.';
COMMENT ON COLUMN gold.mv_imoveis_reincidentes_areas_protegidas.total_focos IS
    'Total absoluto de deteccoes registradas no imovel sob os criterios de protecao.';
COMMENT ON COLUMN gold.mv_imoveis_reincidentes_areas_protegidas.atinge_reserva_legal IS
    'Indica se houve ao menos um foco na Reserva Legal declarada do imovel.';
COMMENT ON COLUMN gold.mv_imoveis_reincidentes_areas_protegidas.atinge_app IS
    'Indica se houve ao menos um foco em Area de Preservacao Permanente.';
COMMENT ON COLUMN gold.mv_imoveis_reincidentes_areas_protegidas.atinge_uc_1km IS
    'Indica se houve ao menos um foco no raio de amortecimento de 1.000 metros de Unidade de Conservacao.';

CREATE UNIQUE INDEX ix_mv_imoveis_reincidentes_cod_imovel
    ON gold.mv_imoveis_reincidentes_areas_protegidas (cod_imovel);

CREATE INDEX ix_mv_imoveis_reincidentes_geom
    ON gold.mv_imoveis_reincidentes_areas_protegidas USING gist (geom);
