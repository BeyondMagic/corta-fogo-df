-- Teste de distribuicao sazonal (Issue #21):
-- Comprova que pelo menos 70% dos focos de calor concentram-se no periodo de seca
-- do Distrito Federal (maio a setembro, is_estacao_seca em dim_tempo), tanto no
-- agregado global da serie (2015-2025) quanto em cada ano individualmente.
-- Detecta possiveis inversoes de calendario (MM/DD vs DD/MM) ou deslocamento de fuso.
-- Na serie real do DF (E1), a concentracao global na seca e 84,3% e o menor ano e 2020 (70,1%).

with focos_com_calendario as (
    select
        f.id_foco,
        f.ano,
        t.is_estacao_seca
    from {{ ref('fato_foco_calor') }} f
    inner join {{ ref('dim_tempo') }} t
        on f.sk_tempo = t.sk_tempo
),

proporcao_global as (
    select
        'GLOBAL_2015_2025'::varchar                                         as escopo,
        count(*)                                                            as total_focos,
        count(*) filter (where is_estacao_seca)                             as focos_seca,
        (count(*) filter (where is_estacao_seca))::double / nullif(count(*), 0) as proporcao_seca
    from focos_com_calendario
),

proporcao_anual as (
    select
        cast(ano as varchar)                                                as escopo,
        count(*)                                                            as total_focos,
        count(*) filter (where is_estacao_seca)                             as focos_seca,
        (count(*) filter (where is_estacao_seca))::double / nullif(count(*), 0) as proporcao_seca
    from focos_com_calendario
    group by ano
),

consolidado as (
    select * from proporcao_global
    union all
    select * from proporcao_anual
)

select
    escopo,
    total_focos,
    focos_seca,
    proporcao_seca
from consolidado
where total_focos is null
   or total_focos = 0
   or proporcao_seca < 0.70

