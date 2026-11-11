---
icon: material/map-legend
---

# :material-map-legend: Mapa Interativo do Distrito Federal

Painel geoespacial com linha do tempo de 11 anos (2015 a 2025) para exploração interativa de focos de calor, limites territoriais das 84 Unidades de Conservação e imóveis rurais cadastrados no CAR com detecções recorrentes.

---

## 1. Métricas Consolidadas da Camada Analítica

Visão quantitativa apurada pela camada Gold do Lakehouse (modelagem dimensional dbt e tabelas Delta Lake), respondendo aos critérios da pergunta de gestão:

--8<-- "docs/snippets/mapa/metricas_gerais.md"

---

## 2. Série Histórica e Dinâmica Temporal das Queimadas

A série de 11 anos evidencia a severidade dos períodos de estiagem no bioma Cerrado e os picos associados a fenômenos de seca extrema no Distrito Federal:

### Evolução Anual de Focos (Total vs Estiagem)

--8<-- "docs/snippets/mapa/grafico_serie_anual.md"

### Distribuição Mensal Acumulada (Sazonalidade)

--8<-- "docs/snippets/mapa/grafico_sazonalidade_mensal.md"

---

## 3. Caracterização Fundiária e Áreas Protegidas Atingidas

Dos 21.047 imóveis cadastrados no CAR-DF, 1.593 apresentaram focos de calor recorrentes em pelo menos 2 anos distintos dentro ou no entorno imediato de áreas sob proteção ambiental:

### Sobreposição por Categoria Protegida

--8<-- "docs/snippets/mapa/grafico_reincidencia_territorial.md"

### Grau de Reincidência Temporal

--8<-- "docs/snippets/mapa/grafico_anos_reincidencia.md"

---

## 4. Exploração Espacial Interativa (Leaflet)

Utilize os controles abaixo para inspecionar os focos de calor em cada ano, aplicar filtros por satélite e explorar a localização geográfica das Unidades de Conservação e dos imóveis rurais reincidentes no Distrito Federal:

