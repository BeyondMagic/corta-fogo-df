-- Dimensao conformada de feicoes protegidas (UC, APP, Reserva Legal).
-- sk_territorio estavel entre recargas: md5(tipo_area || WKT da geometria).
-- id_feicao_origem e o IDENTITY do PostGIS do ciclo atual (so auditoria intra-run).

with uc as (
    select
        md5('unidade_conservacao|' || st_astext(geom))                  as sk_territorio,
        'unidade_conservacao'::varchar                                  as tipo_area,
        id_uc                                                           as id_feicao_origem,
        nome                                                            as nome_area,
        categoria                                                       as categoria_area,
        grupo                                                           as grupo_area,
        null::varchar                                                   as cod_imovel,
        area_ha,
        {{ var('raio_uc_m') }}::double                                  as raio_amortecimento_m,
        data_download,
        geom
    from {{ ref('stg_unidades_conservacao') }}
),

app as (
    select
        md5('app|' || st_astext(geom))                                  as sk_territorio,
        'app'::varchar                                                  as tipo_area,
        id_app                                                          as id_feicao_origem,
        tipo                                                            as nome_area,
        tipo                                                            as categoria_area,
        null::varchar                                                   as grupo_area,
        cod_imovel,
        area_ha,
        0.0::double                                                     as raio_amortecimento_m,
        data_download,
        geom
    from {{ ref('stg_areas_preservacao_permanente') }}
),

reserva as (
    select
        md5('reserva_legal|' || st_astext(geom))                        as sk_territorio,
        'reserva_legal'::varchar                                        as tipo_area,
        id_reserva                                                      as id_feicao_origem,
        null::varchar                                                   as nome_area,
        situacao                                                        as categoria_area,
        null::varchar                                                   as grupo_area,
        cod_imovel,
        area_ha,
        0.0::double                                                     as raio_amortecimento_m,
        data_download,
        geom
    from {{ ref('stg_reservas_legais') }}
)

select * from uc
union all
select * from app
union all
select * from reserva
