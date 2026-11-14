-- ANTES: consulta da camada Gold como definida na migracao V7.
-- Imoveis rurais com foco em Reserva Legal propria, APP ou a ate 1 km de UC em pelo
-- menos 2 anos distintos entre 2015 e 2025.
--
-- Reproduzir (banco do docker compose, depois da carga):
--   docker compose exec -T db psql -U corta-fogo -d corta-fogo-df -f - < docs/explain/antes_mv_imoveis_reincidentes.sql
-- Rodar duas vezes; o plano versionado e o da segunda execucao, com o cache quente.

EXPLAIN (ANALYZE, BUFFERS)
WITH focos_filtrados AS (
    SELECT f.id_foco, date_part('year', f.data_hora_evento)::int AS ano_evento, f.geom
    FROM public.foco_calor f
    WHERE f.data_hora_evento >= '2015-01-01 00:00:00+00' AND f.data_hora_evento <= '2025-12-31 23:59:59+00'
),
cruzamentos AS (
    SELECT i.cod_imovel, i.situacao, i.condicao, i.area_ha, i.geom, f.id_foco, f.ano_evento,
        (r.id_reserva IS NOT NULL) AS atinge_reserva_legal, (a.id_app IS NOT NULL) AS atinge_app, (u.id_uc IS NOT NULL) AS atinge_uc_1km
    FROM focos_filtrados f
    JOIN public.imovel_car i ON ST_Intersects(f.geom, i.geom)
    LEFT JOIN public.reserva_legal r ON r.cod_imovel = i.cod_imovel AND ST_Intersects(f.geom, r.geom)
    LEFT JOIN public.area_preservacao_permanente a ON ST_Intersects(f.geom, a.geom)
    LEFT JOIN public.unidade_conservacao u ON ST_DWithin(f.geom, u.geom, 1000)
    WHERE r.id_reserva IS NOT NULL OR a.id_app IS NOT NULL OR u.id_uc IS NOT NULL
)
SELECT c.cod_imovel, c.situacao, c.condicao, c.area_ha,
    count(DISTINCT c.ano_evento)::int AS anos_com_foco, array_agg(DISTINCT c.ano_evento ORDER BY c.ano_evento) AS lista_anos,
    count(DISTINCT c.id_foco)::int AS total_focos, bool_or(c.atinge_reserva_legal), bool_or(c.atinge_app), bool_or(c.atinge_uc_1km), c.geom
FROM cruzamentos c
GROUP BY c.cod_imovel, c.situacao, c.condicao, c.area_ha, c.geom
HAVING count(DISTINCT c.ano_evento) >= 2;
