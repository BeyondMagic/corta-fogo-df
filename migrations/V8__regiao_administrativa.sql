-- V8: Regioes Administrativas do DF (IDE-DF / SEDUH).
-- Camada de referencia para agregar focos e imoveis por territorio administrativo.
-- Nao entra na regra da pergunta de gestao: serve de dimensao na camada Gold e de
-- lastro para a distribuicao de focos por RA.

CREATE TABLE regiao_administrativa (
    id_ra               INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    codigo              VARCHAR(20) NOT NULL UNIQUE CHECK (btrim(codigo) <> ''),
    nome                VARCHAR(100) NOT NULL CHECK (btrim(nome) <> ''),
    area_km2            NUMERIC(10, 2) CHECK (area_km2 IS NULL OR area_km2 > 0),
    fonte               VARCHAR(80),
    data_download       DATE NOT NULL,
    data_hora_ingestao  TIMESTAMPTZ NOT NULL DEFAULT now(),
    geom                geometry(MultiPolygon, 31983) NOT NULL
                        CHECK (ST_IsValid(geom) AND NOT ST_IsEmpty(geom))
);

COMMENT ON TABLE regiao_administrativa IS
    'Regioes Administrativas do Distrito Federal (IDE-DF / SEDUH). Dimensao territorial da camada Gold.';
COMMENT ON COLUMN regiao_administrativa.codigo IS
    'Codigo oficial da RA no padrao RA-<algarismos romanos> (ex.: RA-VI para Planaltina).';
COMMENT ON COLUMN regiao_administrativa.data_download IS
    'Data em que o arquivo de origem (IDE-DF) foi obtido. Nao e a data de carga no banco.';
COMMENT ON COLUMN regiao_administrativa.data_hora_ingestao IS
    'Momento em que esta linha foi inserida neste banco (carga).';
COMMENT ON COLUMN regiao_administrativa.geom IS
    'MultiPolygon em EPSG:31983.';

CREATE INDEX ix_regiao_administrativa_geom
    ON regiao_administrativa USING gist (geom);
