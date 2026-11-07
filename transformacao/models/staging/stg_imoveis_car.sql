with fonte as (
    select *
    from {{ source('lakehouse', 'imovel_car') }}
)

select
    upper(trim(cod_imovel))                                             as cod_imovel,
    trim(situacao)                                                      as situacao,
    trim(condicao)                                                      as condicao,
    area_ha::double                                                     as area_ha,
    data_download::date                                                 as data_download,
    geom_ewkb_hex::varchar                                              as geom_ewkb_hex,
    st_geomfromhexewkb(geom_ewkb_hex)::geometry('EPSG:31983')           as geom,
    data_hora_ingestao::timestamptz                                     as data_hora_ingestao,
    origem_ingestao::varchar                                            as origem_ingestao,
    operacao_cdc::varchar                                               as operacao_cdc,
    (operacao_cdc = 'D')                                                as is_excluido,
    lsn_origem::bigint                                                  as lsn_origem
from fonte
