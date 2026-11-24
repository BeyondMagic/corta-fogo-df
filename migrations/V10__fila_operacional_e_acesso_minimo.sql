-- V10: destino do ETL reverso e privilegio minimo.
--
-- operacional.fila_vistoria recebe a fila de vistoria calculada no analitico
-- (gold.painel_imoveis_prioritarios, DuckDB) e e lida e atualizada por quem vistoria.
-- Tres papeis, cada um com o minimo de que precisa (docs/etl_reverso_e_acesso.md):
--   etl_reverso      grava as metricas da fila; nao toca no que a vistoria escreve
--   fiscal_vistoria  le so a fila ativa (RLS) e altera so status_vistoria e observacao
--   analista_leitura le imovel_car sem a coluna geom (privilegio por coluna)
--
-- Sem chave estrangeira para imovel_car: load_camadas.py recarrega o cadastro com
-- TRUNCATE ... CASCADE, que apagaria a fila e o historico de vistorias junto.

CREATE SCHEMA IF NOT EXISTS operacional;

CREATE TABLE operacional.fila_vistoria (
    cod_imovel                   VARCHAR(60) PRIMARY KEY,
    posicao                      INTEGER NOT NULL CHECK (posicao > 0),
    codigo_regiao_administrativa VARCHAR(20),
    regiao_administrativa        VARCHAR(100),
    situacao                     VARCHAR(2) NOT NULL,
    cadastro_ativo               BOOLEAN NOT NULL,
    area_ha                      DOUBLE PRECISION,
    classificacao_prioridade     VARCHAR(40) NOT NULL,
    indice_prioridade            DOUBLE PRECISION NOT NULL CHECK (indice_prioridade BETWEEN 0 AND 100),
    anos_com_foco                INTEGER NOT NULL CHECK (anos_com_foco > 0),
    primeiro_ano_com_foco        INTEGER,
    ultimo_ano_com_foco          INTEGER,
    total_focos                  INTEGER,
    focos_reserva_legal          INTEGER,
    focos_app                    INTEGER,
    focos_uc_1km                 INTEGER,
    gold_gerado_em               TIMESTAMPTZ NOT NULL,
    na_fila                      BOOLEAN NOT NULL DEFAULT TRUE,
    carga_em                     TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- Escritos pela vistoria, nunca pelo ETL reverso.
    status_vistoria              VARCHAR(12) NOT NULL DEFAULT 'PENDENTE'
                                 CHECK (status_vistoria IN ('PENDENTE', 'AGENDADA', 'REALIZADA', 'DISPENSADA')),
    observacao                   TEXT,
    atualizado_em                TIMESTAMPTZ
);

CREATE INDEX ix_fila_vistoria_consulta ON operacional.fila_vistoria (na_fila, cadastro_ativo, posicao);

CREATE FUNCTION operacional.carimba_atualizacao() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    NEW.atualizado_em := now();
    RETURN NEW;
END;
$$;

CREATE TRIGGER tg_fila_vistoria_carimbo
    BEFORE UPDATE OF status_vistoria, observacao ON operacional.fila_vistoria
    FOR EACH ROW EXECUTE FUNCTION operacional.carimba_atualizacao();

COMMENT ON TABLE operacional.fila_vistoria IS
    'Fila de vistoria entregue ao sistema operacional (ETL reverso de gold.painel_imoveis_prioritarios). Uma linha por imovel reincidente.';
COMMENT ON COLUMN operacional.fila_vistoria.na_fila IS
    'FALSE quando o imovel saiu da fila na carga mais recente. A linha e mantida para preservar o historico de vistoria.';
COMMENT ON COLUMN operacional.fila_vistoria.carga_em IS
    'Instante da ultima carga do ETL reverso que confirmou esta linha.';
COMMENT ON COLUMN operacional.fila_vistoria.gold_gerado_em IS
    'Instante em que o dbt gerou a tabela de origem (base do frescor).';
COMMENT ON COLUMN operacional.fila_vistoria.status_vistoria IS
    'Situacao da vistoria, escrita por fiscal_vistoria. O ETL reverso nao a altera.';

-- Papeis sem login: quem conecta (ou faz SET ROLE) herda so o que o papel permite.
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'etl_reverso') THEN
        CREATE ROLE etl_reverso NOLOGIN;
    END IF;
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'fiscal_vistoria') THEN
        CREATE ROLE fiscal_vistoria NOLOGIN;
    END IF;
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'analista_leitura') THEN
        CREATE ROLE analista_leitura NOLOGIN;
    END IF;
END
$$;

REVOKE ALL ON SCHEMA operacional FROM PUBLIC;
REVOKE ALL ON operacional.fila_vistoria FROM PUBLIC;
GRANT USAGE ON SCHEMA operacional TO etl_reverso, fiscal_vistoria;

-- etl_reverso: todas as colunas de metrica, mas nao status_vistoria, observacao nem atualizado_em.
GRANT SELECT, INSERT ON operacional.fila_vistoria TO etl_reverso;
GRANT UPDATE (
    posicao, codigo_regiao_administrativa, regiao_administrativa, situacao, cadastro_ativo, area_ha,
    classificacao_prioridade, indice_prioridade, anos_com_foco, primeiro_ano_com_foco, ultimo_ano_com_foco,
    total_focos, focos_reserva_legal, focos_app, focos_uc_1km, gold_gerado_em, na_fila, carga_em
) ON operacional.fila_vistoria TO etl_reverso;

-- fiscal_vistoria: le a fila (filtrada pela RLS abaixo) e altera so status e observacao.
GRANT SELECT ON operacional.fila_vistoria TO fiscal_vistoria;
GRANT UPDATE (status_vistoria, observacao) ON operacional.fila_vistoria TO fiscal_vistoria;

-- analista_leitura: atributos do cadastro sem o perimetro (geom). Sem acesso ao schema operacional.
GRANT SELECT (cod_imovel, situacao, condicao, area_ha, data_download) ON public.imovel_car TO analista_leitura;

-- Recorte de linha: quem vistoria so enxerga e altera imoveis com cadastro ativo que seguem na fila.
ALTER TABLE operacional.fila_vistoria ENABLE ROW LEVEL SECURITY;

CREATE POLICY etl_reverso_total ON operacional.fila_vistoria
    TO etl_reverso USING (TRUE) WITH CHECK (TRUE);

CREATE POLICY fiscal_le_fila_ativa ON operacional.fila_vistoria
    FOR SELECT TO fiscal_vistoria USING (na_fila AND cadastro_ativo);

CREATE POLICY fiscal_atualiza_fila_ativa ON operacional.fila_vistoria
    FOR UPDATE TO fiscal_vistoria
    USING (na_fila AND cadastro_ativo) WITH CHECK (na_fila AND cadastro_ativo);
