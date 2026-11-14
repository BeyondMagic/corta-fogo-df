-- Pares foco e imovel rural: uma linha por (id_foco, cod_imovel).
--
-- O cruzamento usa a versao cadastral vigente na data do evento (SCD Tipo 2):
-- o ponto do foco deve estar dentro do perimetro daquela versao, e a versao nao pode
-- ser uma exclusao logica. Assim a geometria e os atributos do par vem da mesma versao.
-- As vigencias de um imovel nao se sobrepoem, entao cada foco casa com no maximo uma
-- versao por imovel.
--
-- A juncao espacial devolve so as chaves, em CTE materializada e sem nenhum outro
-- predicado: assim o DuckDB usa o operador de juncao espacial (0,1 s). Com o filtro de
-- vigencia na mesma juncao, o plano cai para laco aninhado (160 s medidos na base atual).

with pares_espaciais as materialized (
    select
        f.id_foco,
        v.sk_imovel
    from {{ ref('stg_focos_calor') }} f
    inner join {{ ref('int_imoveis_versoes') }} v
        on st_intersects(f.geom, v.geom)
)

select
    f.id_foco,
    v.cod_imovel,
    v.sk_imovel,
    f.data_hora_evento,
    f.data_evento_local,
    f.ano,
    f.mes,
    f.satelite,
    f.is_satelite_referencia,
    v.situacao  as situacao_imovel,
    v.condicao  as condicao_imovel,
    v.area_ha   as area_ha_imovel
from pares_espaciais p
inner join {{ ref('stg_focos_calor') }} f
    on f.id_foco = p.id_foco
inner join {{ ref('int_imoveis_versoes') }} v
    on v.sk_imovel = p.sk_imovel
where not v.is_excluido
  and f.data_hora_evento >= v.dbt_valid_from
  and f.data_hora_evento < v.dbt_valid_to
