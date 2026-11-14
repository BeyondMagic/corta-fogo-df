-- Regiao Administrativa de cada foco de calor (uma linha por id_foco).
-- Regra de atribuicao na macro atribuir_regiao_administrativa.

{{ atribuir_regiao_administrativa(ref('stg_focos_calor'), 'id_foco', 'geom') }}
