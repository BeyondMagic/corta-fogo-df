/**
 * Componente do Mapa Interativo com Linha do Tempo Temporal (2015-2025)
 * Plataforma Corta-Fogo DF - Entrega 3
 */

(function () {
  let mapInstance = null;
  let focosLayer = null;
  let bufferLayer = null;
  let ucsLayer = null;
  let imoveisLayer = null;
  let activeImovelPolygon = null;
  let isPlaying = false;
  let playTimer = null;
  let currentYear = 2024; // Padrao no ano de maior ocorrencia
  let canvasRenderer = null;
  let osmLayer = null;
  let esriLayer = null;
  let currentBaseLayer = null;

  function initMap() {
    const mapContainer = document.getElementById('corta-fogo-map');
    if (!mapContainer) {
      if (playTimer) {
        clearInterval(playTimer);
        playTimer = null;
        isPlaying = false;
      }
      if (activeImovelPolygon && mapInstance) {
        try {
          mapInstance.removeLayer(activeImovelPolygon);
        } catch (e) {}
        activeImovelPolygon = null;
      }
      if (mapInstance) {
        try {
          mapInstance.remove();
        } catch (e) {}
        mapInstance = null;
      }
      return;
    }
    if (mapContainer.dataset.initialized === 'true') return;

    if (typeof L === 'undefined') {
      setTimeout(initMap, 150);
      return;
    }

    if (!window.DADOS_MAPA_DF) {
      setTimeout(initMap, 150);
      return;
    }

    if (playTimer) {
      clearInterval(playTimer);
      playTimer = null;
      isPlaying = false;
    }
    if (activeImovelPolygon && mapInstance) {
      try {
        mapInstance.removeLayer(activeImovelPolygon);
      } catch (e) {}
      activeImovelPolygon = null;
    }
    if (mapInstance) {
      try {
        mapInstance.remove();
      } catch (e) {}
      mapInstance = null;
    }

    mapContainer.dataset.initialized = 'true';

    // Inicializa o mapa com limites do DF
    const cfg = window.DADOS_MAPA_DF.limites_df;
    mapInstance = L.map('corta-fogo-map', {
      center: cfg.centro,
      zoom: cfg.zoom,
      minZoom: 9,
      maxZoom: 16,
      zoomControl: true
    });

    setTimeout(() => {
      if (mapInstance) {
        mapInstance.invalidateSize();
      }
    }, 200);

    canvasRenderer = L.canvas({ padding: 0.5 });

    // Tiles base abertos sem exigencia de chave de API
    osmLayer = L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
      maxZoom: 19
    });

    esriLayer = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}', {
      attribution: 'Tiles &copy; Esri, HERE, Garmin, OpenStreetMap contributors',
      maxZoom: 16
    });

    currentBaseLayer = osmLayer;
    osmLayer.addTo(mapInstance);

    const baseMaps = {
      'OpenStreetMap (Padrão)': osmLayer,
      'ESRI Light Gray (Neutro)': esriLayer
    };

    L.control.layers(baseMaps, null, { position: 'topright' }).addTo(mapInstance);

    // Botão de tela cheia no Leaflet (canto superior esquerdo, abaixo do zoom)
    const FullscreenControl = L.Control.extend({
      options: { position: 'topleft' },
      onAdd: function () {
        const btn = L.DomUtil.create('button', 'leaflet-bar leaflet-control leaflet-control-custom cf-leaflet-fs-btn');
        btn.type = 'button';
        btn.title = 'Alternar tela cheia';
        btn.setAttribute('aria-label', 'Alternar tela cheia');
        btn.innerHTML = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M8 3H5a2 2 0 0 0-2 2v3m18 0V5a2 2 0 0 0-2-2h-3m0 18h3a2 2 0 0 0 2-2v-3M3 16v3a2 2 0 0 0 2 2h3"/></svg>';
        btn.onclick = function (e) {
          e.stopPropagation();
          e.preventDefault();
          toggleFullscreen();
        };
        return btn;
      }
    });
    mapInstance.addControl(new FullscreenControl());

    // Ordem de camadas no mapa (do fundo para o topo):
    // 1. Faixa de amortecimento (1.000 m)
    // 2. Polígonos de UCs (84 áreas oficiais)
    // 3. Marcadores de imóveis CAR
    // 4. Focos de calor (canvas)
    bufferLayer = L.layerGroup().addTo(mapInstance);
    ucsLayer = L.layerGroup().addTo(mapInstance);
    imoveisLayer = L.layerGroup().addTo(mapInstance);
    focosLayer = L.layerGroup().addTo(mapInstance);

    // Renderiza camadas espaciais
    desenharUcs();
    desenharImoveis();

    // Configura eventos da interface (slider, reproducao, filtros)
    setupControls();

    // Renderiza o ano inicial
    renderYear(currentYear);
  }

  function desenharUcs() {
    bufferLayer.clearLayers();
    ucsLayer.clearLayers();

    const buffersGeo = window.DADOS_MAPA_DF.buffers_geojson;
    const ucsGeo = window.DADOS_MAPA_DF.ucs_geojson;

    // 1. Faixas de amortecimento de 1.000 m
    if (buffersGeo) {
      const bufLayer = L.geoJSON(buffersGeo, {
        style: {
          color: '#15803d',
          dashArray: '4, 4',
          weight: 1.2,
          fillColor: '#86efac',
          fillOpacity: 0.10
        },
        onEachFeature: function (feature, layer) {
          const nome = feature.properties ? feature.properties.nome : 'UC';
          layer.bindTooltip('Faixa de amortecimento (1 km): ' + nome, { sticky: true });
        }
      });
      bufferLayer.addLayer(bufLayer);
    }

    // 2. Polígonos reais das 84 UCs oficiais do DF
    if (ucsGeo) {
      const ucLayer = L.geoJSON(ucsGeo, {
        style: function (feature) {
          const cat = (feature.properties && feature.properties.uc_conserv) || '';
          if (cat.indexOf('Proteção Integral') !== -1) {
            return {
              color: '#15803d',
              weight: 2,
              fillColor: '#22c55e',
              fillOpacity: 0.30
            };
          }
          if (cat.indexOf('Uso Sustentável') !== -1) {
            return {
              color: '#65a30d',
              weight: 1.5,
              fillColor: '#a3e635',
              fillOpacity: 0.20
            };
          }
          return {
            color: '#0d9488',
            weight: 1.5,
            fillColor: '#2dd4bf',
            fillOpacity: 0.20
          };
        },
        onEachFeature: function (feature, layer) {
          const p = feature.properties || {};
          const cat = p.uc_conserv || 'Espaço Protegido';

          let badgeStyle = 'background: #ccfbf1; color: #115e59;';
          let badgeLabel = 'Espaço Protegido';
          if (cat.indexOf('Proteção Integral') !== -1) {
            badgeStyle = 'background: #dcfce7; color: #166534;';
            badgeLabel = 'Proteção Integral';
          } else if (cat.indexOf('Uso Sustentável') !== -1) {
            badgeStyle = 'background: #fef9c3; color: #854d0e;';
            badgeLabel = 'Uso Sustentável';
          }

          const badgeHtml = '<span style="' + badgeStyle + ' padding: 2px 6px; border-radius: 4px; font-weight: bold; font-size: 11px;">' + badgeLabel + '</span>';
          const areaFormatada = Number(p.area_ha || 0).toLocaleString('pt-BR');

          const popupContent = `
            <div style="font-family: inherit; font-size: 13px; line-height: 1.45; min-width: 220px;">
              <strong style="color: #166534; font-size: 14px;">${p.nome || 'Unidade de Conservação'}</strong><br/>
              <div style="margin: 4px 0 6px;">${badgeHtml}</div>
              <hr style="margin: 6px 0; border: none; border-top: 1px solid #e2e8f0;"/>
              <b>Categoria:</b> ${p.uc_conserv || 'N/D'}<br/>
              <b>Gestão:</b> ${p.gestao || 'Distrital (IBRAM)'}<br/>
              <b>Área oficial:</b> ${areaFormatada} ha<br/>
              <b>Ano de criação:</b> ${p.ano_criaca || 'N/D'}<br/>
              <b>Faixa de amortecimento:</b> 1.000 m (critério E1/E2/E3)
            </div>
          `;

          layer.bindPopup(popupContent);
          const tooltipTexto = p.sigla ? `${p.sigla} (${p.nome})` : p.nome;
          layer.bindTooltip(tooltipTexto, { sticky: true });
        }
      });
      ucsLayer.addLayer(ucLayer);
    }
  }

  function desenharImoveis() {
    imoveisLayer.clearLayers();
    const imoveis = window.DADOS_MAPA_DF.imoveis_reincidentes || [];

    imoveis.forEach(imovel => {
      // Marcador pontual com ícone destacado de cadastro fundiário
      const marker = L.circleMarker([imovel.lat, imovel.lon], {
        radius: 8,
        color: '#6b21a8',
        weight: 2,
        fillColor: '#a855f7',
        fillOpacity: 0.90,
        renderer: canvasRenderer
      });

      const anosStr = imovel.anos.join(', ');
      const rlBadge = imovel.atinge_rl
        ? '<span style="background: #dcfce7; color: #166534; padding: 2px 6px; border-radius: 4px; font-weight: bold; font-size: 11px;">Reserva Legal</span>'
        : '<span style="background: #f1f5f9; color: #64748b; padding: 2px 6px; border-radius: 4px; font-size: 11px;">Sem RL</span>';

      const appBadge = imovel.atinge_app
        ? '<span style="background: #e0f2fe; color: #0369a1; padding: 2px 6px; border-radius: 4px; font-weight: bold; font-size: 11px;">APP</span>'
        : '';

      const ucBadge = imovel.atinge_uc1km
        ? '<span style="background: #fef3c7; color: #92400e; padding: 2px 6px; border-radius: 4px; font-weight: bold; font-size: 11px;">Até 1 km de UC</span>'
        : '';

      const sitBadge = '<span style="background: #ede9fe; color: #5b21b6; padding: 2px 6px; border-radius: 4px; font-weight: bold; font-size: 11px;">Situação: ' + imovel.situacao + '</span>';

      const popupContent = `
        <div style="font-family: inherit; font-size: 13px; line-height: 1.45; min-width: 250px;">
          <strong style="color: #6b21a8; font-size: 14px;">Imóvel CAR Reincidente Crítico</strong><br/>
          <code style="font-size: 10.5px; background: #f1f5f9; padding: 2px 4px; border-radius: 3px; word-break: break-all;">${imovel.cod_imovel}</code>
          <div style="margin: 6px 0 4px;">${sitBadge}</div>
          <hr style="margin: 6px 0; border: none; border-top: 1px solid #e2e8f0;"/>
          <b>Total de focos no imóvel:</b> <span style="color: #b91c1c; font-weight: bold;">${imovel.focos_total.toLocaleString('pt-BR')}</span><br/>
          <b>Área cadastrada:</b> ${imovel.area_ha.toLocaleString('pt-BR')} ha<br/>
          <b>Anos com reincidência (${imovel.anos.length}):</b> ${anosStr}<br/>
          <b>Sobreposições críticas:</b>
          <div style="margin-top: 4px; display: flex; gap: 4px; flex-wrap: wrap;">
            ${rlBadge} ${appBadge} ${ucBadge}
          </div>
          <p style="margin: 8px 0 0; color: #475569; font-size: 12px; font-style: italic;">${imovel.detalhe}</p>
        </div>
      `;

      marker.bindPopup(popupContent);
      marker.bindTooltip(`CAR: ${imovel.cod_imovel.substring(0, 18)}... (${imovel.focos_total} focos)`, { sticky: true });

      // Ao abrir o popup, desenha o polígono real cadastral do imóvel no mapa
      marker.on('popupopen', function () {
        if (activeImovelPolygon) {
          mapInstance.removeLayer(activeImovelPolygon);
          activeImovelPolygon = null;
        }
        if (imovel.geometry) {
          activeImovelPolygon = L.geoJSON(imovel.geometry, {
            style: {
              color: '#7c3aed',
              weight: 2.5,
              fillColor: '#c084fc',
              fillOpacity: 0.28
            }
          }).addTo(mapInstance);
        }
      });

      // Ao fechar o popup, remove o polígono cadastral para manter o mapa leve
      marker.on('popupclose', function () {
        if (activeImovelPolygon) {
          mapInstance.removeLayer(activeImovelPolygon);
          activeImovelPolygon = null;
        }
      });

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
    const labelTexto = isAll ? '2015 a 2025 (Todos)' : String(selectedYear);
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
    const checkBuffer = document.getElementById('cf-check-buffer-1km');
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

    if (checkBuffer) {
      checkBuffer.addEventListener('change', function () {
        this.checked ? mapInstance.addLayer(bufferLayer) : mapInstance.removeLayer(bufferLayer);
      });
    }

    if (checkImoveis) {
      checkImoveis.addEventListener('change', function () {
        this.checked ? mapInstance.addLayer(imoveisLayer) : mapInstance.removeLayer(imoveisLayer);
        if (!this.checked && activeImovelPolygon) {
          mapInstance.removeLayer(activeImovelPolygon);
          activeImovelPolygon = null;
        }
      });
    }

    if (checkFocos) {
      checkFocos.addEventListener('change', function () {
        this.checked ? mapInstance.addLayer(focosLayer) : mapInstance.removeLayer(focosLayer);
      });
    }

    const basemapSelect = document.getElementById('cf-select-basemap');
    if (basemapSelect) {
      basemapSelect.addEventListener('change', function () {
        mapInstance.removeLayer(currentBaseLayer);
        if (this.value === 'esri') {
          currentBaseLayer = esriLayer;
        } else {
          currentBaseLayer = osmLayer;
        }
        mapInstance.addLayer(currentBaseLayer);
        currentBaseLayer.bringToBack();
      });
    }

    mapInstance.on('baselayerchange', function (e) {
      currentBaseLayer = e.layer;
      if (basemapSelect) {
        basemapSelect.value = (e.name.indexOf('ESRI') !== -1) ? 'esri' : 'osm';
      }
    });

    // Configura botão de alternância de tela cheia
    const fsBtn = document.getElementById('cf-btn-fullscreen');
    if (fsBtn) {
      fsBtn.addEventListener('click', function (e) {
        e.preventDefault();
        toggleFullscreen();
      });
    }

    document.addEventListener('fullscreenchange', syncFullscreenState);
    document.addEventListener('webkitfullscreenchange', syncFullscreenState);
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') {
        const card = document.querySelector('.cf-map-card');
        if (card && card.classList.contains('cf-fullscreen-fallback')) {
          exitFallbackFullscreen(card);
        }
      }
    });
  }

  function toggleFullscreen() {
    const card = document.querySelector('.cf-map-card');
    if (!card) return;

    const isFs = (document.fullscreenElement === card) ||
                 (document.webkitFullscreenElement === card) ||
                 card.classList.contains('cf-fullscreen-fallback');

    if (!isFs) {
      if (card.requestFullscreen) {
        card.requestFullscreen().catch(() => {
          enterFallbackFullscreen(card);
        });
      } else if (card.webkitRequestFullscreen) {
        card.webkitRequestFullscreen();
      } else {
        enterFallbackFullscreen(card);
      }
    } else {
      if (document.fullscreenElement) {
        document.exitFullscreen().catch(() => {});
      } else if (document.webkitFullscreenElement) {
        document.webkitExitFullscreen();
      } else {
        exitFallbackFullscreen(card);
      }
    }
  }

  function enterFallbackFullscreen(card) {
    card.classList.add('cf-fullscreen-fallback');
    syncFullscreenState();
  }

  function exitFallbackFullscreen(card) {
    card.classList.remove('cf-fullscreen-fallback');
    syncFullscreenState();
  }

  function syncFullscreenState() {
    const card = document.querySelector('.cf-map-card');
    if (!card) return;

    const isFs = (document.fullscreenElement === card) ||
                 (document.webkitFullscreenElement === card) ||
                 card.classList.contains('cf-fullscreen-fallback');

    // Atualiza botão dos controles
    const fsBtn = document.getElementById('cf-btn-fullscreen');
    if (fsBtn) {
      fsBtn.setAttribute('aria-pressed', isFs ? 'true' : 'false');
      const iconEnter = fsBtn.querySelector('.cf-icon-fs-enter');
      const iconExit = fsBtn.querySelector('.cf-icon-fs-exit');
      const textSpan = fsBtn.querySelector('.cf-fs-text');
      if (iconEnter) iconEnter.style.display = isFs ? 'none' : 'inline-block';
      if (iconExit) iconExit.style.display = isFs ? 'inline-block' : 'none';
      if (textSpan) textSpan.textContent = isFs ? 'Sair da Tela Cheia' : 'Tela Cheia';
    }

    // Atualiza botão do Leaflet
    const leafletFsBtn = document.querySelector('.cf-leaflet-fs-btn');
    if (leafletFsBtn) {
      leafletFsBtn.title = isFs ? 'Sair da tela cheia' : 'Alternar tela cheia';
      leafletFsBtn.setAttribute('aria-label', isFs ? 'Sair da tela cheia' : 'Alternar tela cheia');
      leafletFsBtn.innerHTML = isFs
        ? '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M8 3v3a2 2 0 0 1-2 2H3m18 0h-3a2 2 0 0 1-2-2V3m0 18v-3a2 2 0 0 1 2-2h3M3 16h3a2 2 0 0 1 2 2v3"/></svg>'
        : '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M8 3H5a2 2 0 0 0-2 2v3m18 0V5a2 2 0 0 0-2-2h-3m0 18h3a2 2 0 0 0 2-2v-3M3 16v3a2 2 0 0 0 2 2h3"/></svg>';
    }

    // Redimensiona o Leaflet suavemente para acomodar as novas dimensões do viewport
    setTimeout(() => {
      if (mapInstance) mapInstance.invalidateSize();
    }, 100);
    setTimeout(() => {
      if (mapInstance) mapInstance.invalidateSize();
    }, 300);
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
