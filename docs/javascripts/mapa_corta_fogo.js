/**
 * Camada Leaflet integrada ao Dashboard Corta-Fogo DF.
 * Mantem tiles OpenStreetMap/ESRI, camadas oficiais (DF, RAs, 84 UCs, buffers e CAR)
 * e sincroniza filtros e foco espacial com o modulo D3 em window.CFLeafletBridge.
 */
(function () {
  let mapInstance = null;
  let canvasRenderer = null;
  let rasLayer = null;
  let bufferLayer = null;
  let ucsLayer = null;
  let imoveisLayer = null;
  let focosLayer = null;
  let activeOverlayGroup = null;

  let osmLayer = null;
  let esriLayer = null;
  let currentBaseLayer = null;

  let storedData = null;
  let pendingPayload = null;
  let lastState = null;

  function escapeHtml(text) {
    return String(text == null ? '' : text)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function formatPtBr(num, decimals) {
    const val = Number(num || 0);
    if (typeof decimals === 'number') {
      return val.toLocaleString('pt-BR', {
        minimumFractionDigits: decimals,
        maximumFractionDigits: decimals
      });
    }
    return val.toLocaleString('pt-BR');
  }

  function destroyMap() {
    if (activeOverlayGroup && mapInstance) {
      try {
        mapInstance.removeLayer(activeOverlayGroup);
      } catch (e) {}
    }
    activeOverlayGroup = null;
    if (mapInstance) {
      try {
        mapInstance.remove();
      } catch (e) {}
    }
    mapInstance = null;
    canvasRenderer = null;
    rasLayer = null;
    bufferLayer = null;
    ucsLayer = null;
    imoveisLayer = null;
    focosLayer = null;
    osmLayer = null;
    esriLayer = null;
    currentBaseLayer = null;
  }

  function toggleStageFullscreen() {
    const stage = document.getElementById('cf-stage-card') || document.querySelector('.cf-map-card');
    if (!stage) return;
    const isFs = (document.fullscreenElement === stage) ||
      (document.webkitFullscreenElement === stage) ||
      stage.classList.contains('cf-fullscreen-fallback');

    if (!isFs) {
      if (stage.requestFullscreen) {
        stage.requestFullscreen().catch(() => {
          stage.classList.add('cf-fullscreen-fallback');
          invalidateSize();
        });
      } else if (stage.webkitRequestFullscreen) {
        stage.webkitRequestFullscreen();
      } else {
        stage.classList.add('cf-fullscreen-fallback');
        invalidateSize();
      }
    } else if (document.fullscreenElement) {
      document.exitFullscreen().catch(() => {});
    } else if (document.webkitFullscreenElement) {
      document.webkitExitFullscreen();
    } else {
      stage.classList.remove('cf-fullscreen-fallback');
      invalidateSize();
    }
  }

  function invalidateSize() {
    if (!mapInstance) return;
    setTimeout(() => {
      if (mapInstance) mapInstance.invalidateSize();
    }, 60);
    setTimeout(() => {
      if (mapInstance) mapInstance.invalidateSize();
    }, 260);
  }

  function drawVectorLayers(data) {
    if (!mapInstance || !data) return;

    rasLayer.clearLayers();
    bufferLayer.clearLayers();
    ucsLayer.clearLayers();

    if (data.rasGeo) {
      const layer = L.geoJSON(data.rasGeo, {
        style: {
          color: '#64748b',
          weight: 1.1,
          dashArray: '3, 3',
          fillColor: '#94a3b8',
          fillOpacity: 0.04
        },
        onEachFeature: function (feature, lyr) {
          const p = feature.properties || {};
          lyr.bindTooltip(
            escapeHtml((p.codigo ? p.codigo + ' - ' : '') + (p.nome || 'RA')),
            { sticky: true }
          );
          lyr.on('click', function () {
            if (window.CFDashboardBridge && typeof window.CFDashboardBridge.selectRA === 'function') {
              window.CFDashboardBridge.selectRA(p.idx);
            }
          });
        }
      });
      rasLayer.addLayer(layer);
    }

    if (data.buffersGeo) {
      const layer = L.geoJSON(data.buffersGeo, {
        style: {
          color: '#15803d',
          dashArray: '4, 4',
          weight: 1.1,
          fillColor: '#86efac',
          fillOpacity: 0.10
        },
        onEachFeature: function (feature, lyr) {
          const nome = feature.properties ? feature.properties.nome : 'UC';
          lyr.bindTooltip('Faixa de amortecimento (1 km): ' + escapeHtml(nome), { sticky: true });
        }
      });
      bufferLayer.addLayer(layer);
    }

    if (data.ucsGeo) {
      const layer = L.geoJSON(data.ucsGeo, {
        style: function (feature) {
          const cat = (feature.properties && feature.properties.uc_conserv) || '';
          if (cat.indexOf('Proteção Integral') !== -1) {
            return { color: '#15803d', weight: 1.8, fillColor: '#22c55e', fillOpacity: 0.28 };
          }
          if (cat.indexOf('Uso Sustentável') !== -1) {
            return { color: '#65a30d', weight: 1.3, fillColor: '#a3e635', fillOpacity: 0.18 };
          }
          return { color: '#0d9488', weight: 1.3, fillColor: '#2dd4bf', fillOpacity: 0.18 };
        },
        onEachFeature: function (feature, lyr) {
          const p = feature.properties || {};
          const cat = p.uc_conserv || 'Espaço Protegido';
          const popupHtml = `
            <div style="font-family: inherit; font-size: 13px; line-height: 1.45; min-width: 220px;">
              <strong>${escapeHtml(p.nome || 'Unidade de Conservação')}</strong><br/>
              <small>${escapeHtml(cat)}</small>
              <hr style="margin: 6px 0; border: none; border-top: 1px solid #e2e8f0;"/>
              <b>Gestão:</b> ${escapeHtml(p.gestao || 'Distrital (IBRAM)')}<br/>
              <b>Área oficial:</b> ${formatPtBr(p.area_ha, 1)} ha<br/>
              <b>Ano de criação:</b> ${escapeHtml(p.ano_criaca || 'N/D')}<br/>
              <b>Faixa considerada:</b> interior + 1.000 m
            </div>
          `;
          lyr.bindPopup(popupHtml);
          lyr.bindTooltip(
            escapeHtml(p.sigla ? `${p.sigla} (${p.nome})` : (p.nome || 'UC')),
            { sticky: true }
          );
          lyr.on('click', function () {
            if (window.CFDashboardBridge && typeof window.CFDashboardBridge.selectUC === 'function') {
              window.CFDashboardBridge.selectUC(p.idx);
            }
          });
        }
      });
      ucsLayer.addLayer(layer);
    }
  }

  function drawImoveisMarkers(data, state) {
    if (!mapInstance || !data) return;
    imoveisLayer.clearLayers();

    const imoveis = data.carTop50 || [];
    const geoms = data.carTop50Geoms || {};
    const situacaoFiltro = state && state.situacao && state.situacao !== 'todos' ? state.situacao : null;
    const anoFiltro = state && state.ano && state.ano !== 'todos' ? Number(state.ano) : null;

    imoveis.forEach((im) => {
      if (situacaoFiltro && im.situacao !== situacaoFiltro) return;
      if (anoFiltro && (!im.anos || !im.anos.includes(anoFiltro))) return;

      const marker = L.circleMarker([im.lat, im.lon], {
        radius: 7,
        color: '#6b21a8',
        weight: 2,
        fillColor: '#a855f7',
        fillOpacity: 0.9,
        renderer: canvasRenderer
      });

      const badges = [
        `<span style="background:#ede9fe;color:#5b21b6;padding:2px 6px;border-radius:4px;font-weight:700;font-size:11px;">Situação: ${escapeHtml(im.situacao)}</span>`
      ];
      if (im.atinge_rl) {
        badges.push('<span style="background:#dcfce7;color:#166534;padding:2px 6px;border-radius:4px;font-weight:700;font-size:11px;">Reserva Legal</span>');
      }
      if (im.atinge_uc1km) {
        badges.push('<span style="background:#fef3c7;color:#92400e;padding:2px 6px;border-radius:4px;font-weight:700;font-size:11px;">Até 1 km de UC</span>');
      }

      const popupHtml = `
        <div style="font-family: inherit; font-size: 13px; line-height: 1.45; min-width: 245px;">
          <strong style="color:#6b21a8;font-size:14px;">#${im.rank} Imóvel CAR Reincidente</strong><br/>
          <code style="font-size:10.5px;word-break:break-all;">${escapeHtml(im.cod_imovel)}</code>
          <div style="margin:6px 0;display:flex;gap:4px;flex-wrap:wrap;">${badges.join('')}</div>
          <hr style="margin:6px 0;border:none;border-top:1px solid #e2e8f0;"/>
          <b>Focos no imóvel:</b> ${formatPtBr(im.focos_total)}<br/>
          <b>Focos em área protegida (RL / UC 1 km):</b> ${formatPtBr(im.focos_prot)}<br/>
          <b>Área cadastrada:</b> ${formatPtBr(im.area_ha, 1)} ha<br/>
          <b>Anos distintos (${im.anos_qtd}):</b> ${(im.anos || []).join(', ')}
        </div>
      `;

      marker.bindPopup(popupHtml);
      marker.bindTooltip(`#${im.rank} CAR: ${im.cod_imovel.slice(0, 18)}... (${im.focos_total} focos)`, { sticky: true });

      marker.on('popupopen', function () {
        const g = geoms[im.cod_imovel];
        if (g) {
          showActiveGeometries(g.imovel, g.reserva_legal, false);
        }
        if (window.CFDashboardBridge && typeof window.CFDashboardBridge.selectCAR === 'function') {
          window.CFDashboardBridge.selectCAR(im.cod_imovel, false);
        }
      });

      marker.on('popupclose', function () {
        clearActiveGeometries();
      });

      imoveisLayer.addLayer(marker);
    });
  }

  function showActiveGeometries(imovelGeom, rlGeoms, shouldZoom) {
    if (!mapInstance) return;
    clearActiveGeometries();

    const showRl = !lastState || !lastState.layers || lastState.layers.rl !== false;
    const layersToFit = [];

    if (imovelGeom) {
      const carPoly = L.geoJSON(imovelGeom, {
        style: {
          color: '#7c3aed',
          weight: 2.5,
          fillColor: '#c084fc',
          fillOpacity: 0.25
        }
      });
      activeOverlayGroup.addLayer(carPoly);
      layersToFit.push(carPoly);
    }

    if (showRl && Array.isArray(rlGeoms) && rlGeoms.length > 0) {
      const rlPoly = L.geoJSON({ type: 'FeatureCollection', features: rlGeoms.map(g => ({ type: 'Feature', geometry: g, properties: {} })) }, {
        style: {
          color: '#059669',
          weight: 2,
          dashArray: '4, 3',
          fillColor: '#34d399',
          fillOpacity: 0.35
        }
      });
      activeOverlayGroup.addLayer(rlPoly);
      layersToFit.push(rlPoly);
    }

    if (shouldZoom && layersToFit.length > 0) {
      const bounds = L.featureGroup(layersToFit).getBounds();
      if (bounds.isValid()) {
        mapInstance.fitBounds(bounds, { padding: [36, 36], maxZoom: 14 });
      }
    }
  }

  function clearActiveGeometries() {
    if (activeOverlayGroup) {
      activeOverlayGroup.clearLayers();
    }
  }

  function drawFocos(focos, data) {
    if (!mapInstance || !data) return;
    focosLayer.clearLayers();

    const metaMap = data.metadataSensores || {};
    const meses = ['Jan', 'Fev', 'Mar', 'Abr', 'Mai', 'Jun', 'Jul', 'Ago', 'Set', 'Out', 'Nov', 'Dez'];

    // Indices do schema focos.json:
    // [0:lat, 1:lon, 2:ano, 3:mes, 4:hora, 5:ref, 6:seca, 7:sensor, 8:risco, 9:ra, 10:uc_in, 11:uc_buf, 12:flags]
    for (let i = 0; i < focos.length; i += 1) {
      const f = focos[i];
      const lat = f[0];
      const lon = f[1];
      const ano = f[2];
      const mes = f[3];
      const hora = f[4];
      const isRef = f[5] === 1;
      const isSeca = f[6] === 1;
      const sensorTipo = f[7];
      const risco = f[8];

      const cor = isRef ? '#dc2626' : (isSeca ? '#ea580c' : '#f59e0b');
      const raio = isRef ? 4.2 : (sensorTipo === 0 ? 2.4 : 3.3);

      const circle = L.circleMarker([lat, lon], {
        radius: raio,
        color: cor,
        weight: 0.8,
        fillColor: cor,
        fillOpacity: 0.65,
        renderer: canvasRenderer
      });

      const meta = metaMap[String(sensorTipo)] || {
        nome: isRef ? 'MODIS (1.000 m)' : 'Sensor Orbital',
        dimensao: isRef ? '1.000 m x 1.000 m' : 'Variável',
        area_ha: isRef ? 100.0 : 14.1,
        orbita: isRef ? 'Polar (AQUA)' : 'Polar / Geoestacionária'
      };

      const mesNome = meses[(mes - 1) % 12] || String(mes);
      const riscoTxt = risco >= 0 ? `${risco}%` : 'N/D';

      const popupHtml = `
        <div style="font-family:inherit;font-size:13px;line-height:1.45;min-width:240px;">
          <strong style="color:#c2410c;font-size:14px;">Foco de Calor (${ano})</strong><br/>
          <small>${isRef ? 'Satélite de Referência (AQUA_M-T)' : 'Sensor complementar'} · ${isSeca ? 'Estiagem (Mai-Set)' : 'Período Chuvoso'}</small>
          <hr style="margin:6px 0;border:none;border-top:1px solid #e2e8f0;"/>
          <b>Coordenadas:</b> ${lat.toFixed(4)}°, ${lon.toFixed(4)}°<br/>
          <b>Data/hora aproximada:</b> ${mesNome}/${ano}, ${String(hora).padStart(2, '0')}h BRT<br/>
          <b>Risco de fogo (INPE):</b> ${riscoTxt}<br/>
          <b>Sensor / Pegada:</b> ${escapeHtml(meta.nome)} (${escapeHtml(meta.dimensao)}, ~${formatPtBr(meta.area_ha, 1)} ha)
        </div>
      `;

      circle.bindTooltip(`${mesNome}/${ano} (${String(hora).padStart(2, '0')}h) - ${meta.nome}`, { sticky: true });
      circle.bindPopup(popupHtml);
      focosLayer.addLayer(circle);
    }
  }

  function syncLayers(layers) {
    if (!mapInstance || !layers) return;
    const toggle = (flag, group) => {
      if (!group) return;
      if (flag) {
        if (!mapInstance.hasLayer(group)) mapInstance.addLayer(group);
      } else if (mapInstance.hasLayer(group)) {
        mapInstance.removeLayer(group);
      }
    };

    toggle(layers.ras, rasLayer);
    toggle(layers.buffers, bufferLayer);
    toggle(layers.ucs, ucsLayer);
    toggle(layers.imoveis, imoveisLayer);
    toggle(layers.focos, focosLayer);

    if (lastState && lastState.selectedCar && storedData && storedData.carTop50Geoms) {
      const g = storedData.carTop50Geoms[lastState.selectedCar];
      if (g) showActiveGeometries(g.imovel, g.reserva_legal, false);
    }
  }

  function mount(containerId, externalData) {
    const mapContainer = document.getElementById(containerId || 'corta-fogo-map');
    if (!mapContainer || typeof L === 'undefined') return false;

    storedData = externalData || storedData;
    if (!storedData) return false;

    if (mapInstance && mapInstance.getContainer() === mapContainer) {
      invalidateSize();
      return true;
    }

    destroyMap();
    mapContainer.dataset.initialized = 'true';

    const cfg = storedData.limites_df || { centro: [-15.78, -47.88], zoom: 10 };
    mapInstance = L.map(mapContainer, {
      center: cfg.centro,
      zoom: cfg.zoom,
      minZoom: 9,
      maxZoom: 16,
      zoomControl: true,
      preferCanvas: true
    });

    canvasRenderer = L.canvas({ padding: 0.5 });

    osmLayer = L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution: '&copy; OpenStreetMap contributors',
      maxZoom: 19
    });

    esriLayer = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}', {
      attribution: 'Tiles &copy; Esri, HERE, Garmin, OpenStreetMap',
      maxZoom: 16
    });

    const isDark = document.body.getAttribute('data-md-color-scheme') === 'slate';
    currentBaseLayer = osmLayer;
    currentBaseLayer.addTo(mapInstance);
    if (isDark) {
      // Leve atenuacao de brilho controlada por CSS no modo escuro
    }

    L.control.layers(
      {
        'OpenStreetMap (Ruas)': osmLayer,
        'ESRI Light Gray (Neutro)': esriLayer
      },
      null,
      { position: 'topright' }
    ).addTo(mapInstance);

    const FullscreenControl = L.Control.extend({
      options: { position: 'topleft' },
      onAdd: function () {
        const btn = L.DomUtil.create('button', 'leaflet-bar leaflet-control leaflet-control-custom cf-leaflet-fs-btn');
        btn.type = 'button';
        btn.title = 'Alternar tela cheia';
        btn.setAttribute('aria-label', 'Alternar tela cheia');
        btn.innerHTML = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M8 3H5a2 2 0 0 0-2 2v3m18 0V5a2 2 0 0 0-2-2h-3m0 18h3a2 2 0 0 0 2-2v-3M3 16v3a2 2 0 0 0 2 2h3"/></svg>';
        btn.onclick = function (e) {
          e.stopPropagation();
          e.preventDefault();
          toggleStageFullscreen();
        };
        return btn;
      }
    });
    mapInstance.addControl(new FullscreenControl());

    mapInstance.on('baselayerchange', function (e) {
      currentBaseLayer = e.layer;
      const sel = document.getElementById('cf-select-basemap');
      if (sel) {
        sel.value = (e.name.indexOf('ESRI') !== -1) ? 'esri' : 'osm';
      }
    });

    rasLayer = L.layerGroup().addTo(mapInstance);
    bufferLayer = L.layerGroup().addTo(mapInstance);
    ucsLayer = L.layerGroup().addTo(mapInstance);
    imoveisLayer = L.layerGroup().addTo(mapInstance);
    focosLayer = L.layerGroup().addTo(mapInstance);
    activeOverlayGroup = L.layerGroup().addTo(mapInstance);

    drawVectorLayers(storedData);

    if (pendingPayload) {
      updateView(pendingPayload);
      pendingPayload = null;
    } else if (lastState) {
      drawImoveisMarkers(storedData, lastState);
      syncLayers(lastState.layers);
    }

    invalidateSize();
    return true;
  }

  function updateView(payload) {
    if (!payload) return;
    lastState = payload.state || lastState;

    if (!mapInstance) {
      pendingPayload = payload;
      return;
    }

    drawImoveisMarkers(storedData, lastState);
    drawFocos(payload.focos || [], storedData);
    if (lastState && lastState.layers) {
      syncLayers(lastState.layers);
    }
  }

  function setBasemap(mode) {
    if (!mapInstance) return;
    if (currentBaseLayer) mapInstance.removeLayer(currentBaseLayer);
    currentBaseLayer = (mode === 'esri') ? esriLayer : osmLayer;
    mapInstance.addLayer(currentBaseLayer);
    currentBaseLayer.bringToBack();
  }

  function focusFeature(opts) {
    if (!mapInstance || !opts) return;
    if (opts.geojson || opts.rlGeoms) {
      showActiveGeometries(opts.geojson, opts.rlGeoms, true);
      return;
    }
    if (opts.feature) {
      const tmp = L.geoJSON(opts.feature);
      const b = tmp.getBounds();
      if (b.isValid()) {
        mapInstance.fitBounds(b, { padding: [32, 32], maxZoom: 13 });
      }
      return;
    }
    if (typeof opts.lat === 'number' && typeof opts.lon === 'number') {
      mapInstance.setView([opts.lat, opts.lon], opts.zoom || 12);
    }
  }

  function resetZoom() {
    if (!mapInstance || !storedData) return;
    clearActiveGeometries();
    const cfg = storedData.limites_df || { centro: [-15.78, -47.88], zoom: 10 };
    mapInstance.setView(cfg.centro, cfg.zoom);
  }

  window.CFLeafletBridge = {
    mount: mount,
    updateView: updateView,
    setLayersVisible: syncLayers,
    setBasemap: setBasemap,
    focusFeature: focusFeature,
    resetZoom: resetZoom,
    invalidate: invalidateSize,
    destroy: destroyMap
  };

  if (window.document$) {
    window.document$.subscribe(() => {
      if (!document.getElementById('corta-fogo-map')) {
        destroyMap();
      }
    });
  }
})();
