with fonte as (
    select *
    from {{ source('lakehouse', 'foco_calor') }}
)

select
    id_foco::varchar                                                    as id_foco,
    upper(trim(satelite))                                               as satelite,
    is_satelite_referencia::boolean                                     as is_satelite_referencia,
    (data_hora_evento::timestamp at time zone 'UTC')                    as data_hora_evento,
    (data_hora_ingestao::timestamp at time zone 'UTC')                  as data_hora_ingestao,
    ((data_hora_evento::timestamp at time zone 'UTC')
        at time zone '{{ var("fuso_local") }}')::date                   as data_evento_local,
    ano::integer                                                        as ano,
    mes::integer                                                        as mes,
    latitude::double                                                    as latitude,
    longitude::double                                                   as longitude,
    x_31983::double                                                     as x_31983,
    y_31983::double                                                     as y_31983,
    st_point(x_31983, y_31983)::geometry('EPSG:31983')                  as geom,
    upper(trim(municipio))                                              as municipio,
    trim(bioma)                                                         as bioma,
    risco_fogo::double                                                  as risco_fogo,
    origem_ingestao::varchar                                            as origem_ingestao,
    operacao_cdc::varchar                                               as operacao_cdc
from fonte
