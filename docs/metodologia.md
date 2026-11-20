---
icon: material/compass-outline
---

# :material-compass-outline: Metodologia

!!! info "Em construção"
    Esta página reunirá a descrição metodológica completa do projeto Corta-Fogo DF. Enquanto o conteúdo definitivo é consolidado, os detalhes técnicos parciais podem ser consultados no [Dashboard](dashboard.md#nota-metodologica-pegada-espacial-vs-cicatriz-de-queimada), no [ADR 0005](adr/05-indice-de-prioridade-de-vistoria.md) e no documento de [Frescor e SLA](frescor_sla.md).

## Tópicos previstos

### 1. Fontes de dados e pegada espacial dos sensores

- Escopo temporal (`2015-2025`), satélites considerados e protocolo de referência (`AQUA_M-T`).
- Diferença entre centroide do pixel orbital, detecções múltiplas no mesmo dia e área queimada (cicatriz).

### 2. Padronização cartográfica e cruzamentos espaciais

- Projeção oficial adotada (`EPSG:31983`, SIRGAS 2000 / UTM zona 23S) para cálculo de áreas e distâncias.
- Critérios de interseção com Reserva Legal, Área de Preservação Permanente (APP) e faixa de amortecimento de `1.000 m` em torno das Unidades de Conservação.
- Associação histórica com versões do imóvel no SICAR via SCD Tipo 2.

### 3. Reincidência e Índice de Prioridade de Vistoria (IPV)

- Regra de elegibilidade (`>= 2` anos civis distintos com foco em área protegida).
- Formulação de recorrência, recência e intensidade diária por `100 ha` com piso de `14,1 ha` ([ADR 0005](adr/05-indice-de-prioridade-de-vistoria.md)).

### 4. Limitações, defasagens e validação

- Sobreposição entre perímetros declarados no SICAR e cadastros cancelados/suspensos.
- Reconciliação entre a camada Gold (`dbt-duckdb`) e a visão materializada no PostGIS.