<div class="cf-map-card">
  <!-- Estatisticas Dinamicas do Ano -->
  <div class="cf-stats-grid">
    <div class="cf-stat-card">
      <span class="cf-stat-label">Total de Focos no DF</span>
      <span class="cf-stat-val" id="cf-stats-total">6.190</span>
    </div>
    <div class="cf-stat-card">
      <span class="cf-stat-label">Concentração na Seca (Mai a Set)</span>
      <span class="cf-stat-val" id="cf-stats-seca">90,5% (5.604)</span>
    </div>
    <div class="cf-stat-card">
      <span class="cf-stat-label">Satélite de Referência (AQUA_M-T)</span>
      <span class="cf-stat-val" id="cf-stats-ref">5,6% (349)</span>
    </div>
    <div class="cf-stat-card">
      <span class="cf-stat-label">Imóveis Reincidentes Monitorados</span>
      <span class="cf-stat-val" id="cf-stats-imoveis">10 de 10 cadastros críticos</span>
    </div>
  </div>

  <!-- Controles da Linha do Tempo -->
  <div class="cf-slider-container">
    <div class="cf-slider-header">
      <span class="cf-slider-title">Ano de Análise: <span id="cf-ano-badge" class="cf-badge-year">2024</span></span>
      <button id="cf-play-btn" class="cf-play-btn" type="button">&#9654; Reproduzir</button>
    </div>
    <div class="cf-slider-controls">
      <input type="range" id="cf-ano-slider" class="cf-slider" min="2015" max="2026" step="1" value="2024" />
    </div>
    <div class="cf-slider-ticks">
      <span>2015</span>
      <span>2016</span>
      <span>2017</span>
      <span>2018</span>
      <span>2019</span>
      <span>2020</span>
      <span>2021</span>
      <span>2022</span>
      <span>2023</span>
      <span>2024</span>
      <span>2025</span>
      <span>Todos</span>
    </div>
  </div>

  <!-- Filtros de Camadas -->
  <div class="cf-toggles">
    <label class="cf-toggle-label">
      <input type="checkbox" id="cf-check-focos" checked />
      Focos de calor
    </label>
    <label class="cf-toggle-label">
      <input type="checkbox" id="cf-check-only-ref" />
      Apenas satélite de referência (AQUA_M-T)
    </label>
    <label class="cf-toggle-label">
      <input type="checkbox" id="cf-check-ucs" checked />
      Polígonos de UCs (84 áreas)
    </label>
    <label class="cf-toggle-label">
      <input type="checkbox" id="cf-check-buffer-1km" checked />
      Faixa de 1 km (Amortecimento)
    </label>
    <label class="cf-toggle-label">
      <input type="checkbox" id="cf-check-imoveis" checked />
      Top 10 Imóveis CAR reincidentes
    </label>
    <div class="cf-controls-right">
      <label class="cf-toggle-label">
        Mapa base:
        <select id="cf-select-basemap" style="margin-left: 4px; padding: 2px 6px; border-radius: 4px; border: 1px solid #cbd5e1; background: var(--md-default-bg-color, #fff); color: var(--md-default-fg-color, #333);">
          <option value="osm">OpenStreetMap</option>
          <option value="esri">ESRI Neutro</option>
        </select>
      </label>
      <button id="cf-btn-fullscreen" class="cf-btn-fullscreen" type="button" aria-label="Alternar tela cheia" title="Alternar modo tela cheia">
        <svg class="cf-icon-fs-enter" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M8 3H5a2 2 0 0 0-2 2v3m18 0V5a2 2 0 0 0-2-2h-3m0 18h3a2 2 0 0 0 2-2v-3M3 16v3a2 2 0 0 0 2 2h3"/></svg>
        <svg class="cf-icon-fs-exit" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" style="display: none;"><path d="M8 3v3a2 2 0 0 1-2 2H3m18 0h-3a2 2 0 0 1-2-2V3m0 18v-3a2 2 0 0 1 2-2h3M3 16h3a2 2 0 0 1 2 2v3"/></svg>
        <span class="cf-fs-text">Tela Cheia</span>
      </button>
    </div>
  </div>

  <!-- Elemento do Mapa Leaflet -->
  <div id="corta-fogo-map"></div>

  <!-- Legenda -->
  <div class="cf-map-legend">
    <div class="cf-legend-item">
      <span class="cf-legend-dot" style="background: #dc2626;"></span> Satélite AQUA_M-T (Referência)
    </div>
    <div class="cf-legend-item">
      <span class="cf-legend-dot" style="background: #ea580c;"></span> Foco na seca (Mai a Set)
    </div>
    <div class="cf-legend-item">
      <span class="cf-legend-dot" style="background: #f59e0b;"></span> Foco no período chuvoso
    </div>
    <div class="cf-legend-item">
      <span class="cf-legend-dot" style="background: #22c55e; border: 2px solid #15803d;"></span> UC Proteção Integral
    </div>
    <div class="cf-legend-item">
      <span class="cf-legend-dot" style="background: #a3e635; border: 1.5px solid #65a30d;"></span> UC Uso Sustentável
    </div>
    <div class="cf-legend-item">
      <span class="cf-legend-dot" style="background: #86efac; border: 1.5px dashed #15803d;"></span> Faixa de 1 km (Amortecimento)
    </div>
    <div class="cf-legend-item">
      <span class="cf-legend-dot" style="background: #a855f7; border: 2px solid #6b21a8;"></span> Imóvel CAR crítico (Polígono sob demanda)
    </div>
  </div>
</div>

---

## 5. Como Utilizar o Painel

1. **Linha do tempo interativa:** utilize a barra deslizante para selecionar qualquer ano entre 2015 e 2025. A última posição ("Todos") plota os 38.945 focos acumulados de toda a série histórica.
2. **Reprodução automática:** o botão "Reproduzir" avança os anos em sequência contínua a cada 1,2 segundo, permitindo visualizar a dinâmica espacial da seca no Distrito Federal.
3. **Filtro de satélite de referência:** o INPE utiliza o sensor orbital `AQUA_M-T` como referência para comparações temporais homogêneas. Ao marcar "Apenas satélite de referência", o mapa remove os sensores secundários, isolando o subconjunto de 2.350 registros calibrados.
4. **Delimitação real de UCs e amortecimento:** as 84 Unidades de Conservação do DF são exibidas com seus perímetros poligonais exatos (diferenciando Proteção Integral e Uso Sustentável). A camada da faixa de amortecimento de 1 km pode ser alternada de forma independente.
5. **Polígonos cadastrais sob demanda:** clique sobre qualquer um dos 10 marcadores roxos de imóveis rurais críticos para projetar o polígono oficial cadastrado no SICAR, além de consultar o total de focos, anos com reincidência e sobreposições com APP e Reserva Legal.
6. **Alternância para tela cheia:** utilize o botão "Tela Cheia" nos controles ou no canto superior esquerdo do mapa para expandir o painel e explorar a distribuição espacial dos focos com resolução ampliada.
7. **Inspeção da pegada do sensor:** clique em qualquer ponto de foco para abrir o detalhamento com a dimensão nominal e área aproximada abrangida pelo pixel do satélite (ex: 375 m × 375 m / ~14,1 ha para VIIRS; 1.000 m × 1.000 m / ~100 ha para MODIS).

