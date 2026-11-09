with focos as (
    select
        id_foco,
        geom
    from {{ ref('stg_focos_calor') }}
),

em_reserva_legal as (
    select
        f.id_foco,
        md5('reserva_legal|' || coalesce(r.cod_imovel, '') || '|' || st_astext(r.geom)) as sk_territorio,
        'reserva_legal'::varchar                    as tipo_area,
        r.id_reserva                                as id_feicao,
        r.cod_imovel                                as cod_imovel_feicao,
        null::varchar                               as nome_area,
        r.situacao                                  as categoria_area,
        0.0::double                                 as distancia_m
    from focos f
    inner join {{ ref('stg_reservas_legais') }} r
        on st_intersects(f.geom, r.geom)
),

em_app as (
    select
        f.id_foco,
        md5('app|' || coalesce(a.cod_imovel, '') || '|' || st_astext(a.geom)) as sk_territorio,
        'app'::varchar                              as tipo_area,
        a.id_app                                    as id_feicao,
        a.cod_imovel                                as cod_imovel_feicao,
        a.tipo                                      as nome_area,
        a.tipo                                      as categoria_area,
        0.0::double                                 as distancia_m
    from focos f
    inner join {{ ref('stg_areas_preservacao_permanente') }} a
        on st_intersects(f.geom, a.geom)
),

ate_1km_uc as (
    select
        f.id_foco,
        md5('unidade_conservacao|' || st_astext(u.geom)) as sk_territorio,
        'uc_1km'::varchar                                as tipo_area,
        u.id_uc                                          as id_feicao,
        null::varchar                                    as cod_imovel_feicao,
        u.nome                                           as nome_area,
        u.categoria                                      as categoria_area,
        st_distance(f.geom, u.geom)::double              as distancia_m
    from focos f
    inner join {{ ref('stg_unidades_conservacao') }} u
        on st_dwithin(f.geom, u.geom, {{ var('raio_uc_m') }})
)

select * from em_reserva_legal
union all
select * from em_app
union all
select * from ate_1km_uc
