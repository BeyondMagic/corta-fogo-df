---
title: Dashboard
icon: material/view-dashboard
---

# Dashboard de Queimadas do Distrito Federal (2015–2025)

<div class="cf-dashboard-page" id="cf-dashboard-root">
  <div id="cf-loading-banner" class="cf-loading-banner" role="status">Carregando séries históricas e malhas vetoriais (resumo, geometrias e 38.945 focos)...</div>
  <div id="cf-live-status" class="cf-sr-only" role="status" aria-live="polite"></div>
  <section class="cf-resposta-card" aria-labelledby="cf-resposta-titulo">
    <div class="cf-resposta-head">
      <div>
        <p class="cf-resposta-rotulo">Pergunta de gestão</p>
        <p class="cf-resposta-pergunta" id="cf-resposta-titulo">Quais imóveis rurais do DF tiveram focos reincidentes em reserva legal, APP ou a até 1 km de UCs (2015–2025)?</p>
      </div>
      <div id="cf-resposta-corpo" class="cf-resposta-summary"></div>
    </div>
    <p class="cf-narrative" id="cf-narrative"></p>
  </section>
  <section class="cf-filter-dock" aria-label="Filtros operacionais">
    <div class="cf-dock-row-compact">
      <div class="cf-field cf-field-ano">
        <label for="cf-ano-de">De</label>
        <select id="cf-ano-de" class="cf-select">
          <option value="2015" selected>2015</option>
          <option value="2016">2016</option>
          <option value="2017">2017</option>
          <option value="2018">2018</option>
          <option value="2019">2019</option>
          <option value="2020">2020</option>
          <option value="2021">2021</option>
          <option value="2022">2022</option>
          <option value="2023">2023</option>
          <option value="2024">2024</option>
          <option value="2025">2025</option>
        </select>
      </div>
      <div class="cf-field cf-field-ano">
        <label for="cf-ano-ate">Até</label>
        <select id="cf-ano-ate" class="cf-select">
          <option value="2015">2015</option>
          <option value="2016">2016</option>
          <option value="2017">2017</option>
          <option value="2018">2018</option>
          <option value="2019">2019</option>
          <option value="2020">2020</option>
          <option value="2021">2021</option>
          <option value="2022">2022</option>
          <option value="2023">2023</option>
          <option value="2024">2024</option>
          <option value="2025" selected>2025</option>
        </select>
      </div>
      <div class="cf-field">
        <label for="cf-filter-ra">Região Administrativa</label>
        <select id="cf-filter-ra" class="cf-select">
          <option value="todos">Todas as RAs</option>
        </select>
      </div>
      <div class="cf-field">
        <label for="cf-filter-estacao">Estação</label>
        <select id="cf-filter-estacao" class="cf-select">
          <option value="todos">Todas</option>
          <option value="seca">Estiagem (Mai–Set)</option>
          <option value="chuvoso">Chuvoso (Out–Abr)</option>
        </select>
      </div>
      <div class="cf-dock-actions">
        <button type="button" id="cf-btn-adv-filters" class="cf-btn" aria-expanded="false" aria-controls="cf-adv-drawer">Filtros avançados</button>
        <button type="button" id="cf-btn-reset-filters" class="cf-btn">Limpar tudo</button>
      </div>
    </div>
    <div id="cf-adv-drawer" class="cf-adv-drawer" hidden>
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
        <label for="cf-filter-sensor">Sensor / Satélite</label>
        <select id="cf-filter-sensor" class="cf-select">
          <option value="todos">Todos os sensores</option>
          <option value="ref">Satélite de referência</option>
          <option value="0">Alta resolução (375 m)</option>
          <option value="1">Moderada (1.000 m)</option>
          <option value="2">Geoestacionário (2.000 m)</option>
          <option value="3">Varredura clássica (1.100 m)</option>
        </select>
      </div>
      <div class="cf-field">
        <label for="cf-filter-situacao">Situação do cadastro</label>
        <select id="cf-filter-situacao" class="cf-select">
          <option value="todos">Todas</option>
          <option value="AT">Ativo</option>
          <option value="PE">Pendente</option>
          <option value="SU">Suspenso</option>
          <option value="CA">Cancelado</option>
        </select>
      </div>
    </div>
    <div class="cf-chips-row" id="cf-active-chips" role="region" aria-label="Filtros ativos"></div>
  </section>
  <section class="cf-stage-card cf-map-card" id="cf-stage-card" aria-label="Mapa operacional e fila de vistoria">
    <div class="cf-stage-header">
      <div class="cf-tablist" id="cf-stage-tablist" role="tablist" aria-label="Modo de exibição do mapa">
        <button type="button" class="cf-tab-btn" role="tab" id="tab-d3geo" aria-selected="true" aria-controls="panel-d3geo">Mapa Analítico</button>
        <button type="button" class="cf-tab-btn" role="tab" id="tab-leaflet" aria-selected="false" aria-controls="panel-leaflet">Mapa Satélite / Ruas</button>
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
          <label for="cf-select-basemap" class="cf-sr-only">Mapa base</label>
          <select id="cf-select-basemap" class="cf-select">
            <option value="osm" selected>OpenStreetMap (Ruas)</option>
            <option value="esri">ESRI Light Gray (Neutro)</option>
          </select>
        </div>
        <div class="cf-layer-menu-wrap">
          <button type="button" id="cf-btn-layers" class="cf-btn-mini" aria-expanded="false" aria-controls="cf-layer-popover">Camadas (5/6)</button>
          <div id="cf-layer-popover" class="cf-layer-popover" role="group" aria-label="Camadas vetoriais visíveis" hidden>
            <label class="cf-layer-check"><input type="checkbox" id="cf-layer-ras" checked/> 37 Regiões Administrativas</label>
            <label class="cf-layer-check"><input type="checkbox" id="cf-layer-ucs" checked/> 84 UCs</label>
            <label class="cf-layer-check"><input type="checkbox" id="cf-layer-buffers"/> Faixa de 1 km (UC)</label>
            <label class="cf-layer-check"><input type="checkbox" id="cf-layer-imoveis" checked/> Fila de vistoria (imóveis)</label>
            <label class="cf-layer-check"><input type="checkbox" id="cf-layer-rl" checked/> Reserva Legal selecionada</label>
            <label class="cf-layer-check"><input type="checkbox" id="cf-layer-focos" checked/> Focos de calor</label>
          </div>
        </div>
        <button type="button" id="cf-btn-fullscreen" class="cf-btn" aria-pressed="false">Tela cheia</button>
      </div>
    </div>
    <p class="cf-stage-hint">Clique em um imóvel da fila ou no mapa para ver os detalhes dele. Passe o mouse sobre siglas e números para ver o que significam.</p>
    <div class="cf-stage-body">
      <div class="cf-stage-maps">
        <div id="panel-d3geo" class="cf-tabpanel" role="tabpanel" aria-labelledby="tab-d3geo">
          <div class="cf-d3-viewport" id="cf-d3-stage">
            <canvas id="cf-d3-canvas" aria-hidden="true"></canvas>
            <svg id="cf-d3-svg" role="img" aria-label="Mapa analítico interativo do Distrito Federal"></svg>
            <div class="cf-zoom-overlay" role="group" aria-label="Controles de zoom do mapa">
              <button type="button" class="cf-btn" id="cf-d3-zoom-in" title="Aproximar zoom" aria-label="Aproximar zoom">+</button>
              <button type="button" class="cf-btn" id="cf-d3-zoom-out" title="Afastar zoom" aria-label="Afastar zoom">&minus;</button>
              <button type="button" class="cf-btn-mini" id="cf-d3-zoom-reset" title="Enquadrar DF">DF</button>
            </div>
            <div class="cf-d3-legend" id="cf-d3-legend" hidden></div>
          </div>
        </div>
        <div id="panel-leaflet" class="cf-tabpanel" role="tabpanel" aria-labelledby="tab-leaflet" hidden>
          <div id="corta-fogo-map" role="region" aria-label="Mapa satélite e ruas"></div>
        </div>
      </div>
      <aside class="cf-queue-rail" aria-label="Fila de vistoria e inspetor territorial">
        <div id="cf-inspector-box" class="cf-inspector-box" hidden></div>
        <div class="cf-queue-head">
          <div>
            <h3 id="cf-car-table-title">Fila de Vistoria (50)</h3>
            <p class="cf-queue-sub" id="cf-queue-sel-summary">5 marcados filtrando o painel</p>
          </div>
          <div class="cf-seg-group" role="group" aria-label="Atalhos da fila">
            <button type="button" class="cf-btn-mini is-active" id="cf-btn-car-top5" title="Marca os 5 imóveis mais prioritários e mostra só os dados deles">Top 5</button>
            <button type="button" class="cf-btn-mini" id="cf-btn-car-all" title="Marca os 50 imóveis da fila">Todos</button>
            <button type="button" class="cf-btn-mini" id="cf-btn-car-none" title="Desmarca todos e mostra os dados do DF inteiro">Nenhum (DF todo)</button>
            <button type="button" class="cf-btn-mini" id="cf-btn-car-fit" title="Enquadrar imóveis marcados no mapa">Zoom</button>
          </div>
        </div>
        <div class="cf-queue-controls">
          <div class="cf-field cf-queue-search-field">
            <label for="cf-car-search" class="cf-sr-only">Buscar imóvel por código, região administrativa ou situação</label>
            <input type="search" id="cf-car-search" class="cf-input" placeholder="Buscar imóvel ou RA"/>
          </div>
          <div class="cf-field cf-queue-sort-field">
            <label for="cf-car-sort-select" class="cf-sr-only">Ordenar fila de vistoria</label>
            <select id="cf-car-sort-select" class="cf-select">
              <option value="rank:asc" selected>Ordem da fila</option>
              <option value="indice:desc">Maior prioridade</option>
              <option value="focos_prot:desc">Focos área protegida</option>
              <option value="focos_total:desc">Focos totais</option>
              <option value="area_ha:desc">Maior área (ha)</option>
              <option value="anos_qtd:desc">Mais anos</option>
              <option value="ra:asc">Região (A–Z)</option>
            </select>
          </div>
        </div>
        <div class="cf-queue-master-row">
          <label class="cf-queue-master-lbl">
            <input type="checkbox" id="cf-car-check-all" class="cf-car-chk-input"/>
            <span>Marcar visíveis na lista</span>
          </label>
          <span class="cf-muted" id="cf-queue-vis-count">50 exibidos</span>
        </div>
        <p class="cf-queue-legend"><b>RL</b> Reserva Legal · <b>APP</b> Preserv. Permanente · <b>UC 1km</b> até 1 km de Unid. de Conservação · <b>prot.</b> focos nessas áreas</p>
        <div id="cf-table-status" class="cf-sr-only" role="status" aria-live="polite"></div>
        <div class="cf-queue-list-wrap" tabindex="0" role="region" aria-labelledby="cf-car-table-title">
          <ul id="cf-car-tbody" class="cf-queue-list"></ul>
        </div>
      </aside>
    </div>
  </section>
  <section class="cf-kpi-strip" aria-label="Indicadores do recorte selecionado">
    <article class="cf-kpi-card">
      <span class="cf-kpi-label">Focos no recorte</span>
      <span class="cf-kpi-val" id="cf-kpi-focos">-</span>
      <span class="cf-kpi-sub" id="cf-kpi-focos-sub">Série 2015–2025</span>
      <span class="cf-kpi-cmp" id="cf-kpi-focos-cmp"></span>
    </article>
    <article class="cf-kpi-card">
      <span class="cf-kpi-label">Estiagem (Mai a Set)</span>
      <span class="cf-kpi-val" id="cf-kpi-seca">-</span>
      <span class="cf-kpi-sub" id="cf-kpi-seca-sub">Período crítico de seca</span>
      <span class="cf-kpi-cmp" id="cf-kpi-seca-cmp"></span>
    </article>
    <article class="cf-kpi-card">
      <span class="cf-kpi-label">Pressão em UCs (1 km)</span>
      <span class="cf-kpi-val" id="cf-kpi-ucs">-</span>
      <span class="cf-kpi-sub" id="cf-kpi-ucs-sub">Interior ou faixa de 1 km</span>
      <span class="cf-kpi-cmp" id="cf-kpi-ucs-cmp"></span>
    </article>
    <article class="cf-kpi-card">
      <span class="cf-kpi-label">Satélite de referência</span>
      <span class="cf-kpi-val" id="cf-kpi-ref">-</span>
      <span class="cf-kpi-sub" id="cf-kpi-ref-sub">Série histórica contínua</span>
      <span class="cf-kpi-cmp" id="cf-kpi-ref-cmp"></span>
    </article>
  </section>
  <section class="cf-bento-grid" aria-label="Tendência e pressão territorial">
    <article class="cf-card cf-col-6">
      <div class="cf-card-head">
        <div>
          <h3>Tendência Temporal dos Focos</h3>
          <p class="cf-card-sub">Clique em uma barra ou célula para filtrar o período.</p>
        </div>
        <div class="cf-seg-group" id="cf-temporal-tablist" role="tablist" aria-label="Visão temporal">
          <button type="button" class="cf-btn-mini is-active" role="tab" id="tab-temp-anual" aria-selected="true" aria-controls="panel-temp-anual" data-temporal-tab="anual">Anual</button>
          <button type="button" class="cf-btn-mini" role="tab" id="tab-temp-mensal" aria-selected="false" aria-controls="panel-temp-mensal" data-temporal-tab="mensal">Mensal</button>
          <button type="button" class="cf-btn-mini" role="tab" id="tab-temp-heatmap" aria-selected="false" aria-controls="panel-temp-heatmap" data-temporal-tab="heatmap">Matriz Ano×Mês</button>
        </div>
      </div>
      <div id="panel-temp-anual" role="tabpanel" aria-labelledby="tab-temp-anual">
        <div class="cf-subtoolbar">
          <div class="cf-seg-group" role="group" aria-label="Agrupamento da série anual">
            <button type="button" class="cf-btn-mini is-active" data-anual-mode="estacao">Estiagem vs Chuvoso</button>
            <button type="button" class="cf-btn-mini" data-anual-mode="referencia">Referência vs Demais</button>
          </div>
        </div>
        <div class="cf-chart-box" id="chart-anual"></div>
      </div>
      <div id="panel-temp-mensal" role="tabpanel" aria-labelledby="tab-temp-mensal" hidden>
        <p class="cf-card-sub">Faixa laranja marca a estiagem de maio a setembro. Clique no mês para filtrar.</p>
        <div class="cf-chart-box" id="chart-mensal"></div>
      </div>
      <div id="panel-temp-heatmap" role="tabpanel" aria-labelledby="tab-temp-heatmap" hidden>
        <p class="cf-card-sub">Clique em uma célula para isolar ano e mês simultaneamente.</p>
        <div class="cf-chart-box" id="chart-heatmap"></div>
      </div>
    </article>
    <article class="cf-card cf-col-6">
      <div class="cf-card-head">
        <div>
          <h3>Ranking das UCs Mais Pressionadas</h3>
          <p class="cf-card-sub">Focos no interior da UC e na faixa de 1 km no recorte ativo. Clique para focar.</p>
        </div>
        <div class="cf-seg-group" role="group" aria-label="Métrica de ranking das UCs">
          <button type="button" class="cf-btn-mini is-active" data-uc-metric="absoluto">Contagem</button>
          <button type="button" class="cf-btn-mini" data-uc-metric="densidade">Focos / 100 ha</button>
        </div>
      </div>
      <div class="cf-chart-box" id="chart-ucs-ranking"></div>
    </article>
  </section>
  <details class="cf-deep-section" id="cf-deep-details">
    <summary class="cf-deep-summary">
      <span>Exploração aprofundada (Sensores, Horário local, Risco de fogo e 1.593 imóveis)</span>
    </summary>
    <div class="cf-bento-grid cf-deep-grid">
      <article class="cf-card cf-col-6">
        <div class="cf-card-head">
          <div>
            <h3>Sensores, Horário Local e Risco de Fogo</h3>
            <p class="cf-card-sub">Análise detalhada sobre os focos do recorte ativo.</p>
          </div>
          <div class="cf-seg-group" role="tablist" aria-label="Dimensão dos sensores">
            <button type="button" class="cf-btn-mini is-active" role="tab" aria-selected="true" data-sensor-tab="evolucao">Sensores</button>
            <button type="button" class="cf-btn-mini" role="tab" aria-selected="false" data-sensor-tab="horario">Horário local</button>
            <button type="button" class="cf-btn-mini" role="tab" aria-selected="false" data-sensor-tab="risco">Risco de fogo</button>
          </div>
        </div>
        <div class="cf-chart-box" id="chart-sensores-hora"></div>
      </article>
      <article class="cf-card cf-col-6">
        <div class="cf-card-head">
          <div>
            <h3>Reincidência Fundiária e Sobreposições</h3>
            <p class="cf-card-sub"><span class="cf-scope-badge">Escopo: Todos os 1.593 imóveis reincidentes</span></p>
          </div>
          <div class="cf-seg-group" role="tablist" aria-label="Visão da reincidência fundiária">
            <button type="button" class="cf-btn-mini is-active" role="tab" aria-selected="true" data-car-tab="situacao">Situação e Porte</button>
            <button type="button" class="cf-btn-mini" role="tab" aria-selected="false" data-car-tab="reincidencia">Anos (2–11)</button>
            <button type="button" class="cf-btn-mini" role="tab" aria-selected="false" data-car-tab="protegidas">Áreas Protegidas</button>
          </div>
        </div>
        <div class="cf-chart-box" id="chart-car-reincidencia"></div>
      </article>
    </div>
  </details>
</div>
<div id="cf-floating-tooltip" class="cf-floating-tooltip" role="tooltip" hidden></div>
