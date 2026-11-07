-- Reproduz a regra da gold.mv_imoveis_reincidentes_areas_protegidas (migracao V7)
-- sobre os modelos da camada Intermediate para conferencia de contagem entre o
-- pipeline dbt-duckdb e a Materialized View da Entrega 1.

with cruzamentos as (
    select
        fi.cod_imovel,
        fi.situacao_imovel as situacao,
        fi.condicao_imovel as condicao,
        fi.area_ha_imovel  as area_ha,
        fi.id_foco,
        fi.ano             as ano_evento,
        bool_or(
            ap.tipo_area = 'reserva_legal'
            and ap.cod_imovel_feicao = fi.cod_imovel
        )                  as atinge_reserva_legal,
        bool_or(ap.tipo_area = 'app')    as atinge_app,
        bool_or(ap.tipo_area = 'uc_1km') as atinge_uc_1km
    from {{ ref('int_focos_imoveis') }} fi
    inner join {{ ref('int_focos_areas_protegidas') }} ap
        on fi.id_foco = ap.id_foco
        and (
            ap.tipo_area in ('app', 'uc_1km')
            or (ap.tipo_area = 'reserva_legal' and ap.cod_imovel_feicao = fi.cod_imovel)
        )
    where fi.ano between 2015 and 2025
    group by
        fi.cod_imovel,
        fi.situacao_imovel,
        fi.condicao_imovel,
        fi.area_ha_imovel,
        fi.id_foco,
        fi.ano
)

select
    cod_imovel,
    situacao,
    condicao,
    area_ha,
    count(distinct ano_evento)::integer             as anos_com_foco,
    list(distinct ano_evento order by ano_evento)   as lista_anos,
    count(distinct id_foco)::integer                as total_focos,
    bool_or(atinge_reserva_legal)                   as atinge_reserva_legal,
    bool_or(atinge_app)                             as atinge_app,
    bool_or(atinge_uc_1km)                          as atinge_uc_1km
from cruzamentos
group by
    cod_imovel,
    situacao,
    condicao,
    area_ha
having count(distinct ano_evento) >= 2
