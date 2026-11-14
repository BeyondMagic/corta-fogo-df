-- DEPOIS: a mesma pergunta com a consulta da migracao V9.
-- Tres mudancas em relacao ao ANTES:
--   1. APP e UC subdivididas (ST_Subdivide, ate 64 vertices) em gold.mv_app_subdividida
--      e gold.mv_uc_subdividida, com indice GiST;
--   2. marcas de APP e de UC calculadas uma vez por foco, e nao por par foco e imovel;
--   3. geometria do imovel fora da agregacao (entra so na juncao final).
--
-- Reproduzir (banco do docker compose, depois da carga e do refresh_gold):
--   docker compose exec -T db psql -U corta-fogo -d corta-fogo-df -f - < docs/explain/depois_mv_imoveis_reincidentes.sql
-- Rodar duas vezes; o plano versionado e o da segunda execucao, com o cache quente.

EXPLAIN (ANALYZE, BUFFERS)
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
    i.cod_imovel, i.situacao, i.condicao, i.area_ha,
    a.anos_com_foco, a.lista_anos, a.total_focos,
    a.atinge_reserva_legal, a.atinge_app, a.atinge_uc_1km,
    i.geom
FROM agregado a
JOIN public.imovel_car i ON i.cod_imovel = a.cod_imovel;
