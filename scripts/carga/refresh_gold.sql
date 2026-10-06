-- Atualiza a Materialized View da camada Gold com os dados carregados nas camadas Silver.
-- Pode ser executado manualmente ou automaticamente ao final da carga do docker-compose.

\timing on

\echo 'Atualizando gold.mv_imoveis_reincidentes_areas_protegidas...'

REFRESH MATERIALIZED VIEW gold.mv_imoveis_reincidentes_areas_protegidas;

ANALYZE gold.mv_imoveis_reincidentes_areas_protegidas;

SELECT count(*) AS total_imoveis_reincidentes_gold
FROM gold.mv_imoveis_reincidentes_areas_protegidas;
