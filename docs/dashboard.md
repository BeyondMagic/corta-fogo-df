---
title: Dashboard
icon: material/view-dashboard
---

# Dashboard de Queimadas do Distrito Federal (2015–2025)

Painel interativo em **D3.js** (`d3-geo` + Canvas + SVG) integrado ao mapa **Leaflet** com todos os **38.945 focos de calor** registrados entre **2015 e 2025**, **37 Regiões Administrativas**, **84 Unidades de Conservação** (com faixa de amortecimento de 1 km) e cruzamento local sobre **21.041 imóveis do CAR** e **13.494 Reservas Legais**. Clique em qualquer ano, mês, célula, RA, UC ou imóvel para filtrar todo o painel.

<div class="cf-dashboard-page" id="cf-dashboard-root">
  <div id="cf-loading-banner" class="cf-loading-banner" role="status">Carregando séries históricas e malhas vetoriais (resumo, geometrias e 38.945 focos)...</div>
  <div id="cf-live-status" class="cf-sr-only" role="status" aria-live="polite"></div>
  <section class="cf-kpi-strip" aria-label="Indicadores do recorte selecionado">
    <article class="cf-kpi-card">
      <span class="cf-kpi-label">Focos no recorte</span>
      <span class="cf-kpi-val" id="cf-kpi-focos">-</span>
      <span class="cf-kpi-sub" id="cf-kpi-focos-sub">Série 2015–2025</span>
    </article>
    <article class="cf-kpi-card">
      <span class="cf-kpi-label">Estiagem (Mai a Set)</span>
      <span class="cf-kpi-val" id="cf-kpi-seca">-</span>
      <span class="cf-kpi-sub" id="cf-kpi-seca-sub">Período crítico de seca</span>
    </article>
    <article class="cf-kpi-card">
      <span class="cf-kpi-label">Satélite de referência</span>
      <span class="cf-kpi-val" id="cf-kpi-ref">-</span>
      <span class="cf-kpi-sub" id="cf-kpi-ref-sub">AQUA_M-T (MODIS 1 km)</span>
    </article>
    <article class="cf-kpi-card">
      <span class="cf-kpi-label">Pressão em UCs</span>
      <span class="cf-kpi-val" id="cf-kpi-ucs">-</span>
      <span class="cf-kpi-sub" id="cf-kpi-ucs-sub">Interior ou faixa de 1 km</span>
    </article>
    <article class="cf-kpi-card">
      <span class="cf-kpi-label">CAR Reincidentes</span>
      <span class="cf-kpi-val" id="cf-kpi-car">-</span>
      <span class="cf-kpi-sub" id="cf-kpi-car-sub">Top 50 críticos / Gold</span>
    </article>
  </section>
  <section class="cf-filter-dock" aria-label="Controles temporais e filtros globais">
    <div class="cf-dock-row">
      <div class="cf-timeline-group">
        <button type="button" id="cf-play-btn" class="cf-btn cf-btn-primary">Reproduzir</button>
        <div class="cf-field" style="min-width:96px;">
          <label for="cf-speed-select">Velocidade</label>
          <select id="cf-speed-select" class="cf-select">
            <option value="0.5">0.5x</option>
            <option value="1" selected>1x</option>
            <option value="2">2x</option>
          </select>
        </div>
        <div class="cf-slider-wrap">
          <label for="cf-ano-slider" class="cf-sr-only">Ano da linha do tempo</label>
          <input type="range" id="cf-ano-slider" min="2015" max="2026" step="1" value="2026"/>
          <span class="cf-year-pill" id="cf-ano-badge">2015 a 2025 (Todos)</span>
        </div>
        <button type="button" id="cf-btn-todos" class="cf-btn">Todos (2015–2025)</button>
      </div>
      <div class="cf-field">
        <label for="cf-filter-estacao">Estação</label>
        <select id="cf-filter-estacao" class="cf-select">
          <option value="todos">Todas</option>
          <option value="seca">Estiagem (Mai–Set)</option>
          <option value="chuvoso">Chuvoso (Out–Abr)</option>
        </select>
      </div>
      <div class="cf-field">
        <label for="cf-filter-sensor">Sensor / Satélite</label>
        <select id="cf-filter-sensor" class="cf-select">
          <option value="todos">Todos os sensores</option>
          <option value="ref">AQUA_M-T (Referência)</option>
          <option value="0">VIIRS (375 m)</option>
          <option value="1">MODIS (1.000 m)</option>
          <option value="2">GOES (2.000 m)</option>
          <option value="3">AVHRR / Outros (1.100 m)</option>
        </select>
      </div>
      <div class="cf-field">
        <label for="cf-filter-situacao">Situação CAR</label>
        <select id="cf-filter-situacao" class="cf-select">
          <option value="todos">Todas (AT/PE/SU/CA)</option>
          <option value="AT">AT (Ativo)</option>
          <option value="PE">PE (Pendente)</option>
          <option value="SU">SU (Suspenso)</option>
          <option value="CA">CA (Cancelado)</option>
        </select>
      </div>
      <button type="button" id="cf-btn-reset-filters" class="cf-btn">Limpar filtros</button>
    </div>
    <div class="cf-chips-row" id="cf-active-chips" role="region" aria-label="Filtros ativos"></div>
  </section>
  <section class="cf-stage-card cf-map-card" id="cf-stage-card" aria-label="Palco espacial interativo">
    <div class="cf-stage-header">
      <div class="cf-tablist" id="cf-stage-tablist" role="tablist" aria-label="Modo de exibição do mapa">
        <button type="button" class="cf-tab-btn" role="tab" id="tab-d3geo" aria-selected="true" aria-controls="panel-d3geo">Mapa Analítico (d3-geo)</button>
        <button type="button" class="cf-tab-btn" role="tab" id="tab-leaflet" aria-selected="false" aria-controls="panel-leaflet">Mapa Satélite / Ruas (Leaflet)</button>
      </div>
      <div class="cf-stage-actions">
        <div id="cf-d3-toolbar-opts" class="cf-seg-group">
          <div id="cf-d3-mode-group" class="cf-seg-group" role="group" aria-label="Camada de visualização D3">
            <button type="button" class="cf-btn-mini is-active" data-mode="points" aria-pressed="true">Pontos</button>
            <button type="button" class="cf-btn-mini" data-mode="hexbin" aria-pressed="false">Hexbin</button>
            <button type="button" class="cf-btn-mini" data-mode="choropleth" aria-pressed="false">Coroplético</button>
          </div>
          <div id="cf-choro-controls" class="cf-seg-group" hidden>
            <label for="cf-choro-target" class="cf-sr-only">Alvo coroplético</label>
            <select id="cf-choro-target" class="cf-select">
              <option value="ra">Por RA (37)</option>
              <option value="uc">Por UC (84)</option>
            </select>
            <label for="cf-choro-metric" class="cf-sr-only">Métrica coroplética</label>
            <select id="cf-choro-metric" class="cf-select">
              <option value="total">Focos totais</option>
              <option value="densidade">Densidade (/100 km² ou ha)</option>
            </select>
          </div>
        </div>
        <div id="cf-leaflet-toolbar-opts" class="cf-seg-group" hidden>
          <label for="cf-select-basemap" class="cf-sr-only">Mapa base Leaflet</label>
          <select id="cf-select-basemap" class="cf-select">
            <option value="osm">OpenStreetMap (Ruas)</option>
            <option value="esri">ESRI Light Gray (Neutro)</option>
          </select>
        </div>
        <button type="button" id="cf-btn-fullscreen" class="cf-btn" aria-pressed="false">Tela cheia</button>
      </div>
    </div>
    <div class="cf-layer-bar" role="group" aria-label="Camadas vetoriais visíveis">
      <label class="cf-layer-check"><input type="checkbox" id="cf-layer-ras" checked/> 37 Regiões Administrativas</label>
      <label class="cf-layer-check"><input type="checkbox" id="cf-layer-ucs" checked/> 84 UCs</label>
      <label class="cf-layer-check"><input type="checkbox" id="cf-layer-buffers" checked/> Faixa de 1 km (UC)</label>
      <label class="cf-layer-check"><input type="checkbox" id="cf-layer-imoveis" checked/> Top 50 CAR reincidentes</label>
      <label class="cf-layer-check"><input type="checkbox" id="cf-layer-rl" checked/> Reserva Legal selecionada</label>
      <label class="cf-layer-check"><input type="checkbox" id="cf-layer-focos" checked/> Focos de calor</label>
    </div>
    <div id="panel-d3geo" class="cf-tabpanel" role="tabpanel" aria-labelledby="tab-d3geo">
      <div class="cf-stage-body">
        <div class="cf-d3-viewport" id="cf-d3-stage">
          <canvas id="cf-d3-canvas" aria-hidden="true"></canvas>
          <svg id="cf-d3-svg" role="img" aria-label="Mapa vetorial interativo do Distrito Federal em d3-geo"></svg>
          <div class="cf-zoom-overlay" role="group" aria-label="Controles de zoom do mapa">
            <button type="button" class="cf-btn" id="cf-d3-zoom-in" title="Aproximar zoom" aria-label="Aproximar zoom">+</button>
            <button type="button" class="cf-btn" id="cf-d3-zoom-out" title="Afastar zoom" aria-label="Afastar zoom">&minus;</button>
            <button type="button" class="cf-btn-mini" id="cf-d3-zoom-reset" title="Enquadrar DF">DF</button>
          </div>
          <div class="cf-d3-legend" id="cf-d3-legend" hidden></div>
        </div>
        <aside class="cf-inspector" id="cf-inspector-box" aria-label="Inspetor de feições selecionadas"></aside>
      </div>
    </div>
    <div id="panel-leaflet" class="cf-tabpanel" role="tabpanel" aria-labelledby="tab-leaflet" hidden>
      <div id="corta-fogo-map" role="region" aria-label="Mapa interativo Leaflet"></div>
    </div>
  </section>
  <section class="cf-bento-grid" aria-label="Gráficos analíticos interativos">
    <article class="cf-card cf-col-6">
      <div class="cf-card-head">
        <div>
          <h3>Série Histórica Anual (2015–2025)</h3>
          <p class="cf-card-sub">Clique em uma barra para filtrar o ano.</p>
        </div>
        <div class="cf-seg-group" role="group" aria-label="Agrupamento da série anual">
          <button type="button" class="cf-btn-mini is-active" data-anual-mode="estacao">Estiagem vs Chuvoso</button>
          <button type="button" class="cf-btn-mini" data-anual-mode="referencia">AQUA_M-T vs Demais</button>
        </div>
      </div>
      <div class="cf-chart-box" id="chart-anual"></div>
    </article>
    <article class="cf-card cf-col-6">
      <div class="cf-card-head">
        <div>
          <h3>Matriz Ano x Mês (11 x 12)</h3>
          <p class="cf-card-sub">Clique em uma célula para isolar ano e mês simultaneamente.</p>
        </div>
      </div>
      <div class="cf-chart-box" id="chart-heatmap"></div>
    </article>
    <article class="cf-card cf-col-5">
      <div class="cf-card-head">
        <div>
          <h3>Sazonalidade Mensal (Jan–Dez)</h3>
          <p class="cf-card-sub">Faixa laranja marca a estiagem de maio a setembro. Clique no mês para filtrar.</p>
        </div>
      </div>
      <div class="cf-chart-box" id="chart-mensal"></div>
    </article>
    <article class="cf-card cf-col-7">
      <div class="cf-card-head">
        <div>
          <h3>Sensores, Horário (BRT) e Risco de Fogo</h3>
          <p class="cf-card-sub">Alterne a dimensão analítica sobre os focos do recorte.</p>
        </div>
        <div class="cf-seg-group" role="tablist" aria-label="Dimensão dos sensores">
          <button type="button" class="cf-btn-mini is-active" role="tab" aria-selected="true" data-sensor-tab="evolucao">Sensores (2015–2025)</button>
          <button type="button" class="cf-btn-mini" role="tab" aria-selected="false" data-sensor-tab="horario">Ciclo Horário (BRT)</button>
          <button type="button" class="cf-btn-mini" role="tab" aria-selected="false" data-sensor-tab="risco">Risco de Fogo INPE</button>
        </div>
      </div>
      <div class="cf-chart-box" id="chart-sensores-hora"></div>
    </article>
    <article class="cf-card cf-col-6">
      <div class="cf-card-head">
        <div>
          <h3>Ranking das UCs Mais Pressionadas</h3>
          <p class="cf-card-sub">Focos no interior da UC e na faixa de 1 km. Clique para focar.</p>
        </div>
        <div class="cf-seg-group" role="group" aria-label="Métrica de ranking das UCs">
          <button type="button" class="cf-btn-mini is-active" data-uc-metric="absoluto">Contagem</button>
          <button type="button" class="cf-btn-mini" data-uc-metric="densidade">Focos / 100 ha</button>
        </div>
      </div>
      <div class="cf-chart-box" id="chart-ucs-ranking"></div>
    </article>
    <article class="cf-card cf-col-6">
      <div class="cf-card-head">
        <div>
          <h3>Reincidência Fundiária e Sobreposições</h3>
          <p class="cf-card-sub">Cruzamento local (RL + UC 1 km) comparado à referência Gold E3 (com APP).</p>
        </div>
        <div class="cf-seg-group" role="tablist" aria-label="Visão da reincidência CAR">
          <button type="button" class="cf-btn-mini is-active" role="tab" aria-selected="true" data-car-tab="situacao">Situação e Porte</button>
          <button type="button" class="cf-btn-mini" role="tab" aria-selected="false" data-car-tab="reincidencia">Anos (2–11)</button>
          <button type="button" class="cf-btn-mini" role="tab" aria-selected="false" data-car-tab="protegidas">Áreas Protegidas</button>
        </div>
      </div>
      <div class="cf-chart-box" id="chart-car-reincidencia"></div>
    </article>
    <article class="cf-card cf-col-12">
      <div class="cf-card-head">
        <div>
          <h3 id="cf-car-table-title">Top 50 Imóveis CAR com Maior Reincidência</h3>
          <p class="cf-card-sub">Clique no código do imóvel para desenhar os polígonos do perímetro CAR e das Reservas Legais no mapa.</p>
        </div>
        <div class="cf-table-toolbar">
          <div class="cf-field" style="min-width:240px;">
            <label for="cf-car-search">Filtrar código CAR, situação ou condição</label>
            <input type="search" id="cf-car-search" class="cf-input" placeholder="Ex.: DF-5300108, CA, Pendente..."/>
          </div>
        </div>
      </div>
      <div id="cf-table-status" class="cf-sr-only" role="status" aria-live="polite"></div>
      <div class="cf-table-wrap" tabindex="0" role="region" aria-labelledby="cf-car-table-title">
        <table id="cf-car-table">
          <thead>
            <tr>
              <th scope="col" class="cf-num" data-sort="rank" data-type="number"><button type="button" class="cf-sort-btn"><span>#</span><span class="cf-sort-indicator" aria-hidden="true"></span></button></th>
              <th scope="col" data-sort="cod_imovel" data-type="string"><button type="button" class="cf-sort-btn"><span>Código CAR</span><span class="cf-sort-indicator" aria-hidden="true"></span></button></th>
              <th scope="col" data-sort="situacao" data-type="string"><button type="button" class="cf-sort-btn"><span>Situação</span><span class="cf-sort-indicator" aria-hidden="true"></span></button></th>
              <th scope="col" class="cf-num" data-sort="anos_qtd" data-type="number"><button type="button" class="cf-sort-btn"><span>Anos</span><span class="cf-sort-indicator" aria-hidden="true"></span></button></th>
              <th scope="col" class="cf-num" data-sort="area_ha" data-type="number"><button type="button" class="cf-sort-btn"><span>Área (ha)</span><span class="cf-sort-indicator" aria-hidden="true"></span></button></th>
              <th scope="col" class="cf-num" data-sort="focos_total" data-type="number" aria-sort="descending"><button type="button" class="cf-sort-btn"><span>Focos no CAR</span><span class="cf-sort-indicator" aria-hidden="true"></span></button></th>
              <th scope="col" class="cf-num" data-sort="focos_prot" data-type="number"><button type="button" class="cf-sort-btn"><span>Em RL / UC 1 km</span><span class="cf-sort-indicator" aria-hidden="true"></span></button></th>
              <th scope="col">Sobreposições</th>
            </tr>
          </thead>
          <tbody id="cf-car-tbody"></tbody>
        </table>
      </div>
    </article>
  </section>
