-- Resposta da pergunta de gestao: quais imoveis rurais do DF tiveram focos de calor
-- reincidentes em reserva legal, APP ou ate 1 km de unidade de conservacao entre
-- 2015 e 2025, na ordem em que devem ser vistoriados.
--
-- Reincidente: foco em area protegida em pelo menos 2 anos civis (UTC) distintos.
-- Ordem: Indice de Prioridade de Vistoria (docs/adr/06-indice-de-prioridade-de-vistoria.md).
-- Granularidade do resultado: uma linha por imovel reincidente.
-- total_focos soma os focos distintos do imovel; um foco sobre imoveis sobrepostos
-- no SICAR e contado em cada um deles.
--
-- Execucao: docker compose --profile transformacao run --rm dbt show --select consulta_pergunta_gestao --limit 20

select
    posicao,
    cod_imovel,
    regiao_administrativa,
    situacao,
    area_ha,
    classificacao_prioridade,
    indice_prioridade,
    anos_com_foco,
    ultimo_ano_com_foco,
    lista_anos,
    total_focos,
    dias_com_foco,
    atinge_reserva_legal,
    atinge_app,
    atinge_uc_1km
from {{ ref('painel_imoveis_prioritarios') }}
order by posicao
