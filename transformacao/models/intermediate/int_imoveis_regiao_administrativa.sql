-- Regiao Administrativa de cada versao de imovel rural (uma linha por sk_imovel).
-- Usa um ponto interno do perimetro (st_pointonsurface): imoveis grandes cruzam mais
-- de uma RA, e o ponto interno escolhe uma so, de forma deterministica.

{% set versoes %}
(
    select
        sk_imovel,
        st_pointonsurface(geom)                                         as ponto_interno
    from {{ ref('int_imoveis_versoes') }}
    where geom is not null
)
{% endset %}

{{ atribuir_regiao_administrativa(versoes, 'sk_imovel', 'ponto_interno') }}
