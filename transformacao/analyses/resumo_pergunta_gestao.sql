-- Numeros consolidados da pergunta de gestao (Entrega 3), calculados sobre
-- mart_reincidencia_imovel_ano. Complementa consulta_pergunta_gestao.sql.
-- Cada linha e uma metrica: contagens de imoveis (distintos por cod_imovel) e de focos.
-- Os criterios (reserva legal, APP, UC a 1 km) se sobrepoem: um imovel pode atingir mais de um.
--
-- Execucao: docker compose --profile transformacao run --rm dbt show --select resumo_pergunta_gestao --limit 40

with por_imovel as (
    select
        cod_imovel,
        max(anos_com_foco_protegido)    as anos_com_foco,
        bool_or(imovel_reincidente)     as reincidente,
        sum(total_focos)::bigint        as total_focos,
        bool_or(atinge_reserva_legal)   as atinge_reserva_legal,
        bool_or(atinge_app)             as atinge_app,
        bool_or(atinge_uc_1km)          as atinge_uc_1km
    from {{ ref('mart_reincidencia_imovel_ano') }}
    group by cod_imovel
),

reincidentes as (
    select * from por_imovel where reincidente
),

metricas as (
    select 1 as ordem, 'imoveis_ativos_no_cadastro' as metrica, count(*)::bigint as valor
    from {{ ref('dim_imovel_car') }}
    where is_current and not is_excluido

    union all
    select 2, 'imoveis_com_foco_em_area_protegida', count(*) from por_imovel

    union all
    select 3, 'imoveis_reincidentes', count(*) from reincidentes

    union all
    select 4, 'reincidentes_com_foco_em_reserva_legal', count(*) filter (where atinge_reserva_legal) from reincidentes

    union all
    select 5, 'reincidentes_com_foco_em_app', count(*) filter (where atinge_app) from reincidentes

    union all
    select 6, 'reincidentes_com_foco_ate_1km_de_uc', count(*) filter (where atinge_uc_1km) from reincidentes

    union all
    select 7, 'focos_em_imoveis_reincidentes', coalesce(sum(total_focos), 0) from reincidentes

    union all
    select 10 + anos_com_foco, 'reincidentes_com_' || anos_com_foco || '_anos_de_foco', count(*)
    from reincidentes
    group by anos_com_foco
)

select metrica, valor
from metricas
order by ordem
