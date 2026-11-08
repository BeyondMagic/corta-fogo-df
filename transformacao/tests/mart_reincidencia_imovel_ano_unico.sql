-- Grain do mart: no maximo uma linha por (cod_imovel, ano).
select
    cod_imovel,
    ano,
    count(*) as qtd
from {{ ref('mart_reincidencia_imovel_ano') }}
group by
    cod_imovel,
    ano
having count(*) > 1
