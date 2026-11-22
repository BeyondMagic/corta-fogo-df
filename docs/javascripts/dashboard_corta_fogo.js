/**
 * Dashboard Interativo Corta-Fogo DF (D3.js v7 + d3-geo + ponte Leaflet).
 * Carrega JSONs sob demanda de docs/assets/dados_dashboard/ e sincroniza
 * filtros cruzados entre mapa d3-geo, mapa Leaflet, graficos e tabela CAR.
 */
(function () {
  const INITIAL_SCRIPT_URL = (typeof document !== 'undefined' && document.currentScript && document.currentScript.src)
    ? document.currentScript.src
    : null;
  const ANOS = [2015, 2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025];
  const MESES = ['Jan', 'Fev', 'Mar', 'Abr', 'Mai', 'Jun', 'Jul', 'Ago', 'Set', 'Out', 'Nov', 'Dez'];
  const SENSOR_NOMES = {
    '0': 'VIIRS (375 m)',
    '1': 'MODIS (1.000 m)',
    '2': 'GOES (2.000 m)',
    '3': 'AVHRR / Outros (1.100 m)'
  };
  const SITUACAO_LABELS = {
    AT: 'Ativo',
    PE: 'Pendente',
    SU: 'Suspenso',
    CA: 'Cancelado'
  };

  let dataCachePromise = null;
  let loadedData = null;
  let resizeObserver = null;
  let themeObserver = null;
  let motionMediaQuery = null;
  let playTimer = null;
  let isPlaying = false;

  // Estado da projecao D3 no estagio espacial
  let d3Projection = null;
  let d3Path = null;
  let d3ZoomBehavior = null;
  let d3CurrentTransform = null;
  let projectedFocos = [];
  let currentFiltered = null;
  let currentAgg = null;
  let hoverQuadtree = null;
  let activeFocusIdx = -1;

  const state = {
    // Periodo: ano = inicio ('todos' = serie inteira) e anoFim = fim. Ano unico: ano === anoFim.
    ano: 'todos',
    anoFim: null,
    mes: null,
    estacao: 'todos',
    sensor: 'todos',
    situacao: 'todos',
    raIdx: null,
    ucIdx: null,
    selectedCar: null,
    checkedCars: new Set(),
    checkedInitialized: false,
    defaultTop5Cods: [],
    tab: 'd3geo',
    d3Mode: 'points',
    choroTarget: 'ra',
    choroMetric: 'total',
    anualMode: 'estacao',
    temporalTab: 'anual',
    sensorTab: 'evolucao',
    ucMetric: 'absoluto',
    carSubTab: 'situacao',
    layers: {
      ras: true,
      ucs: true,
      buffers: false,
      imoveis: true,
      rl: true,
      focos: true
    },
    carSearch: '',
    // A tabela abre na ordem da fila de vistoria (posicao 1 = maior prioridade).
    sortCol: 'rank',
    sortDir: 'asc'
  };

  function prefersReducedMotion() {
    return Boolean(window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches);
  }

  function transitionDuration(ms) {
    return prefersReducedMotion() ? 0 : ms;
  }

  function formatInt(n) {
    return Math.round(Number(n || 0)).toLocaleString('pt-BR');
  }

  function formatDec(n, digits) {
    return Number(n || 0).toLocaleString('pt-BR', {
      minimumFractionDigits: digits,
      maximumFractionDigits: digits
    });
  }

  // Codigo CAR curto para leitura (o completo vai no title e na busca).
  function shortCod(cod) {
    const c = String(cod || '');
    return c.length > 24 ? `${c.slice(0, 16)}…${c.slice(-4)}` : c;
  }

  function escapeHtml(text) {
    return String(text == null ? '' : text)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function isDarkScheme() {
    const scheme = document.body ? document.body.getAttribute('data-md-color-scheme') : null;
    if (scheme === 'slate') return true;
    if (scheme === 'default') return false;
    return Boolean(window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches);
  }

  function getTokens() {
    const dark = isDarkScheme();
    return {
      dark: dark,
      text: dark ? '#e6e8eb' : '#111418',
      muted: dark ? '#9aa1ab' : '#5b616b',
      border: dark ? '#2a3039' : '#e3e5e8',
      grid: dark ? 'rgba(255, 255, 255, 0.07)' : 'rgba(17, 20, 24, 0.07)',
      surface: dark ? '#14181e' : '#ffffff',
      surfaceAlt: dark ? '#1a1f26' : '#f6f7f9',
      totalBar: dark ? '#5b616b' : '#a3a9b2',
      // Paleta categorica validada (daltonismo e contraste) nos dois modos.
      seca: dark ? '#d95926' : '#eb6834',
      chuvoso: dark ? '#3987e5' : '#2a78d6',
      ref: dark ? '#e66767' : '#d03b3b',
      otherSensor: dark ? '#5b616b' : '#a3a9b2',
      foco: dark ? '#e66767' : '#d03b3b',
      focoClaro: dark ? 'rgba(230, 103, 103, 0.45)' : 'rgba(208, 59, 59, 0.40)',
      // Intensidade (matriz, hexagonos, coropletico): um matiz so, laranja de fogo.
      // Mais focos = laranja mais forte, nos dois temas. Mesmo par em extra.css.
      seqLow: dark ? '#2b1d16' : '#fdebdf',
      seqHigh: dark ? '#ff9a5c' : '#8a2b0a',
      ucClaro: dark ? '#3d7a3d' : '#8cc98c',
      carForte: dark ? '#c3bcf5' : '#3d2f9e',
      uc: dark ? '#0ca30c' : '#008300',
      ucFill: dark ? 'rgba(12, 163, 12, 0.10)' : 'rgba(0, 131, 0, 0.08)',
      ucBuf: dark ? '#0ca30c' : '#008300',
      car: dark ? '#9085e9' : '#6250d6',
      carSel: dark ? '#ffffff' : '#111418',
      rl: dark ? '#199e70' : '#1baf7a',
      raStroke: dark ? '#4a515c' : '#a3a9b2',
      sensorColors: {
        '0': dark ? '#3987e5' : '#2a78d6',
        '1': dark ? '#d95926' : '#eb6834',
        '2': dark ? '#199e70' : '#1baf7a',
        '3': dark ? '#c98500' : '#eda100'
      },
      // Situacao e identidade de uma unica serie por grafico: uma cor so.
      situacaoColors: {
        AT: dark ? '#9085e9' : '#6250d6',
        PE: dark ? '#9085e9' : '#6250d6',
        SU: dark ? '#9085e9' : '#6250d6',
        CA: dark ? '#9085e9' : '#6250d6'
      }
    };
  }

  function resolveDataBaseUrl() {
    if (INITIAL_SCRIPT_URL) {
      return new URL('../assets/dados_dashboard/', INITIAL_SCRIPT_URL).href;
    }
    const cfgEl = document.getElementById('__config');
    if (cfgEl && cfgEl.textContent) {
      try {
        const cfg = JSON.parse(cfgEl.textContent);
        if (cfg && typeof cfg.base === 'string') {
          const base = cfg.base.replace(/\/+$/, '');
          const rel = (base === '.' || base === '') ? 'assets/dados_dashboard/' : base + '/assets/dados_dashboard/';
          return new URL(rel, window.location.href).href;
        }
      } catch (e) { }
    }
    return '../assets/dados_dashboard/';
  }

  function ringArea2D(ring) {
    if (!ring || ring.length < 4) return 0;
    let a = 0;
    for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
      a += (ring[i][0] * ring[j][1]) - (ring[j][0] * ring[i][1]);
    }
    return a / 2;
  }

  function normalizePolygonRings(rings) {
    if (!Array.isArray(rings) || rings.length === 0) return null;
    const ext = rings[0];
    if (Math.abs(ringArea2D(ext)) < 1e-12) return null;
    const out = [];
    for (let idx = 0; idx < rings.length; idx += 1) {
      const r = rings[idx];
      if (Math.abs(ringArea2D(r)) < 1e-12) continue;
      const area = d3.geoArea({ type: 'Polygon', coordinates: [r] });
      const needFlip = (idx === 0) ? (area > 2 * Math.PI) : (area <= 2 * Math.PI);
      out.push(needFlip ? r.slice().reverse() : r);
    }
    return out.length > 0 ? out : null;
  }

  function rewindGeometry(geom) {
    if (!geom || typeof d3 === 'undefined') return geom;
    if (geom.type === 'Polygon') {
      const norm = normalizePolygonRings(geom.coordinates);
      return norm ? { type: 'Polygon', coordinates: norm } : null;
    }
    if (geom.type === 'MultiPolygon') {
      const polys = [];
      for (let i = 0; i < geom.coordinates.length; i += 1) {
        const norm = normalizePolygonRings(geom.coordinates[i]);
        if (norm) polys.push(norm);
      }
      return polys.length > 0 ? { type: 'MultiPolygon', coordinates: polys } : null;
    }
    return geom;
  }

  function rewindFeature(feat) {
    if (!feat || !feat.geometry || typeof d3 === 'undefined') return feat;
    const g = rewindGeometry(feat.geometry);
    if (!g) return null;
    return {
      type: 'Feature',
      properties: feat.properties,
      geometry: g
    };
  }

  // Normaliza aneis de cada poligono individualmente (remove aneis degenerados e evita inversao global)
  function rewindFeatureCollection(fc) {
    if (!fc || typeof d3 === 'undefined') return fc;
    return {
      type: 'FeatureCollection',
      features: (fc.features || []).map(rewindFeature).filter(Boolean)
    };
  }

  // Indice espacial em memoria: mapeia cada foco aos cod_imovel da fila Top 50 que o contem.
  function ringContainsPoint(lon, lat, ring) {
    let inside = false;
    for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
      const xi = ring[i][0];
      const yi = ring[i][1];
      const xj = ring[j][0];
      const yj = ring[j][1];
      if (((yi > lat) !== (yj > lat)) && (lon < ((xj - xi) * (lat - yi)) / ((yj - yi) || 1e-12) + xi)) {
        inside = !inside;
      }
    }
    return inside;
  }

  function polyContainsPoint(lon, lat, rings) {
    if (!rings || !rings.length || !ringContainsPoint(lon, lat, rings[0])) return false;
    for (let h = 1; h < rings.length; h += 1) {
      if (ringContainsPoint(lon, lat, rings[h])) return false;
    }
    return true;
  }

  function geomContainsPoint(lon, lat, geom) {
    if (!geom) return false;
    if (geom.type === 'Polygon') return polyContainsPoint(lon, lat, geom.coordinates);
    if (geom.type === 'MultiPolygon') {
      for (let p = 0; p < geom.coordinates.length; p += 1) {
        if (polyContainsPoint(lon, lat, geom.coordinates[p])) return true;
      }
    }
    return false;
  }

  function expandBboxRing(ring, bbox) {
    for (let i = 0; i < ring.length; i += 1) {
      const x = ring[i][0];
      const y = ring[i][1];
      if (x < bbox[0]) bbox[0] = x;
      if (y < bbox[1]) bbox[1] = y;
      if (x > bbox[2]) bbox[2] = x;
      if (y > bbox[3]) bbox[3] = y;
    }
  }

  function buildFocoCarsIndex(focos, carTop50, carGeoms) {
    const cars = (carTop50 || []).map((im) => {
      const geom = carGeoms && carGeoms[im.cod_imovel] ? carGeoms[im.cod_imovel].imovel : null;
      const bbox = [Infinity, Infinity, -Infinity, -Infinity];
      if (geom) {
        if (geom.type === 'Polygon') geom.coordinates.forEach((r) => expandBboxRing(r, bbox));
        else if (geom.type === 'MultiPolygon') geom.coordinates.forEach((p) => p.forEach((r) => expandBboxRing(r, bbox)));
      }
      return { cod: im.cod_imovel, geom: geom, bbox: bbox };
    }).filter((c) => c.geom);

    const result = new Array(focos.length);
    for (let i = 0; i < focos.length; i += 1) {
      const f = focos[i];
      const lat = f[0];
      const lon = f[1];
      let matched = null;
      for (let c = 0; c < cars.length; c += 1) {
        const car = cars[c];
        const b = car.bbox;
        if (lon < b[0] || lon > b[2] || lat < b[1] || lat > b[3]) continue;
        if (geomContainsPoint(lon, lat, car.geom)) {
          if (!matched) matched = [];
          matched.push(car.cod);
        }
      }
      result[i] = matched;
    }
    return result;
  }

  function loadAllData() {
    if (dataCachePromise) return dataCachePromise;
    const base = resolveDataBaseUrl();
    dataCachePromise = Promise.all([
      fetch(base + 'resumo.json').then((r) => {
        if (!r.ok) throw new Error('Falha ao carregar resumo.json (' + r.status + ')');
        return r.json();
      }),
      fetch(base + 'geometrias.json').then((r) => {
        if (!r.ok) throw new Error('Falha ao carregar geometrias.json (' + r.status + ')');
        return r.json();
      }),
      fetch(base + 'focos.json').then((r) => {
        if (!r.ok) throw new Error('Falha ao carregar focos.json (' + r.status + ')');
        return r.json();
      }),
      fetch(base + 'gold.json').then((r) => {
        if (!r.ok) throw new Error('Falha ao carregar gold.json (' + r.status + ')');
        return r.json();
      })
    ]).then(([resumo, geometrias, focosRaw, gold]) => {
      // Tudo sobre imoveis reincidentes vem da camada Gold (gold.json, exportado de
      // gold.painel_imoveis_prioritarios). O painel nao recalcula o cruzamento.
      resumo.gold_referencia = gold.gold_referencia;
      resumo.car_cruzamento = gold.car_cruzamento;
      resumo.car_top50 = gold.car_top50;
      resumo.gold_meta = {
        fonte: gold.fonte,
        gerado_em: gold.gerado_em,
        exportado_em: gold.exportado_em,
        sla_frescor_horas: gold.sla_frescor_horas,
        indice: gold.indice
      };
      geometrias.car_top50_geoms = gold.car_top50_geoms;

      const extraMap = new Map();
      const extraObj = focosRaw.uc_extra || {};
      Object.keys(extraObj).forEach((k) => {
        extraMap.set(Number(k), extraObj[k]);
      });

      const limiteDf = rewindFeatureCollection(geometrias.limite_df);
      const rasGeo = rewindFeatureCollection(geometrias.ras);
      const ucsGeo = rewindFeatureCollection(geometrias.ucs);
      const buffersGeo = rewindFeatureCollection(geometrias.buffers);

      const ucsByIdx = new Map();
      (resumo.ucs_resumo || []).forEach((u) => ucsByIdx.set(u.idx, u));
      const rasByIdx = new Map();
      (resumo.ras_resumo || []).forEach((r) => rasByIdx.set(r.idx, r));
      const carByCod = new Map();
      (resumo.car_top50 || []).forEach((c) => carByCod.set(c.cod_imovel, c));

      const focosList = focosRaw.focos || [];
      let baseSeca = 0;
      let baseUc = 0;
      let baseRef = 0;
      for (let i = 0; i < focosList.length; i += 1) {
        const fl = focosList[i];
        if (fl[6] === 1) baseSeca += 1;
        if (fl[5] === 1) baseRef += 1;
        if ((fl[12] & 4) || (fl[12] & 8)) baseUc += 1;
      }
      const baseN = Math.max(1, focosList.length);
      const baselines = {
        secaPct: (baseSeca / baseN) * 100,
        ucPct: (baseUc / baseN) * 100,
        refPct: (baseRef / baseN) * 100
      };

      const focoCars = buildFocoCarsIndex(focosList, resumo.car_top50, geometrias.car_top50_geoms);
      state.defaultTop5Cods = (resumo.car_top50 || [])
        .slice()
        .sort((a, b) => a.rank - b.rank)
        .slice(0, 5)
        .map((im) => im.cod_imovel);
      if (!state.checkedInitialized) {
        state.checkedCars = new Set(state.defaultTop5Cods);
        state.checkedInitialized = true;
      }

      loadedData = {
        resumo: resumo,
        geometrias: geometrias,
        limiteDf: limiteDf,
        rasGeo: rasGeo,
        ucsGeo: ucsGeo,
        buffersGeo: buffersGeo,
        focos: focosList,
        baselines: baselines,
        focoCars: focoCars,
        extraMap: extraMap,
        ucsByIdx: ucsByIdx,
        rasByIdx: rasByIdx,
        carByCod: carByCod,
        leafletBundle: {
          limites_df: geometrias.limites_df,
          rasGeo: geometrias.ras,
          ucsGeo: geometrias.ucs,
          buffersGeo: geometrias.buffers,
          carTop50: resumo.car_top50,
          carTop50Geoms: geometrias.car_top50_geoms,
          metadataSensores: resumo.metadata_sensores
        }
      };
      return loadedData;
    }).catch((err) => {
      dataCachePromise = null;
      throw err;
    });
    return dataCachePromise;
  }

  function showTooltip(html, clientX, clientY) {
    const tip = document.getElementById('cf-floating-tooltip');
    if (!tip) return;
    tip.innerHTML = html;
    tip.hidden = false;

    const pad = 14;
    const rect = tip.getBoundingClientRect();
    let left = clientX + pad;
    let top = clientY + pad;

    if (left + rect.width > window.innerWidth - 10) {
      left = Math.max(10, clientX - rect.width - pad);
    }
    if (top + rect.height > window.innerHeight - 10) {
      top = Math.max(10, clientY - rect.height - pad);
    }
    tip.style.left = left + 'px';
    tip.style.top = top + 'px';
  }

  function hideTooltip() {
    const tip = document.getElementById('cf-floating-tooltip');
    if (tip) tip.hidden = true;
  }

  function announceStatus(msg) {
    const el = document.getElementById('cf-live-status');
    if (el) el.textContent = msg;
  }

  // Filtragem unica de 38.945 registros com agregacoes para todos os graficos
  const ANO_MIN = 2015;
  const ANO_MAX = 2025;

  // O ano esta no periodo filtrado? Sem filtro de ano, todos estao.
  function anoNoFiltro(ano) {
    if (state.ano === 'todos') return true;
    return ano >= state.ano && ano <= state.anoFim;
  }

  // Ano do filtro quando o periodo e um ano so; null quando e 'todos' ou um intervalo.
  function anoUnico() {
    return (state.ano !== 'todos' && state.ano === state.anoFim) ? state.ano : null;
  }

  // Imovel da fila com foco em algum ano do periodo.
  function imovelNoPeriodo(im) {
    if (state.ano === 'todos') return true;
    return Boolean(im.anos && im.anos.some(anoNoFiltro));
  }

  function filterAndAggregate() {
    if (!loadedData) return;
    const focos = loadedData.focos;
    const extraMap = loadedData.extraMap;
    const hasYear = state.ano !== 'todos';
    const hasMonth = state.mes !== null;
    const targetMonth = hasMonth ? Number(state.mes) : null;
    const hasRa = state.raIdx !== null;
    const targetRa = hasRa ? Number(state.raIdx) : null;
    const hasUc = state.ucIdx !== null;
    const targetUc = hasUc ? Number(state.ucIdx) : null;
    const hasCheckedCars = state.checkedCars.size > 0;
    const focoCars = loadedData.focoCars;

    const filteredIndices = [];
    const filteredFocos = [];

    // Agregadores considerando filtros nao temporais para manter contexto nas barras anuais/mensais
    const byYearAll = Array.from({ length: 11 }, (_, idx) => ({
      ano: 2015 + idx,
      total: 0,
      seca: 0,
      chuvoso: 0,
      ref: 0,
      secSensor: 0,
      sensores: [0, 0, 0, 0]
    }));
    const byMonth = Array.from({ length: 12 }, (_, idx) => ({
      mes: idx + 1,
      nome: MESES[idx],
      total: 0,
      ref: 0,
      seca: idx >= 4 && idx <= 8
    }));
    const heatmapMatrix = Array.from({ length: 11 }, () => new Array(12).fill(0));
    const byHour = Array.from({ length: 24 }, (_, h) => ({ hora: h, total: 0, seca: 0, ref: 0 }));
    const riscoBins = Array.from({ length: 10 }, (_, b) => ({
      faixa: `${b * 10}-${b === 9 ? 100 : (b + 1) * 10}`,
      min: b * 10,
      count: 0,
      ref: 0
    }));
    let riscoComValor = 0;

    const raTotals = new Array(loadedData.resumo.ras_resumo.length).fill(0);
    const ucInTotals = new Array(loadedData.resumo.ucs_resumo.length).fill(0);
    const ucBufTotals = new Array(loadedData.resumo.ucs_resumo.length).fill(0);

    let totalSeca = 0;
    let totalRef = 0;
    let totalCar = 0;
    let totalRl = 0;
    let totalUcArea = 0;

    for (let i = 0; i < focos.length; i += 1) {
      const f = focos[i];
      // [0:lat, 1:lon, 2:ano, 3:mes, 4:hora, 5:ref, 6:seca, 7:sensor, 8:risco, 9:ra, 10:uc_in, 11:uc_buf, 12:flags]
      const ano = f[2];
      const mes = f[3];
      const hora = f[4];
      const isRef = f[5] === 1;
      const isSeca = f[6] === 1;
      const sensor = f[7];
      const risco = f[8];
      const ra = f[9];
      const ucIn = f[10];
      const ucBuf = f[11];
      const flags = f[12];

      if (state.estacao === 'seca' && !isSeca) continue;
      if (state.estacao === 'chuvoso' && isSeca) continue;
      if (state.sensor === 'ref' && !isRef) continue;
      if (state.sensor !== 'todos' && state.sensor !== 'ref' && String(sensor) !== state.sensor) continue;
      if (hasRa && ra !== targetRa) continue;

      if (hasCheckedCars) {
        const cars = focoCars ? focoCars[i] : null;
        if (!cars) continue;
        let hitCar = false;
        for (let c = 0; c < cars.length; c += 1) {
          const cod = cars[c];
          if (!state.checkedCars.has(cod)) continue;
          if (state.situacao !== 'todos') {
            const imObj = loadedData.carByCod.get(cod);
            if (imObj && imObj.situacao !== state.situacao) continue;
          }
          hitCar = true;
          break;
        }
        if (!hitCar) continue;
      }

      if (hasUc) {
        let matchUc = false;
        if (extraMap.has(i)) {
          const ex = extraMap.get(i);
          matchUc = ex[0].includes(targetUc) || ex[1].includes(targetUc);
        } else {
          matchUc = (ucIn === targetUc || ucBuf === targetUc);
        }
        if (!matchUc) continue;
      }

      // Serie anual e heatmap preservam visibilidade de todos os anos para permitir clique
      const yIdx = ano - 2015;
      const mIdx = mes - 1;
      if ((!hasMonth || mes === targetMonth) && yIdx >= 0 && yIdx < 11) {
        const slot = byYearAll[yIdx];
        slot.total += 1;
        if (isSeca) slot.seca += 1;
        else slot.chuvoso += 1;
        if (isRef) slot.ref += 1;
        else slot.secSensor += 1;
        if (sensor >= 0 && sensor <= 3) slot.sensores[sensor] += 1;
      }
      if (yIdx >= 0 && yIdx < 11 && mIdx >= 0 && mIdx < 12) {
        heatmapMatrix[yIdx][mIdx] += 1;
      }

      if (hasYear && !anoNoFiltro(ano)) continue;
      if (hasMonth && mes !== targetMonth) continue;

      filteredIndices.push(i);
      filteredFocos.push(f);

      if (isSeca) totalSeca += 1;
      if (isRef) totalRef += 1;
      if (flags & 1) totalCar += 1;
      if (flags & 2) totalRl += 1;
      if ((flags & 4) || (flags & 8)) totalUcArea += 1;

      if (mIdx >= 0 && mIdx < 12) {
        byMonth[mIdx].total += 1;
        if (isRef) byMonth[mIdx].ref += 1;
      }
      if (hora >= 0 && hora < 24) {
        byHour[hora].total += 1;
        if (isSeca) byHour[hora].seca += 1;
        if (isRef) byHour[hora].ref += 1;
      }
      if (risco >= 0) {
        const binIdx = Math.min(9, Math.floor(risco / 10));
        riscoBins[binIdx].count += 1;
        if (isRef) riscoBins[binIdx].ref += 1;
        riscoComValor += 1;
      }

      if (ra >= 0 && ra < raTotals.length) {
        raTotals[ra] += 1;
      }
      if (extraMap.has(i)) {
        const ex = extraMap.get(i);
        for (let k = 0; k < ex[0].length; k += 1) ucInTotals[ex[0][k]] += 1;
        for (let k = 0; k < ex[1].length; k += 1) ucBufTotals[ex[1][k]] += 1;
      } else {
        if (ucIn >= 0 && ucIn < ucInTotals.length) ucInTotals[ucIn] += 1;
        if (ucBuf >= 0 && ucBuf < ucBufTotals.length) ucBufTotals[ucBuf] += 1;
      }
    }

    currentFiltered = {
      indices: filteredIndices,
      focos: filteredFocos
    };
    currentAgg = {
      total: filteredFocos.length,
      totalSeca: totalSeca,
      totalRef: totalRef,
      totalCar: totalCar,
      totalRl: totalRl,
      totalUcArea: totalUcArea,
      byYearAll: byYearAll,
      byMonth: byMonth,
      heatmapMatrix: heatmapMatrix,
      byHour: byHour,
      riscoBins: riscoBins,
      riscoComValor: riscoComValor,
      raTotals: raTotals,
      ucInTotals: ucInTotals,
      ucBufTotals: ucBufTotals
    };
  }

  function setComparator(elId, text, tone) {
    const el = document.getElementById(elId);
    if (!el) return;
    el.className = 'cf-kpi-cmp' + (tone ? ' is-' + tone : '');
    el.textContent = text;
  }

  function updateKPIs() {
    if (!loadedData || !currentAgg) return;
    const total = currentAgg.total;
    const totalGlobal = loadedData.resumo.escopo.total_focos || 38945;
    const base = loadedData.baselines || { secaPct: 84.3, ucPct: 47.0, refPct: 6.0 };

    const kpiFocos = document.getElementById('cf-kpi-focos');
    const kpiFocosSub = document.getElementById('cf-kpi-focos-sub');
    if (kpiFocos) kpiFocos.textContent = formatInt(total);
    const pctGlobal = totalGlobal > 0 ? (total / totalGlobal) * 100 : 0;
    if (kpiFocosSub) {
      kpiFocosSub.textContent = state.checkedCars.size > 0
        ? `nos ${state.checkedCars.size} imóveis marcados da fila`
        : 'em todo o Distrito Federal';
    }
    setComparator(
      'cf-kpi-focos-cmp',
      state.checkedCars.size > 0 || total < totalGlobal
        ? `${formatDec(pctGlobal, 1)}% do total DF (${formatInt(totalGlobal)})`
        : '100% da série histórica DF',
      ''
    );

    const kpiSeca = document.getElementById('cf-kpi-seca');
    const kpiSecaSub = document.getElementById('cf-kpi-seca-sub');
    const pctSeca = total > 0 ? (currentAgg.totalSeca / total) * 100 : 0;
    if (kpiSeca) kpiSeca.textContent = `${formatDec(pctSeca, 1)}%`;
    if (kpiSecaSub) kpiSecaSub.textContent = `${formatInt(currentAgg.totalSeca)} focos entre mai e set`;
    if (total === 0) {
      setComparator('cf-kpi-seca-cmp', 'Sem focos no recorte', '');
    } else {
      const diffSeca = pctSeca - base.secaPct;
      const arrow = diffSeca >= 0 ? '▲' : '▼';
      const tone = diffSeca > 2 ? 'crit' : (diffSeca < -2 ? 'good' : '');
      setComparator('cf-kpi-seca-cmp', `${arrow} ${diffSeca >= 0 ? '+' : ''}${formatDec(diffSeca, 1)} p.p. vs DF (${formatDec(base.secaPct, 1)}%)`, tone);
    }

    const kpiUcs = document.getElementById('cf-kpi-ucs');
    const kpiUcsSub = document.getElementById('cf-kpi-ucs-sub');
    let ucsAtingidas = 0;
    for (let i = 0; i < currentAgg.ucInTotals.length; i += 1) {
      if (currentAgg.ucInTotals[i] > 0 || currentAgg.ucBufTotals[i] > 0) ucsAtingidas += 1;
    }
    const pctUc = total > 0 ? (currentAgg.totalUcArea / total) * 100 : 0;
    if (kpiUcs) kpiUcs.textContent = formatInt(currentAgg.totalUcArea);
    if (kpiUcsSub) kpiUcsSub.textContent = `${formatDec(pctUc, 1)}% do recorte em ${ucsAtingidas} de 84 UCs`;
    if (total === 0) {
      setComparator('cf-kpi-ucs-cmp', 'Sem focos no recorte', '');
    } else {
      const diffUc = pctUc - base.ucPct;
      const arrow = diffUc >= 0 ? '▲' : '▼';
      const tone = diffUc > 5 ? 'crit' : (diffUc > 0 ? 'warn' : 'good');
      setComparator('cf-kpi-ucs-cmp', `${arrow} ${diffUc >= 0 ? '+' : ''}${formatDec(diffUc, 1)} p.p. vs DF (${formatDec(base.ucPct, 1)}%)`, tone);
    }

    const kpiRef = document.getElementById('cf-kpi-ref');
    const kpiRefSub = document.getElementById('cf-kpi-ref-sub');
    const pctRef = total > 0 ? (currentAgg.totalRef / total) * 100 : 0;
    if (kpiRef) kpiRef.textContent = `${formatDec(pctRef, 1)}%`;
    if (kpiRefSub) kpiRefSub.textContent = `${formatInt(currentAgg.totalRef)} detecções do satélite de referência`;
    if (total === 0) {
      setComparator('cf-kpi-ref-cmp', 'Sem focos no recorte', '');
    } else {
      const diffRef = pctRef - base.refPct;
      setComparator('cf-kpi-ref-cmp', `Base DF: ${formatDec(base.refPct, 1)}% (${diffRef >= 0 ? '+' : ''}${formatDec(diffRef, 1)} p.p.)`, '');
    }

    updateNarrative(total, pctSeca, pctUc, ucsAtingidas, base);
  }

  function updateNarrative(total, pctSeca, pctUc, ucsAtingidas, base) {
    const el = document.getElementById('cf-narrative');
    if (!el || !loadedData) return;

    if (total === 0) {
      el.textContent = 'Nenhum foco encontrado para os filtros atuais. Remova algum filtro ou desmarque imóveis para ampliar o recorte.';
      return;
    }

    const escopoDesc = state.checkedCars.size > 0
      ? (isTop5Selection()
        ? 'nos 5 primeiros imóveis da fila de vistoria (padrão)'
        : `nos ${state.checkedCars.size} imóveis marcados da fila`)
      : 'em todo o Distrito Federal';

    const diffSeca = pctSeca - base.secaPct;
    const diffUc = pctUc - base.ucPct;
    const secaTxt = Math.abs(diffSeca) < 1
      ? `${formatDec(pctSeca, 1)}% na estiagem (próximo à média do DF)`
      : `${formatDec(pctSeca, 1)}% na estiagem (${diffSeca > 0 ? '+' : ''}${formatDec(diffSeca, 1)} p.p. vs média DF)`;
    const ucTxt = `${formatDec(pctUc, 1)}% dentro ou a até 1 km de ${ucsAtingidas} UCs (${diffUc >= 0 ? '+' : ''}${formatDec(diffUc, 1)} p.p. vs DF)`;

    el.innerHTML = `Recorte ativo: <b>${formatInt(total)}</b> focos ${escopoDesc}, sendo ${secaTxt} e ${ucTxt}.`;
  }

  const CLASSIFICACAO_LABELS = {
    'PRIORIDADE CRITICA': 'Crítica',
    'PRIORIDADE ALTA': 'Alta',
    'PRIORIDADE MEDIA': 'Média',
    'PRIORIDADE BAIXA': 'Baixa'
  };

  // Bloco de abertura compacto: resumo dos imóveis reincidentes (a fila acionável fica ao lado do mapa).
  function renderResposta() {
    const box = document.getElementById('cf-resposta-corpo');
    if (!box || !loadedData) return;

    const ref = loadedData.resumo.gold_referencia;
    const cruz = loadedData.resumo.car_cruzamento || {};
    const porClasse = cruz.por_classificacao || {};
    const criticos = porClasse['PRIORIDADE CRITICA'] || { imoveis: 0, cadastro_ativo: 0 };

    box.innerHTML = `
      <div class="cf-gold-inline">
        <span class="cf-gold-inline-item"><strong>${formatInt(ref.imoveis_reincidentes)}</strong><span>reincidentes</span></span>
        <span class="cf-gold-inline-item cf-gold-inline-item--accent"><strong>${formatInt(criticos.imoveis)}</strong><span>prioridade crítica</span></span>
        <span class="cf-gold-inline-item"><strong>${formatInt(criticos.cadastro_ativo)}</strong><span>críticos ativos</span></span>
      </div>`;
  }

  function renderFilterChips() {
    const wrap = document.getElementById('cf-active-chips');
    if (!wrap || !loadedData) return;

    const chips = [];
    if (state.ano !== 'todos') {
      chips.push({ key: 'ano', label: anoUnico() !== null ? `Ano: ${state.ano}` : `Anos: ${state.ano}–${state.anoFim}` });
    }
    if (state.mes !== null) {
      chips.push({ key: 'mes', label: `Mês: ${MESES[state.mes - 1]}` });
    }
    if (state.estacao !== 'todos') {
      chips.push({ key: 'estacao', label: state.estacao === 'seca' ? 'Estação: Estiagem (Mai-Set)' : 'Estação: Chuvoso' });
    }
    if (state.sensor !== 'todos') {
      const sLabel = state.sensor === 'ref' ? 'Satélite de referência' : SENSOR_NOMES[state.sensor];
      chips.push({ key: 'sensor', label: `Sensor: ${sLabel}` });
    }
    if (state.situacao !== 'todos') {
      chips.push({ key: 'situacao', label: `Cadastro: ${SITUACAO_LABELS[state.situacao] || state.situacao}` });
    }
    if (state.raIdx !== null) {
      const ra = loadedData.rasByIdx.get(state.raIdx);
      chips.push({ key: 'raIdx', label: `RA: ${ra ? ra.nome : state.raIdx}` });
    }
    if (state.ucIdx !== null) {
      const uc = loadedData.ucsByIdx.get(state.ucIdx);
      chips.push({ key: 'ucIdx', label: `UC: ${uc ? (uc.sigla || uc.nome) : state.ucIdx}` });
    }
    if (state.selectedCar) {
      chips.push({ key: 'selectedCar', label: `Imóvel selecionado: ${state.selectedCar.slice(0, 18)}...` });
    }
    if (state.checkedCars.size > 0) {
      let chkLabel = `Imóveis marcados: ${state.checkedCars.size}`;
      if (isTop5Selection()) chkLabel = 'Imóveis da fila: Top 5 (padrão)';
      else if (state.checkedCars.size === (loadedData.resumo.car_top50 || []).length) chkLabel = 'Imóveis da fila: Todos (50)';
      chips.push({ key: 'checkedCars', label: chkLabel });
    }

    if (chips.length === 0) {
      wrap.innerHTML = '<span class="cf-chip-empty">Série completa ativa: 2015–2025, 37 RAs, 84 UCs e todos os 38.945 focos do DF.</span>';
      return;
    }

    wrap.innerHTML = chips.map((c) => (
      `<button type="button" class="cf-filter-chip" data-clear="${c.key}" title="Remover filtro ${escapeHtml(c.label)}">` +
      `<span>${escapeHtml(c.label)}</span>` +
      `<span aria-hidden="true" class="cf-chip-x">&times;</span>` +
      `</button>`
    )).join('');

    wrap.querySelectorAll('.cf-filter-chip').forEach((btn) => {
      btn.addEventListener('click', function () {
        const key = this.getAttribute('data-clear');
        if (key === 'ano') setYearFilter('todos', false);
        else if (key === 'mes') state.mes = null;
        else if (key === 'estacao') state.estacao = 'todos';
        else if (key === 'sensor') state.sensor = 'todos';
        else if (key === 'situacao') state.situacao = 'todos';
        else if (key === 'raIdx') state.raIdx = null;
        else if (key === 'ucIdx') state.ucIdx = null;
        else if (key === 'selectedCar') state.selectedCar = null;
        else if (key === 'checkedCars') state.checkedCars.clear();
        syncControlsFromState();
        refreshAll(true);
      });
    });
  }

  function syncControlsFromState() {
    const isAll = state.ano === 'todos';
    // Bolinha e selo: num periodo, a bolinha fica no ultimo ano e o selo mostra o intervalo.
    const slider = document.getElementById('cf-ano-slider');
    const badge = document.getElementById('cf-ano-badge');
    if (slider) slider.value = isAll ? '2026' : String(state.anoFim);
    if (badge) {
      badge.textContent = isAll
        ? '2015 a 2025 (Todos)'
        : (anoUnico() !== null ? String(state.ano) : `${state.ano} a ${state.anoFim}`);
    }
    const selDe = document.getElementById('cf-ano-de');
    const selAte = document.getElementById('cf-ano-ate');
    if (selDe) selDe.value = isAll ? String(ANO_MIN) : String(state.ano);
    if (selAte) selAte.value = isAll ? String(ANO_MAX) : String(state.anoFim);

    const selEst = document.getElementById('cf-filter-estacao');
    if (selEst) selEst.value = state.estacao;
    const selSen = document.getElementById('cf-filter-sensor');
    if (selSen) selSen.value = state.sensor;
    const selSit = document.getElementById('cf-filter-situacao');
    if (selSit) selSit.value = state.situacao;

    // Lista de RAs: preenchida uma vez, quando os dados chegam; segue state.raIdx,
    // que tambem muda ao clicar numa RA no mapa ou no ranking.
    const selRa = document.getElementById('cf-filter-ra');
    if (selRa && loadedData) {
      if (selRa.options.length <= 1) {
        loadedData.resumo.ras_resumo
          .slice()
          .sort((a, b) => a.nome.localeCompare(b.nome, 'pt-BR'))
          .forEach((r) => selRa.add(new Option(r.nome, String(r.idx))));
      }
      selRa.value = state.raIdx === null ? 'todos' : String(state.raIdx);
    }

    document.querySelectorAll('#cf-d3-mode-group button[data-mode]').forEach((btn) => {
      const active = btn.getAttribute('data-mode') === state.d3Mode;
      btn.classList.toggle('is-active', active);
      btn.setAttribute('aria-pressed', active ? 'true' : 'false');
    });

    const choroControls = document.getElementById('cf-choro-controls');
    if (choroControls) choroControls.hidden = (state.d3Mode !== 'choropleth');

    const choroTarget = document.getElementById('cf-choro-target');
    if (choroTarget) choroTarget.value = state.choroTarget;
    const choroMetric = document.getElementById('cf-choro-metric');
    if (choroMetric) choroMetric.value = state.choroMetric;

    const advBtn = document.getElementById('cf-btn-adv-filters');
    if (advBtn) {
      let advCount = 0;
      if (state.sensor !== 'todos') advCount += 1;
      if (state.situacao !== 'todos') advCount += 1;
      if (isPlaying || anoUnico() !== null) advCount += 1;
      advBtn.textContent = advCount > 0 ? `Filtros avançados (${advCount})` : 'Filtros avançados';
    }

    const layersBtn = document.getElementById('cf-btn-layers');
    if (layersBtn) {
      const ativos = Object.values(state.layers).filter(Boolean).length;
      layersBtn.textContent = `Camadas (${ativos}/6)`;
    }
  }

  // Um ano so (anoFimVal omitido) ou um periodo. De ANO_MIN a ANO_MAX equivale a 'todos'.
  function setYearFilter(anoVal, fromPlayback, anoFimVal) {
    if (!fromPlayback && isPlaying) stopPlayback();
    if (anoVal === 'todos' || Number(anoVal) === 2026) {
      state.ano = 'todos';
      state.anoFim = null;
    } else {
      let ini = Number(anoVal);
      let fim = (anoFimVal === undefined || anoFimVal === null) ? ini : Number(anoFimVal);
      if (fim < ini) { const t = ini; ini = fim; fim = t; }
      if (ini <= ANO_MIN && fim >= ANO_MAX) {
        state.ano = 'todos';
        state.anoFim = null;
      } else {
        state.ano = ini;
        state.anoFim = fim;
      }
    }
    syncControlsFromState();
  }

  function updateInspector(info) {
    const box = document.getElementById('cf-inspector-box');
    if (!box || !loadedData) return;

    if (!info) {
      if (state.selectedCar && loadedData.carByCod.has(state.selectedCar)) {
        const im = loadedData.carByCod.get(state.selectedCar);
        box.hidden = false;
        box.innerHTML = renderCarInspectorHtml(im);
        bindInspectorClear(box);
        return;
      }
      if (state.ucIdx !== null && loadedData.ucsByIdx.has(state.ucIdx)) {
        const uc = loadedData.ucsByIdx.get(state.ucIdx);
        box.hidden = false;
        box.innerHTML = renderUcInspectorHtml(uc);
        bindInspectorClear(box);
        return;
      }
      if (state.raIdx !== null && loadedData.rasByIdx.has(state.raIdx)) {
        const ra = loadedData.rasByIdx.get(state.raIdx);
        box.hidden = false;
        box.innerHTML = renderRaInspectorHtml(ra);
        bindInspectorClear(box);
        return;
      }

      box.hidden = true;
      box.innerHTML = '';
      return;
    }

    box.hidden = false;
    box.innerHTML = info;
    bindInspectorClear(box);
  }

  function bindInspectorClear(box) {
    const btn = box.querySelector('[data-action="clear-selection"]');
    if (btn) {
      btn.addEventListener('click', function () {
        state.raIdx = null;
        state.ucIdx = null;
        state.selectedCar = null;
        resetMapZoom();
        syncControlsFromState();
        refreshAll(true);
      });
    }
  }

  function renderRaInspectorHtml(ra) {
    const filteredCount = currentAgg ? currentAgg.raTotals[ra.idx] : ra.total;
    const dens = ra.area_km2 > 0 ? (filteredCount / ra.area_km2) * 100 : 0;
    return `
      <div class="cf-inspector-card">
        <div class="cf-inspector-head">
          <span class="cf-badge cf-badge-ra">${escapeHtml(ra.codigo)}</span>
          <button type="button" class="cf-btn-mini" data-action="clear-selection">Limpar foco</button>
        </div>
        <h4>${escapeHtml(ra.nome)}</h4>
        <dl class="cf-kv-list">
          <div><dt>Focos no filtro</dt><dd>${formatInt(filteredCount)}</dd></div>
          <div><dt>Série 2015–2025</dt><dd>${formatInt(ra.total)}</dd></div>
          <div><dt>Área oficial</dt><dd>${formatDec(ra.area_km2, 1)} km²</dd></div>
          <div><dt>Densidade</dt><dd>${formatDec(dens, 1)} focos/100 km²</dd></div>
        </dl>
      </div>
    `;
  }

  function renderUcInspectorHtml(uc) {
    const inCount = currentAgg ? currentAgg.ucInTotals[uc.idx] : uc.dentro;
    const bufCount = currentAgg ? currentAgg.ucBufTotals[uc.idx] : uc.buffer_1km;
    return `
      <div class="cf-inspector-card">
        <div class="cf-inspector-head">
          <span class="cf-badge cf-badge-uc">${escapeHtml(uc.grupo)}</span>
          <button type="button" class="cf-btn-mini" data-action="clear-selection">Limpar foco</button>
        </div>
        <h4>${escapeHtml(uc.nome)}</h4>
        <dl class="cf-kv-list">
          <div><dt>Dentro da UC</dt><dd>${formatInt(inCount)}</dd></div>
          <div><dt>Faixa de 1 km</dt><dd>${formatInt(bufCount)}</dd></div>
          <div><dt>Área oficial</dt><dd>${formatDec(uc.area_ha, 1)} ha</dd></div>
          <div><dt>Gestão / Criação</dt><dd>${escapeHtml(uc.gestao)} (${escapeHtml(uc.ano_criacao || 'N/D')})</dd></div>
        </dl>
      </div>
    `;
  }

  // Faixa 2015-2025: cada ano e uma celula, acesa quando houve foco no imovel.
  function renderAnosStrip(anos) {
    const set = new Set((anos || []).map(Number));
    const cells = ANOS.map((a) => `<span class="${set.has(a) ? 'is-on' : ''}" title="${a}: ${set.has(a) ? 'com foco' : 'sem foco'}"></span>`).join('');
    return `
      <div class="cf-anos-strip">
        <div class="cf-anos-strip-head"><span>Anos com foco</span><b>${set.size} de ${ANOS.length}</b></div>
        <div class="cf-anos-strip-cells">${cells}</div>
        <div class="cf-anos-strip-axis"><span>${ANOS[0]}</span><span>${ANOS[ANOS.length - 1]}</span></div>
      </div>`;
  }

  function carTooltipHtml(d) {
    return `<strong>#${d.rank} na fila · ${escapeHtml(d.ra || 'Imóvel rural')}</strong><br/>` +
      `Índice ${formatDec(d.indice, 1)} · ${escapeHtml(SITUACAO_LABELS[d.situacao] || d.situacao)} · ${formatDec(d.area_ha, 1)} ha<br/>` +
      `${formatInt(d.focos_prot)} focos em área protegida em ${d.anos_qtd} anos<br/>` +
      `<code>${escapeHtml(shortCod(d.cod_imovel))}</code>`;
  }

  function renderCarInspectorHtml(im) {
    return `
      <div class="cf-inspector-card cf-car-card">
        <div class="cf-car-card-head">
          <span class="cf-car-card-rank">#${im.rank}</span>
          <div class="cf-car-card-title">
            <h4>${escapeHtml(im.ra || 'Imóvel rural')}</h4>
            <code title="${escapeHtml(im.cod_imovel)}">${escapeHtml(shortCod(im.cod_imovel))}</code>
          </div>
          <button type="button" class="cf-car-card-close" data-action="clear-selection" title="Limpar seleção" aria-label="Limpar seleção">×</button>
        </div>
        <div class="cf-car-card-score">
          <span class="cf-indice-bar" aria-hidden="true"><span style="width:${Math.max(0, Math.min(100, Number(im.indice) || 0))}%"></span></span>
          <b>${formatDec(im.indice, 1)}</b>
          <span class="cf-badge cf-badge-car">${escapeHtml(CLASSIFICACAO_LABELS[im.classificacao] || '-')}</span>
          <span class="cf-badge">${escapeHtml(SITUACAO_LABELS[im.situacao] || im.situacao || '-')}</span>
        </div>
        <div class="cf-car-card-stats">
          <div><span>Focos no imóvel</span><b>${formatInt(im.focos_total)}</b></div>
          <div><span>Em área protegida</span><b>${formatInt(im.focos_prot)}<small>${im.focos_total > 0 ? ` ${formatDec((im.focos_prot / im.focos_total) * 100, 0)}%` : ''}</small></b></div>
          <div><span>Dias com foco</span><b>${formatInt(im.dias_com_foco)}</b></div>
          <div><span>Área do imóvel</span><b>${formatDec(im.area_ha, 0)}<small> ha</small></b></div>
        </div>
        ${renderAnosStrip(im.anos)}
        ${im.condicao ? `<p class="cf-inspector-hint"><span>Condição cadastral</span> ${escapeHtml(im.condicao)}</p>` : ''}
      </div>
    `;
  }

  // Hexbin em coordenadas de tela (sem dependencia de plugin legado d3-hexbin)
  function computeHexbins(points, radiusPx) {
    const dx = radiusPx * 2 * Math.sin(Math.PI / 3);
    const dy = radiusPx * 1.5;
    const binsByKey = new Map();

    for (let i = 0; i < points.length; i += 1) {
      const p = points[i];
      const py = p.y / dy;
      let pj = Math.round(py);
      const px = p.x / dx - (pj & 1) * 0.5;
      let pi = Math.round(px);
      const py1 = py - pj;

      if (Math.abs(py1) * 3 > 1) {
        const px1 = px - pi;
        const pi2 = pi + (px < pi ? -0.5 : 0.5);
        const pj2 = pj + (py < pj ? -1 : 1);
        const px2 = px - pi2;
        const py2 = py - pj2;
        if (px1 * px1 + py1 * py1 > px2 * px2 + py2 * py2) {
          pi = pi2 + (pj & 1 ? 0.5 : -0.5);
          pj = pj2;
        }
      }

      const cx = (pi + (pj & 1) * 0.5) * dx;
      const cy = pj * dy;
      const key = `${Math.round(pi * 2)}:${pj}`;
      let bin = binsByKey.get(key);
      if (!bin) {
        bin = { x: cx, y: cy, count: 0, refCount: 0, secaCount: 0 };
        binsByKey.set(key, bin);
      }
      bin.count += 1;
      if (p.f[5] === 1) bin.refCount += 1;
      if (p.f[6] === 1) bin.secaCount += 1;
    }

    return Array.from(binsByKey.values());
  }

  function hexVertices(cx, cy, r) {
    const pts = [];
    for (let a = 0; a < 6; a += 1) {
      const angle = (Math.PI / 3) * a + Math.PI / 6;
      pts.push([cx + r * Math.cos(angle), cy + r * Math.sin(angle)]);
    }
    return pts;
  }

  function renderD3Map(refitProjection) {
    const stage = document.getElementById('cf-d3-stage');
    const svgEl = document.getElementById('cf-d3-svg');
    const canvasEl = document.getElementById('cf-d3-canvas');
    if (!stage || !svgEl || !canvasEl || !loadedData || typeof d3 === 'undefined') return;

    const width = Math.max(320, stage.clientWidth || 720);
    const height = Math.max(380, stage.clientHeight || 600);
    const tokens = getTokens();

    if (refitProjection || !d3Projection || d3Projection.lastW !== width || d3Projection.lastH !== height) {
      const pad = 20;
      d3Projection = d3.geoMercator().fitExtent(
        [[pad, pad], [width - pad, height - pad]],
        loadedData.limiteDf
      );
      d3Projection.lastW = width;
      d3Projection.lastH = height;
      d3Path = d3.geoPath(d3Projection);

      // Reprojeta focos na nova base de tela
      projectedFocos = loadedData.focos.map((f, idx) => {
        const pt = d3Projection([f[1], f[0]]);
        return { x: pt[0], y: pt[1], f: f, idx: idx };
      });
    }

    const svg = d3.select(svgEl)
      .attr('width', width)
      .attr('height', height)
      .attr('viewBox', `0 0 ${width} ${height}`);

    let zoomGroup = svg.select('g.cf-zoom-root');
    if (zoomGroup.empty()) {
      svg.selectAll('*').remove();
      zoomGroup = svg.append('g').attr('class', 'cf-zoom-root');
      zoomGroup.append('g').attr('class', 'cf-layer-df');
      zoomGroup.append('g').attr('class', 'cf-layer-ras');
      zoomGroup.append('g').attr('class', 'cf-layer-buffers');
      zoomGroup.append('g').attr('class', 'cf-layer-ucs');
      zoomGroup.append('g').attr('class', 'cf-layer-car-sel');
      zoomGroup.append('g').attr('class', 'cf-layer-car-pins');
      d3CurrentTransform = d3.zoomIdentity;

      d3ZoomBehavior = d3.zoom()
        .scaleExtent([0.85, 50])
        .on('zoom', (event) => {
          d3CurrentTransform = event.transform;
          zoomGroup.attr('transform', d3CurrentTransform.toString());
          updateD3StrokeWeights();
          drawD3Canvas();
        });

      svg.call(d3ZoomBehavior);
      svgEl.addEventListener('wheel', function (e) {
        e.preventDefault();
      }, { passive: false });
    }

    const choroActive = (state.d3Mode === 'choropleth');
    const raExtent = d3.max(currentAgg.raTotals) || 1;
    const raDensMax = d3.max(loadedData.resumo.ras_resumo, (r) => {
      const c = currentAgg.raTotals[r.idx] || 0;
      return r.area_km2 > 0 ? (c / r.area_km2) * 100 : 0;
    }) || 1;

    const ucTotVals = loadedData.resumo.ucs_resumo.map((u) => (currentAgg.ucInTotals[u.idx] || 0) + (currentAgg.ucBufTotals[u.idx] || 0));
    const ucMax = d3.max(ucTotVals) || 1;
    const ucDensMax = d3.max(loadedData.resumo.ucs_resumo, (u, idx) => (u.area_ha > 0 ? (ucTotVals[idx] / u.area_ha) * 100 : 0)) || 1;

    const seqInterpolator = d3.interpolateLab(tokens.seqLow, tokens.seqHigh);
    // Escala raiz: poucas RAs concentram muitos focos e, na escala linear, as demais
    // ficavam todas com a mesma cor. A legenda usa a mesma escala (meio = max / 4).
    const raScale = d3.scaleSequentialSqrt(seqInterpolator).domain([0, state.choroMetric === 'densidade' ? raDensMax : raExtent]);
    const ucScale = d3.scaleSequentialSqrt(seqInterpolator).domain([0, state.choroMetric === 'densidade' ? ucDensMax : ucMax]);

    // 1. Limite DF
    zoomGroup.select('g.cf-layer-df')
      .selectAll('path')
      .data(loadedData.limiteDf.features)
      .join('path')
      .attr('d', d3Path)
      .attr('fill', tokens.surfaceAlt)
      .attr('stroke', tokens.border)
      .attr('stroke-width', 1.4)
      .attr('vector-effect', 'non-scaling-stroke');

    // 2. Regioes Administrativas (37)
    const showRas = state.layers.ras || (choroActive && state.choroTarget === 'ra');
    const rasSel = zoomGroup.select('g.cf-layer-ras')
      .attr('display', showRas ? null : 'none')
      .selectAll('path')
      .data(loadedData.rasGeo.features, (d) => d.properties.idx)
      .join('path')
      .attr('d', d3Path)
      .attr('class', 'cf-ra-poly')
      .attr('vector-effect', 'non-scaling-stroke')
      .attr('fill', (d) => {
        const idx = d.properties.idx;
        if (choroActive && state.choroTarget === 'ra') {
          const val = state.choroMetric === 'densidade'
            ? ((d.properties.area_km2 > 0) ? ((currentAgg.raTotals[idx] || 0) / d.properties.area_km2) * 100 : 0)
            : (currentAgg.raTotals[idx] || 0);
          return val > 0 ? raScale(val) : tokens.surfaceAlt;
        }
        return state.raIdx === idx ? 'rgba(234, 88, 12, 0.16)' : 'transparent';
      })
      .attr('fill-opacity', choroActive && state.choroTarget === 'ra' ? 0.85 : 1)
      .attr('stroke', (d) => (state.raIdx === d.properties.idx ? tokens.text : tokens.raStroke))
      .attr('stroke-width', (d) => (state.raIdx === d.properties.idx ? 2.2 : 0.7))
      .attr('stroke-dasharray', null)
      .style('cursor', 'pointer')
      .on('mousemove', function (event, d) {
        const ra = loadedData.rasByIdx.get(d.properties.idx);
        if (!ra) return;
        const val = currentAgg.raTotals[ra.idx] || 0;
        const dens = ra.area_km2 > 0 ? (val / ra.area_km2) * 100 : 0;
        showTooltip(
          `<strong>${escapeHtml(ra.codigo)} · ${escapeHtml(ra.nome)}</strong><br/>` +
          `Focos no filtro: <b>${formatInt(val)}</b><br/>` +
          `Densidade: ${formatDec(dens, 1)} / 100 km²`,
          event.clientX,
          event.clientY
        );
      })
      .on('mouseleave', hideTooltip)
      .on('click', function (event, d) {
        event.stopPropagation();
        const idx = d.properties.idx;
        state.raIdx = (state.raIdx === idx) ? null : idx;
        if (state.raIdx !== null) {
          zoomToFeature(d, 10);
        } else {
          resetMapZoom();
        }
        syncControlsFromState();
        refreshAll(true);
      });
    rasSel.order();

    // 3. Faixas de amortecimento 1 km
    zoomGroup.select('g.cf-layer-buffers')
      .attr('display', state.layers.buffers ? null : 'none')
      .selectAll('path')
      .data(loadedData.buffersGeo.features, (d) => d.properties.idx)
      .join('path')
      .attr('d', d3Path)
      .attr('fill', 'none')
      .attr('stroke', tokens.ucBuf)
      .attr('stroke-width', 0.9)
      .attr('stroke-dasharray', '3,3')
      .attr('stroke-opacity', 0.72)
      .attr('vector-effect', 'non-scaling-stroke')
      .style('pointer-events', 'none');

    // 4. Unidades de Conservacao (84)
    const showUcs = state.layers.ucs || (choroActive && state.choroTarget === 'uc');
    zoomGroup.select('g.cf-layer-ucs')
      .attr('display', showUcs ? null : 'none')
      .selectAll('path')
      .data(loadedData.ucsGeo.features, (d) => d.properties.idx)
      .join('path')
      .attr('d', d3Path)
      .attr('vector-effect', 'non-scaling-stroke')
      .attr('fill', (d) => {
        const idx = d.properties.idx;
        if (choroActive && state.choroTarget === 'uc') {
          const tot = ucTotVals[idx] || 0;
          const area = d.properties.area_ha || 0;
          const val = state.choroMetric === 'densidade' ? (area > 0 ? (tot / area) * 100 : 0) : tot;
          return val > 0 ? ucScale(val) : tokens.surfaceAlt;
        }
        // No coropletico por RA, a UC fica so com o contorno para nao tingir a rampa.
        if (choroActive) return 'transparent';
        return state.ucIdx === idx ? (tokens.dark ? 'rgba(12, 163, 12, 0.30)' : 'rgba(0, 131, 0, 0.24)') : tokens.ucFill;
      })
      .attr('stroke', (d) => (state.ucIdx === d.properties.idx ? tokens.text : tokens.uc))
      .attr('stroke-width', (d) => (state.ucIdx === d.properties.idx ? 2 : 0.9))
      .attr('stroke-opacity', 0.85)
      .style('cursor', 'pointer')
      .on('mousemove', function (event, d) {
        const uc = loadedData.ucsByIdx.get(d.properties.idx);
        if (!uc) return;
        const dentro = currentAgg.ucInTotals[uc.idx] || 0;
        const buf = currentAgg.ucBufTotals[uc.idx] || 0;
        showTooltip(
          `<strong>${escapeHtml(uc.nome)}</strong><br/>` +
          `${escapeHtml(uc.grupo)} · ${formatDec(uc.area_ha, 0)} ha<br/>` +
          `Dentro: <b>${formatInt(dentro)}</b> · Faixa 1 km: <b>${formatInt(buf)}</b>`,
          event.clientX,
          event.clientY
        );
      })
      .on('mouseleave', hideTooltip)
      .on('click', function (event, d) {
        event.stopPropagation();
        const idx = d.properties.idx;
        state.ucIdx = (state.ucIdx === idx) ? null : idx;
        if (state.ucIdx !== null) {
          zoomToFeature(d, 10);
        } else {
          resetMapZoom();
        }
        syncControlsFromState();
        refreshAll(true);
      });

    // 5. Poligonos dos imoveis marcados e/ou imovel focado + Reservas Legais
    const carSelLayer = zoomGroup.select('g.cf-layer-car-sel');
    carSelLayer.selectAll('*').remove();
    const polyCods = getMapPolygonCods();
    polyCods.forEach((cod) => {
      const gObj = loadedData.geometrias.car_top50_geoms[cod];
      if (!gObj) return;
      const isFocused = (state.selectedCar === cod);
      if (gObj.imovel) {
        const imFeat = rewindFeature({ type: 'Feature', geometry: gObj.imovel, properties: {} });
        if (imFeat) {
          carSelLayer.append('path')
            .datum(imFeat)
            .attr('d', d3Path)
            .attr('fill', isFocused
              ? (tokens.dark ? 'rgba(144, 133, 233, 0.24)' : 'rgba(98, 80, 214, 0.20)')
              : (tokens.dark ? 'rgba(249, 115, 22, 0.14)' : 'rgba(194, 65, 12, 0.10)'))
            .attr('stroke', isFocused ? tokens.carSel : tokens.car)
            .attr('stroke-width', isFocused ? 2.6 : 1.8)
            .attr('vector-effect', 'non-scaling-stroke')
            .style('cursor', 'pointer')
            .on('mousemove', function (event) {
              const im = loadedData.carByCod.get(cod);
              if (im) showTooltip(carTooltipHtml(im), event.clientX, event.clientY);
            })
            .on('mouseleave', hideTooltip)
            .on('click', function (event) {
              event.stopPropagation();
              if (state.selectedCar !== cod) selectCAR(cod, false);
            });
        }
      }
      if (state.layers.rl && Array.isArray(gObj.reserva_legal)) {
        gObj.reserva_legal.forEach((rlG) => {
          const rlFeat = rewindFeature({ type: 'Feature', geometry: rlG, properties: {} });
          if (!rlFeat) return;
          carSelLayer.append('path')
            .datum(rlFeat)
            .attr('d', d3Path)
            .attr('fill', 'rgba(5, 150, 105, 0.28)')
            .attr('stroke', tokens.rl)
            .attr('stroke-width', 1.4)
            .attr('stroke-dasharray', '4,2')
            .attr('vector-effect', 'non-scaling-stroke')
            .style('pointer-events', 'none');
        });
      }
    });

    // 6. Pinos dos 50 primeiros imoveis da fila de vistoria
    const visibleCars = getVisibleCars();

    zoomGroup.select('g.cf-layer-car-pins')
      .selectAll('circle')
      .data(visibleCars, (d) => d.cod_imovel)
      .join('circle')
      .attr('cx', (d) => d3Projection([d.lon, d.lat])[0])
      .attr('cy', (d) => d3Projection([d.lon, d.lat])[1])
      .attr('r', (d) => (state.selectedCar === d.cod_imovel ? 9.5 : (d.rank <= 10 ? 8 : 4.5)))
      .attr('fill', 'transparent')
      .attr('stroke', 'none')
      .style('pointer-events', 'all')
      .style('cursor', 'pointer')
      .on('mousemove', function (event, d) {
        showTooltip(carTooltipHtml(d), event.clientX, event.clientY);
      })
      .on('mouseleave', hideTooltip)
      .on('click', function (event, d) {
        event.stopPropagation();
        selectCAR(d.cod_imovel, true);
      });

    updateD3StrokeWeights();
    drawD3Canvas();
    renderD3ChoroplethLegend(choroActive, raScale, ucScale, raExtent, raDensMax, ucMax, ucDensMax);
    bindCanvasInteractions();
  }

  function isTop5Selection() {
    if (!state.defaultTop5Cods || state.defaultTop5Cods.length === 0) return false;
    if (state.checkedCars.size !== state.defaultTop5Cods.length) return false;
    return state.defaultTop5Cods.every((cod) => state.checkedCars.has(cod));
  }

  function getMapPolygonCods() {
    const cods = [];
    const seen = new Set();
    if (state.layers.imoveis && state.checkedCars.size > 0) {
      getVisibleCars().forEach((im) => {
        if (!seen.has(im.cod_imovel)) {
          seen.add(im.cod_imovel);
          cods.push(im.cod_imovel);
        }
      });
    }
    if (state.selectedCar && !seen.has(state.selectedCar)) {
      cods.push(state.selectedCar);
    }
    return cods;
  }

  function getVisibleCars() {
    if (!loadedData || !state.layers.imoveis) return [];
    const sitFilter = state.situacao !== 'todos' ? state.situacao : null;
    const filterChecked = state.checkedCars.size > 0;
    return (loadedData.resumo.car_top50 || []).filter((im) => {
      if (filterChecked && !state.checkedCars.has(im.cod_imovel)) return false;
      if (sitFilter && im.situacao !== sitFilter) return false;
      if (!imovelNoPeriodo(im)) return false;
      return true;
    });
  }

  function drawCanvasCarOverlay(ctx, transform, tokens) {
    if (!loadedData || !d3Projection) return;
    const scaleInv = Math.pow(transform.k, 0.55);

    const canvasPath = d3.geoPath(d3Projection, ctx);
    getMapPolygonCods().forEach((cod) => {
      const gObj = loadedData.geometrias.car_top50_geoms[cod];
      if (!gObj) return;
      const isFocused = (state.selectedCar === cod);
      if (gObj.imovel) {
        ctx.beginPath();
        canvasPath({ type: 'Feature', geometry: gObj.imovel, properties: {} });
        ctx.strokeStyle = isFocused ? tokens.carSel : tokens.car;
        ctx.lineWidth = (isFocused ? 2.6 : 1.8) / transform.k;
        ctx.globalAlpha = 1;
        ctx.stroke();
      }
      if (state.layers.rl && Array.isArray(gObj.reserva_legal)) {
        gObj.reserva_legal.forEach((rlG) => {
          ctx.beginPath();
          canvasPath({ type: 'Feature', geometry: rlG, properties: {} });
          ctx.strokeStyle = tokens.rl;
          ctx.lineWidth = 1.5 / transform.k;
          ctx.stroke();
        });
      }
    });

    // Fila de vistoria por cima dos focos: anel da cor da superficie separa o
    // marcador dos pontos de baixo; os 10 primeiros levam a posicao escrita.
    const visibleCars = getVisibleCars().slice().sort((a, b) => b.rank - a.rank);
    for (let i = 0; i < visibleCars.length; i += 1) {
      const d = visibleCars[i];
      const pt = d3Projection([d.lon, d.lat]);
      const isSel = (state.selectedCar === d.cod_imovel);
      const top10 = d.rank <= 10;
      const r = (isSel ? 9.5 : (top10 ? 8 : 4.5)) / scaleInv;
      ctx.beginPath();
      ctx.arc(pt[0], pt[1], r, 0, 2 * Math.PI);
      ctx.fillStyle = isSel ? tokens.carSel : tokens.car;
      ctx.globalAlpha = 1;
      ctx.fill();
      ctx.lineWidth = 2 / transform.k;
      ctx.strokeStyle = tokens.surface;
      ctx.stroke();
      if (top10 || isSel) {
        ctx.fillStyle = isSel ? tokens.surface : '#ffffff';
        ctx.font = `600 ${(d.rank >= 10 ? 8.5 : 10) / scaleInv}px Inter, system-ui, sans-serif`;
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText(String(d.rank), pt[0], pt[1] + 0.4 / scaleInv);
      }
    }
  }

  function updateD3StrokeWeights() {
    const k = d3CurrentTransform ? d3CurrentTransform.k : 1;
    // Os circulos SVG so recebem o mouse; o desenho visivel e o do canvas.
    d3.select('#cf-d3-svg').selectAll('.cf-layer-car-pins circle')
      .attr('r', (d) => ((state.selectedCar === d.cod_imovel ? 9.5 : (d.rank <= 10 ? 8 : 4.5)) / Math.pow(k, 0.55)) + 2 / k);
  }

  function drawD3Canvas() {
    const stage = document.getElementById('cf-d3-stage');
    const canvasEl = document.getElementById('cf-d3-canvas');
    if (!stage || !canvasEl || !currentFiltered || !d3Projection) return;

    const width = Math.max(320, stage.clientWidth || 720);
    const height = Math.max(380, stage.clientHeight || 600);
    const dpr = Math.min(window.devicePixelRatio || 1, 2);

    if (canvasEl.width !== Math.round(width * dpr) || canvasEl.height !== Math.round(height * dpr)) {
      canvasEl.width = Math.round(width * dpr);
      canvasEl.height = Math.round(height * dpr);
      canvasEl.style.width = width + 'px';
      canvasEl.style.height = height + 'px';
    }

    const ctx = canvasEl.getContext('2d');
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, width, height);

    if (!state.layers.focos || state.d3Mode === 'choropleth') {
      hoverQuadtree = null;
      // Sem focos, a fila de vistoria continua desenhada.
      const t0 = d3CurrentTransform || d3.zoomIdentity;
      ctx.save();
      ctx.translate(t0.x, t0.y);
      ctx.scale(t0.k, t0.k);
      drawCanvasCarOverlay(ctx, t0, getTokens());
      ctx.restore();
      return;
    }

    const t = d3CurrentTransform || d3.zoomIdentity;
    ctx.save();
    ctx.translate(t.x, t.y);
    ctx.scale(t.k, t.k);

    const indices = currentFiltered.indices;
    const tokens = getTokens();

    if (state.d3Mode === 'hexbin') {
      const pts = [];
      for (let idx = 0; idx < indices.length; idx += 1) {
        pts.push(projectedFocos[indices[idx]]);
      }
      const radiusPx = 14 / Math.pow(t.k, 0.72);
      const bins = computeHexbins(pts, radiusPx);
      const maxCount = d3.max(bins, (b) => b.count) || 1;
      const colorScale = d3.scaleSequential(d3.interpolateLab(tokens.seqLow, tokens.seqHigh))
        .domain([1, Math.max(2, Math.sqrt(maxCount))]);

      for (let i = 0; i < bins.length; i += 1) {
        const b = bins[i];
        const r = radiusPx * (0.42 + 0.54 * Math.min(1, Math.sqrt(b.count) / Math.sqrt(maxCount)));
        const verts = hexVertices(b.x, b.y, r);
        ctx.beginPath();
        ctx.moveTo(verts[0][0], verts[0][1]);
        for (let v = 1; v < 6; v += 1) ctx.lineTo(verts[v][0], verts[v][1]);
        ctx.closePath();
        ctx.fillStyle = colorScale(Math.sqrt(b.count));
        ctx.globalAlpha = 0.78;
        ctx.fill();
        ctx.strokeStyle = tokens.dark ? 'rgba(15, 23, 42, 0.6)' : 'rgba(255, 255, 255, 0.75)';
        ctx.lineWidth = 0.8 / t.k;
        ctx.globalAlpha = 0.9;
        ctx.stroke();
      }
      drawCanvasCarOverlay(ctx, t, tokens);
      ctx.restore();
      hoverQuadtree = null;
      return;
    }

    // Modo Pontos Individuais em Canvas + quadtree para hover O(log N)
    const activePts = [];
    const scaleInv = Math.pow(t.k, 0.65);

    // Cada foco e um ponto pequeno e translucido de uma cor so: a sobreposicao
    // mostra a densidade sem esconder os limites nem a fila de vistoria.
    const rFoco = Math.max(0.5, 1.35 / Math.pow(t.k, 0.8));
    ctx.fillStyle = tokens.foco;
    ctx.globalAlpha = tokens.dark ? 0.30 : 0.28;
    for (let i = 0; i < indices.length; i += 1) {
      const pt = projectedFocos[indices[i]];
      activePts.push(pt);
      // Um fill por ponto: as sobreposicoes acumulam opacidade e mostram a densidade.
      ctx.beginPath();
      ctx.arc(pt.x, pt.y, rFoco, 0, 2 * Math.PI);
      ctx.fill();
    }
    ctx.globalAlpha = 1;

    if (activeFocusIdx >= 0 && projectedFocos[activeFocusIdx]) {
      const pSel = projectedFocos[activeFocusIdx];
      ctx.beginPath();
      ctx.arc(pSel.x, pSel.y, 7 / scaleInv, 0, 2 * Math.PI);
      ctx.strokeStyle = tokens.text;
      ctx.lineWidth = 2 / t.k;
      ctx.globalAlpha = 1;
      ctx.stroke();
    }

    drawCanvasCarOverlay(ctx, t, tokens);
    ctx.restore();

    hoverQuadtree = d3.quadtree()
      .x((d) => d.x)
      .y((d) => d.y)
      .addAll(activePts);
  }

  function renderD3ChoroplethLegend(visible, raScale, ucScale, raMax, raDensMax, ucMax, ucDensMax) {
    const legEl = document.getElementById('cf-d3-legend');
    if (!legEl) return;

    if (!visible && state.d3Mode === 'points') {
      const tokens = getTokens();
      legEl.hidden = false;
      legEl.innerHTML = `
        <div class="cf-d3-legend-list">
          <div class="cf-d3-legend-row"><span class="cf-d3-swatch cf-d3-swatch--pin" style="background:${tokens.car}">1</span><span>Fila de vistoria (posição)</span></div>
          <div class="cf-d3-legend-row"><span class="cf-d3-swatch" style="background:${tokens.foco}"></span><span>Foco de calor</span></div>
          <div class="cf-d3-legend-row"><span class="cf-d3-swatch cf-d3-swatch--area" style="background:${tokens.ucFill};border-color:${tokens.uc}"></span><span>Unidade de Conservação</span></div>
        </div>
      `;
      return;
    }

    if (!visible && state.d3Mode !== 'hexbin') {
      legEl.hidden = true;
      return;
    }

    legEl.hidden = false;
    if (state.d3Mode === 'hexbin') {
      legEl.innerHTML = `
        <div class="cf-legend-title">Focos de calor por hexágono</div>
        <div class="cf-legend-ramp"></div>
        <div class="cf-legend-ticks"><span>menos focos</span><span>mais focos</span></div>
      `;
      return;
    }

    const isRa = state.choroTarget === 'ra';
    const maxVal = state.choroMetric === 'densidade' ? (isRa ? raDensMax : ucDensMax) : (isRa ? raMax : ucMax);
    const unit = state.choroMetric === 'densidade' ? (isRa ? 'focos/100 km²' : 'focos/100 ha') : 'focos';
    const titulo = state.choroMetric === 'densidade' ? 'Densidade de focos de calor' : 'Focos de calor';
    legEl.innerHTML = `
      <div class="cf-legend-title">${titulo} por ${isRa ? 'Região Administrativa' : 'Unidade de Conservação'} (${unit})</div>
      <div class="cf-legend-ramp"></div>
      <div class="cf-legend-ticks"><span>0</span><span>${formatDec(maxVal / 4, maxVal < 20 ? 1 : 0)}</span><span>${formatDec(maxVal, maxVal < 20 ? 1 : 0)}</span></div>
      <div class="cf-legend-ticks"><span>menos focos</span><span>mais focos</span></div>
    `;
  }

  function bindCanvasInteractions() {
    const svgEl = document.getElementById('cf-d3-svg');
    if (!svgEl || svgEl.dataset.hoverBound === 'true') return;
    svgEl.dataset.hoverBound = 'true';

    svgEl.addEventListener('mousemove', function (event) {
      if (state.d3Mode !== 'points' || !hoverQuadtree || !d3CurrentTransform) return;
      // Se o cursor ja estiver diretamente sobre um poligono ou marcador SVG interativo, prioriza o evento dele
      const target = event.target;
      if (target && target.tagName && (target.tagName.toLowerCase() === 'circle')) return;

      const rect = svgEl.getBoundingClientRect();
      const mx = event.clientX - rect.left;
      const my = event.clientY - rect.top;
      const inv = d3CurrentTransform.invert([mx, my]);
      const radius = 10 / d3CurrentTransform.k;
      const hit = hoverQuadtree.find(inv[0], inv[1], radius);

      if (hit) {
        const f = hit.f;
        activeFocusIdx = hit.idx;
        const mesNome = MESES[(f[3] - 1) % 12] || f[3];
        const sensorNome = SENSOR_NOMES[String(f[7])] || 'Sensor Orbital';
        const riscoStr = f[8] >= 0 ? `${f[8]}%` : 'N/D';
        const ra = f[9] >= 0 ? loadedData.rasByIdx.get(f[9]) : null;
        const uc = f[10] >= 0 ? loadedData.ucsByIdx.get(f[10]) : null;

        showTooltip(
          `<strong>Foco de Calor · ${mesNome}/${f[2]} (${String(f[4]).padStart(2, '0')}h)</strong><br/>` +
          `${f[5] === 1 ? 'Satélite de referência' : sensorNome} · Risco: ${riscoStr}<br/>` +
          `${ra ? 'RA: ' + escapeHtml(ra.nome) + '<br/>' : ''}` +
          `${uc ? 'Dentro da UC: ' + escapeHtml(uc.nome) : (f[11] >= 0 ? 'Faixa 1 km de UC' : 'Fora de UC')}`,
          event.clientX,
          event.clientY
        );
      } else if (activeFocusIdx !== -1) {
        activeFocusIdx = -1;
      }
    });

    svgEl.addEventListener('mouseleave', function () {
      activeFocusIdx = -1;
      hideTooltip();
    });
  }

  function zoomToFeature(geojsonFeatureOrBounds, maxScale) {
    const svg = d3.select('#cf-d3-svg');
    const stage = document.getElementById('cf-d3-stage');
    if (svg.empty() || !stage || !d3Path || !d3ZoomBehavior) return;

    const width = stage.clientWidth || 720;
    const height = stage.clientHeight || 600;
    const [[x0, y0], [x1, y1]] = d3Path.bounds(geojsonFeatureOrBounds);
    const dx = Math.max(8, x1 - x0);
    const dy = Math.max(8, y1 - y0);
    const x = (x0 + x1) / 2;
    const y = (y0 + y1) / 2;
    const scale = Math.max(1, Math.min(maxScale || 10, 0.78 / Math.max(dx / width, dy / height)));
    const translate = [width / 2 - scale * x, height / 2 - scale * y];

    svg.transition()
      .duration(transitionDuration(550))
      .call(d3ZoomBehavior.transform, d3.zoomIdentity.translate(translate[0], translate[1]).scale(scale));
  }

  function resetMapZoom() {
    const svg = d3.select('#cf-d3-svg');
    if (!svg.empty() && d3ZoomBehavior) {
      svg.transition()
        .duration(transitionDuration(450))
        .call(d3ZoomBehavior.transform, d3.zoomIdentity);
    }
    if (window.CFLeafletBridge) {
      window.CFLeafletBridge.resetZoom();
    }
  }

  // Grafico 1: Serie Anual 2015-2025 (Estiagem/Chuvoso ou AQUA_M-T/Demais)
  function renderAnualChart() {
    const box = document.getElementById('chart-anual');
    if (!box || !currentAgg || typeof d3 === 'undefined') return;

    const width = Math.max(280, box.clientWidth || 500);
    const height = 270;
    const margin = { top: 18, right: 14, bottom: 34, left: 52 };
    const iw = width - margin.left - margin.right;
    const ih = height - margin.top - margin.bottom;
    const tokens = getTokens();
    const data = currentAgg.byYearAll;

    const svg = d3.select(box).selectAll('svg').data([null]).join('svg')
      .attr('width', width)
      .attr('height', height)
      .attr('role', 'img')
      .attr('aria-label', 'Série anual de focos de calor de 2015 a 2025');

    svg.selectAll('*').remove();
    const g = svg.append('g').attr('transform', `translate(${margin.left},${margin.top})`);

    const x = d3.scaleBand().domain(data.map((d) => String(d.ano))).range([0, iw]).padding(0.24);
    const yMax = Math.max(10, d3.max(data, (d) => d.total) || 10);
    const y = d3.scaleLinear().domain([0, yMax * 1.1]).nice().range([ih, 0]);

    g.append('g')
      .call(d3.axisLeft(y).ticks(5).tickSize(-iw).tickFormat((d) => formatInt(d)))
      .call((ax) => ax.select('.domain').remove())
      .call((ax) => ax.selectAll('line').attr('stroke', tokens.grid))
      .call((ax) => ax.selectAll('text').attr('fill', tokens.muted).attr('font-size', '11px'));

    g.append('g')
      .attr('transform', `translate(0,${ih})`)
      .call(d3.axisBottom(x))
      .call((ax) => ax.select('.domain').attr('stroke', tokens.border))
      .call((ax) => ax.selectAll('text').attr('fill', tokens.muted).attr('font-size', '11px'));

    const keys = state.anualMode === 'referencia' ? ['ref', 'secSensor'] : ['seca', 'chuvoso'];
    const colors = state.anualMode === 'referencia'
      ? { ref: tokens.ref, secSensor: tokens.otherSensor }
      : { seca: tokens.seca, chuvoso: tokens.chuvoso };
    const labels = state.anualMode === 'referencia'
      ? { ref: 'Satélite de referência', secSensor: 'Demais sensores' }
      : { seca: 'Estiagem (Mai-Set)', chuvoso: 'Chuvoso (Out-Abr)' };

    const stackGen = d3.stack().keys(keys);
    const series = stackGen(data);

    const groups = g.selectAll('g.cf-stack-group')
      .data(series)
      .join('g')
      .attr('class', 'cf-stack-group')
      .attr('fill', (d) => colors[d.key]);

    groups.selectAll('rect')
      .data((d) => d.map((item) => ({ key: d.key, seg: item, data: item.data })))
      .join('rect')
      .attr('x', (d) => x(String(d.data.ano)))
      .attr('width', x.bandwidth())
      .attr('rx', 2)
      .attr('opacity', (d) => (anoNoFiltro(d.data.ano) ? 0.94 : 0.34))
      .attr('y', ih)
      .attr('height', 0)
      .style('cursor', 'pointer')
      .on('mousemove', function (event, d) {
        const val = d.data[d.key];
        const pct = d.data.total > 0 ? (val / d.data.total) * 100 : 0;
        showTooltip(
          `<strong>${d.data.ano}</strong> · Total: <b>${formatInt(d.data.total)}</b><br/>` +
          `${labels[d.key]}: <b>${formatInt(val)}</b> (${formatDec(pct, 1)}%)<br/>` +
          `<small>Clique para filtrar ${d.data.ano}</small>`,
          event.clientX,
          event.clientY
        );
      })
      .on('mouseleave', hideTooltip)
      .on('click', function (_, d) {
        const clicked = d.data.ano;
        setYearFilter(anoUnico() === clicked ? 'todos' : clicked, false);
        refreshAll(false);
      })
      .transition()
      .duration(transitionDuration(380))
      .attr('y', (d) => y(d.seg[1]))
      .attr('height', (d) => Math.max(0, y(d.seg[0]) - y(d.seg[1])));

    // Legenda compacta no topo
    const leg = svg.append('g').attr('transform', `translate(${margin.left}, 12)`);
    let lx = 0;
    keys.forEach((k) => {
      leg.append('rect').attr('x', lx).attr('y', -9).attr('width', 10).attr('height', 10).attr('rx', 2).attr('fill', colors[k]);
      leg.append('text').attr('x', lx + 14).attr('y', 0).attr('fill', tokens.muted).attr('font-size', '11px').text(labels[k]);
      lx += labels[k].length * 6.8 + 26;
    });
  }

  // Grafico 2: Heatmap Ano x Mes (11 x 12)
  function renderHeatmapChart() {
    const box = document.getElementById('chart-heatmap');
    if (!box || !currentAgg || typeof d3 === 'undefined') return;

    const width = Math.max(300, box.clientWidth || 500);
    const height = 270;
    const margin = { top: 24, right: 12, bottom: 26, left: 46 };
    const iw = width - margin.left - margin.right;
    const ih = height - margin.top - margin.bottom;
    const tokens = getTokens();

    const matrix = currentAgg.heatmapMatrix;
    const flat = [];
    let maxCell = 1;
    for (let y = 0; y < 11; y += 1) {
      for (let m = 0; m < 12; m += 1) {
        const val = matrix[y][m];
        if (val > maxCell) maxCell = val;
        flat.push({ ano: 2015 + y, mes: m + 1, nomeMes: MESES[m], count: val });
      }
    }

    const svg = d3.select(box).selectAll('svg').data([null]).join('svg')
      .attr('width', width)
      .attr('height', height)
      .attr('role', 'img')
      .attr('aria-label', 'Matriz de calor de focos por ano e mês (2015 a 2025)');

    svg.selectAll('*').remove();
    const g = svg.append('g').attr('transform', `translate(${margin.left},${margin.top})`);

    const x = d3.scaleBand().domain(MESES).range([0, iw]).padding(0.08);
    const y = d3.scaleBand().domain(ANOS.map(String)).range([0, ih]).padding(0.10);
    const colorScale = d3.scaleSequential(d3.interpolateLab(tokens.seqLow, tokens.seqHigh))
      .domain([0, Math.sqrt(maxCell)]);

    g.append('g')
      .call(d3.axisTop(x))
      .call((ax) => ax.select('.domain').remove())
      .call((ax) => ax.selectAll('line').remove())
      .call((ax) => ax.selectAll('text').attr('fill', tokens.muted).attr('font-size', '11px'));

    g.append('g')
      .call(d3.axisLeft(y))
      .call((ax) => ax.select('.domain').remove())
      .call((ax) => ax.selectAll('line').remove())
      .call((ax) => ax.selectAll('text').attr('fill', tokens.muted).attr('font-size', '11px'));

    g.selectAll('rect.cf-heat-cell')
      .data(flat)
      .join('rect')
      .attr('class', 'cf-heat-cell')
      .attr('x', (d) => x(d.nomeMes))
      .attr('y', (d) => y(String(d.ano)))
      .attr('width', x.bandwidth())
      .attr('height', y.bandwidth())
      .attr('rx', 3)
      .attr('fill', (d) => (d.count === 0 ? tokens.surfaceAlt : colorScale(Math.sqrt(d.count))))
      .attr('stroke', (d) => {
        const isActive = (anoUnico() === d.ano && state.mes === d.mes);
        return isActive ? tokens.text : 'transparent';
      })
      .attr('stroke-width', 1.8)
      .attr('opacity', (d) => {
        const anoMatch = anoNoFiltro(d.ano);
        const mesMatch = state.mes === null || state.mes === d.mes;
        return (anoMatch && mesMatch) ? 1 : 0.32;
      })
      .style('cursor', 'pointer')
      .on('mousemove', function (event, d) {
        showTooltip(
          `<strong>${d.nomeMes}/${d.ano}</strong><br/>` +
          `Focos registrados: <b>${formatInt(d.count)}</b><br/>` +
          `<small>Clique para filtrar ${d.nomeMes}/${d.ano}</small>`,
          event.clientX,
          event.clientY
        );
      })
      .on('mouseleave', hideTooltip)
      .on('click', function (_, d) {
        if (anoUnico() === d.ano && state.mes === d.mes) {
          setYearFilter('todos', false);
          state.mes = null;
        } else {
          setYearFilter(d.ano, false);
          state.mes = d.mes;
        }
        syncControlsFromState();
        refreshAll(false);
      });
  }

  // Grafico 3: Sazonalidade Mensal (Jan-Dez)
  function renderMensalChart() {
    const box = document.getElementById('chart-mensal');
    if (!box || !currentAgg || typeof d3 === 'undefined') return;

    const width = Math.max(260, box.clientWidth || 420);
    const height = 240;
    const margin = { top: 14, right: 12, bottom: 30, left: 48 };
    const iw = width - margin.left - margin.right;
    const ih = height - margin.top - margin.bottom;
    const tokens = getTokens();
    const data = currentAgg.byMonth;

    const svg = d3.select(box).selectAll('svg').data([null]).join('svg')
      .attr('width', width)
      .attr('height', height)
      .attr('role', 'img')
      .attr('aria-label', 'Sazonalidade mensal de focos de janeiro a dezembro');

    svg.selectAll('*').remove();
    const g = svg.append('g').attr('transform', `translate(${margin.left},${margin.top})`);

    const x = d3.scaleBand().domain(MESES).range([0, iw]).padding(0.22);
    const yMax = Math.max(10, d3.max(data, (d) => d.total) || 10);
    const y = d3.scaleLinear().domain([0, yMax * 1.1]).nice().range([ih, 0]);

    // Faixa visual destacando a estacao seca (Mai-Set)
    const dryStart = x('Mai');
    const dryEnd = x('Set') + x.bandwidth();
    if (dryStart != null && dryEnd != null) {
      g.append('rect')
        .attr('x', dryStart - 2)
        .attr('y', 0)
        .attr('width', dryEnd - dryStart + 4)
        .attr('height', ih)
        .attr('fill', tokens.seca)
        .attr('fill-opacity', tokens.dark ? 0.12 : 0.07)
        .attr('rx', 4);
    }

    g.append('g')
      .call(d3.axisLeft(y).ticks(5).tickSize(-iw).tickFormat((d) => formatInt(d)))
      .call((ax) => ax.select('.domain').remove())
      .call((ax) => ax.selectAll('line').attr('stroke', tokens.grid))
      .call((ax) => ax.selectAll('text').attr('fill', tokens.muted).attr('font-size', '11px'));

    g.append('g')
      .attr('transform', `translate(0,${ih})`)
      .call(d3.axisBottom(x))
      .call((ax) => ax.select('.domain').attr('stroke', tokens.border))
      .call((ax) => ax.selectAll('text').attr('fill', tokens.muted).attr('font-size', '11px'));

    g.selectAll('rect.cf-mes-bar')
      .data(data)
      .join('rect')
      .attr('class', 'cf-mes-bar')
      .attr('x', (d) => x(d.nome))
      .attr('width', x.bandwidth())
      .attr('rx', 3)
      .attr('fill', (d) => (d.seca ? tokens.seca : tokens.chuvoso))
      .attr('opacity', (d) => (state.mes === null || state.mes === d.mes ? 0.92 : 0.30))
      .attr('y', ih)
      .attr('height', 0)
      .style('cursor', 'pointer')
      .on('mousemove', function (event, d) {
        showTooltip(
          `<strong>${d.nome}</strong> (${d.seca ? 'Estiagem' : 'Chuvoso'})<br/>` +
          `Total: <b>${formatInt(d.total)}</b> focos<br/>` +
          `Referência: ${formatInt(d.ref)}`,
          event.clientX,
          event.clientY
        );
      })
      .on('mouseleave', hideTooltip)
      .on('click', function (_, d) {
        state.mes = (state.mes === d.mes) ? null : d.mes;
        syncControlsFromState();
        refreshAll(false);
      })
      .transition()
      .duration(transitionDuration(350))
      .attr('y', (d) => y(d.total))
      .attr('height', (d) => Math.max(0, ih - y(d.total)));
  }

  // Grafico 4: Evolucao de Sensores / Ciclo Horario / Risco de Fogo
  function renderSensorOrSubdailyChart() {
    const box = document.getElementById('chart-sensores-hora');
    if (!box || !currentAgg || typeof d3 === 'undefined') return;

    const width = Math.max(280, box.clientWidth || 540);
    const height = 240;
    const margin = { top: 20, right: 14, bottom: 32, left: 48 };
    const iw = width - margin.left - margin.right;
    const ih = height - margin.top - margin.bottom;
    const tokens = getTokens();

    const svg = d3.select(box).selectAll('svg').data([null]).join('svg')
      .attr('width', width)
      .attr('height', height)
      .attr('role', 'img');
    svg.selectAll('*').remove();

    const g = svg.append('g').attr('transform', `translate(${margin.left},${margin.top})`);

    if (state.sensorTab === 'evolucao') {
      svg.attr('aria-label', 'Evolução anual por família de sensor orbital (2015-2025)');
      const rows = currentAgg.byYearAll.map((d) => ({
        ano: d.ano,
        s0: d.sensores[0],
        s1: d.sensores[1],
        s2: d.sensores[2],
        s3: d.sensores[3],
        total: d.total
      }));
      const keys = ['s0', 's1', 's2', 's3'];
      const colorMap = { s0: tokens.sensorColors['0'], s1: tokens.sensorColors['1'], s2: tokens.sensorColors['2'], s3: tokens.sensorColors['3'] };
      const labelMap = { s0: 'VIIRS 375m', s1: 'MODIS 1km', s2: 'GOES 2km', s3: 'AVHRR 1.1km' };

      const x = d3.scalePoint().domain(rows.map((r) => r.ano)).range([0, iw]).padding(0.2);
      const stack = d3.stack().keys(keys)(rows);
      const yMax = Math.max(10, d3.max(stack, (s) => d3.max(s, (d) => d[1])) || 10);
      const y = d3.scaleLinear().domain([0, yMax * 1.08]).nice().range([ih, 0]);

      g.append('g')
        .call(d3.axisLeft(y).ticks(5).tickSize(-iw).tickFormat((d) => formatInt(d)))
        .call((ax) => ax.select('.domain').remove())
        .call((ax) => ax.selectAll('line').attr('stroke', tokens.grid))
        .call((ax) => ax.selectAll('text').attr('fill', tokens.muted).attr('font-size', '11px'));

      g.append('g')
        .attr('transform', `translate(0,${ih})`)
        .call(d3.axisBottom(x))
        .call((ax) => ax.select('.domain').attr('stroke', tokens.border))
        .call((ax) => ax.selectAll('text').attr('fill', tokens.muted).attr('font-size', '11px'));

      const area = d3.area()
        .x((d) => x(d.data.ano))
        .y0((d) => y(d[0]))
        .y1((d) => y(d[1]))
        .curve(d3.curveMonotoneX);

      g.selectAll('path.cf-sensor-area')
        .data(stack)
        .join('path')
        .attr('class', 'cf-sensor-area')
        .attr('d', area)
        .attr('fill', (d) => colorMap[d.key])
        .attr('fill-opacity', 0.78)
        .attr('stroke', (d) => colorMap[d.key])
        .attr('stroke-width', 1.2)
        .style('cursor', 'pointer')
        .on('mousemove', function (event, d) {
          const sum = d3.sum(rows, (r) => r[d.key]);
          showTooltip(`<strong>${labelMap[d.key]}</strong><br/>Total visível na série: <b>${formatInt(sum)}</b> focos<br/><small>Clique para filtrar família de sensor</small>`, event.clientX, event.clientY);
        })
        .on('mouseleave', hideTooltip)
        .on('click', function (_, d) {
          const code = d.key.slice(1);
          state.sensor = (state.sensor === code) ? 'todos' : code;
          syncControlsFromState();
          refreshAll(false);
        });

      const leg = svg.append('g').attr('transform', `translate(${margin.left}, 12)`);
      let lx = 0;
      keys.forEach((k) => {
        leg.append('rect').attr('x', lx).attr('y', -9).attr('width', 9).attr('height', 9).attr('rx', 2).attr('fill', colorMap[k]);
        leg.append('text').attr('x', lx + 13).attr('y', 0).attr('fill', tokens.muted).attr('font-size', '10.5px').text(labelMap[k]);
        lx += labelMap[k].length * 6.2 + 22;
      });
      return;
    }

    if (state.sensorTab === 'horario') {
      svg.attr('aria-label', 'Distribuição horária das detecções em horário de Brasília (UTC-3)');
      const data = currentAgg.byHour;
      const x = d3.scaleBand().domain(data.map((d) => d.hora)).range([0, iw]).padding(0.18);
      const yMax = Math.max(5, d3.max(data, (d) => d.total) || 5);
      const y = d3.scaleLinear().domain([0, yMax * 1.1]).nice().range([ih, 0]);

      g.append('g')
        .call(d3.axisLeft(y).ticks(5).tickSize(-iw).tickFormat((d) => formatInt(d)))
        .call((ax) => ax.select('.domain').remove())
        .call((ax) => ax.selectAll('line').attr('stroke', tokens.grid))
        .call((ax) => ax.selectAll('text').attr('fill', tokens.muted).attr('font-size', '11px'));

      g.append('g')
        .attr('transform', `translate(0,${ih})`)
        .call(d3.axisBottom(x).tickValues([0, 3, 6, 9, 12, 15, 18, 21]).tickFormat((h) => `${String(h).padStart(2, '0')}h`))
        .call((ax) => ax.select('.domain').attr('stroke', tokens.border))
        .call((ax) => ax.selectAll('text').attr('fill', tokens.muted).attr('font-size', '11px'));

      g.selectAll('rect.cf-hora-bar')
        .data(data)
        .join('rect')
        .attr('class', 'cf-hora-bar')
        .attr('x', (d) => x(d.hora))
        .attr('width', x.bandwidth())
        .attr('rx', 2)
        .attr('fill', (d) => ((d.hora >= 12 && d.hora <= 18) ? tokens.foco : tokens.totalBar))
        .attr('opacity', 0.9)
        .attr('y', ih)
        .attr('height', 0)
        .on('mousemove', function (event, d) {
          showTooltip(
            `<strong>${String(d.hora).padStart(2, '0')}h00–${String(d.hora).padStart(2, '0')}h59 (horário local)</strong><br/>` +
            `Detecções: <b>${formatInt(d.total)}</b> (Referência: ${formatInt(d.ref)})`,
            event.clientX,
            event.clientY
          );
        })
        .on('mouseleave', hideTooltip)
        .transition()
        .duration(transitionDuration(350))
        .attr('y', (d) => y(d.total))
        .attr('height', (d) => Math.max(0, ih - y(d.total)));
      return;
    }

    // Risco de Fogo INPE (0-100%)
    svg.attr('aria-label', 'Distribuição do índice de risco de fogo do INPE');
    const bins = currentAgg.riscoBins;
    const x = d3.scaleBand().domain(bins.map((b) => b.faixa)).range([0, iw]).padding(0.18);
    const yMax = Math.max(5, d3.max(bins, (b) => b.count) || 5);
    const y = d3.scaleLinear().domain([0, yMax * 1.1]).nice().range([ih, 0]);

    g.append('g')
      .call(d3.axisLeft(y).ticks(5).tickSize(-iw).tickFormat((d) => formatInt(d)))
      .call((ax) => ax.select('.domain').remove())
      .call((ax) => ax.selectAll('line').attr('stroke', tokens.grid))
      .call((ax) => ax.selectAll('text').attr('fill', tokens.muted).attr('font-size', '11px'));

    g.append('g')
      .attr('transform', `translate(0,${ih})`)
      .call(d3.axisBottom(x))
      .call((ax) => ax.select('.domain').attr('stroke', tokens.border))
      .call((ax) => ax.selectAll('text').attr('fill', tokens.muted).attr('font-size', '10px'));

    g.selectAll('rect.cf-risco-bar')
      .data(bins)
      .join('rect')
      .attr('class', 'cf-risco-bar')
      .attr('x', (d) => x(d.faixa))
      .attr('width', x.bandwidth())
      .attr('rx', 2)
      .attr('fill', (d) => (d.min >= 80 ? tokens.foco : (d.min >= 50 ? tokens.focoClaro : tokens.totalBar)))
      .attr('y', ih)
      .attr('height', 0)
      .on('mousemove', function (event, d) {
        showTooltip(
          `<strong>Risco de Fogo INPE: ${d.faixa}%</strong><br/>` +
          `Ocorrências medidas: <b>${formatInt(d.count)}</b>`,
          event.clientX,
          event.clientY
        );
      })
      .on('mouseleave', hideTooltip)
      .transition()
      .duration(transitionDuration(350))
      .attr('y', (d) => y(d.count))
      .attr('height', (d) => Math.max(0, ih - y(d.count)));
  }

  // Grafico 5: Ranking Top 15 UCs Mais Pressionadas (Dentro vs Faixa 1 km)
  function renderUcsRankingChart() {
    const box = document.getElementById('chart-ucs-ranking');
    if (!box || !loadedData || !currentAgg || typeof d3 === 'undefined') return;

    const ucs = loadedData.resumo.ucs_resumo;
    const rows = ucs.map((u) => {
      const dentro = currentAgg.ucInTotals[u.idx] || 0;
      const buf = currentAgg.ucBufTotals[u.idx] || 0;
      const total = dentro + buf;
      const denom = (state.ucMetric === 'densidade' && u.area_ha > 0) ? (u.area_ha / 100) : 1;
      return {
        idx: u.idx,
        nome: u.sigla || u.nome,
        nomeCompleto: u.nome,
        grupo: u.grupo,
        area_ha: u.area_ha,
        dentroRaw: dentro,
        bufRaw: buf,
        totalRaw: total,
        dentro: dentro / denom,
        buf: buf / denom,
        total: total / denom
      };
    })
      .filter((r) => r.totalRaw > 0)
      .sort((a, b) => b.total - a.total)
      .slice(0, 14);

    const width = Math.max(300, box.clientWidth || 500);
    const height = Math.max(240, rows.length * 24 + 54);
    const margin = { top: 24, right: 20, bottom: 26, left: 168 };
    const iw = Math.max(80, width - margin.left - margin.right);
    const ih = height - margin.top - margin.bottom;
    const tokens = getTokens();

    const svg = d3.select(box).selectAll('svg').data([null]).join('svg')
      .attr('width', width)
      .attr('height', height)
      .attr('role', 'img')
      .attr('aria-label', 'Ranking das unidades de conservação mais pressionadas');
    svg.selectAll('*').remove();

    if (rows.length === 0) {
      svg.append('text')
        .attr('x', width / 2)
        .attr('y', height / 2)
        .attr('text-anchor', 'middle')
        .attr('fill', tokens.muted)
        .attr('font-size', '12px')
        .text('Nenhum foco registrado em UCs para o filtro selecionado.');
      return;
    }

    const g = svg.append('g').attr('transform', `translate(${margin.left},${margin.top})`);
    const y = d3.scaleBand().domain(rows.map((r) => r.nome)).range([0, ih]).padding(0.24);
    const xMax = Math.max(1, d3.max(rows, (r) => r.total) || 1);
    const x = d3.scaleLinear().domain([0, xMax * 1.08]).nice().range([0, iw]);

    g.append('g')
      .attr('transform', `translate(0,${ih})`)
      .call(d3.axisBottom(x).ticks(5).tickFormat((d) => formatDec(d, Number.isInteger(d) ? 0 : 1)))
      .call((ax) => ax.select('.domain').attr('stroke', tokens.border))
      .call((ax) => ax.selectAll('text').attr('fill', tokens.muted).attr('font-size', '11px'));

    g.append('g')
      .call(d3.axisLeft(y))
      .call((ax) => ax.select('.domain').remove())
      .call((ax) => ax.selectAll('line').remove())
      .call((ax) => ax.selectAll('text')
        .attr('fill', (name) => {
          const item = rows.find((r) => r.nome === name);
          return (item && state.ucIdx === item.idx) ? tokens.car : tokens.text;
        })
        .attr('font-size', '11px')
        .text((name) => (name.length > 23 ? name.slice(0, 22) + '...' : name)));

    const stack = d3.stack().keys(['dentro', 'buf'])(rows);
    const colorMap = { dentro: tokens.uc, buf: tokens.ucClaro };

    g.selectAll('g.cf-uc-stack')
      .data(stack)
      .join('g')
      .attr('class', 'cf-uc-stack')
      .attr('fill', (d) => colorMap[d.key])
      .selectAll('rect')
      .data((d) => d.map((seg) => ({ key: d.key, seg: seg, row: seg.data })))
      .join('rect')
      .attr('y', (d) => y(d.row.nome))
      .attr('height', y.bandwidth())
      .attr('rx', 2)
      .attr('opacity', (d) => (state.ucIdx === null || state.ucIdx === d.row.idx ? 0.92 : 0.35))
      .attr('x', 0)
      .attr('width', 0)
      .style('cursor', 'pointer')
      .on('mousemove', function (event, d) {
        const unitLabel = state.ucMetric === 'densidade' ? ' focos/100 ha' : ' focos';
        showTooltip(
          `<strong>${escapeHtml(d.row.nomeCompleto)}</strong> (${escapeHtml(d.row.grupo)})<br/>` +
          `Dentro da UC: <b>${formatInt(d.row.dentroRaw)}</b> · Faixa 1 km: <b>${formatInt(d.row.bufRaw)}</b><br/>` +
          `Métrica exibida: <b>${formatDec(d.row.total, state.ucMetric === 'densidade' ? 1 : 0)}${unitLabel}</b><br/>` +
          `<small>Clique para focar no mapa</small>`,
          event.clientX,
          event.clientY
        );
      })
      .on('mouseleave', hideTooltip)
      .on('click', function (_, d) {
        selectUC(d.row.idx);
      })
      .transition()
      .duration(transitionDuration(350))
      .attr('x', (d) => x(d.seg[0]))
      .attr('width', (d) => Math.max(0, x(d.seg[1]) - x(d.seg[0])));

    const leg = svg.append('g').attr('transform', `translate(${margin.left}, 12)`);
    leg.append('rect').attr('x', 0).attr('y', -9).attr('width', 10).attr('height', 10).attr('rx', 2).attr('fill', tokens.uc);
    leg.append('text').attr('x', 14).attr('y', 0).attr('fill', tokens.muted).attr('font-size', '11px').text('Dentro da UC');
    leg.append('rect').attr('x', 105).attr('y', -9).attr('width', 10).attr('height', 10).attr('rx', 2).attr('fill', tokens.ucClaro);
    leg.append('text').attr('x', 119).attr('y', 0).attr('fill', tokens.muted).attr('font-size', '11px').text('Faixa de 1 km');
  }

  // Grafico 6: Reincidencia Fundiaria e Sobreposicoes Protegidas
  function renderCarAnalyticsChart() {
    const box = document.getElementById('chart-car-reincidencia');
    if (!box || !loadedData || typeof d3 === 'undefined') return;

    const cc = loadedData.resumo.car_cruzamento;
    const gold = loadedData.resumo.gold_referencia;
    const width = Math.max(280, box.clientWidth || 500);
    const height = 270;
    const tokens = getTokens();

    const svg = d3.select(box).selectAll('svg').data([null]).join('svg')
      .attr('width', width)
      .attr('height', height)
      .attr('role', 'img');
    svg.selectAll('*').remove();

    if (state.carSubTab === 'situacao') {
      svg.attr('aria-label', 'Imóveis CAR reincidentes por situação cadastral e porte em hectares');
      const margin = { top: 20, right: 16, bottom: 32, left: 108 };
      const iw = width - margin.left - margin.right;
      const ih = height - margin.top - margin.bottom;
      const g = svg.append('g').attr('transform', `translate(${margin.left},${margin.top})`);

      const sitKeys = ['AT', 'PE', 'SU', 'CA'];
      const sitRows = sitKeys.map((k) => ({
        codigo: k,
        label: `${k} (${SITUACAO_LABELS[k]})`,
        imoveis: (cc.por_situacao[k] && cc.por_situacao[k].imoveis) || 0,
        focos: (cc.por_situacao[k] && cc.por_situacao[k].focos) || 0,
        mediana: (cc.por_situacao[k] && cc.por_situacao[k].mediana_ha) || 0
      }));

      const y = d3.scaleBand().domain(sitRows.map((r) => r.label)).range([0, ih * 0.44]).padding(0.24);
      const x = d3.scaleLinear().domain([0, d3.max(sitRows, (r) => r.imoveis) * 1.45]).range([0, iw]);

      g.append('g').call(d3.axisLeft(y)).call((ax) => ax.select('.domain').remove()).call((ax) => ax.selectAll('line').remove())
        .call((ax) => ax.selectAll('text').attr('fill', tokens.text).attr('font-size', '11px'));

      g.selectAll('rect.cf-sit-bar')
        .data(sitRows)
        .join('rect')
        .attr('x', 0)
        .attr('y', (d) => y(d.label))
        .attr('height', y.bandwidth())
        .attr('width', (d) => x(d.imoveis))
        .attr('rx', 3)
        .attr('fill', (d) => tokens.situacaoColors[d.codigo])
        .attr('opacity', (d) => (state.situacao === 'todos' || state.situacao === d.codigo ? 0.92 : 0.35))
        .style('cursor', 'pointer')
        .on('mousemove', function (event, d) {
          showTooltip(
            `<strong>Situação ${escapeHtml(d.label)}</strong><br/>` +
            `Imóveis reincidentes: <b>${formatInt(d.imoveis)}</b><br/>` +
            `Focos totais: <b>${formatInt(d.focos)}</b> · Mediana: ${formatDec(d.mediana, 1)} ha`,
            event.clientX,
            event.clientY
          );
        })
        .on('mouseleave', hideTooltip)
        .on('click', function (_, d) {
          state.situacao = (state.situacao === d.codigo) ? 'todos' : d.codigo;
          syncControlsFromState();
          refreshAll(true);
        });

      g.selectAll('text.cf-sit-val')
        .data(sitRows)
        .join('text')
        .attr('x', (d) => x(d.imoveis) + 5)
        .attr('y', (d) => y(d.label) + y.bandwidth() / 2 + 4)
        .attr('fill', tokens.muted)
        .attr('font-size', '11px')
        .text((d) => `${formatInt(d.imoveis)} · ${formatInt(d.focos)} focos`);

      // Parte inferior: Faixa de area (ha)
      const areaOrder = ['Até 20 ha', '20 a 100 ha', '100 a 500 ha', '500 a 5.000 ha', 'Acima de 5.000 ha'];
      const areaRows = areaOrder.map((k) => ({ faixa: k, qtd: (cc.por_faixa_area && cc.por_faixa_area[k]) || 0 }));
      const y2 = d3.scaleBand().domain(areaRows.map((r) => r.faixa)).range([ih * 0.54, ih]).padding(0.2);
      const x2 = d3.scaleLinear().domain([0, d3.max(areaRows, (r) => r.qtd) * 1.15]).range([0, iw]);

      g.append('text').attr('x', 0).attr('y', ih * 0.51).attr('fill', tokens.muted).attr('font-size', '11px').attr('font-weight', '700')
        .text('Distribuição por faixa de área cadastrada (ha)');

      g.append('g').call(d3.axisLeft(y2)).call((ax) => ax.select('.domain').remove()).call((ax) => ax.selectAll('line').remove())
        .call((ax) => ax.selectAll('text').attr('fill', tokens.muted).attr('font-size', '10.5px'));

      g.selectAll('rect.cf-area-bar')
        .data(areaRows)
        .join('rect')
        .attr('x', 0)
        .attr('y', (d) => y2(d.faixa))
        .attr('height', y2.bandwidth())
        .attr('width', (d) => x2(d.qtd))
        .attr('rx', 2)
        .attr('fill', tokens.totalBar);

      g.selectAll('text.cf-area-val')
        .data(areaRows)
        .join('text')
        .attr('x', (d) => x2(d.qtd) + 5)
        .attr('y', (d) => y2(d.faixa) + y2.bandwidth() / 2 + 4)
        .attr('fill', tokens.muted)
        .attr('font-size', '10.5px')
        .text((d) => formatInt(d.qtd));
      return;
    }

    if (state.carSubTab === 'reincidencia') {
      svg.attr('aria-label', 'Distribuição de imóveis reincidentes por número de anos com foco (2 a 11 anos)');
      const margin = { top: 20, right: 14, bottom: 32, left: 48 };
      const iw = width - margin.left - margin.right;
      const ih = height - margin.top - margin.bottom;
      const g = svg.append('g').attr('transform', `translate(${margin.left},${margin.top})`);

      const anosDist = Array.from({ length: 10 }, (_, i) => {
        const k = String(i + 2);
        return {
          anos: `${k}a`,
          anosNum: i + 2,
          gold: (gold.distribuicao_anos && gold.distribuicao_anos[k]) || 0
        };
      });

      const x = d3.scaleBand().domain(anosDist.map((d) => d.anos)).range([0, iw]).padding(0.24);
      const y = d3.scaleLinear().domain([0, (d3.max(anosDist, (d) => d.gold) || 750) * 1.12]).nice().range([ih, 0]);

      g.append('g')
        .call(d3.axisLeft(y).ticks(5).tickSize(-iw).tickFormat((d) => formatInt(d)))
        .call((ax) => ax.select('.domain').remove())
        .call((ax) => ax.selectAll('line').attr('stroke', tokens.grid))
        .call((ax) => ax.selectAll('text').attr('fill', tokens.muted).attr('font-size', '11px'));

      g.append('g').attr('transform', `translate(0,${ih})`).call(d3.axisBottom(x))
        .call((ax) => ax.select('.domain').attr('stroke', tokens.border))
        .call((ax) => ax.selectAll('text').attr('fill', tokens.muted).attr('font-size', '11px'));

      g.selectAll('rect.cf-reinc-gold')
        .data(anosDist)
        .join('rect')
        .attr('x', (d) => x(d.anos))
        .attr('width', x.bandwidth())
        .attr('y', (d) => y(d.gold))
        .attr('height', (d) => ih - y(d.gold))
        .attr('rx', 3)
        .attr('fill', (d) => (d.anosNum >= 10 ? tokens.carForte : tokens.car))
        .on('mousemove', function (event, d) {
          showTooltip(
            `<strong>${d.anosNum} anos distintos com foco</strong><br/>` +
            `<b>${formatInt(d.gold)}</b> imóveis reincidentes`,
            event.clientX,
            event.clientY
          );
        })
        .on('mouseleave', hideTooltip);
      return;
    }

    // Sub-tab: Sobreposicoes Protegidas (camada Gold)
    svg.attr('aria-label', 'Imóveis reincidentes por critério: Reserva Legal, APP e faixa de 1 km de UC');
    const margin = { top: 22, right: 56, bottom: 28, left: 155 };
    const iw = width - margin.left - margin.right;
    const ih = height - margin.top - margin.bottom;
    const g = svg.append('g').attr('transform', `translate(${margin.left},${margin.top})`);

    const protRows = [
      { label: 'Até 1 km de UC', gold: gold.reincidentes_por_categoria.uc_1km },
      { label: 'Reserva Legal', gold: gold.reincidentes_por_categoria.reserva_legal },
      { label: 'APP', gold: gold.reincidentes_por_categoria.app }
    ];

    const y = d3.scaleBand().domain(protRows.map((r) => r.label)).range([0, ih]).padding(0.32);
    const x = d3.scaleLinear().domain([0, (d3.max(protRows, (r) => r.gold) || 1) * 1.1]).nice().range([0, iw]);

    g.append('g')
      .attr('transform', `translate(0,${ih})`)
      .call(d3.axisBottom(x).ticks(4).tickFormat((d) => formatInt(d)))
      .call((ax) => ax.select('.domain').attr('stroke', tokens.border))
      .call((ax) => ax.selectAll('text').attr('fill', tokens.muted).attr('font-size', '11px'));

    g.append('g').call(d3.axisLeft(y)).call((ax) => ax.select('.domain').remove()).call((ax) => ax.selectAll('line').remove())
      .call((ax) => ax.selectAll('text').attr('fill', tokens.text).attr('font-size', '11px'));

    g.selectAll('rect.cf-prot-gold')
      .data(protRows)
      .join('rect')
      .attr('x', 0)
      .attr('y', (d) => y(d.label))
      .attr('height', y.bandwidth())
      .attr('width', (d) => x(d.gold))
      .attr('rx', 2)
      .attr('fill', tokens.uc);

    g.selectAll('text.cf-prot-val')
      .data(protRows)
      .join('text')
      .attr('x', (d) => x(d.gold) + 5)
      .attr('y', (d) => y(d.label) + y.bandwidth() / 2 + 4)
      .attr('fill', tokens.muted)
      .attr('font-size', '11px')
      .text((d) => formatInt(d.gold));

    svg.append('text').attr('x', margin.left).attr('y', 12).attr('fill', tokens.muted).attr('font-size', '10.5px')
      .text('Os critérios se sobrepõem: um imóvel pode atender a mais de um.');
  }

  // Lista operacional da fila de vistoria: cria <li> uma vez e reordena via DOM
  function buildCarTableRows() {
    const listEl = document.getElementById('cf-car-tbody');
    if (!listEl || !loadedData) return;

    const list = loadedData.resumo.car_top50 || [];
    listEl.innerHTML = list.map((im) => {
      const layersBadges = [];
      if (im.atinge_rl) layersBadges.push('<span class="cf-tbl-tag cf-tag-rl">RL</span>');
      if (im.atinge_app) layersBadges.push('<span class="cf-tbl-tag cf-tag-app">APP</span>');
      if (im.atinge_uc1km) layersBadges.push('<span class="cf-tbl-tag cf-tag-uc">UC 1km</span>');

      return `
        <li class="cf-queue-item"
            data-cod="${escapeHtml(im.cod_imovel)}"
            data-rank="${im.rank}"
            data-ra="${escapeHtml(im.ra || '')}"
            data-situacao="${escapeHtml(im.situacao)}"
            data-indice="${im.indice}"
            data-anos_qtd="${im.anos_qtd}"
            data-area_ha="${im.area_ha}"
            data-focos_total="${im.focos_total}"
            data-focos_prot="${im.focos_prot}"
            data-search="${escapeHtml((im.cod_imovel + ' ' + im.situacao + ' ' + (im.condicao || '') + ' ' + (im.ra || '')).toLowerCase())}">
          <div class="cf-queue-chk-cell">
            <input type="checkbox" class="cf-car-chk-input" data-check-car="${escapeHtml(im.cod_imovel)}" aria-label="Selecionar imóvel #${im.rank} (${escapeHtml(im.ra || im.cod_imovel)})"/>
          </div>
          <div class="cf-queue-main">
            <div class="cf-queue-top">
              <button type="button" class="cf-queue-focus-btn" data-select-car="${escapeHtml(im.cod_imovel)}" title="${escapeHtml(im.cod_imovel)}">
                <span class="cf-queue-rank">#${im.rank}</span>
                <span class="cf-queue-ra">${escapeHtml(im.ra || 'DF')}</span>
              </button>
              <span class="cf-indice" title="Índice de prioridade">
                <span class="cf-indice-bar" aria-hidden="true"><span style="width:${Math.max(0, Math.min(100, Number(im.indice) || 0))}%"></span></span>
                <b>${formatDec(im.indice, 1)}</b>
              </span>
            </div>
            <div class="cf-queue-meta">
              <span title="${escapeHtml(SITUACAO_LABELS[im.situacao] || im.situacao)} · ${formatDec(im.area_ha, 0)} ha · ${im.anos_qtd} anos com foco · ${formatInt(im.focos_prot)} focos em área protegida">${formatDec(im.area_ha, 0)} ha · ${im.anos_qtd} anos · ${formatInt(im.focos_prot)} prot.</span>
              <span class="cf-queue-tags">${layersBadges.join('')}</span>
            </div>
          </div>
        </li>
      `;
    }).join('');

    listEl.querySelectorAll('.cf-queue-focus-btn').forEach((btn) => {
      btn.addEventListener('click', function () {
        selectCAR(this.getAttribute('data-select-car'), true);
      });
    });

    listEl.querySelectorAll('.cf-car-chk-input').forEach((chk) => {
      chk.addEventListener('change', function () {
        const cod = this.getAttribute('data-check-car');
        if (this.checked) state.checkedCars.add(cod);
        else state.checkedCars.delete(cod);
        refreshAll(false);
      });
    });

    setupTableSorting();
  }

  function setupTableSorting() {
    const sel = document.getElementById('cf-car-sort-select');
    if (sel && sel.dataset.bound !== 'true') {
      sel.dataset.bound = 'true';
      sel.addEventListener('change', function () {
        const parts = String(this.value || 'rank:asc').split(':');
        state.sortCol = parts[0] || 'rank';
        state.sortDir = parts[1] || 'asc';
        updateCarTable();
      });
    }
  }

  function updateCarTable() {
    const listEl = document.getElementById('cf-car-tbody');
    if (!listEl || !loadedData) return;

    const rows = Array.from(listEl.querySelectorAll('li.cf-queue-item'));
    const numericCols = new Set(['rank', 'indice', 'anos_qtd', 'area_ha', 'focos_total', 'focos_prot']);
    const dataType = numericCols.has(state.sortCol) ? 'number' : 'string';
    const mult = (state.sortDir === 'asc') ? 1 : -1;

    rows.sort((a, b) => {
      const av = a.getAttribute('data-' + state.sortCol) || '';
      const bv = b.getAttribute('data-' + state.sortCol) || '';
      if (dataType === 'number') {
        return (Number(av) - Number(bv)) * mult;
      }
      return av.localeCompare(bv, 'pt-BR') * mult;
    });

    // Reordena nos <li> existentes sem reconstruir o DOM via innerHTML
    const searchTerm = state.carSearch.trim().toLowerCase();
    const sitFilter = state.situacao !== 'todos' ? state.situacao : null;
    let visibleCount = 0;
    let checkedVisibleCount = 0;

    rows.forEach((row) => {
      const cod = row.getAttribute('data-cod');
      const sit = row.getAttribute('data-situacao');
      const hay = row.getAttribute('data-search') || '';
      const matches = (!sitFilter || sit === sitFilter) && (!searchTerm || hay.includes(searchTerm));
      const isChecked = state.checkedCars.has(cod);
      row.hidden = !matches;
      row.classList.toggle('is-checked', isChecked);
      row.classList.toggle('is-selected', cod === state.selectedCar);
      const chkEl = row.querySelector('.cf-car-chk-input');
      if (chkEl) chkEl.checked = isChecked;
      if (matches) {
        visibleCount += 1;
        if (isChecked) checkedVisibleCount += 1;
      }

      if (typeof listEl.moveBefore === 'function') {
        listEl.moveBefore(row, null);
      } else {
        listEl.appendChild(row);
      }
    });

    const masterChk = document.getElementById('cf-car-check-all');
    if (masterChk) {
      masterChk.checked = (visibleCount > 0 && checkedVisibleCount === visibleCount);
      masterChk.indeterminate = (checkedVisibleCount > 0 && checkedVisibleCount < visibleCount);
    }

    const totalLen = (loadedData.resumo.car_top50 || []).length;
    const btnTop5 = document.getElementById('cf-btn-car-top5');
    const btnAll = document.getElementById('cf-btn-car-all');
    const btnNone = document.getElementById('cf-btn-car-none');
    const btnFit = document.getElementById('cf-btn-car-fit');
    if (btnTop5) btnTop5.classList.toggle('is-active', isTop5Selection());
    if (btnAll) btnAll.classList.toggle('is-active', totalLen > 0 && state.checkedCars.size === totalLen);
    if (btnNone) btnNone.classList.toggle('is-active', state.checkedCars.size === 0);
    if (btnFit) btnFit.disabled = (state.checkedCars.size === 0);

    const selSummary = document.getElementById('cf-queue-sel-summary');
    if (selSummary) {
      selSummary.textContent = state.checkedCars.size > 0
        ? `${state.checkedCars.size} marcados filtrando o painel`
        : 'Nenhum marcado · DF completo (38.945 focos)';
    }

    const visCountEl = document.getElementById('cf-queue-vis-count');
    if (visCountEl) {
      visCountEl.textContent = `${visibleCount} de ${rows.length} exibidos`;
    }

    const stEl = document.getElementById('cf-table-status');
    if (stEl) {
      stEl.textContent = `${visibleCount} de ${rows.length} imóveis exibidos; ${state.checkedCars.size} marcados filtrando o painel.`;
    }
  }

  function selectRA(raIdx) {
    if (!loadedData) return;
    state.raIdx = (state.raIdx === raIdx) ? null : raIdx;
    if (state.raIdx !== null) {
      const feat = loadedData.rasGeo.features.find((f) => f.properties.idx === raIdx);
      if (feat) {
        zoomToFeature(feat, 10);
        if (window.CFLeafletBridge) window.CFLeafletBridge.focusFeature({ feature: feat });
      }
    } else {
      resetMapZoom();
    }
    syncControlsFromState();
    refreshAll(true);
  }

  function selectUC(ucIdx) {
    if (!loadedData) return;
    state.ucIdx = (state.ucIdx === ucIdx) ? null : ucIdx;
    if (state.ucIdx !== null) {
      const feat = loadedData.ucsGeo.features.find((f) => f.properties.idx === ucIdx);
      if (feat) {
        zoomToFeature(feat, 10);
        if (window.CFLeafletBridge) window.CFLeafletBridge.focusFeature({ feature: feat });
      }
    } else {
      resetMapZoom();
    }
    syncControlsFromState();
    refreshAll(true);
  }

  function selectCAR(codImovel, zoom) {
    if (!loadedData) return;
    state.selectedCar = (state.selectedCar === codImovel && !zoom) ? null : codImovel;
    const im = loadedData.carByCod.get(state.selectedCar);
    const geom = state.selectedCar ? loadedData.geometrias.car_top50_geoms[state.selectedCar] : null;

    if (zoom && geom && geom.imovel) {
      zoomToFeature({ type: 'Feature', geometry: geom.imovel, properties: {} }, 14);
      if (window.CFLeafletBridge) {
        window.CFLeafletBridge.focusFeature({
          geojson: geom.imovel,
          rlGeoms: geom.reserva_legal
        });
      }
    } else if (zoom && im) {
      if (window.CFLeafletBridge) window.CFLeafletBridge.focusFeature({ lat: im.lat, lon: im.lon, zoom: 13 });
    }

    refreshAll(true);
  }

  function syncLeafletBridge() {
    if (!window.CFLeafletBridge || !loadedData || !currentFiltered) return;
    if (state.tab === 'leaflet') {
      window.CFLeafletBridge.mount('corta-fogo-map', loadedData.leafletBundle);
    }
    window.CFLeafletBridge.updateView({
      focos: currentFiltered.focos,
      state: state
    });
  }

  function renderActiveTemporalChart() {
    if (state.temporalTab === 'mensal') renderMensalChart();
    else if (state.temporalTab === 'heatmap') renderHeatmapChart();
    else renderAnualChart();
  }

  function renderDeepChartsIfOpen() {
    const deep = document.getElementById('cf-deep-details');
    if (!deep || deep.open) {
      renderSensorOrSubdailyChart();
      renderCarAnalyticsChart();
    }
  }

  function refreshAll(refitProjection) {
    if (!loadedData) return;
    filterAndAggregate();
    updateKPIs();
    renderFilterChips();
    updateInspector(null);
    renderD3Map(Boolean(refitProjection));
    renderActiveTemporalChart();
    renderUcsRankingChart();
    renderDeepChartsIfOpen();
    updateCarTable();
    syncLeafletBridge();
    announceStatus(`${formatInt(currentAgg.total)} focos correspondem aos filtros ativos.`);
  }

  function startPlayback() {
    if (isPlaying) return;
    isPlaying = true;
    const btn = document.getElementById('cf-play-btn');
    if (btn) btn.textContent = 'Pausar';

    const speedSel = document.getElementById('cf-speed-select');
    const mult = speedSel ? Number(speedSel.value || 1) : 1;
    const delayMs = Math.round(1200 / mult);

    // Percorre o periodo escolhido ano a ano e, no fim, mostra o periodo inteiro antes de recomecar.
    const ini = state.ano === 'todos' ? ANO_MIN : state.ano;
    const fim = state.ano === 'todos' ? ANO_MAX : state.anoFim;
    let passo = 0;
    const mostrar = () => {
      const ano = ini + passo;
      if (ano > fim) setYearFilter(ini, true, fim);
      else setYearFilter(ano, true);
      refreshAll(false);
      passo = ano > fim ? 0 : passo + 1;
    };
    mostrar();
    playTimer = setInterval(mostrar, delayMs);
  }

  function stopPlayback() {
    isPlaying = false;
    if (playTimer) {
      clearInterval(playTimer);
      playTimer = null;
    }
    const btn = document.getElementById('cf-play-btn');
    if (btn) btn.textContent = 'Reproduzir';
  }

  function activateStageTab(tabId) {
    state.tab = tabId;
    const isD3 = (tabId === 'd3geo');
    const tabD3 = document.getElementById('tab-d3geo');
    const tabLeaf = document.getElementById('tab-leaflet');
    const panelD3 = document.getElementById('panel-d3geo');
    const panelLeaf = document.getElementById('panel-leaflet');

    if (tabD3) tabD3.setAttribute('aria-selected', isD3 ? 'true' : 'false');
    if (tabLeaf) tabLeaf.setAttribute('aria-selected', isD3 ? 'false' : 'true');
    if (panelD3) panelD3.hidden = !isD3;
    if (panelLeaf) panelLeaf.hidden = isD3;

    const d3OnlyToolbar = document.getElementById('cf-d3-toolbar-opts');
    const leafOnlyToolbar = document.getElementById('cf-leaflet-toolbar-opts');
    if (d3OnlyToolbar) d3OnlyToolbar.hidden = !isD3;
    if (leafOnlyToolbar) leafOnlyToolbar.hidden = isD3;

    if (!isD3 && window.CFLeafletBridge && loadedData) {
      window.CFLeafletBridge.mount('corta-fogo-map', loadedData.leafletBundle);
      syncLeafletBridge();
      window.CFLeafletBridge.invalidate();
      // Em tela cheia o mapa e bem maior: enquadra o DF para nao ficar pequeno no meio.
      const stageCard = document.getElementById('cf-stage-card');
      const emTelaCheia = stageCard && (document.fullscreenElement === stageCard || stageCard.classList.contains('cf-fullscreen-fallback'));
      const semFoco = state.raIdx === null && state.ucIdx === null && !state.selectedCar;
      if (emTelaCheia && semFoco && window.CFLeafletBridge.fitDf) window.CFLeafletBridge.fitDf();
    } else if (isD3) {
      renderD3Map(true);
    }
  }

  function toggleFullscreen() {
    const stage = document.getElementById('cf-stage-card');
    if (!stage) return;
    const isFs = (document.fullscreenElement === stage) ||
      (document.webkitFullscreenElement === stage) ||
      stage.classList.contains('cf-fullscreen-fallback');

    if (!isFs) {
      if (stage.requestFullscreen) {
        stage.requestFullscreen().catch(() => {
          stage.classList.add('cf-fullscreen-fallback');
          syncFullscreenUi();
        });
      } else {
        stage.classList.add('cf-fullscreen-fallback');
        syncFullscreenUi();
      }
    } else if (document.fullscreenElement) {
      document.exitFullscreen().catch(() => {});
    } else {
      stage.classList.remove('cf-fullscreen-fallback');
      syncFullscreenUi();
    }
  }

  function syncFullscreenUi() {
    const stage = document.getElementById('cf-stage-card');
    if (!stage) return;
    const isFs = (document.fullscreenElement === stage) || stage.classList.contains('cf-fullscreen-fallback');
    const btn = document.getElementById('cf-btn-fullscreen');
    if (btn) {
      btn.setAttribute('aria-pressed', isFs ? 'true' : 'false');
      btn.textContent = isFs ? 'Sair da tela cheia' : 'Tela cheia';
    }
    setTimeout(() => {
      renderD3Map(true);
      if (window.CFLeafletBridge) {
        window.CFLeafletBridge.invalidate();
        // Sem RA, UC ou imovel em foco, reenquadra o DF no novo tamanho do mapa.
        const semFoco = state.raIdx === null && state.ucIdx === null && !state.selectedCar;
        if (semFoco && window.CFLeafletBridge.fitDf) window.CFLeafletBridge.fitDf();
      }
    }, 120);
  }

  function bindDashboardEvents() {
    const slider = document.getElementById('cf-ano-slider');
    if (slider) {
      slider.addEventListener('input', function () {
        setYearFilter(Number(this.value) === 2026 ? 'todos' : Number(this.value), false);
        refreshAll(false);
      });
    }

    // De / Ate: escolher um "De" depois do "Ate" (ou o contrario) leva o outro junto.
    const selDe = document.getElementById('cf-ano-de');
    const selAte = document.getElementById('cf-ano-ate');
    const aplicarPeriodo = (mudou) => {
      let de = Number(selDe.value);
      let ate = Number(selAte.value);
      if (de > ate) {
        if (mudou === 'de') ate = de; else de = ate;
      }
      state.mes = null;
      setYearFilter(de, false, ate);
      refreshAll(false);
    };
    if (selDe && selAte) {
      selDe.addEventListener('change', () => aplicarPeriodo('de'));
      selAte.addEventListener('change', () => aplicarPeriodo('ate'));
    }

    const playBtn = document.getElementById('cf-play-btn');
    if (playBtn) {
      playBtn.addEventListener('click', function () {
        isPlaying ? stopPlayback() : startPlayback();
      });
    }

    const speedSel = document.getElementById('cf-speed-select');
    if (speedSel) {
      speedSel.addEventListener('change', function () {
        if (isPlaying) {
          stopPlayback();
          startPlayback();
        }
      });
    }

    const btnTodos = document.getElementById('cf-btn-todos');
    if (btnTodos) {
      btnTodos.addEventListener('click', function () {
        setYearFilter('todos', false);
        refreshAll(false);
      });
    }

    const bindSelect = (id, key) => {
      const el = document.getElementById(id);
      if (!el) return;
      el.addEventListener('change', function () {
        state[key] = this.value;
        refreshAll(false);
      });
    };
    bindSelect('cf-filter-estacao', 'estacao');
    bindSelect('cf-filter-sensor', 'sensor');
    bindSelect('cf-filter-situacao', 'situacao');

    const selRaEl = document.getElementById('cf-filter-ra');
    if (selRaEl) {
      selRaEl.addEventListener('change', function () {
        if (this.value === 'todos') {
          if (state.raIdx !== null) selectRA(state.raIdx);
        } else {
          const idx = Number(this.value);
          if (state.raIdx !== idx) selectRA(idx);
        }
      });
    }

    const resetAllBtn = document.getElementById('cf-btn-reset-filters');
    if (resetAllBtn) {
      resetAllBtn.addEventListener('click', function () {
        stopPlayback();
        state.ano = 'todos';
        state.anoFim = null;
        state.mes = null;
        state.estacao = 'todos';
        state.sensor = 'todos';
        state.situacao = 'todos';
        state.raIdx = null;
        state.ucIdx = null;
        state.selectedCar = null;
        state.checkedCars.clear();
        state.carSearch = '';
        const searchEl = document.getElementById('cf-car-search');
        if (searchEl) searchEl.value = '';
        resetMapZoom();
        syncControlsFromState();
        refreshAll(true);
      });
    }

    // Tabs do estagio espacial com navegacao por setas
    const tabList = document.getElementById('cf-stage-tablist');
    if (tabList) {
      const tabs = Array.from(tabList.querySelectorAll('[role="tab"]'));
      tabs.forEach((tab, idx) => {
        tab.addEventListener('click', () => activateStageTab(tab.id === 'tab-d3geo' ? 'd3geo' : 'leaflet'));
        tab.addEventListener('keydown', (e) => {
          if (e.key === 'ArrowRight' || e.key === 'ArrowLeft') {
            e.preventDefault();
            const next = e.key === 'ArrowRight' ? tabs[(idx + 1) % tabs.length] : tabs[(idx - 1 + tabs.length) % tabs.length];
            next.focus();
            next.click();
          }
        });
      });
    }

    // Modos do d3-geo
    document.querySelectorAll('#cf-d3-mode-group button[data-mode]').forEach((btn) => {
      btn.addEventListener('click', function () {
        state.d3Mode = this.getAttribute('data-mode');
        syncControlsFromState();
        renderD3Map(false);
      });
    });

    const choroTargetEl = document.getElementById('cf-choro-target');
    if (choroTargetEl) {
      choroTargetEl.addEventListener('change', function () {
        state.choroTarget = this.value;
        renderD3Map(false);
      });
    }
    const choroMetricEl = document.getElementById('cf-choro-metric');
    if (choroMetricEl) {
      choroMetricEl.addEventListener('change', function () {
        state.choroMetric = this.value;
        renderD3Map(false);
      });
    }

    // Botoes de zoom
    const zoomStep = (factor) => {
      const svg = d3.select('#cf-d3-svg');
      if (!svg.empty() && d3ZoomBehavior) {
        svg.transition().duration(transitionDuration(250)).call(d3ZoomBehavior.scaleBy, factor);
      }
    };
    const btnZIn = document.getElementById('cf-d3-zoom-in');
    const btnZOut = document.getElementById('cf-d3-zoom-out');
    const btnZReset = document.getElementById('cf-d3-zoom-reset');
    if (btnZIn) btnZIn.addEventListener('click', () => zoomStep(1.6));
    if (btnZOut) btnZOut.addEventListener('click', () => zoomStep(0.625));
    if (btnZReset) btnZReset.addEventListener('click', resetMapZoom);

    // Basemap Leaflet
    const baseSel = document.getElementById('cf-select-basemap');
    if (baseSel) {
      baseSel.addEventListener('change', function () {
        if (window.CFLeafletBridge) window.CFLeafletBridge.setBasemap(this.value);
      });
    }

    // Fullscreen
    const fsBtn = document.getElementById('cf-btn-fullscreen');
    if (fsBtn) fsBtn.addEventListener('click', toggleFullscreen);
    document.addEventListener('fullscreenchange', syncFullscreenUi);
    document.addEventListener('webkitfullscreenchange', syncFullscreenUi);

    // Checkboxes de camadas compartilhadas
    const layerInputs = [
      ['cf-layer-ras', 'ras'],
      ['cf-layer-ucs', 'ucs'],
      ['cf-layer-buffers', 'buffers'],
      ['cf-layer-imoveis', 'imoveis'],
      ['cf-layer-rl', 'rl'],
      ['cf-layer-focos', 'focos']
    ];
    layerInputs.forEach(([id, key]) => {
      const cb = document.getElementById(id);
      if (cb) {
        cb.addEventListener('change', function () {
          state.layers[key] = this.checked;
          syncControlsFromState();
          renderD3Map(false);
          if (window.CFLeafletBridge) window.CFLeafletBridge.setLayersVisible(state.layers);
        });
      }
    });

    const btnAdv = document.getElementById('cf-btn-adv-filters');
    const advDrawer = document.getElementById('cf-adv-drawer');
    if (btnAdv && advDrawer) {
      btnAdv.addEventListener('click', function () {
        const nextOpen = advDrawer.hidden;
        advDrawer.hidden = !nextOpen;
        btnAdv.setAttribute('aria-expanded', nextOpen ? 'true' : 'false');
      });
    }

    const btnLayers = document.getElementById('cf-btn-layers');
    const layerPopover = document.getElementById('cf-layer-popover');
    if (btnLayers && layerPopover) {
      btnLayers.addEventListener('click', function (e) {
        e.stopPropagation();
        const nextOpen = layerPopover.hidden;
        layerPopover.hidden = !nextOpen;
        btnLayers.setAttribute('aria-expanded', nextOpen ? 'true' : 'false');
      });
      document.addEventListener('click', function (e) {
        if (!layerPopover.hidden && !layerPopover.contains(e.target) && e.target !== btnLayers) {
          layerPopover.hidden = true;
          btnLayers.setAttribute('aria-expanded', 'false');
        }
      });
      document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape' && !layerPopover.hidden) {
          layerPopover.hidden = true;
          btnLayers.setAttribute('aria-expanded', 'false');
        }
      });
    }

    const tempTablist = document.getElementById('cf-temporal-tablist');
    if (tempTablist) {
      const tempTabs = Array.from(tempTablist.querySelectorAll('[role="tab"]'));
      const activateTempTab = (tabKey) => {
        state.temporalTab = tabKey;
        tempTabs.forEach((b) => {
          const active = b.getAttribute('data-temporal-tab') === tabKey;
          b.classList.toggle('is-active', active);
          b.setAttribute('aria-selected', active ? 'true' : 'false');
        });
        ['anual', 'mensal', 'heatmap'].forEach((k) => {
          const p = document.getElementById('panel-temp-' + k);
          if (p) p.hidden = (k !== tabKey);
        });
        renderActiveTemporalChart();
      };
      tempTabs.forEach((tab, idx) => {
        tab.addEventListener('click', () => activateTempTab(tab.getAttribute('data-temporal-tab')));
        tab.addEventListener('keydown', (e) => {
          if (e.key === 'ArrowRight' || e.key === 'ArrowLeft') {
            e.preventDefault();
            const next = e.key === 'ArrowRight' ? tempTabs[(idx + 1) % tempTabs.length] : tempTabs[(idx - 1 + tempTabs.length) % tempTabs.length];
            next.focus();
            next.click();
          }
        });
      });
    }

    const deepDetails = document.getElementById('cf-deep-details');
    if (deepDetails) {
      deepDetails.addEventListener('toggle', function () {
        if (this.open) {
          renderSensorOrSubdailyChart();
          renderCarAnalyticsChart();
        }
      });
    }

    // Alternadores internos dos cards de graficos
    document.querySelectorAll('[data-anual-mode]').forEach((btn) => {
      btn.addEventListener('click', function () {
        state.anualMode = this.getAttribute('data-anual-mode');
        document.querySelectorAll('[data-anual-mode]').forEach((b) => b.classList.toggle('is-active', b === this));
        renderAnualChart();
      });
    });

    document.querySelectorAll('[data-sensor-tab]').forEach((btn) => {
      btn.addEventListener('click', function () {
        state.sensorTab = this.getAttribute('data-sensor-tab');
        document.querySelectorAll('[data-sensor-tab]').forEach((b) => {
          const active = (b === this);
          b.classList.toggle('is-active', active);
          b.setAttribute('aria-selected', active ? 'true' : 'false');
        });
        renderSensorOrSubdailyChart();
      });
    });

    document.querySelectorAll('[data-uc-metric]').forEach((btn) => {
      btn.addEventListener('click', function () {
        state.ucMetric = this.getAttribute('data-uc-metric');
        document.querySelectorAll('[data-uc-metric]').forEach((b) => b.classList.toggle('is-active', b === this));
        renderUcsRankingChart();
      });
    });

    document.querySelectorAll('[data-car-tab]').forEach((btn) => {
      btn.addEventListener('click', function () {
        state.carSubTab = this.getAttribute('data-car-tab');
        document.querySelectorAll('[data-car-tab]').forEach((b) => {
          const active = (b === this);
          b.classList.toggle('is-active', active);
          b.setAttribute('aria-selected', active ? 'true' : 'false');
        });
        renderCarAnalyticsChart();
      });
    });

    const carSearch = document.getElementById('cf-car-search');
    if (carSearch) {
      carSearch.addEventListener('input', function () {
        state.carSearch = this.value;
        updateCarTable();
      });
    }

    const masterChk = document.getElementById('cf-car-check-all');
    if (masterChk) {
      masterChk.addEventListener('change', function () {
        const listEl = document.getElementById('cf-car-tbody');
        if (!listEl) return;
        const rows = listEl.querySelectorAll('li.cf-queue-item');
        rows.forEach((row) => {
          if (row.hidden) return;
          const cod = row.getAttribute('data-cod');
          if (!cod) return;
          if (this.checked) state.checkedCars.add(cod);
          else state.checkedCars.delete(cod);
        });
        refreshAll(false);
      });
    }

    const btnTop5 = document.getElementById('cf-btn-car-top5');
    if (btnTop5) {
      btnTop5.addEventListener('click', function () {
        state.checkedCars = new Set(state.defaultTop5Cods || []);
        refreshAll(false);
      });
    }

    const btnAll = document.getElementById('cf-btn-car-all');
    if (btnAll) {
      btnAll.addEventListener('click', function () {
        const list = (loadedData && loadedData.resumo && loadedData.resumo.car_top50) || [];
        state.checkedCars = new Set(list.map((im) => im.cod_imovel));
        refreshAll(false);
      });
    }

    const btnNone = document.getElementById('cf-btn-car-none');
    if (btnNone) {
      btnNone.addEventListener('click', function () {
        state.checkedCars.clear();
        refreshAll(false);
      });
    }

    const btnFit = document.getElementById('cf-btn-car-fit');
    if (btnFit) {
      btnFit.addEventListener('click', function () {
        if (!loadedData || state.checkedCars.size === 0) return;
        const d3Feats = [];
        const rawFeats = [];
        state.checkedCars.forEach((cod) => {
          const g = loadedData.geometrias.car_top50_geoms[cod];
          if (g && g.imovel) {
            const rawFeat = { type: 'Feature', geometry: g.imovel, properties: {} };
            rawFeats.push(rawFeat);
            const rew = rewindFeature(rawFeat);
            if (rew) d3Feats.push(rew);
          }
        });
        if (d3Feats.length > 0) {
          zoomToFeature({ type: 'FeatureCollection', features: d3Feats }, 13);
          if (window.CFLeafletBridge) {
            window.CFLeafletBridge.focusFeature({ features: rawFeats });
          }
        }
      });
    }
  }

  function cleanup() {
    stopPlayback();
    hideTooltip();
    if (resizeObserver) {
      resizeObserver.disconnect();
      resizeObserver = null;
    }
    if (themeObserver) {
      themeObserver.disconnect();
      themeObserver = null;
    }
    if (motionMediaQuery && motionMediaQuery._cfHandler) {
      motionMediaQuery.removeEventListener('change', motionMediaQuery._cfHandler);
      motionMediaQuery = null;
    }
    d3Projection = null;
  }

  function initDashboard() {
    const root = document.getElementById('cf-dashboard-root');
    if (!root) {
      cleanup();
      return;
    }
    if (root.dataset.mounted === 'true') return;
    if (typeof d3 === 'undefined') {
      setTimeout(initDashboard, 120);
      return;
    }

    root.dataset.mounted = 'true';
    const loadingEl = document.getElementById('cf-loading-banner');

    bindDashboardEvents();
    syncControlsFromState();

    loadAllData()
      .then(() => {
        if (!document.getElementById('cf-dashboard-root')) return;
        if (loadingEl) loadingEl.hidden = true;

        renderResposta();
        buildCarTableRows();
        syncControlsFromState();
        refreshAll(true);

        if (typeof ResizeObserver !== 'undefined') {
          let timer = null;
          resizeObserver = new ResizeObserver(() => {
            if (timer) clearTimeout(timer);
            timer = setTimeout(() => {
              renderD3Map(true);
              renderActiveTemporalChart();
              renderUcsRankingChart();
              renderDeepChartsIfOpen();
            }, 90);
          });
          resizeObserver.observe(root);
        }

        if (typeof MutationObserver !== 'undefined' && document.body) {
          themeObserver = new MutationObserver(() => {
            refreshAll(false);
          });
          themeObserver.observe(document.body, {
            attributes: true,
            attributeFilter: ['data-md-color-scheme']
          });
        }

        if (window.matchMedia) {
          motionMediaQuery = window.matchMedia('(prefers-color-scheme: dark)');
          motionMediaQuery._cfHandler = () => refreshAll(false);
          motionMediaQuery.addEventListener('change', motionMediaQuery._cfHandler);
        }
      })
      .catch((err) => {
        if (loadingEl) {
          loadingEl.hidden = false;
          loadingEl.innerHTML = `<strong>Erro ao carregar dados do dashboard:</strong> ${escapeHtml(err.message)}`;
        }
      });
  }

  window.CFDashboardBridge = {
    selectRA: selectRA,
    selectUC: selectUC,
    selectCAR: selectCAR
  };

  if (window.document$) {
    window.document$.subscribe(() => {
      initDashboard();
    });
  } else if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initDashboard);
  } else {
    initDashboard();
  }
})();
