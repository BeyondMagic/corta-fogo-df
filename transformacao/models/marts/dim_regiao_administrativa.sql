-- Dimensao de Regioes Administrativas do DF: uma linha por RA (37).
-- sk_regiao_administrativa = md5(codigo): estavel entre recargas do PostGIS.

select
    md5(codigo)                                                         as sk_regiao_administrativa,
    codigo,
    nome,
    area_km2,
    data_download,
    geom
from {{ ref('stg_regioes_administrativas') }}
