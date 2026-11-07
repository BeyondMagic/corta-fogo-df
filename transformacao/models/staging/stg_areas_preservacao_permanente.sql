with fonte as (
    select *
    from {{ source('oltp', 'area_preservacao_permanente') }}
)

select
    id_app::integer                                                     as id_app,
    upper(trim(cod_imovel))                                             as cod_imovel,
    trim(tipo)                                                          as tipo,
    area_ha::double                                                     as area_ha,
    trim(fonte)                                                         as fonte,
    data_download::date                                                 as data_download,
    data_hora_ingestao::timestamptz                                     as data_hora_ingestao,
    geom::geometry('EPSG:31983')                                        as geom
from fonte
