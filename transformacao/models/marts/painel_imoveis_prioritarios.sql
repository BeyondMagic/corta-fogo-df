-- Tabela de consumo do painel: responde a pergunta de gestao da E1, "quais imoveis
-- rurais do DF tiveram focos de calor reincidentes em reserva legal, APP ou a ate 1 km
-- de UC entre 2015 e 2025", na ordem em que devem ser vistoriados.
-- Uma linha por imovel reincidente que ainda existe no cadastro; posicao 1 e o de maior
-- Indice de Prioridade de Vistoria (ADR 0006). Imovel com cadastro cancelado, suspenso
-- ou pendente entra na fila e fica marcado em situacao e cadastro_ativo.
-- gerado_em e o instante da execucao do dbt: base da metrica de frescor (docs/frescor_sla.md).

select
    row_number() over (
        order by
            f.indice_prioridade desc,
            f.anos_com_foco desc,
            f.dias_com_foco desc,
            f.cod_imovel
    )::integer                                                          as posicao,
    f.cod_imovel,
    ra.codigo                                                           as codigo_regiao_administrativa,
    ra.nome                                                             as regiao_administrativa,
    d.situacao,
    coalesce(d.situacao = 'AT', false)                                  as cadastro_ativo,
    d.condicao,
    f.area_ha,
    f.classificacao_prioridade,
    f.indice_prioridade,
    f.componente_recorrencia,
    f.componente_recencia,
    f.componente_intensidade,
    f.anos_com_foco,
    f.primeiro_ano_com_foco,
    f.ultimo_ano_com_foco,
    f.lista_anos,
    f.total_focos,
    f.dias_com_foco,
    f.dias_com_foco_por_100ha,
    f.focos_satelite_referencia,
    f.focos_estacao_seca,
    f.focos_reserva_legal,
    f.focos_app,
    f.focos_uc_1km,
    f.atinge_reserva_legal,
    f.atinge_app,
    f.atinge_uc_1km,
    now()                                                               as gerado_em
from {{ ref('fct_reincidencia_imovel') }} f
inner join {{ ref('dim_imovel_car') }} d
    on d.sk_imovel = f.sk_imovel
inner join {{ ref('dim_imovel_car') }} atual
    on atual.cod_imovel = f.cod_imovel
    and atual.is_current
    and not atual.is_excluido
left join {{ ref('dim_regiao_administrativa') }} ra
    on ra.sk_regiao_administrativa = f.sk_regiao_administrativa
where f.imovel_reincidente
