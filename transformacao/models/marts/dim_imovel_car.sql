-- Dimensao SCD Tipo 2 de imoveis rurais: uma linha por versao cadastral (Issue #19).
-- A logica de versoes (descarte de reentregas do CDC, abertura e fechamento da
-- vigencia) fica em int_imoveis_versoes, porque o cruzamento espacial com os focos
-- (int_focos_imoveis) usa a geometria de cada versao e nao pode depender de um mart.

select
    sk_imovel,
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
    dbt_valid_from,
    dbt_valid_to,
    is_current
from {{ ref('int_imoveis_versoes') }}
