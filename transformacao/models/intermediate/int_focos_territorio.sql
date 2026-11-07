with focos as (
    select *
    from {{ ref('stg_focos_calor') }}
),

imoveis_por_foco as (
    select
        id_foco,
        count(distinct cod_imovel)::integer as qtd_imoveis
    from {{ ref('int_focos_imoveis') }}
    group by id_foco
),

areas_por_foco as (
    select
        id_foco,
        bool_or(tipo_area = 'reserva_legal')                        as em_reserva_legal,
        bool_or(tipo_area = 'app')                                  as em_app,
        bool_or(tipo_area = 'uc_1km')                               as ate_1km_uc,
        min(distancia_m) filter (where tipo_area = 'uc_1km')        as distancia_min_uc_m
    from {{ ref('int_focos_areas_protegidas') }}
    group by id_foco
)

select
    f.id_foco,
    f.satelite,
    f.is_satelite_referencia,
    f.data_hora_evento,
    f.data_hora_ingestao,
    f.data_evento_local,
    f.ano,
    f.mes,
    f.latitude,
    f.longitude,
    f.x_31983,
    f.y_31983,
    f.geom,
    f.municipio,
    f.bioma,
    f.risco_fogo,
    f.origem_ingestao,
    f.operacao_cdc,
    coalesce(im.qtd_imoveis, 0)::integer                            as qtd_imoveis,
    (coalesce(im.qtd_imoveis, 0) > 0)                               as em_imovel_car,
    coalesce(ap.em_reserva_legal, false)                            as em_reserva_legal,
    coalesce(ap.em_app, false)                                      as em_app,
    coalesce(ap.ate_1km_uc, false)                                  as ate_1km_uc,
    ap.distancia_min_uc_m                                           as distancia_min_uc_m,
    (
        coalesce(ap.em_reserva_legal, false)
        or coalesce(ap.em_app, false)
        or coalesce(ap.ate_1km_uc, false)
    )                                                               as em_area_protegida
from focos f
left join imoveis_por_foco im
    on f.id_foco = im.id_foco
left join areas_por_foco ap
    on f.id_foco = ap.id_foco