</div>
<div id="cf-floating-tooltip" class="cf-floating-tooltip" role="tooltip" hidden></div>

---

## Nota Metodológica: Pegada Espacial vs. Cicatriz de Queimada

Cada coordenada exibida no painel não representa apenas um ponto infinitesimal de ignição, nem corresponde diretamente à área contínua destruída pelo fogo: trata-se do **centroide do pixel orbital** (célula de resolução) onde o sensor termal identificou energia radiativa compatível com combustão ativa no instante da passagem.

Sensores distintos cobrem resoluções diferentes em uma mesma série histórica:

| Família / Sensor | Exemplos na série do DF | Dimensão do pixel no solo | Área nominal do pixel | Órbita típica |
| :--- | :--- | :--- | :--- | :--- |
| **VIIRS** (`I-Band`) | `NPP-375`, `NOAA-20`, `NOAA-21` | `375 m x 375 m` | `~14,1 ha` (`~0,14 km²`) | Polar (alta resolução) |
| **MODIS** (`AQUA_M-T`, Referência) | `AQUA_M-T`, `TERRA_M-M` | `1.000 m x 1.000 m` | `~100,0 ha` (`1,00 km²`) | Polar (série climatológica) |
| **AVHRR / Outros** | `NOAA-18`, `NOAA-19`, `METOP-B/C` | `1.100 m x 1.100 m` | `~121,0 ha` (`~1,21 km²`) | Polar |
| **ABI / SEVIRI** (Geoestacionário) | `GOES-16`, `GOES-19`, `MSG-03` | `2.000 m x 2.000 m` | `~400,0 ha` (`4,00 km²`) | Geoestacionária (passagens a cada 10–15 min) |

