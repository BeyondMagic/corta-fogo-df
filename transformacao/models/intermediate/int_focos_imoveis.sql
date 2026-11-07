with focos as (
    select
        id_foco,
        data_hora_evento,
        data_evento_local,
        ano,
        mes,
        satelite,
        is_satelite_referencia,
        geom
    from {{ ref('stg_focos_calor') }}
),

imoveis_ativos as (
    select
        cod_imovel,
        situacao,
        condicao,
        area_ha,
        geom
    from {{ ref('stg_imoveis_car') }}
    where not is_excluido
)

select
    f.id_foco,
    i.cod_imovel,
    f.data_hora_evento,
    f.data_evento_local,
    f.ano,
    f.mes,
    f.satelite,
    f.is_satelite_referencia,
    i.situacao as situacao_imovel,
    i.condicao as condicao_imovel,
    i.area_ha  as area_ha_imovel
from focos f
inner join imoveis_ativos i
    on st_intersects(f.geom, i.geom)
