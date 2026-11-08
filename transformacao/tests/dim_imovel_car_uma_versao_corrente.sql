-- Cada imovel deve ter exatamente uma versao corrente em dim_imovel_car.
select
    cod_imovel,
    count(*) filter (where is_current) as versoes_correntes
from {{ ref('dim_imovel_car') }}
group by cod_imovel
having count(*) filter (where is_current) <> 1
