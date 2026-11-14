with fonte as (
    select *
    from {{ source('oltp', 'regiao_administrativa') }}
)

select
    id_ra::integer                                                      as id_ra,
    upper(trim(codigo))                                                 as codigo,
    trim(nome)                                                          as nome,
    area_km2::double                                                    as area_km2,
    trim(fonte)                                                         as fonte,
    data_download::date                                                 as data_download,
    data_hora_ingestao::timestamptz                                     as data_hora_ingestao,
    geom::geometry('EPSG:31983')                                        as geom
from fonte
