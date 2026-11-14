-- Versoes cadastrais dos imoveis rurais (SCD Tipo 2, Issue #19): uma linha por versao.
-- Base de dim_imovel_car e do cruzamento espacial historico em int_focos_imoveis.
--
-- 1. Linha do snapshot com o mesmo conteudo (atributos, geometria e exclusao) da linha
--    anterior do imovel nao e versao nova: vem de reentrega do CDC (at-least-once) ou de
--    recarga do OLTP com os mesmos dados. Essas linhas sao descartadas e a validade e
--    recalculada sobre as versoes restantes.
-- 2. dbt_valid_from da primeira versao de cada imovel e aberto em
--    var('inicio_vigencia_aberta'): o snapshot so comeca a observar o cadastro na
--    carga inicial do CDC, e sem essa abertura nenhum foco anterior a carga
--    encontraria versao vigente. O instante real da gravacao segue em data_hora_ingestao.
-- 3. dbt_valid_to da versao corrente e fechado em var('fim_vigencia_aberta'), para que
--    o cruzamento temporal use sempre: dbt_valid_from <= data_hora_evento < dbt_valid_to.
-- 4. O dbt-duckdb grava dbt_valid_from como TIMESTAMP sem fuso; o valor esta em UTC
--    (TimeZone do profile) e e convertido explicitamente para TIMESTAMPTZ.

with snapshot as (
    select
        * replace (cast(dbt_valid_from as timestamptz) as dbt_valid_from),
        md5(concat_ws('|',
            situacao, condicao, cast(area_ha as varchar), cast(data_download as varchar),
            geom_ewkb_hex, cast(is_excluido as varchar)
        ))                                                              as hash_conteudo
    from {{ ref('snp_imovel_car') }}
),

com_anterior as (
    select
        *,
        lag(hash_conteudo) over (
            partition by cod_imovel
            order by dbt_valid_from
        ) as hash_versao_anterior
    from snapshot
),

-- Uma versao so existe quando o conteudo do imovel muda. Reentregas do CDC (mesmo
-- lsn_origem) e recargas do OLTP com os mesmos dados (lsn_origem novo, conteudo igual)
-- geram linhas no snapshot, mas nao versoes.
versoes as (
    select * exclude (hash_conteudo, hash_versao_anterior)
    from com_anterior
    where hash_versao_anterior is null
       or hash_conteudo <> hash_versao_anterior
),

validade as (
    select
        *,
        lead(dbt_valid_from) over (
            partition by cod_imovel
            order by dbt_valid_from
        ) as proximo_valid_from,
        row_number() over (
            partition by cod_imovel
            order by dbt_valid_from
        ) as numero_versao
    from versoes
)

select
    md5(cod_imovel || '|' || cast(lsn_origem as varchar))               as sk_imovel,
    cod_imovel,
    numero_versao,
    situacao,
    condicao,
    area_ha,
    data_download,
    geom_ewkb_hex,
    geom,
    is_excluido,
    operacao_cdc,
    lsn_origem,
    data_hora_ingestao,
    case
        when numero_versao = 1
            then cast('{{ var("inicio_vigencia_aberta") }}' as timestamptz)
        else dbt_valid_from
    end                                                                 as dbt_valid_from,
    coalesce(
        proximo_valid_from,
        cast('{{ var("fim_vigencia_aberta") }}' as timestamptz)
    )                                                                   as dbt_valid_to,
    (proximo_valid_from is null)                                        as is_current
from validade
