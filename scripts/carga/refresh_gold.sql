-- Atualiza as Materialized Views da camada Gold com os dados carregados nas camadas Silver.
-- Pode ser executado manualmente ou automaticamente ao final da carga do docker-compose.
-- As MVs de apoio (APP e UC subdivididas, migracao V9) vem primeiro: a MV principal le delas.

\timing on

\echo 'Atualizando gold.mv_app_subdividida e gold.mv_uc_subdividida...'

REFRESH MATERIALIZED VIEW gold.mv_app_subdividida;
REFRESH MATERIALIZED VIEW gold.mv_uc_subdividida;

ANALYZE gold.mv_app_subdividida;
ANALYZE gold.mv_uc_subdividida;

\echo 'Atualizando gold.mv_imoveis_reincidentes_areas_protegidas...'

REFRESH MATERIALIZED VIEW gold.mv_imoveis_reincidentes_areas_protegidas;

ANALYZE gold.mv_imoveis_reincidentes_areas_protegidas;

SELECT count(*) AS total_imoveis_reincidentes_gold
FROM gold.mv_imoveis_reincidentes_areas_protegidas;
