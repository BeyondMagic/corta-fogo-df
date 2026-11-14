{#
  Atribui uma Regiao Administrativa a cada linha de `relacao`, pelo ponto `ponto`.
  1. RA que contem o ponto (em empate de borda, a de menor codigo).
  2. Ponto fora de todas as RAs (borda do DF, imprecisao da malha): a RA mais proxima,
     ate var('tolerancia_ra_m') metros.
  3. Alem da tolerancia: sem RA (sk_regiao_administrativa nulo).
  Devolve uma linha por `chave`.
#}
{% macro atribuir_regiao_administrativa(relacao, chave, ponto) %}
with pontos as (
    select
        {{ chave }}                                                     as chave,
        {{ ponto }}                                                     as ponto
    from {{ relacao }}
    where {{ ponto }} is not null
),

ras as (
    select
        md5(codigo)                                                     as sk_regiao_administrativa,
        codigo,
        geom
    from {{ ref('stg_regioes_administrativas') }}
),

dentro as (
    select
        p.chave,
        r.sk_regiao_administrativa,
        r.codigo
    from pontos p
    inner join ras r
        on st_intersects(p.ponto, r.geom)
    qualify row_number() over (partition by p.chave order by r.codigo) = 1
),

fora as (
    select p.chave, p.ponto
    from pontos p
    where not exists (select 1 from dentro d where d.chave = p.chave)
),

mais_proxima as (
    select
        f.chave,
        arg_min(r.sk_regiao_administrativa, st_distance(f.ponto, r.geom)) as sk_regiao_administrativa,
        min(st_distance(f.ponto, r.geom))                                as distancia_m
    from fora f
    cross join ras r
    group by f.chave
)

select
    chave                                                               as {{ chave }},
    sk_regiao_administrativa,
    0.0::double                                                         as distancia_ra_m
from dentro

union all

select
    chave                                                               as {{ chave }},
    case
        when distancia_m <= {{ var('tolerancia_ra_m') }} then sk_regiao_administrativa
    end                                                                 as sk_regiao_administrativa,
    distancia_m::double                                                 as distancia_ra_m
from mais_proxima
{% endmacro %}
