-- Reconciliacao entre as duas implementacoes da pergunta de gestao:
-- gold.mv_imoveis_reincidentes_areas_protegidas (juncao espacial direta no PostGIS, E1)
-- e fct_reincidencia_imovel (dbt-duckdb sobre o Delta, E3).
-- Cada linha devolvida e um imovel que so existe em um dos lados ou que diverge em
-- anos, focos ou criterios atingidos.
--
-- Severidade warn: os dois lados leem o cadastro em momentos diferentes. A MV e
-- atualizada pelo servico refresh_gold na carga; o fato usa a versao do imovel vigente
-- na data de cada foco (SCD Tipo 2) e a tabela Delta mantida pelo CDC. Uma retificacao
-- de perimetro ou uma exclusao posterior ao ultimo REFRESH gera divergencia legitima.
-- Com cadastro e MV no mesmo estado, o teste devolve zero linhas.

{{ config(severity='warn') }}

with fato as (
    select
        cod_imovel,
        anos_com_foco,
        total_focos,
        atinge_reserva_legal,
        atinge_app,
        atinge_uc_1km
    from {{ ref('fct_reincidencia_imovel') }}
    where imovel_reincidente
),

mv as (
    select
        cod_imovel::varchar                                             as cod_imovel,
        anos_com_foco::integer                                          as anos_com_foco,
        total_focos::integer                                            as total_focos,
        atinge_reserva_legal,
        atinge_app,
        atinge_uc_1km
    from {{ source('oltp_gold', 'mv_imoveis_reincidentes_areas_protegidas') }}
)

select 'so_no_fato_dbt' as origem, *
from (select * from fato except select * from mv)

union all

select 'so_na_mv_postgis' as origem, *
from (select * from mv except select * from fato)
