with fonte as (
    select *
    from {{ source('oltp', 'unidade_conservacao') }}
)

select
    id_uc::integer                                                      as id_uc,
    trim(nome)                                                          as nome,
    trim(categoria)                                                     as categoria,
    trim(grupo)                                                         as grupo,
    area_ha::double                                                     as area_ha,
    trim(fonte)                                                         as fonte,
    data_download::date                                                 as data_download,
    data_hora_ingestao::timestamptz                                     as data_hora_ingestao,
    geom::geometry('EPSG:31983')                                        as geom
from fonte
