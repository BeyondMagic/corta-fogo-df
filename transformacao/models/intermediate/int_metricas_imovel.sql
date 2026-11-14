-- Metricas da pergunta de gestao por imovel rural: uma linha por cod_imovel com ao
-- menos um foco em area protegida entre 2015 e 2025.
-- Contagens sao aditivas entre imoveis, com a ressalva de que um foco sobre imoveis
-- sobrepostos no SICAR conta em cada um deles.
-- Atributos cadastrais (sk_imovel, situacao, condicao, area_ha): versao vigente no
-- foco mais recente do imovel.

select
    cod_imovel,
    arg_max(sk_imovel, data_hora_evento)                                as sk_imovel,
    arg_max(situacao_imovel, data_hora_evento)                          as situacao,
    arg_max(condicao_imovel, data_hora_evento)                          as condicao,
    arg_max(area_ha_imovel, data_hora_evento)                           as area_ha,
    count(distinct ano)::integer                                        as anos_com_foco,
    min(ano)::integer                                                   as primeiro_ano_com_foco,
    max(ano)::integer                                                   as ultimo_ano_com_foco,
    list(distinct ano order by ano)                                     as lista_anos,
    count(distinct id_foco)::integer                                    as total_focos,
    count(distinct data_evento_local)::integer                          as dias_com_foco,
    (count(distinct id_foco) filter (where is_satelite_referencia))::integer        as focos_satelite_referencia,
    (count(distinct id_foco) filter (where is_estacao_seca))::integer               as focos_estacao_seca,
    (count(distinct id_foco) filter (where em_reserva_legal_do_imovel))::integer    as focos_reserva_legal,
    (count(distinct id_foco) filter (where em_app))::integer                        as focos_app,
    (count(distinct id_foco) filter (where ate_1km_uc))::integer                    as focos_uc_1km,
    bool_or(em_reserva_legal_do_imovel)                                 as atinge_reserva_legal,
    bool_or(em_app)                                                     as atinge_app,
    bool_or(ate_1km_uc)                                                 as atinge_uc_1km
from {{ ref('int_focos_protegidos_imovel') }}
group by cod_imovel
