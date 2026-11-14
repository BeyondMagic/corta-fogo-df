-- Fato da pergunta de gestao no grao do imovel: uma linha por imovel rural com ao menos
-- um foco em Reserva Legal propria, em APP ou a ate 1 km de UC entre 2015 e 2025.
--
-- Contagens (focos, dias, anos) sao aditivas entre imoveis, com a ressalva de que um
-- foco sobre imoveis sobrepostos no SICAR conta em cada um. Densidade, componentes e o
-- indice nao sao aditivos. O indice so existe para imoveis reincidentes.
-- sk_imovel aponta para a versao cadastral vigente no foco mais recente do imovel.
-- O fato e recriado a cada execucao (retrato do periodo 2015 a 2025).

select
    m.sk_imovel,
    m.cod_imovel,
    ra.sk_regiao_administrativa,
    m.area_ha,
    m.anos_com_foco,
    m.primeiro_ano_com_foco,
    m.ultimo_ano_com_foco,
    m.lista_anos,
    m.total_focos,
    m.dias_com_foco,
    m.focos_satelite_referencia,
    m.focos_estacao_seca,
    m.focos_reserva_legal,
    m.focos_app,
    m.focos_uc_1km,
    m.atinge_reserva_legal,
    m.atinge_app,
    m.atinge_uc_1km,
    (m.anos_com_foco >= {{ var('anos_minimos_reincidencia') }})         as imovel_reincidente,
    i.dias_com_foco_por_100ha,
    i.componente_recorrencia,
    i.componente_recencia,
    i.componente_intensidade,
    i.indice_prioridade,
    coalesce(i.classificacao_prioridade, 'NAO REINCIDENTE')             as classificacao_prioridade
from {{ ref('int_metricas_imovel') }} m
left join {{ ref('int_imoveis_regiao_administrativa') }} ra
    on ra.sk_imovel = m.sk_imovel
left join {{ ref('int_indice_prioridade_imovel') }} i
    on i.cod_imovel = m.cod_imovel
