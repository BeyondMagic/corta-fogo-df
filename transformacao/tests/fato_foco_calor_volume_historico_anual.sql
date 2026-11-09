-- Teste de volume historico (Issue #21):
-- Confere que cada ano da serie (2015 a 2025) esta presente em fato_foco_calor
-- e contem ao menos 500 ocorrencias no total e 80 no satelite de referencia (AQUA_M-T),
-- evitando ingestao truncada ou perda de particoes anuais.
-- Na serie real do DF (E1), o menor volume anual foi 2018 (948 total, 88 no AQUA_M-T).

with anos_esperados as (
    select unnest(generate_series(2015, 2025))::integer as ano
),

contagem_por_ano as (
    select
        ano,
        count(*)                                            as total_focos,
        count(*) filter (where is_satelite_referencia)      as focos_referencia
    from {{ ref('fato_foco_calor') }}
    group by ano
)

select
    a.ano,
    coalesce(c.total_focos, 0)      as total_focos,
    coalesce(c.focos_referencia, 0) as focos_referencia
from anos_esperados a
left join contagem_por_ano c
    on a.ano = c.ano
where coalesce(c.total_focos, 0) < 500
   or coalesce(c.focos_referencia, 0) < 80

