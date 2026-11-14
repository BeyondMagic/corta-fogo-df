-- Mart da pergunta de gestao: uma linha por imovel rural por ano UTC
-- em que houve foco no imovel em RL, APP ou faixa de 1 km de UC.
-- A regra do cruzamento e a versao SCD2 vigente na data do foco vem de
-- int_focos_protegidos_imovel.

with por_ano as (
    select
        cod_imovel,
        ano,
        count(distinct id_foco)::integer                                as total_focos,
        bool_or(em_reserva_legal_do_imovel)                             as atinge_reserva_legal,
        bool_or(em_app)                                                 as atinge_app,
        bool_or(ate_1km_uc)                                             as atinge_uc_1km,
        arg_max(sk_imovel, data_hora_evento)                            as sk_imovel,
        arg_max(situacao_imovel, data_hora_evento)                      as situacao,
        arg_max(condicao_imovel, data_hora_evento)                      as condicao,
        arg_max(area_ha_imovel, data_hora_evento)                       as area_ha
    from {{ ref('int_focos_protegidos_imovel') }}
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
),

cadastro_atual as (
    select
        cod_imovel,
        is_excluido
    from {{ ref('dim_imovel_car') }}
    where is_current
)

select
    h.cod_imovel,
    h.ano,
    h.sk_imovel,
    h.situacao,
    h.condicao,
    h.area_ha,
    c.is_excluido,
    h.total_focos,
    h.atinge_reserva_legal,
    h.atinge_app,
    h.atinge_uc_1km,
    h.anos_com_foco_protegido,
    h.lista_anos_protegidos,
    (h.anos_com_foco_protegido >= 2)                                    as imovel_reincidente
from com_historico h
inner join cadastro_atual c
    on h.cod_imovel = c.cod_imovel
