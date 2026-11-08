-- Mart da pergunta de gestao: uma linha por imovel rural por ano UTC
-- em que houve foco no imovel em RL, APP ou faixa de 1 km de UC.
-- Join SCD2: versao do imovel vigente na data_hora_evento do foco.

with cruzamentos as (
    select
        fi.cod_imovel,
        fi.ano                                                          as ano,
        fi.id_foco,
        fi.data_hora_evento,
        d.sk_imovel,
        d.situacao,
        d.condicao,
        d.area_ha,
        d.is_excluido,
        bool_or(
            ap.tipo_area = 'reserva_legal'
            and ap.cod_imovel_feicao = fi.cod_imovel
        )                                                               as atinge_reserva_legal,
        bool_or(ap.tipo_area = 'app')                                   as atinge_app,
        bool_or(ap.tipo_area = 'uc_1km')                                as atinge_uc_1km
    from {{ ref('int_focos_imoveis') }} fi
    inner join {{ ref('dim_imovel_car') }} d
        on fi.cod_imovel = d.cod_imovel
        and fi.data_hora_evento >= d.dbt_valid_from
        and fi.data_hora_evento < d.dbt_valid_to
    inner join {{ ref('int_focos_areas_protegidas') }} ap
        on fi.id_foco = ap.id_foco
        and (
            ap.tipo_area in ('app', 'uc_1km')
            or (
                ap.tipo_area = 'reserva_legal'
                and ap.cod_imovel_feicao = fi.cod_imovel
            )
        )
    where fi.ano between 2015 and 2025
    group by
        fi.cod_imovel,
        fi.ano,
        fi.id_foco,
        fi.data_hora_evento,
        d.sk_imovel,
        d.situacao,
        d.condicao,
        d.area_ha,
        d.is_excluido
),

por_ano as (
    select
        cod_imovel,
        ano,
        count(distinct id_foco)::integer                                as total_focos,
        bool_or(atinge_reserva_legal)                                   as atinge_reserva_legal,
        bool_or(atinge_app)                                             as atinge_app,
        bool_or(atinge_uc_1km)                                          as atinge_uc_1km,
        arg_max(sk_imovel, data_hora_evento)                            as sk_imovel,
        arg_max(situacao, data_hora_evento)                             as situacao,
        arg_max(condicao, data_hora_evento)                             as condicao,
        arg_max(area_ha, data_hora_evento)                              as area_ha,
        arg_max(is_excluido, data_hora_evento)                          as is_excluido
    from cruzamentos
    group by
        cod_imovel,
        ano
),

com_historico as (
    select
        *,
        count(*) over (partition by cod_imovel)::integer                as anos_com_foco_protegido,
        list(ano) over (
            partition by cod_imovel
            order by ano
            rows between unbounded preceding and unbounded following
        )                                                               as lista_anos_protegidos
    from por_ano
)

select
    cod_imovel,
    ano,
    sk_imovel,
    situacao,
    condicao,
    area_ha,
    is_excluido,
    total_focos,
    atinge_reserva_legal,
    atinge_app,
    atinge_uc_1km,
    anos_com_foco_protegido,
    lista_anos_protegidos,
    (anos_com_foco_protegido >= 2)                                      as imovel_reincidente
from com_historico
