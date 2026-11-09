/**
 * Componente do Mapa Interativo com Linha do Tempo Temporal (2015-2025)
 * Plataforma Corta-Fogo DF - Entrega 3
 */

(function () {
  let mapInstance = null;
  let focosLayer = null;
  let ucsLayer = null;
  let imoveisLayer = null;
  let isPlaying = false;
  let playTimer = null;
  let currentYear = 2024; // Padrão no ano de maior ocorrência
  let canvasRenderer = null;

  function initMap() {
    const mapContainer = document.getElementById('corta-fogo-map');
    if (!mapContainer) return;
    if (mapContainer.dataset.initialized === 'true') return;

    if (typeof L === 'undefined') {
      setTimeout(initMap, 150);
      return;
    }

    if (!window.DADOS_MAPA_DF) {
      setTimeout(initMap, 150);
      return;
    }

    mapContainer.dataset.initialized = 'true';

    // Inicializa o mapa com limites do DF
    const cfg = window.DADOS_MAPA_DF.limites_df;
    mapInstance = L.map('corta-fogo-map', {
      center: cfg.centro,
      zoom: cfg.zoom,
      minZoom: 9,
      maxZoom: 15,
      zoomControl: true
    });

    canvasRenderer = L.canvas({ padding: 0.5 });

    // Tiles base elegantes (CartoDB Positron / OpenStreetMap)
    L.tileLayer('https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png', {
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>',
      subdomains: 'abcd',
      maxZoom: 19
    }).addTo(mapInstance);

    // Camadas de grupos
    ucsLayer = L.layerGroup().addTo(mapInstance);
    imoveisLayer = L.layerGroup().addTo(mapInstance);
    focosLayer = L.layerGroup().addTo(mapInstance);

    // Desenha as UCs e os imóveis uma vez
    desenharUcs();
    desenharImoveis();

    // Configura eventos da interface (slider, play, checkboxes)
    setupControls();

    // Renderiza o ano inicial
    renderYear(currentYear);
  }

  function desenharUcs() {
    ucsLayer.clearLayers();
    const ucs = window.DADOS_MAPA_DF.ucs || [];

    ucs.forEach(uc => {
      // Zona de amortecimento (1.000 m além do raio da UC)
      const buffer = L.circle([uc.lat, uc.lon], {
        radius: uc.raio_m + 1000,
        color: '#15803d',
        dashArray: '4, 4',
        weight: 1.5,
        fillColor: '#86efac',
        fillOpacity: 0.12,
        renderer: canvasRenderer
      });

      // Limite estimado da Unidade de Conservação
      const core = L.circle([uc.lat, uc.lon], {
        radius: uc.raio_m,
        color: '#166534',
        weight: 2,
        fillColor: '#22c55e',
        fillOpacity: 0.25,
        renderer: canvasRenderer
      });

      const popupContent = `
        <div style="font-family: inherit; font-size: 13px; line-height: 1.4;">
          <strong style="color: #166534; font-size: 14px;">${uc.nome}</strong><br/>
          <span style="font-size: 11px; color: #64748b;">${uc.tipo}</span>
          <hr style="margin: 6px 0; border: none; border-top: 1px solid #e2e8f0;"/>
          <b>Área aproximada:</b> ${uc.area_ha.toLocaleString('pt-BR')} ha<br/>
          <b>Faixa de amortecimento:</b> 1.000 m (critério E1/E2/E3)<br/>
          <p style="margin: 6px 0 0; color: #334155;">${uc.descricao}</p>
        </div>
      `;

      core.bindPopup(popupContent);
      buffer.bindTooltip(`Faixa de 1 km: ${uc.nome}`, { sticky: true });

      ucsLayer.addLayer(buffer);
      ucsLayer.addLayer(core);
    });
  }

  function desenharImoveis() {
    imoveisLayer.clearLayers();
    const imoveis = window.DADOS_MAPA_DF.imoveis_reincidentes || [];

    imoveis.forEach(imovel => {
      // Marcador com ícone de polígono/propriedade
      const marker = L.circleMarker([imovel.lat, imovel.lon], {
        radius: 8,
        color: '#7c3aed',
        weight: 2,
        fillColor: '#a855f7',
        fillOpacity: 0.85,
        renderer: canvasRenderer
      });

      const anosStr = imovel.anos.join(', ');
      const rlBadge = imovel.atinge_rl ? '<span style="background: #dcfce7; color: #166534; padding: 2px 6px; border-radius: 4px; font-weight: bold; font-size: 11px;">Reserva Legal</span>' : '';
      const appBadge = imovel.atinge_app ? '<span style="background: #e0f2fe; color: #0369a1; padding: 2px 6px; border-radius: 4px; font-weight: bold; font-size: 11px;">APP</span>' : '';
      const ucBadge = imovel.atinge_uc1km ? '<span style="background: #fef3c7; color: #92400e; padding: 2px 6px; border-radius: 4px; font-weight: bold; font-size: 11px;">Até 1 km de UC</span>' : '';

      const popupContent = `
        <div style="font-family: inherit; font-size: 13px; line-height: 1.4;">
          <strong style="color: #6b21a8; font-size: 14px;">Imóvel Rural Reincidente (CAR)</strong><br/>
          <code style="font-size: 11px; background: #f1f5f9; padding: 2px 4px; border-radius: 3px;">${imovel.cod_imovel}</code>
          <hr style="margin: 6px 0; border: none; border-top: 1px solid #e2e8f0;"/>
          <b>Região:</b> ${imovel.ra}<br/>
          <b>Área cadastrada:</b> ${imovel.area_ha.toLocaleString('pt-BR')} ha<br/>
          <b>Total de focos no imóvel:</b> ${imovel.focos_total}<br/>
          <b>Anos com reincidência (${imovel.anos.length}):</b> ${anosStr}<br/>
          <b>Sobreposições críticas:</b><br/>
          <div style="margin-top: 4px; display: flex; gap: 4px; flex-wrap: wrap;">
            ${rlBadge} ${appBadge} ${ucBadge}
          </div>
          <p style="margin: 8px 0 0; color: #475569; font-size: 12px; font-style: italic;">${imovel.detalhe}</p>
        </div>
      `;

      marker.bindPopup(popupContent);
      marker.bindTooltip(`CAR: ${imovel.cod_imovel.substring(0, 16)}... (${imovel.ra})`, { sticky: true });
      imoveisLayer.addLayer(marker);
    });
  }

  function renderYear(selectedYear) {
    currentYear = selectedYear;
    focosLayer.clearLayers();

    const statsEl = document.getElementById('cf-stats-total');
    const secaEl = document.getElementById('cf-stats-seca');
    const refEl = document.getElementById('cf-stats-ref');
    const imoveisEl = document.getElementById('cf-stats-imoveis');
    const badgeEl = document.getElementById('cf-ano-badge');

    const isAll = (selectedYear === 2026);
    const labelTexto = isAll ? '2015–2025 (Todos)' : String(selectedYear);
    if (badgeEl) badgeEl.textContent = labelTexto;

    const onlyRefCheckbox = document.getElementById('cf-check-only-ref');
    const onlyRef = onlyRefCheckbox ? onlyRefCheckbox.checked : false;

    let totalPontos = 0;
    let totalSeca = 0;
    let totalRef = 0;

    const anosParaProcessar = isAll ? Array.from({ length: 11 }, (_, i) => 2015 + i) : [selectedYear];

    anosParaProcessar.forEach(ano => {
      const pontos = window.DADOS_MAPA_DF.focos_ano[ano] || [];
      const st = window.DADOS_MAPA_DF.stats_ano[ano];
      if (st) {
        totalPontos += st.total;
        totalSeca += st.seca;
        totalRef += st.referencia;
      }

      pontos.forEach(pt => {
        const [lat, lon, isRef, isSeca, mes] = pt;
        if (onlyRef && !isRef) return;

        // Estilo visual: cor mais vívida para satélite de referência e seca
        const cor = isRef ? '#dc2626' : (isSeca ? '#ea580c' : '#f59e0b');
        const raio = isRef ? 4 : 2.5;

        const circle = L.circleMarker([lat, lon], {
          radius: raio,
          color: cor,
          weight: 1,
          fillColor: cor,
          fillOpacity: 0.65,
          renderer: canvasRenderer
        });

        circle.bindTooltip(
          `Foco em ${ano} (mês ${mes}) - ${isRef ? 'AQUA_M-T (Referência)' : 'Sensor Secundário'}`,
          { sticky: true }
        );

        focosLayer.addLayer(circle);
      });
    });

    // Atualiza os cartões de estatísticas
    if (statsEl) statsEl.textContent = totalPontos.toLocaleString('pt-BR');
    if (secaEl) {
      const pctSeca = totalPontos > 0 ? ((totalSeca / totalPontos) * 100).toFixed(1) : '0.0';
      secaEl.textContent = `${pctSeca}% (${totalSeca.toLocaleString('pt-BR')})`;
    }
    if (refEl) {
      const pctRef = totalPontos > 0 ? ((totalRef / totalPontos) * 100).toFixed(1) : '0.0';
      refEl.textContent = `${pctRef}% (${totalRef.toLocaleString('pt-BR')})`;
    }
    if (imoveisEl) {
      // Conta quantos imóveis da amostra tiveram focos neste ano
      const imoveis = window.DADOS_MAPA_DF.imoveis_reincidentes || [];
      const ativos = isAll
        ? imoveis.length
        : imoveis.filter(im => im.anos.includes(selectedYear)).length;
      imoveisEl.textContent = `${ativos} de ${imoveis.length} cadastros críticos`;
    }
  }

  function setupControls() {
    const slider = document.getElementById('cf-ano-slider');
    const playBtn = document.getElementById('cf-play-btn');
    const onlyRefCheckbox = document.getElementById('cf-check-only-ref');
    const checkUcs = document.getElementById('cf-check-ucs');
    const checkImoveis = document.getElementById('cf-check-imoveis');
    const checkFocos = document.getElementById('cf-check-focos');

    if (slider) {
      slider.addEventListener('input', function () {
        if (isPlaying) stopPlay();
        renderYear(parseInt(this.value, 10));
      });
    }

    if (playBtn) {
      playBtn.addEventListener('click', function () {
        isPlaying ? stopPlay() : startPlay();
      });
    }

    if (onlyRefCheckbox) {
      onlyRefCheckbox.addEventListener('change', function () {
        renderYear(currentYear);
      });
    }

    if (checkUcs) {
      checkUcs.addEventListener('change', function () {
        this.checked ? mapInstance.addLayer(ucsLayer) : mapInstance.removeLayer(ucsLayer);
      });
    }

    if (checkImoveis) {
      checkImoveis.addEventListener('change', function () {
        this.checked ? mapInstance.addLayer(imoveisLayer) : mapInstance.removeLayer(imoveisLayer);
      });
    }

    if (checkFocos) {
      checkFocos.addEventListener('change', function () {
        this.checked ? mapInstance.addLayer(focosLayer) : mapInstance.removeLayer(focosLayer);
      });
    }
  }

  function startPlay() {
    isPlaying = true;
    const playBtn = document.getElementById('cf-play-btn');
    if (playBtn) playBtn.innerHTML = '&#10074;&#10074; Pausar';

    const slider = document.getElementById('cf-ano-slider');

    playTimer = setInterval(() => {
      let nextYear = currentYear + 1;
      if (nextYear > 2026) {
        nextYear = 2015;
      }
      currentYear = nextYear;
      if (slider) slider.value = currentYear;
      renderYear(currentYear);
    }, 1200);
  }

  function stopPlay() {
    isPlaying = false;
    clearInterval(playTimer);
    const playBtn = document.getElementById('cf-play-btn');
    if (playBtn) playBtn.innerHTML = '&#9654; Reproduzir';
  }

  // Registra no ciclo de vida do Zensical / DOM
  if (window.document$) {
    window.document$.subscribe(() => {
      initMap();
    });
  } else if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initMap);
  } else {
    initMap();
  }
})();