O filtro **Satélite de referência (`AQUA_M-T`)** segue o protocolo oficial do INPE de série consistente desde 2002 (pixel nominal de 1 km²), eliminando distorções provocadas pela entrada de sensores polares de 375 m (`NPP-375`, `NOAA-20`) ou geoestacionários a partir de 2016–2018. Para medição física contínua de área queimada (**cicatrizes**), combinam-se séries multiespectrais ópticas (como `Landsat` 30 m ou `Sentinel-2` 10–20 m).

---

## Escopo dos Dados Exibidos e Diferença para a Camada Gold

O script [scripts/gerar_dados_dashboard.py](https://github.com/BeyondMagic/corta-fogo-df/blob/main/scripts/gerar_dados_dashboard.py) realiza o cruzamento espacial direto via `shapely.STRtree` (em projeção métrica SIRGAS 2000 UTM 23S, EPSG:31983) sobre todos os arquivos locais em `data/`, exportando os três pacotes JSON sob demanda em `docs/assets/dados_dashboard/`.

A tabela resume os indicadores do cruzamento local em Python frente à camada dimensional Gold ([Entrega 3](entrega/03/README.md)):

| Indicador | Cruzamento local no Dashboard | Camada Gold (`mart_reincidencia_imovel_ano`) | Motivo da diferença |
| :--- | :--- | :--- | :--- |
| **Imóveis com foco protegido** | `3.926` | `4.068` | Cruzamento local cobre Reserva Legal + faixa de 1 km de UC (sem polígono completo de APP) |
| **Imóveis reincidentes (>= 2 anos)** | `1.537` | `1.593` | Mesma diferença de cobertura da APP; nas faixas longas (11 anos), ambas somam `41` imóveis |
| **Em Reserva Legal / UC 1 km** | `932` RL / `1.226` UC 1 km | `958` RL / `1.231` UC 1 km | Pequenas diferenças de simplificação e deduplicação entre Shapefile local e ingestão PostGIS |

---

## Origem Oficial dos Dados e Ferramentas

| Camada / Componente | Fonte Oficial / Biblioteca | Abrangência | Frequência / Uso |
| :--- | :--- | :--- | :--- |
| **Focos de Calor (`2015–2025`)** | [INPE BDQueimadas](https://terrabrasilis.dpi.inpe.br/queimadas/bdqueimadas/) | Todos os `38.945` registros no DF | Dados históricos reais em `focos.json` |
| **Regiões Administrativas e Limite do DF** | [IDE-DF / SEDUH (`Publico/LIMITES`)](https://www.geoservicos.ide.df.gov.br/arcgis/rest/services/Publico/LIMITES/FeatureServer) | `37` Regiões Administrativas oficiais | Malha base vetorial e coroplético por RA |
| **Unidades de Conservação e Faixa 1 km** | [IDE-DF / IBRAM](https://www.geoservicos.ide.df.gov.br/arcgis/rest/services) | `84` áreas protegidas e buffers de 1.000 m | Ranking dinâmico e filtro por UC |
| **Malha Fundiária (CAR e Reserva Legal)** | [SICAR Federal](https://consultapublica.car.gov.br/publico/imoveis/index) | `21.041` perímetros e `13.494` RLs analisados | Situação cadastral, porte e polígonos do Top 50 |
| **Visualização Analítica e Cartográfica** | [D3.js v7](https://d3js.org/) (`d3-geo` + Canvas + SVG) & [Leaflet 1.9](https://leafletjs.com/) | Projeção vetorial local + tiles OSM / ESRI | Palco duplo com filtros cruzados em memória |
