-- Indice de Prioridade de Vistoria (IPV, ADR 0004): uma linha por imovel reincidente.
--
-- IPV = 100 x (peso_recorrencia x recorrencia + peso_recencia x recencia
--              + peso_intensidade x intensidade), cada componente entre 0 e 1:
--   recorrencia: anos com foco em area protegida, de 2 anos (0) aos 11 da serie (1);
--   recencia:    ultimo ano com foco, de 2015 (0) a 2025 (1);
--   intensidade: dias distintos com foco por 100 ha, saturada nos percentis 5 e 95
--                dos reincidentes e normalizada min-max entre eles.
--
-- A intensidade conta dias, e nao deteccoes: um mesmo fogo captado por varios satelites
-- no mesmo dia conta uma vez, o que neutraliza a entrada de sensores novos na serie.
-- A area do denominador tem piso em var('area_minima_ha'), o pixel do sensor mais fino
-- da serie: nenhuma deteccao localiza o fogo com resolucao melhor que essa.
-- A classificacao usa os quartis do IPV entre os reincidentes.

{% set anos_da_serie = var('ano_fim_serie') - var('ano_inicio_serie') + 1 %}

with reincidentes as (
    select
        cod_imovel,
        anos_com_foco,
        ultimo_ano_com_foco,
        dias_com_foco,
        area_ha,
        dias_com_foco::double
            / greatest(coalesce(area_ha, 0), {{ var('area_minima_ha') }}) * 100 as dias_com_foco_por_100ha
    from {{ ref('int_metricas_imovel') }}
    where anos_com_foco >= {{ var('anos_minimos_reincidencia') }}
),

limites as (
    select
        quantile_cont(dias_com_foco_por_100ha, 0.05)                    as d05,
        quantile_cont(dias_com_foco_por_100ha, 0.95)                    as d95
    from reincidentes
),

componentes as (
    select
        r.cod_imovel,
        r.dias_com_foco_por_100ha,
        least(greatest(
            (r.anos_com_foco - {{ var('anos_minimos_reincidencia') }})::double
                / ({{ anos_da_serie }} - {{ var('anos_minimos_reincidencia') }}),
            0), 1)                                                      as componente_recorrencia,
        least(greatest(
            (r.ultimo_ano_com_foco - {{ var('ano_inicio_serie') }})::double
                / ({{ var('ano_fim_serie') }} - {{ var('ano_inicio_serie') }}),
            0), 1)                                                      as componente_recencia,
        case
            when l.d95 > l.d05
                then (least(greatest(r.dias_com_foco_por_100ha, l.d05), l.d95) - l.d05) / (l.d95 - l.d05)
            else 0
        end                                                             as componente_intensidade
    from reincidentes r
    cross join limites l
),

indice as (
    select
        *,
        round(
            100 * (
                {{ var('peso_recorrencia') }} * componente_recorrencia
                + {{ var('peso_recencia') }} * componente_recencia
                + {{ var('peso_intensidade') }} * componente_intensidade
            ),
            1
        )                                                               as indice_prioridade
    from componentes
),

quartis as (
    select
        quantile_cont(indice_prioridade, 0.25)                          as q25,
        quantile_cont(indice_prioridade, 0.50)                          as q50,
        quantile_cont(indice_prioridade, 0.75)                          as q75
    from indice
)

select
    i.cod_imovel,
    round(i.dias_com_foco_por_100ha, 2)                                 as dias_com_foco_por_100ha,
    round(i.componente_recorrencia, 4)                                  as componente_recorrencia,
    round(i.componente_recencia, 4)                                     as componente_recencia,
    round(i.componente_intensidade, 4)                                  as componente_intensidade,
    i.indice_prioridade,
    case
        when i.indice_prioridade >= q.q75 then 'PRIORIDADE CRITICA'
        when i.indice_prioridade >= q.q50 then 'PRIORIDADE ALTA'
        when i.indice_prioridade >= q.q25 then 'PRIORIDADE MEDIA'
        else 'PRIORIDADE BAIXA'
    end                                                                 as classificacao_prioridade
from indice i
cross join quartis q
