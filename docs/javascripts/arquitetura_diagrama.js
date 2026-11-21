/**
 * Diagrama interativo de arquitetura em camadas (Bronze, Silver e Gold).
 * Renderiza nos HTML legiveis em escala real com conectores SVG em D3.js
 * e rastreamento de linhagem (upstream/downstream) ao passar ou clicar.
 */
(function () {
  const NODES = [
    // Bronze / Fontes
    {
      id: 'delta_foco_calor',
      layer: 'bronze',
      col: 0,
      nome: 'foco_calor',
      tipo: 'Delta Lake · Lote',
      linhas: '38.945',
      papel: 'Série histórica de focos de calor do INPE (2015–2025), particionada por ano/mês.'
    },
    {
      id: 'delta_imovel_car',
      layer: 'bronze',
      col: 0,
      nome: 'imovel_car',
      tipo: 'Delta Lake · CDC',
      linhas: '21.047',
      papel: 'Perímetros rurais do CAR replicados via WAL do PostgreSQL com controle de exclusão.'
    },
    {
      id: 'postgis_territorio',
      layer: 'bronze',
      col: 0,
      nome: 'UC · APP · RL · RA',
      tipo: 'PostGIS (EPSG:31983)',
      linhas: '15.851',
      papel: '84 UCs, 2.234 APPs, 13.499 Reservas Legais e 37 Regiões Administrativas.'
    },
    // Silver · Staging
    {
      id: 'stg_focos_calor',
      layer: 'silver',
      sub: 'Staging (views)',
      col: 1,
      nome: 'stg_focos_calor',
      tipo: 'View SQL',
      linhas: '38.945',
      papel: 'Padroniza fuso local (America/Sao_Paulo), coordenadas e chaves de satélite.'
    },
    {
      id: 'stg_imoveis_car',
      layer: 'silver',
      sub: 'Staging (views)',
      col: 1,
      nome: 'stg_imoveis_car',
      tipo: 'View SQL',
      linhas: '21.047',
      papel: 'Limpa atributos cadastrais e prepara alterações históricas para o snapshot.'
    },
    {
      id: 'stg_territorio',
      layer: 'silver',
      sub: 'Staging (views)',
      col: 1,
      nome: 'stg_unidades / app / rl / ra',
      tipo: 'Views SQL',
      linhas: '15.851',
      papel: 'Padroniza geometrias protegidas e gera faixa de amortecimento de 1 km nas UCs.'
    },
    // Silver · Snapshot & Intermediate
    {
      id: 'snp_imovel_car',
      layer: 'silver',
      sub: 'Intermediate & SCD2',
      col: 2,
      nome: 'snp_imovel_car',
      tipo: 'Snapshot SCD2',
      linhas: '21.049',
      papel: 'Preserva histórico de perímetros e situação cadastral por versão.'
    },
    {
      id: 'int_imoveis_versoes',
      layer: 'silver',
      sub: 'Intermediate & SCD2',
      col: 2,
      nome: 'int_imoveis_versoes',
      tipo: 'Tabela',
      linhas: '21.049',
      papel: 'Define intervalos de vigência [dbt_valid_from, dbt_valid_to) para cruzamento histórico.'
    },
    {
      id: 'int_focos_imoveis',
      layer: 'silver',
      sub: 'Intermediate & SCD2',
      col: 2,
      nome: 'int_focos_imoveis',
      tipo: 'Tabela N:N',
      linhas: '—',
      papel: 'Cruza cada foco com a versão do imóvel vigente na data do evento.'
    },
    {
      id: 'int_focos_areas_protegidas',
      layer: 'silver',
      sub: 'Intermediate & SCD2',
      col: 2,
      nome: 'int_focos_areas_protegidas',
      tipo: 'Tabela espacial',
      linhas: '—',
      papel: 'Identifica focos em Reserva Legal, APP ou faixa de 1 km de UC.'
    },
    {
      id: 'int_focos_protegidos_imovel',
      layer: 'silver',
      sub: 'Intermediate & SCD2',
      col: 2,
      nome: 'int_focos_protegidos_imovel',
      tipo: 'Tabela',
      linhas: '—',
      papel: 'Aplica a regra central: foco em área protegida dentro do perímetro do imóvel.'
    },
    {
      id: 'int_metricas_indice',
      layer: 'silver',
      sub: 'Intermediate & SCD2',
      col: 2,
      nome: 'int_metricas + int_indice',
      tipo: 'Tabelas',
      linhas: '4.068',
      papel: 'Calcula recorrência, recência, dias/100 ha (piso 14,1 ha) e quartis de prioridade.'
    },
    {
      id: 'int_focos_territorio',
      layer: 'silver',
      sub: 'Intermediate & SCD2',
      col: 2,
      nome: 'int_focos_territorio',
      tipo: 'Tabela',
      linhas: '38.944',
      papel: 'Consolida flags territoriais por detecção de foco para a fato atômica.'
    },
    // Gold · Modelo Estrela & Fila
    {
      id: 'dim_tempo_sat_ra_terr',
      layer: 'gold',
      col: 3,
      nome: 'dim_tempo · satelite · ra · territorio',
      tipo: 'Dimensões',
      linhas: '4 dims',
      papel: 'Dimensões de tempo (4.018), satélites (20), RAs (37) e áreas protegidas (15.814).'
    },
    {
      id: 'dim_imovel_car',
      layer: 'gold',
      col: 3,
      nome: 'dim_imovel_car',
      tipo: 'Dimensão SCD2',
      linhas: '21.049',
      papel: 'Interface de consumo das versões cadastrais históricas (sk_imovel).'
    },
    {
      id: 'fato_foco_calor',
      layer: 'gold',
      col: 3,
      nome: 'fato_foco_calor',
      tipo: 'Fato atômica',
      linhas: '38.944',
      papel: 'Uma linha por detecção de foco (tempo × espaço × satélite), sem explodir por imóvel.'
    },
    {
      id: 'fct_reincidencia_imovel',
      layer: 'gold',
      col: 3,
      nome: 'fct_reincidencia_imovel',
      tipo: 'Fato do imóvel',
      linhas: '4.068',
      papel: 'Sujeito da pergunta de gestão: contagens e índice de prioridade por imóvel.'
    },
    {
      id: 'mart_reincidencia_imovel_ano',
      layer: 'gold',
      col: 3,
      nome: 'mart_reincidencia_imovel_ano',
      tipo: 'Mart anual',
      linhas: '8.271',
      papel: 'Série anual de reincidência por imóvel × ano civil UTC.'
    },
    {
      id: 'painel_imoveis_prioritarios',
      layer: 'gold',
      col: 3,
      nome: 'painel_imoveis_prioritarios',
      tipo: 'Tabela de consumo',
      linhas: '1.593',
      papel: 'Fila ordenada de vistoria (>= 2 anos) com contrato de esquema e frescor de 30h.'
    },
    // Orquestração & Consumo
    {
      id: 'dagster_orquestracao',
      layer: 'ops',
      col: 4,
      nome: 'Dagster (Orquestração)',
      tipo: 'Agenda · Retry · Backfill',
      linhas: '03:00 BRT',
      papel: 'Executa pipeline Silver/Gold diariamente às 03h e verifica SLA de frescor.'
    },
    {
      id: 'dashboard_consumo',
      layer: 'ops',
      col: 4,
      nome: 'Dashboard Interativo',
      tipo: 'gold.json + D3 / Leaflet',
      linhas: 'Top 50 + DF',
      papel: 'Painel web exportado por exportar_painel_gold.py para apoio à vistoria em campo.'
    }
  ];

  const EDGES = [
    ['delta_foco_calor', 'stg_focos_calor'],
    ['delta_imovel_car', 'stg_imoveis_car'],
    ['postgis_territorio', 'stg_territorio'],

    ['stg_imoveis_car', 'snp_imovel_car'],
    ['snp_imovel_car', 'int_imoveis_versoes'],
    ['int_imoveis_versoes', 'dim_imovel_car'],

    ['stg_focos_calor', 'int_focos_imoveis'],
    ['int_imoveis_versoes', 'int_focos_imoveis'],
    ['stg_focos_calor', 'int_focos_areas_protegidas'],
    ['stg_territorio', 'int_focos_areas_protegidas'],

    ['int_focos_imoveis', 'int_focos_protegidos_imovel'],
    ['int_focos_areas_protegidas', 'int_focos_protegidos_imovel'],
    ['int_focos_protegidos_imovel', 'int_metricas_indice'],
    ['int_focos_protegidos_imovel', 'mart_reincidencia_imovel_ano'],

    ['stg_focos_calor', 'int_focos_territorio'],
    ['int_focos_imoveis', 'int_focos_territorio'],
    ['int_focos_areas_protegidas', 'int_focos_territorio'],

    ['stg_focos_calor', 'dim_tempo_sat_ra_terr'],
    ['stg_territorio', 'dim_tempo_sat_ra_terr'],

    ['int_focos_territorio', 'fato_foco_calor'],
    ['dim_tempo_sat_ra_terr', 'fato_foco_calor'],
    ['int_metricas_indice', 'fct_reincidencia_imovel'],
    ['dim_imovel_car', 'fct_reincidencia_imovel'],

    ['fct_reincidencia_imovel', 'painel_imoveis_prioritarios'],
    ['dim_imovel_car', 'painel_imoveis_prioritarios'],
    ['dim_tempo_sat_ra_terr', 'painel_imoveis_prioritarios'],

    ['painel_imoveis_prioritarios', 'dashboard_consumo'],
    ['fct_reincidencia_imovel', 'dashboard_consumo'],
    ['dagster_orquestracao', 'painel_imoveis_prioritarios']
  ];

  const COLUMNS = [
    { col: 0, title: 'Bronze', layer: 'bronze' },
    { col: 1, title: 'Silver · Staging', layer: 'silver' },
    { col: 2, title: 'Silver · Intermediate', layer: 'silver' },
    { col: 3, title: 'Gold', layer: 'gold' },
    { col: 4, title: 'Consumo', layer: 'ops' }
  ];

  const LAYER_LABELS = {
    bronze: 'Bronze (Fontes)',
    silver: 'Silver (Transformação)',
    gold: 'Gold (Modelo Estrela)',
    ops: 'Orquestração & Consumo'
  };

  function escapeHtml(text) {
    return String(text == null ? '' : text)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function buildGraphLookup() {
    const byId = new Map();
    const parents = new Map();
    const children = new Map();
    NODES.forEach((n) => {
      byId.set(n.id, n);
      parents.set(n.id, []);
      children.set(n.id, []);
    });
    EDGES.forEach(([src, dst]) => {
      if (children.has(src) && parents.has(dst)) {
        children.get(src).push(dst);
        parents.get(dst).push(src);
      }
    });
    return { byId: byId, parents: parents, children: children };
  }

  function collectAncestors(startId, parents) {
    const visited = new Set();
    const queue = [startId];
    while (queue.length > 0) {
      const cur = queue.shift();
      const list = parents.get(cur) || [];
      for (let i = 0; i < list.length; i += 1) {
        if (!visited.has(list[i])) {
          visited.add(list[i]);
          queue.push(list[i]);
        }
      }
    }
    return visited;
  }

  function collectDescendants(startId, children) {
    const visited = new Set();
    const queue = [startId];
    while (queue.length > 0) {
      const cur = queue.shift();
      const list = children.get(cur) || [];
      for (let i = 0; i < list.length; i += 1) {
        if (!visited.has(list[i])) {
          visited.add(list[i]);
          queue.push(list[i]);
        }
      }
    }
    return visited;
  }

  function mountWidget(root) {
    if (!root || root.dataset.archInit === 'true') return;
    root.dataset.archInit = 'true';

    const graph = buildGraphLookup();
    let layerFilter = 'all';
    let searchTerm = '';
    let lockedId = null;
    let hoverId = null;

    root.innerHTML = `
      <div class="cf-arch-toolbar">
        <div class="cf-arch-filters" role="group" aria-label="Filtrar camadas da arquitetura">
          <button type="button" class="cf-arch-pill is-active" data-arch-layer="all" aria-pressed="true">Todas as camadas</button>
          <button type="button" class="cf-arch-pill" data-arch-layer="bronze" aria-pressed="false">Bronze</button>
          <button type="button" class="cf-arch-pill" data-arch-layer="silver" aria-pressed="false">Silver</button>
          <button type="button" class="cf-arch-pill" data-arch-layer="gold" aria-pressed="false">Gold</button>
          <button type="button" class="cf-arch-pill" data-arch-layer="ops" aria-pressed="false">Orquestração &amp; Consumo</button>
        </div>
        <div class="cf-arch-tools">
          <label class="cf-arch-search-wrap">
            <span class="cf-sr-only">Buscar tabela ou modelo na arquitetura</span>
            <input type="search" class="cf-arch-search" placeholder="Buscar tabela (ex.: fato_foco_calor)..."/>
          </label>
          <button type="button" class="cf-arch-clear-btn" hidden>Limpar seleção</button>
        </div>
      </div>
      <div class="cf-arch-detail" role="status" aria-live="polite">
        Passe o mouse ou clique em qualquer tabela para destacar sua origem (upstream) e destino (downstream).
      </div>
      <div class="cf-arch-scroll">
        <div class="cf-arch-stage">
          <svg class="cf-arch-links" aria-hidden="true"></svg>
          <div class="cf-arch-columns"></div>
        </div>
      </div>
    `;

    const colsEl = root.querySelector('.cf-arch-columns');
    const stageEl = root.querySelector('.cf-arch-stage');
    const svgEl = root.querySelector('.cf-arch-links');
    const detailEl = root.querySelector('.cf-arch-detail');
    const clearBtn = root.querySelector('.cf-arch-clear-btn');
    const searchInput = root.querySelector('.cf-arch-search');

    colsEl.innerHTML = COLUMNS.map((c) => {
      const colNodes = NODES.filter((n) => n.col === c.col);
      const cardsHtml = colNodes.map((n) => {
        const rowsHtml = (n.linhas && n.linhas !== '—')
          ? `<span class="cf-arch-node-rows">${escapeHtml(n.linhas)}</span>`
          : '';
        return `
        <button type="button" class="cf-arch-node cf-arch-node--${n.layer}" data-node-id="${n.id}">
          <div class="cf-arch-node-head">
            <span class="cf-arch-node-name">${escapeHtml(n.nome)}</span>
            ${rowsHtml}
          </div>
        </button>
      `;
      }).join('');

      return `
        <div class="cf-arch-col cf-arch-col--${c.layer}" data-col-layer="${c.layer}">
          <div class="cf-arch-col-head">
            <strong>${escapeHtml(c.title)}</strong>
          </div>
          <div class="cf-arch-col-body">${cardsHtml}</div>
        </div>
      `;
    }).join('');

    const nodeEls = new Map();
    root.querySelectorAll('.cf-arch-node').forEach((el) => {
      nodeEls.set(el.getAttribute('data-node-id'), el);
    });

    function drawEdges(activeId, ancestors, descendants) {
      const rectStage = stageEl.getBoundingClientRect();
      const w = Math.max(stageEl.scrollWidth, rectStage.width);
      const h = Math.max(stageEl.scrollHeight, rectStage.height);
      svgEl.setAttribute('width', String(Math.round(w)));
      svgEl.setAttribute('height', String(Math.round(h)));
      svgEl.setAttribute('viewBox', `0 0 ${Math.round(w)} ${Math.round(h)}`);

      const pathsHtml = [];
      EDGES.forEach(([srcId, dstId]) => {
        const srcEl = nodeEls.get(srcId);
        const dstEl = nodeEls.get(dstId);
        if (!srcEl || !dstEl) return;

        const r1 = srcEl.getBoundingClientRect();
        const r2 = dstEl.getBoundingClientRect();
        if (r1.width === 0 || r2.width === 0) return;

        const x1 = r1.right - rectStage.left;
        const y1 = r1.top + r1.height / 2 - rectStage.top;
        const x2 = r2.left - rectStage.left;
        const y2 = r2.top + r2.height / 2 - rectStage.top;
        const dx = Math.max(24, Math.abs(x2 - x1) * 0.48);

        let cls = 'cf-arch-edge';
        if (activeId) {
          const isUp = (dstId === activeId || (ancestors.has(dstId) && (ancestors.has(srcId) || srcId === activeId))) && (ancestors.has(srcId) || srcId === activeId);
          const isDown = (srcId === activeId || (descendants.has(srcId) && (descendants.has(dstId) || dstId === activeId))) && (descendants.has(dstId) || dstId === activeId);
          if (isUp) cls += ' is-upstream';
          else if (isDown) cls += ' is-downstream';
          else cls += ' is-dimmed';
        }

        const d = `M ${x1.toFixed(1)} ${y1.toFixed(1)} C ${(x1 + dx).toFixed(1)} ${y1.toFixed(1)}, ${(x2 - dx).toFixed(1)} ${y2.toFixed(1)}, ${x2.toFixed(1)} ${y2.toFixed(1)}`;
        pathsHtml.push(`<path class="${cls}" d="${d}"/>`);
      });

      svgEl.innerHTML = pathsHtml.join('');
    }

    function updateState() {
      const focusId = hoverId || lockedId;
      const ancestors = focusId ? collectAncestors(focusId, graph.parents) : new Set();
      const descendants = focusId ? collectDescendants(focusId, graph.children) : new Set();
      const term = searchTerm.trim().toLowerCase();

      clearBtn.hidden = !lockedId;

      root.querySelectorAll('.cf-arch-col').forEach((colEl) => {
        const colLayer = colEl.getAttribute('data-col-layer');
        colEl.classList.toggle('is-layer-muted', layerFilter !== 'all' && colLayer !== layerFilter);
      });

      nodeEls.forEach((el, id) => {
        const node = graph.byId.get(id);
        const matchesLayer = (layerFilter === 'all' || node.layer === layerFilter);
        const matchesSearch = !term
          || node.nome.toLowerCase().includes(term)
          || node.tipo.toLowerCase().includes(term)
          || node.papel.toLowerCase().includes(term);

        let dim = !matchesLayer || (Boolean(term) && !matchesSearch);
        el.classList.toggle('is-focus', id === focusId);
        el.classList.toggle('is-upstream', ancestors.has(id));
        el.classList.toggle('is-downstream', descendants.has(id));

        if (focusId) {
          const inLineage = (id === focusId || ancestors.has(id) || descendants.has(id));
          dim = dim || !inLineage;
        }
        el.classList.toggle('is-dimmed', dim);
        el.classList.toggle('is-search-hit', Boolean(term) && matchesSearch);
      });

      if (focusId && graph.byId.has(focusId)) {
        const n = graph.byId.get(focusId);
        const ups = (graph.parents.get(focusId) || []).map((id) => `<code>${escapeHtml(graph.byId.get(id).nome)}</code>`).join(', ') || 'Origem direta';
        const downs = (graph.children.get(focusId) || []).map((id) => `<code>${escapeHtml(graph.byId.get(id).nome)}</code>`).join(', ') || 'Consumo final';
        const metaText = (n.linhas && n.linhas !== '—') ? `${n.tipo} · ${n.linhas}` : n.tipo;
        detailEl.innerHTML = `
          <div class="cf-arch-detail-row">
            <span class="cf-arch-badge cf-arch-badge--${n.layer}">${escapeHtml(LAYER_LABELS[n.layer])}</span>
            <strong><code>${escapeHtml(n.nome)}</code></strong>
            <span class="cf-muted">${escapeHtml(metaText)}</span>
          </div>
          <p class="cf-arch-detail-papel">${escapeHtml(n.papel)}</p>
          <div class="cf-arch-detail-lin">
            <span><strong>Recebe de:</strong> ${ups}</span>
            <span><strong>Alimenta:</strong> ${downs}</span>
          </div>
        `;
      } else {
        detailEl.textContent = 'Passe o mouse ou clique em qualquer tabela para destacar sua origem (upstream) e destino (downstream).';
      }

      requestAnimationFrame(() => drawEdges(focusId, ancestors, descendants));
    }

    root.querySelectorAll('.cf-arch-pill').forEach((btn) => {
      btn.addEventListener('click', function () {
        layerFilter = this.getAttribute('data-arch-layer');
        root.querySelectorAll('.cf-arch-pill').forEach((b) => {
          const act = (b === this);
          b.classList.toggle('is-active', act);
          b.setAttribute('aria-pressed', act ? 'true' : 'false');
        });
        updateState();
      });
    });

    if (searchInput) {
      searchInput.addEventListener('input', function () {
        searchTerm = this.value;
        updateState();
      });
    }

    clearBtn.addEventListener('click', function () {
      lockedId = null;
      hoverId = null;
      updateState();
    });

    nodeEls.forEach((el, id) => {
      el.addEventListener('mouseenter', function () {
        hoverId = id;
        updateState();
      });
      el.addEventListener('mouseleave', function () {
        hoverId = null;
        updateState();
      });
      el.addEventListener('click', function () {
        lockedId = (lockedId === id) ? null : id;
        updateState();
      });
    });

    if (typeof ResizeObserver !== 'undefined') {
      const ro = new ResizeObserver(() => updateState());
      ro.observe(stageEl);
    }

    updateState();
  }

  function initAll() {
    document.querySelectorAll('[data-cf-arch]').forEach(mountWidget);
  }

  if (window.document$) {
    window.document$.subscribe(initAll);
  } else if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initAll);
  } else {
    initAll();
  }
})();
