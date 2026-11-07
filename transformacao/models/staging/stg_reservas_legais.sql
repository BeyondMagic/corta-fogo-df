with fonte as (
    select *
    from {{ source('oltp', 'reserva_legal') }}
)

select
    id_reserva::integer                                                 as id_reserva,
    upper(trim(cod_imovel))                                             as cod_imovel,
    trim(situacao)                                                      as situacao,
    area_ha::double                                                     as area_ha,
    data_download::date                                                 as data_download,
    data_hora_ingestao::timestamptz                                     as data_hora_ingestao,
    geom::geometry('EPSG:31983')                                        as geom
from fonte
