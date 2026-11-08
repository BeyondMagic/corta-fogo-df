-- Fato atomica: uma linha por deteccao de foco (id_foco).
-- Nao explode por imovel: a relacao N:N fica em int_focos_imoveis / mart.

select
    t.id_foco,
    (year(t.data_evento_local) * 10000
        + month(t.data_evento_local) * 100
        + day(t.data_evento_local))::integer                            as sk_tempo,
    md5(t.satelite)                                                     as sk_satelite,
    t.satelite,
    t.is_satelite_referencia,
    t.data_hora_evento,
    t.data_hora_ingestao,
    t.data_evento_local,
    t.ano,
    t.mes,
    t.latitude,
    t.longitude,
    t.x_31983,
    t.y_31983,
    t.geom,
    t.municipio,
    t.bioma,
    t.risco_fogo,
    t.origem_ingestao,
    t.operacao_cdc,
    t.qtd_imoveis,
    t.em_imovel_car,
    t.em_reserva_legal,
    t.em_app,
    t.ate_1km_uc,
    t.distancia_min_uc_m,
    t.em_area_protegida
from {{ ref('int_focos_territorio') }} t
