-- Dimensao calendario: uma linha por data civil (2015-01-01 a 2025-12-31).
-- Estacao seca do DF: maio a setembro (meses 5 a 9), conforme volumetria da E1.

with calendario as (
    select data::date as data
    from generate_series(
        date '2015-01-01',
        date '2025-12-31',
        interval '1 day'
    ) as t(data)
)

select
    (year(data) * 10000 + month(data) * 100 + day(data))::integer      as sk_tempo,
    data,
    year(data)::integer                                                 as ano,
    month(data)::integer                                                as mes,
    day(data)::integer                                                  as dia,
    case month(data)
        when 1 then 'janeiro'
        when 2 then 'fevereiro'
        when 3 then 'marco'
        when 4 then 'abril'
        when 5 then 'maio'
        when 6 then 'junho'
        when 7 then 'julho'
        when 8 then 'agosto'
        when 9 then 'setembro'
        when 10 then 'outubro'
        when 11 then 'novembro'
        else 'dezembro'
    end                                                                 as nome_mes,
    (month(data) between 5 and 9)                                       as is_estacao_seca
from calendario
