-- Teste de distribuicao espacial (Issue #21):
-- Valida que 100% das coordenadas metricas (EPSG:31983, SIRGAS 2000 / UTM zone 23S)
-- e geograficas (WGS84) estao situadas no envelope geografico do Distrito Federal,
-- e que todas as geometrias da camada Gold sao topologicamente validas e nao vazias.
-- Detecta inversao de eixos (lat/lon ou X/Y), falha de reprojecao ou geometria corrompida.

with violacoes_focos as (
    select
        'fato_foco_calor'::varchar as modelo,
        id_foco                    as chave_registro,
        x_31983                    as x_min,
        x_31983                    as x_max,
        y_31983                    as y_min,
        y_31983                    as y_max
    from {{ ref('fato_foco_calor') }}
    where x_31983 is null
       or y_31983 is null
       or x_31983 not between 140000 and 260000
       or y_31983 not between 8210000 and 8300000
       or latitude not between -16.15 and -15.45
       or longitude not between -48.35 and -47.25
       or geom is null
       or st_isempty(geom)
       or not st_isvalid(geom)
),

violacoes_imoveis as (
    select
        'dim_imovel_car'::varchar  as modelo,
        sk_imovel                  as chave_registro,
        st_xmin(geom)              as x_min,
        st_xmax(geom)              as x_max,
        st_ymin(geom)              as y_min,
        st_ymax(geom)              as y_max
    from {{ ref('dim_imovel_car') }}
    where geom is null
       or st_isempty(geom)
       or not st_isvalid(geom)
       or st_xmin(geom) < 130000
       or st_xmax(geom) > 270000
       or st_ymin(geom) < 8200000
       or st_ymax(geom) > 8310000
),

violacoes_territorio as (
    select
        'dim_territorio'::varchar  as modelo,
        sk_territorio              as chave_registro,
        st_xmin(geom)              as x_min,
        st_xmax(geom)              as x_max,
        st_ymin(geom)              as y_min,
        st_ymax(geom)              as y_max
    from {{ ref('dim_territorio') }}
    where geom is null
       or st_isempty(geom)
       or not st_isvalid(geom)
       or st_xmin(geom) < 130000
       or st_xmax(geom) > 270000
       or st_ymin(geom) < 8200000
       or st_ymax(geom) > 8310000
)

select * from violacoes_focos
union all
select * from violacoes_imoveis
union all
select * from violacoes_territorio

