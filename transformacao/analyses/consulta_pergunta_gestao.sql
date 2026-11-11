-- Resposta da pergunta de gestao da E1 (Entrega 3): quais imoveis rurais do DF
-- tiveram focos de calor reincidentes em reserva legal, APP ou ate 1 km de
-- unidade de conservacao entre 2015 e 2025.
--
-- Reincidente: foco em area protegida em pelo menos 2 anos civis (UTC) distintos
-- (flag imovel_reincidente de mart_reincidencia_imovel_ano).
-- Granularidade do resultado: uma linha por imovel rural reincidente.
-- total_focos soma os focos distintos do imovel; um foco sobre imoveis sobrepostos
-- no SICAR e contado em cada um deles.
--
-- Execucao: docker compose --profile transformacao run --rm dbt show --select consulta_pergunta_gestao --limit 20

select
    cod_imovel,
    arg_max(situacao, ano)          as situacao,
    arg_max(area_ha, ano)           as area_ha,
    anos_com_foco_protegido         as anos_com_foco,
    lista_anos_protegidos           as lista_anos,
    sum(total_focos)::integer       as total_focos,
    bool_or(atinge_reserva_legal)   as atinge_reserva_legal,
    bool_or(atinge_app)             as atinge_app,
    bool_or(atinge_uc_1km)          as atinge_uc_1km
from {{ ref('mart_reincidencia_imovel_ano') }}
where imovel_reincidente
group by
    cod_imovel,
    anos_com_foco_protegido,
    lista_anos_protegidos
order by
    total_focos desc,
    cod_imovel
