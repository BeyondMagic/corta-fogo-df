-- Numeros consolidados da pergunta de gestao, sobre fct_reincidencia_imovel e a tabela
-- de consumo painel_imoveis_prioritarios. Complementa consulta_pergunta_gestao.sql.
-- Cada linha e uma metrica: contagens de imoveis (distintos por cod_imovel) e de focos.
-- Os criterios (reserva legal, APP, UC a 1 km) se sobrepoem: um imovel pode atingir mais de um.
--
-- Execucao: docker compose --profile transformacao run --rm dbt show --select resumo_pergunta_gestao --limit 40

with reincidentes as (
    select * from {{ ref('painel_imoveis_prioritarios') }}
),

metricas as (
    select 1 as ordem, 'imoveis_ativos_no_cadastro' as metrica, count(*)::bigint as valor
    from {{ ref('dim_imovel_car') }}
    where is_current and not is_excluido

    union all
    select 2, 'imoveis_com_foco_em_area_protegida', count(*) from {{ ref('fct_reincidencia_imovel') }}

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
    select 8, 'reincidentes_em_prioridade_critica', count(*) filter (where classificacao_prioridade = 'PRIORIDADE CRITICA') from reincidentes

    union all
    select 10 + anos_com_foco, 'reincidentes_com_' || anos_com_foco || '_anos_de_foco', count(*)
    from reincidentes
    group by anos_com_foco
)

select metrica, valor
from metricas
order by ordem
