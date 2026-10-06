-- V7: camada Gold para resposta direta a pergunta de gestao.
-- Cria o schema 'gold' e a MATERIALIZED VIEW que consolida os imoveis rurais
-- reincidentes em focos de calor proximos ou sobrepostos a areas protegidas
-- (Reserva Legal, APP ou a ate 1 km de Unidades de Conservacao) entre 2015 e 2025.

CREATE SCHEMA IF NOT EXISTS gold;

CREATE MATERIALIZED VIEW gold.mv_imoveis_reincidentes_areas_protegidas AS
WITH focos_filtrados AS (
    SELECT
        f.id_foco,
        f.data_hora_evento,
        date_part('year', f.data_hora_evento)::int AS ano_evento,
        f.geom
    FROM public.foco_calor f
    WHERE f.data_hora_evento >= '2015-01-01 00:00:00+00'
      AND f.data_hora_evento <= '2025-12-31 23:59:59+00'
),
cruzamentos AS (
    SELECT
        i.cod_imovel,
        i.situacao,
        i.condicao,
        i.area_ha,
        i.geom,
        f.id_foco,
        f.ano_evento,
        (r.id_reserva IS NOT NULL) AS atinge_reserva_legal,
        (a.id_app IS NOT NULL) AS atinge_app,
        (u.id_uc IS NOT NULL) AS atinge_uc_1km
    FROM focos_filtrados f
    JOIN public.imovel_car i ON ST_Intersects(f.geom, i.geom)
    LEFT JOIN public.reserva_legal r ON r.cod_imovel = i.cod_imovel AND ST_Intersects(f.geom, r.geom)
    LEFT JOIN public.area_preservacao_permanente a ON ST_Intersects(f.geom, a.geom)
    LEFT JOIN public.unidade_conservacao u ON ST_DWithin(f.geom, u.geom, 1000)
    WHERE r.id_reserva IS NOT NULL
       OR a.id_app IS NOT NULL
       OR u.id_uc IS NOT NULL
)
SELECT
    c.cod_imovel,
    c.situacao,
    c.condicao,
    c.area_ha,
    count(DISTINCT c.ano_evento)::int AS anos_com_foco,
    array_agg(DISTINCT c.ano_evento ORDER BY c.ano_evento) AS lista_anos,
    count(DISTINCT c.id_foco)::int AS total_focos,
    bool_or(c.atinge_reserva_legal) AS atinge_reserva_legal,
    bool_or(c.atinge_app) AS atinge_app,
    bool_or(c.atinge_uc_1km) AS atinge_uc_1km,
    c.geom
FROM cruzamentos c
GROUP BY c.cod_imovel, c.situacao, c.condicao, c.area_ha, c.geom
HAVING count(DISTINCT c.ano_evento) >= 2;

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
