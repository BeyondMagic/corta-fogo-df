-- As vigencias de um imovel devem ser contiguas e sem sobreposicao: cada versao
-- termina exatamente onde a seguinte comeca, e nenhuma tem duracao nula ou negativa.
-- Assim, todo instante cai em uma unica versao no cruzamento temporal com focos.
with ordenadas as (
    select
        cod_imovel,
        sk_imovel,
        dbt_valid_from,
        dbt_valid_to,
        lead(dbt_valid_from) over (
            partition by cod_imovel
            order by dbt_valid_from
        ) as inicio_seguinte
    from {{ ref('dim_imovel_car') }}
)

select *
from ordenadas
where dbt_valid_to <= dbt_valid_from
   or (inicio_seguinte is not null and dbt_valid_to <> inicio_seguinte)
