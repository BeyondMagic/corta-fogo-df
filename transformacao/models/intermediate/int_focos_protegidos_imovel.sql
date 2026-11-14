-- Regra da pergunta de gestao, uma linha por (id_foco, cod_imovel): foco dentro do
-- imovel e em Reserva Legal do mesmo imovel, em APP ou a ate 1 km de UC, de 2015 a 2025.
-- Fonte unica de mart_reincidencia_imovel_ano e de int_metricas_imovel.

select
    fi.id_foco,
    fi.cod_imovel,
    fi.sk_imovel,
    fi.data_hora_evento,
    fi.data_evento_local,
    fi.ano,
    fi.is_satelite_referencia,
    (month(fi.data_evento_local) between 5 and 9)                       as is_estacao_seca,
    fi.situacao_imovel,
    fi.condicao_imovel,
    fi.area_ha_imovel,
    bool_or(ap.tipo_area = 'reserva_legal')                             as em_reserva_legal_do_imovel,
    bool_or(ap.tipo_area = 'app')                                       as em_app,
    bool_or(ap.tipo_area = 'uc_1km')                                    as ate_1km_uc
from {{ ref('int_focos_imoveis') }} fi
inner join {{ ref('int_focos_areas_protegidas') }} ap
    on fi.id_foco = ap.id_foco
    and (
        ap.tipo_area in ('app', 'uc_1km')
        or (
            ap.tipo_area = 'reserva_legal'
            and ap.cod_imovel_feicao = fi.cod_imovel
        )
    )
where fi.ano between 2015 and 2025
group by
    fi.id_foco,
    fi.cod_imovel,
    fi.sk_imovel,
    fi.data_hora_evento,
    fi.data_evento_local,
    fi.ano,
    fi.is_satelite_referencia,
    fi.situacao_imovel,
    fi.condicao_imovel,
    fi.area_ha_imovel
