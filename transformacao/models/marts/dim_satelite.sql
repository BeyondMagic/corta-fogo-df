-- Dimensao de satelites detectores: uma linha por nome de satelite.

select
    md5(satelite)                                                       as sk_satelite,
    satelite,
    bool_or(is_satelite_referencia)                                     as is_referencia
from {{ ref('stg_focos_calor') }}
group by satelite