---

## 6. Metodologia: Focos de Calor Orbitais vs. Cicatrizes de Queimada

Uma dúvida técnica frequente em sensoriamento remoto aplicado a incêndios florestais é se o dado pontual do foco de calor delimita a área total queimada. A resposta técnica é **não**:

!!! note "Por que focos de calor são representados como pontos e não polígonos?"
    Os dados do BDQueimadas (INPE) registram **anomalias térmicas instantâneas** captadas por radiômetros orbitais no momento exato da passagem do satélite. O sensor não desenha o contorno do fogo; ele divide a superfície terrestre em uma grade de varredura regular (pixels).
    
    - **O que a coordenada (latitude e longitude) representa:** é o **centroide matemático** do pixel de varredura orbital onde uma temperatura significativamente superior à vizinhança foi identificada.
    - **Sensibilidade subpixel:** uma linha de fogo ativa de apenas 30 metros de extensão com temperatura em torno de 800 °C é suficiente para aquecer a resposta espectral média de um pixel inteiro de 1 km × 1 km (100 hectares no satélite AQUA/MODIS), ativando a detecção.
    - **Foco pontual vs. Cicatriz de queima:** a cicatriz (área contínua consumida pelo fogo) é um produto poligonal posterior (como o MapBiomas Fogo ou o produto MODIS MCD64A1), obtido por contraste de índices de vegetação (NBR, NDVI) antes e depois do evento. Na plataforma Corta-Fogo DF, o objetivo central é o monitoramento temporal de detecções e reincidência cadastral, motivo pelo qual a unidade básica de análise é o foco georreferenciado e sua pegada nominal de pixel.

### Resolução Espacial e Pegada no Solo por Família de Sensores

| Família de Sensores | Satélites Principais | Tipo de Órbita | Dimensão Nominal do Pixel | Área Abrangida no Solo | Proporção na Base do DF |
| :--- | :--- | :--- | :--- | ---: | ---: |
| **VIIRS (I-Band 375 m)** | Suomi-NPP, NOAA-20, NOAA-21 | Polar (Sol-Síncrona) | 375 m × 375 m | ~14,1 ha (~0,14 km²) | 73,0% (28.436 focos) |
| **MODIS (1.000 m)** | AQUA_M-T (Referência), TERRA | Polar (Sol-Síncrona) | 1.000 m × 1.000 m | ~100,0 ha (~1,00 km²) | 10,6% (4.124 focos) |
| **GOES (ABI 2.000 m)** | GOES-16, GOES-19 | Geoestacionária (~35.786 km) | 2.000 m × 2.000 m | ~400,0 ha (~4,00 km²) | 11,5% (4.483 focos) |
| **AVHRR / Outros** | NOAA-18, NOAA-19, MetOp-B | Polar (Sol-Síncrona) | 1.100 m × 1.100 m | ~121,0 ha (~1,21 km²) | 4,9% (1.902 focos) |

---

## 7. Fontes e Rastreabilidade dos Dados

| Camada | Fonte Pública Oficial | Período / Versão | Papel na Plataforma |
| :--- | :--- | :--- | :--- |
| **Focos de calor** | BDQueimadas (INPE) | 2015 a 2025 | Ingestão em lote diária/anual em Parquet particionado no Delta Lake |
| **Imóveis rurais** | SICAR / Ministério da Agricultura | Cadastros do DF | Dimensão temporal com histórico preservado em SCD Tipo 2 e polígonos cadastrais |
| **Unidades de Conservação** | IBRAM / SISDIA | 84 áreas oficiais | Polígonos reais de proteção integral, uso sustentável e faixa de amortecimento métrica de 1.000 m (EPSG:31983) |
| **Áreas de Proteção (RL e APP)** | SICAR e Geoportal DF | Mapeamento territorial | Cruzamento espacial métrico para apuração de reincidência e priorização de fiscalização |
