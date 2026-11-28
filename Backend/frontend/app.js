function escapeHtml(val) {
  return String(val ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

const STAFF = [
      { initials: 'NM', name: 'Naledi Mokoena', role: 'QA lead' },
      { initials: 'SP', name: 'Sipho Peters', role: 'Site technician' },
      { initials: 'AD', name: 'Aisha Dlamini', role: 'Pharmacist' },
      { initials: 'JV', name: 'Johan van Wyk', role: 'Logistics' },
      { initials: 'TK', name: 'Thandi Kumalo', role: 'Inventory analyst' },
      { initials: 'RM', name: 'Ravi Moodley', role: 'Facilities' }
    ];

    let appData = { units: [], batches: [], investigations: [], tasks: [], datasetFile: 'cold_chain_labeled_2022_2026.csv' };
    let activeTab = 'home';
    let prevTab = 'home';
    let batchFilter = 'ALL';
    let batchSort = 'hottest';
    let searchQuery = '';
    let selectedSimUnit = null;
    let selectedInvId = null;
    let selectedStaff = 'Naledi Mokoena';
    let invSubTab = 'Timeline';


    const API_KEY_STORAGE_KEY = 'coldtrace_api_key';

    function resolveApiKey() {
      const inputEl = document.getElementById('apiKey');
      const fromInput = inputEl && inputEl.value ? inputEl.value.trim() : '';
      if (fromInput) {
        try { localStorage.setItem(API_KEY_STORAGE_KEY, fromInput); } catch (_) {}
        return fromInput;
      }
      try {
        const fromStorage = (localStorage.getItem(API_KEY_STORAGE_KEY) || '').trim();
        if (fromStorage) return fromStorage;
      } catch (_) {}
      try {
        const params = new URLSearchParams(window.location.search);
        const fromQuery = (params.get('api_key') || '').trim();
        if (fromQuery) {
          localStorage.setItem(API_KEY_STORAGE_KEY, fromQuery);
          return fromQuery;
        }
      } catch (_) {}
      return '';
    }

    const headers = () => ({
      'Content-Type': 'application/json',
      'X-API-Key': resolveApiKey()
    });

    function showToast(msg) {
      const t = document.getElementById('toastMsg');
      t.innerText = msg;
      t.classList.add('show');
      setTimeout(() => t.classList.remove('show'), 2800);
    }

    function toggleConfig() {
      document.getElementById('configDrawer').classList.toggle('open');
    }

    function handleSearch(q) {
      searchQuery = q.trim().toLowerCase();
      renderHome();
      renderBatches();
      renderInvestigations();
    }

    function switchTab(tab) {
      prevTab = activeTab;
      activeTab = tab;
      document.getElementById('mainHeader').style.display = 'block';
      ['home', 'batches', 'investigations', 'quality', 'batch-detail', 'inv-detail'].forEach(s => {
        document.getElementById('screen-' + s).style.display = (s === tab) ? 'block' : 'none';
      });
      ['home', 'batches', 'investigations', 'quality'].forEach(t => {
        const b = document.getElementById('tab-' + t);
        const sb = document.getElementById('snav-' + t);
        if (b) b.classList.toggle('active', t === tab);
        if (sb) sb.classList.toggle('active', t === tab);
      });
      routeTo('#' + tab);
      if (tab === 'quality') loadInsights();
    }

    // Shareable URLs + working Back button: #home, #batches, #investigations, #quality,
    // #batch/<code>, #inv/<id>. pushState adds history entries; popstate replays them.
    let routing = false;
    function routeTo(hash) {
      if (routing || window.location.hash === hash) return;
      try { history.pushState({ hash }, '', hash); } catch (_) {}
    }
    function applyRoute() {
      const h = (window.location.hash || '#home').slice(1);
      routing = true;
      try {
        if (h.startsWith('batch/')) openBatchDetail(decodeURIComponent(h.slice(6)));
        else if (h.startsWith('inv/')) openInvestigationDetail(decodeURIComponent(h.slice(4)));
        else if (['home', 'batches', 'investigations', 'quality'].includes(h)) switchTab(h);
      } finally { routing = false; }
    }
    window.addEventListener('popstate', applyRoute);

    function goBackFromDetail() {
      switchTab(prevTab === 'batches' ? 'batches' : 'home');
    }

      function stepperHTML(stageIndex, opts = {}) {
        const stages = ['In storage', 'Monitoring', 'Investigation', 'Resolution'];
        const isClosed = Boolean(opts.closed);
        const maxActiveStage = isClosed ? 3 : Math.min(Number(stageIndex) || 0, 2);
        return `<div class="stepper" aria-label="Batch progress" aria-disabled="true">
          <div class="step-line"></div>
          ${stages.map((st, idx) => {
            const isCompletedStage = (idx < maxActiveStage) || (idx === 3 && isClosed);
            const isCurrentStage = !isCompletedStage && (idx === maxActiveStage);
            const cls = isCompletedStage ? 'done' : (isCurrentStage ? 'current' : 'pending');
            const dot = isCompletedStage ? '✓' : '';
            return `<div class="step ${cls}" style="${cls === 'pending' ? 'opacity:0.45;' : ''}"><div class="step-dot">${dot}</div><div class="step-label">${st}</div></div>`;
          }).join('')}
        </div>`;
      }

    function sparklineHTML(series, height = 82, category = 'pharma') {
      const pharma = isPharmaCategory(category);
      const pts = (series && series.length > 1) ? series : [1.1, 1.3, 1.2, 1.5, 1.4, 2.8, 5.3];
      const w = 340, h = height, min = 0, max = 11;
      const yThresh = h - ((2.0 - min) / (max - min)) * h;
        const yHighThresh = h - ((8.0 - min) / (max - min)) * h;
      const coords = pts.map((v, i) => {
        const x = (i / (pts.length - 1)) * (w - 30);
        const y = h - ((Math.max(min, Math.min(max, v)) - min) / (max - min)) * h;
        return { x, y, v };
      });
      const poly = coords.map(c => `${c.x.toFixed(1)},${c.y.toFixed(1)}`).join(' ');
      const last = coords[coords.length - 1];
      const out = isTempOutOfRange(last.v, category);
      const stroke = out ? '#DC2626' : '#2563EB';
      const fill = out ? 'rgba(220,38,38,0.08)' : 'rgba(37,99,235,0.08)';
      const areaPts = `0,${h} ${poly} ${(w - 30)},${h}`;
      const dots = coords.map(c => `<circle cx="${c.x.toFixed(1)}" cy="${c.y.toFixed(1)}" r="2.6" fill="#FFFFFF" stroke="${stroke}" stroke-width="1.6"><title>${c.v.toFixed(1)} °C</title></circle>`).join('');

      return `<svg width="100%" height="${h}" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none">
        <rect x="0" y="${yThresh}" width="${w - 30}" height="${h - yThresh}" fill="rgba(22,163,74,0.07)" />
        <polygon fill="${fill}" points="${areaPts}" />
        <line x1="0" y1="${yThresh}" x2="${w - 28}" y2="${yThresh}" stroke="#94A3B8" stroke-dasharray="3,3" stroke-width="1.2" />
        <text x="${w - 24}" y="${yThresh + 3}" font-size="9.5" font-weight="600" fill="#64748B">2°C</text>
        ${pharma ? `<line x1="0" y1="${yHighThresh}" x2="${w - 28}" y2="${yHighThresh}" stroke="#DC2626" stroke-dasharray="3,3" stroke-width="1.2" />
        <text x="${w - 24}" y="${yHighThresh + 3}" font-size="9.5" font-weight="600" fill="#DC2626">8°C</text>` : ''}
        <polyline fill="none" stroke="${stroke}" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" points="${poly}" />
        ${dots}
        <circle cx="${last.x.toFixed(1)}" cy="${last.y.toFixed(1)}" r="4" fill="${stroke}" />
      </svg>
      <div style="display:flex; justify-content:space-between; font-size:10px; color:var(--muted); margin-top:4px; padding-right:28px;">
        <span>Sat</span><span>Sun</span><span>Mon</span><span>Tue</span><span>Wed</span><span>Thu</span><span>Fri</span>
      </div>`;
    }

    async function refreshAll() {
      try {
        const res = await fetch('/api/ui/state', { headers: headers() });
        appData = await res.json();
        if (appData.datasetFile) {
          document.getElementById('datasetLabel').innerText = appData.datasetFile;
        }
        renderHome();
        renderBatches();
        renderInvestigations();
        renderQualityAndVault();
        if (!refreshAll._routed) { refreshAll._routed = true; if (window.location.hash) applyRoute(); }
        if (selectedInvId && document.getElementById('screen-inv-detail').style.display === 'block') {
          openInvestigationDetail(selectedInvId);
        }
      } catch (e) {
        console.error(e);
      }
    }

    function matchesSearch(obj) {
      if (!searchQuery) return true;
      return [obj.code, obj.id, obj.invId, obj.title, obj.sub, obj.product, obj.category, obj.unit, obj.unitName, obj.site, obj.location, obj.batchCode, obj.shipmentId].filter(Boolean).some(v => String(v).toLowerCase().includes(searchQuery));
    }

    function renderHome() {
  syncDynamicKpisAndChips();
      const flagged = appData.batches.filter(b => b.status === 'Out of range');
      const totalUnits = flagged.reduce((acc, b) => acc + b.units, 0);
      document.getElementById('headerSub').innerText = `${flagged.length} batches affected • ${totalUnits} units`;
      document.getElementById('sideFlagCount').innerText = flagged.length;

      if (flagged.length) {
        const codes = flagged.slice(0, 3).map(b => b.code).join(', ');
        const peak = Math.max(...flagged.map(b => b.temp));
        document.getElementById('bannerHeadline').innerText = `Batches ${codes} are outside their temperature band`;
        document.getElementById('bannerPeak').innerText = `🌡 ${peak.toFixed(1)}°C`;
      }

      const visTasks = appData.tasks.filter(matchesSearch);
      document.getElementById('tasksRemaining').innerText = `${visTasks.length} remaining ›`;
      document.getElementById('tasksList').innerHTML = visTasks.map(t => {
        const iconCls = t.badgeClass === 'high' ? 'warn' : (t.badgeClass === 'progress' ? 'info' : 'neutral');
        const handler = t.action === 'assign'
          ? `openAssignModal('${escapeHtml(t.invId)}')`
          : (t.action === 'ai'
            ? `askNvidiaAI('${escapeHtml(t.invId)}')`
            : `openInvestigationDetail('${escapeHtml(t.invId)}')`);
        return `<div class="list-row" tabindex="0" role="button" onclick="${handler}" onkeydown="if(event.key==='Enter'||event.key===' '){event.preventDefault();${handler};}">
          <div class="row-icon ${iconCls}">${t.icon}</div>
          <div class="row-main">
            <div class="row-title">${t.title}</div>
            <div class="row-sub">${t.sub}</div>
          </div>
          <span class="badge ${t.badgeClass}">${t.badge}</span>
          <span style="color:var(--muted);">›</span>
        </div>`;
      }).join('');

      const visFlagged = flagged.filter(matchesSearch);
      document.getElementById('affectedCount').innerText = `${visFlagged.length} of ${appData.batches.length} ›`;
      document.getElementById('homeBatchesList').innerHTML = visFlagged.map(b => `
        <div class="card interactive" tabindex="0" role="button" onclick="openBatchDetail('${b.code}')">
          <div style="display:flex; justify-content:space-between; align-items:flex-start;">
            <div style="display:flex; gap:12px;">
              <div class="row-icon warn">⚠️</div>
              <div>
                <div style="font-weight:700; font-size:15.5px;">${b.code}</div>
                <div class="batch-sub-pills">
                    <span class="cat-badge">${escapeHtml(b.category)}</span>
                    <span class="band-badge">Band ${escapeHtml(tempBandLabel(b.category))}</span>
                    <span style="font-size:12.5px; color:var(--muted);">${escapeHtml(b.product)}</span>
                  </div>
              </div>
            </div>
            <div style="display:flex; align-items:center; gap:6px;">
              <span class="badge high mono">Temp ${b.temp.toFixed(1)}°C</span>
              <span style="color:var(--muted);">›</span>
            </div>
          </div>
          <div style="font-size:12px; color:var(--muted); margin-top:10px;">
            🧊 ${b.unitName} &nbsp;•&nbsp; 📦 ${b.units} / ${b.units} units &nbsp;•&nbsp; 🕒 Arrived ${b.arrived}
          </div>
          ${stepperHTML(b.stageIndex, { closed: b.invStatus === 'Closed' })}
        </div>
      `).join('');
    }

    function setBatchFilter(f, btn) {
      batchFilter = f;
      document.querySelectorAll('.seg-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      renderBatches();
    }

    function setBatchSort(s) {
      batchSort = s;
      document.getElementById('sortHottest').style.background = s === 'hottest' ? '#F1F5F9' : 'transparent';
      document.getElementById('sortNewest').style.background = s === 'newest' ? '#F1F5F9' : 'transparent';
      renderBatches();
    }

    async function apiFetch(url, options = {}, errLabel = 'Request failed') {
      const res = await fetch(url, options);
      if (!res.ok) {
        let detail = '';
        try {
          const raw = await res.text();
          if (raw) {
            try {
              const parsed = JSON.parse(raw);
              detail = parsed.detail || raw;
            } catch (_) {
              detail = raw;
            }
          }
        } catch (_) {}
        if (res.status === 401) {
          // Write actions (assign, Ask AI, resolve, replay) need the operator key.
          showToast('🔑 Operator key needed: enter your X-API-Key in the 🐻‍❄️ panel, then try again');
          const drawer = document.getElementById('configDrawer');
          if (drawer && !drawer.classList.contains('open')) drawer.classList.add('open');
          const keyEl = document.getElementById('apiKey');
          if (keyEl) keyEl.focus();
          throw new Error(`${errLabel} (HTTP 401)`);
        }
        const msg = `${errLabel} (HTTP ${res.status})${detail ? ': ' + String(detail).slice(0, 140) : ''}`;
        showToast(`✕ ${msg}`);
        throw new Error(msg);
      }
      return res;
    }

    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') {
        closeSimModal();
        closeAssignModal();
        const cfg = document.getElementById('configDrawer');
        if (cfg) cfg.classList.remove('open');
      }
    });

    function isPharmaCategory(cat = '') {
      const c = String(cat).toLowerCase();
      return c.includes('pharma') || c.includes('biologic') || c.includes('vaccine') || c.includes('insulin');
    }

    function tempBandLabel(cat = '') {
      return isPharmaCategory(cat) ? '2°C–8°C' : '≤ 2°C';
    }

    function isTempOutOfRange(temp, cat = '') {
      const t = Number(temp);
      if (Number.isNaN(t)) return false;
      if (isPharmaCategory(cat)) return t < 2.0 || t > 8.0;
      return t > 2.0;
    }

    function pluralize(n, singular, plural) {
      return `${n} ${n === 1 ? singular : plural}`;
    }

    function openFlaggedBatches() {
      batchFilter = 'Flagged';
      switchTab('batches');
      document.querySelectorAll('.seg-btn').forEach(btn => {
        btn.classList.toggle('active', btn.textContent.trim().toLowerCase().startsWith('flagged'));
      });
      renderBatches();
    }

    document.addEventListener('keydown', (e) => {
      if ((e.key === 'Enter' || e.key === ' ') && e.target && e.target.matches('.card.interactive, .list-row[onclick], .unit-card[onclick], .staff-row[onclick]')) {
        e.preventDefault();
        e.target.click();
      }
    });

    function syncDynamicKpisAndChips() {
  const batches = Array.isArray(appData.batches) ? appData.batches : [];
  const invs = Array.isArray(appData.investigations) ? appData.investigations : [];

  const flaggedCount = batches.filter(b => b.status === 'Out of range').length;
  const watchCount = batches.filter(b => b.status === 'Monitoring').length;
  const heldShipments = new Set(
    batches
      .filter(b => b.status === 'Out of range' || b.held)
      .map(b => b.shipmentId || b.code)
  ).size;

  const openInvCount = invs.filter(i => String(i.state || '').toLowerCase() !== 'closed').length;
  const assignedInvCount = invs.filter(i => {
    const a = String(i.assignee || i.statusText || '').trim().toLowerCase();
    return a && a !== 'unassigned';
  }).length;

  const setText = (id, val) => {
    const el = document.getElementById(id);
    if (el) el.innerText = String(val);
  };

  setText('kpiTotalB', batches.length);
  setText('kpiFlaggedB', flaggedCount);
  setText('kpiWatchB', watchCount);
  setText('kpiHeldB', heldShipments);
  setText('kpiOpenInv', openInvCount);
  setText('kpiAssignedInv', assignedInvCount);

  const chipText = `${flaggedCount} flagged batch${flaggedCount === 1 ? '' : 'es'} / ${heldShipments} held shipment${heldShipments === 1 ? '' : 's'}`;
  document.querySelectorAll('[data-ai-chip], .ai-chip').forEach(el => {
    el.innerText = chipText;
  });
}

function cycleBatchFilter() {
  const order = ['All', 'Flagged', 'Watch', 'Cleared'];
  const cur = typeof batchFilter === 'string' ? batchFilter : 'All';
  const next = order[(order.indexOf(cur) + 1) % order.length];
  if (typeof setBatchFilter === 'function') {
    setBatchFilter(next);
  } else {
    batchFilter = next;
    if (typeof renderBatches === 'function') renderBatches();
  }
}

let activeCategoryFilter = 'ALL';

function setCategoryFilter(cat) {
  activeCategoryFilter = cat || 'ALL';
  renderBatches();
}

function resetAllBatchFilters() {
  activeCategoryFilter = 'ALL';
  setBatchFilter('ALL', null);
}

function renderCategoryFilterBar(totalCount, filteredCount) {
  const hostId = 'categoryFilterBar';
  let bar = document.getElementById(hostId);
  if (!bar) {
    const listEl = document.getElementById('batchesList');
    if (!listEl || !listEl.parentElement) return;
    bar = document.createElement('div');
    bar.id = hostId;
    bar.className = 'cat-filter-bar';
    listEl.parentElement.insertBefore(bar, listEl);
  }

  const categories = ['ALL', ...Array.from(new Set(
    (Array.isArray(appData.batches) ? appData.batches : [])
      .map(b => b.category)
      .filter(Boolean)
  ))];

  const chipsHtml = categories.map(cat => {
    const isActive = activeCategoryFilter.toLowerCase() === cat.toLowerCase();
    const label = cat === 'ALL' ? 'All Categories' : cat;
    return `<button type="button" class="cat-chip ${isActive ? 'active' : ''}" aria-pressed="${isActive ? 'true' : 'false'}" onclick="setCategoryFilter('${escapeHtml(cat)}')">${escapeHtml(label)}</button>`;
  }).join('');

  const hasNarrowFilter = activeCategoryFilter !== 'ALL' || (typeof batchFilter === 'string' && batchFilter.toUpperCase() !== 'ALL');
  const resetHtml = hasNarrowFilter
    ? `<button type="button" class="btn-reset-filter" onclick="resetAllBatchFilters()">Reset</button>`
    : '';

  bar.innerHTML = `
    <div class="cat-chip-group" role="group" aria-label="Filter by category">${chipsHtml}</div>
    <div class="filter-summary-bar">
      <span id="batchFilterCount">Showing <strong>${filteredCount}</strong> of <strong>${totalCount}</strong> batches</span>
      ${resetHtml}
    </div>
  `;
}

function reconcileAuditContradictions() {
  const batches = Array.isArray(appData.batches) ? appData.batches : [];
  const units = Array.isArray(appData.units) ? appData.units : [];
  const invs = Array.isArray(appData.investigations) ? appData.investigations : [];

  // Keep unit temperature consistent with any flagged batch in that unit
  units.forEach(u => {
    const unitCode = u.locationId || u.unitId || u.unitName || '';
    const flaggedInUnit = batches.filter(b =>
      b.status === 'Out of range' &&
      ((u.locationId && b.locationId === u.locationId) ||
       (u.unitName && b.unitName === u.unitName) ||
       (u.unitId && b.unitId === u.unitId))
    );
    if (flaggedInUnit.length) {
      const maxExcursion = Math.max(...flaggedInUnit.map(b => Number(b.temp ?? b.peak ?? u.temp)).filter(Number.isFinite));
      if (Number.isFinite(maxExcursion) && maxExcursion > Number(u.temp ?? -999)) {
        u.temp = maxExcursion;
      }
    }
  });

  const flaggedBatches = batches.filter(b => b.status === 'Out of range');
  const heldCount = new Set(
    batches
      .filter(b => b.status === 'Out of range' || b.held || String(b.shipmentStatus || '').toLowerCase().includes('hold'))
      .map(b => b.shipmentId || b.code)
  ).size;

  const assignedCount = invs.filter(i => {
    const assignee = String(i.assignee || '').trim();
    return assignee && assignee.toLowerCase() !== 'unassigned';
  }).length;

  const openCount = invs.filter(i => String(i.state || i.status || '').trim().toLowerCase() !== 'closed').length;

  const setNum = (id, val) => {
    const el = document.getElementById(id);
    if (el) el.innerText = String(val);
  };
  setNum('kpiFlaggedB', flaggedBatches.length);
  setNum('kpiHeldB', heldCount);
  setNum('kpiAssignedInv', assignedCount);
  setNum('kpiOpenInv', openCount);
}

function renderBatches() {
  reconcileAuditContradictions();
      document.getElementById('storageUnitsGrid').innerHTML = appData.units.map(u => `
        <div class="unit-card" tabindex="0" role="button" onclick="openSimModal('${u.locationId}')">
          <div style="display:flex; justify-content:space-between; font-size:13px; font-weight:700;">
            <span>${u.unitName}</span>
            <span style="color:${(u.flaggedCount > 0 || u.temp > 8) ? 'var(--red)' : 'var(--green)'};">●</span>
          </div>
          <div class="unit-temp mono" style="color:${(u.flaggedCount > 0 || u.temp > 8) ? 'var(--red)' : 'var(--blue)'};">${u.temp.toFixed(1)}°C</div>
          <div style="font-size:11.5px; color:var(--muted);">${u.flaggedCount} flagged • ${u.invCode}</div>
        </div>
      `).join('');

      let list = [...appData.batches].filter(matchesSearch);
      if (batchFilter === 'Flagged') list = list.filter(b => b.status === 'Out of range');
      if (batchFilter === 'Watch') list = list.filter(b => b.status === 'Monitoring');
      if (batchFilter === 'Cleared') list = list.filter(b => b.status === 'In range');
      if (batchSort === 'hottest') list.sort((a, b) => b.temp - a.temp);
      if (batchSort === 'newest') list.sort((a, b) => Date.parse(b.arrived || b.ts || 0) - Date.parse(a.arrived || a.ts || 0));

      document.getElementById('kpiTotalB').innerText = appData.batches.length;
      document.getElementById('kpiFlaggedB').innerText = appData.batches.filter(b => b.status === 'Out of range').length;
      document.getElementById('batchListHeading').innerText = list.length ? pluralize(list.length, 'batch', 'batches') : (searchQuery ? `No batches matching "${searchQuery}"` : '0 batches');

      document.getElementById('batchesList').innerHTML = list.map(b => {
        const badgeCls = b.status === 'Out of range' ? 'high' : (b.status === 'Monitoring' ? 'progress' : 'ok');
        const tempColor = isTempOutOfRange(b.temp, b.category) ? 'var(--red)' : 'var(--blue)';
        return `<div class="card interactive" tabindex="0" role="button" onclick="openBatchDetail('${b.code}')">
          <div style="display:flex; justify-content:space-between; align-items:flex-start; gap:8px;">
            <div style="display:flex; gap:12px;">
              <div class="row-icon ${b.status === 'Out of range' ? 'warn' : 'ok'}">${b.status === 'Out of range' ? '⚠️' : '✓'}</div>
              <div>
                <div style="font-weight:700; font-size:15.5px;">${b.code}</div>
                <div class="batch-sub-pills">
                    <span class="cat-badge">${escapeHtml(b.category)}</span>
                    <span class="band-badge">Band ${escapeHtml(tempBandLabel(b.category))}</span>
                    <span style="font-size:12.5px; color:var(--muted);">${escapeHtml(b.product)}</span>
                  </div>
              </div>
            </div>
            <div style="text-align:right; margin-left:auto;">
              <div class="mono" style="font-weight:800; font-size:16px; color:${tempColor};">${b.temp.toFixed(1)}°C</div>
              <div style="font-size:11px; color:var(--muted);">Target band ${tempBandLabel(b.category)}</div>
            </div>
            <span class="badge ${badgeCls}">${b.status}</span>
          </div>
          <div style="font-size:12px; color:var(--muted); margin-top:10px;">
            🧊 ${b.unitName} &nbsp;•&nbsp; 📦 ${b.units} / ${b.units} units &nbsp;•&nbsp; 🕒 Arrived ${b.arrived}
          </div>
          ${b.status === 'In range' ? `<div style="margin-top:12px; display:grid; grid-template-columns:1.3fr 1fr; gap:12px; align-items:center;">
            <div>${sparklineHTML(b.series, 46, b.category)}</div>
            <div style="background:var(--surface-soft); border:1px solid var(--border); padding:10px; border-radius:12px; font-size:11.5px;">
              <strong>🚚 ${b.shipmentId}</strong>
              <div><span class="badge progress" style="display:inline-block;margin:4px 0;">In storage</span></div>
              <span style="color:var(--muted);">ETA 45h 57m</span>
            </div>
          </div>` : stepperHTML(b.stageIndex, { closed: b.invStatus === 'Closed' })}
        </div>`;
      }).join('');
    }

    function openBatchDetail(code) {
      const b = appData.batches.find(x => x.code === code);
      if (!b) return;
      document.getElementById('mainHeader').style.display = 'none';
      document.getElementById('bdCode').innerText = b.code;
      document.getElementById('bdStatusBadge').innerText = b.status;
      document.getElementById('bdStatusBadge').className = 'badge ' + (b.status === 'Out of range' ? 'high' : 'ok');
      document.getElementById('bdSubtitle').innerText = `${b.category} • ${b.product} • ${b.locationSite}`;

      document.getElementById('batchDetailBody').innerHTML = `
        <div class="card">
          <div style="font-size:12.5px; color:var(--muted);">🧊 ${b.unitName} &nbsp;•&nbsp; 📦 ${b.units} / ${b.units} units &nbsp;•&nbsp; 🕒 Arrived ${b.arrived}</div>
          ${stepperHTML(b.stageIndex, { closed: b.invStatus === 'Closed' })}
        </div>
        <div class="card">
          <div style="font-weight:700; font-size:15px; margin-bottom:12px;">Sensor readings • last 7 days</div>
          <div style="display:grid; grid-template-columns:repeat(3,1fr); margin-bottom:12px;">
            <div><div style="font-size:11.5px;color:var(--muted);">Latest</div><div class="mono" style="font-size:21px;font-weight:800;color:${b.temp > 2 ? 'var(--red)' : 'var(--blue)'};">${b.temp.toFixed(1)}°C</div></div>
            <div><div style="font-size:11.5px;color:var(--muted);">Peak</div><div class="mono" style="font-size:21px;font-weight:800;">${b.peak.toFixed(1)}°C</div></div>
            <div><div style="font-size:11.5px;color:var(--muted);">Out-of-band</div><div class="mono" style="font-size:21px;font-weight:800;">${b.aboveHours}h</div></div>
          </div>
          ${sparklineHTML(b.series, 92, b.category)}
          <div style="font-size:11.5px; color:var(--muted); margin-top:8px;">30-minute telemetry cadence from sensor ${b.sensorId}.</div>
        </div>
        <div class="home-grid">
          <div class="card">
            <div style="font-weight:700; font-size:15px; margin-bottom:10px;">Linked shipment</div>
            <div style="background:var(--surface-soft); border:1px solid var(--border); border-radius:14px; padding:12px; display:inline-block; min-width:180px;">
              <div style="font-weight:700; font-size:13.5px;">🚚 ${b.shipmentId}</div>
              <div style="margin:6px 0;"><span class="badge ${b.status === 'Out of range' ? 'high' : 'ok'}">${b.status === 'Out of range' ? 'On hold' : 'Cleared'}</span></div>
              <div style="font-size:11.5px; color:var(--muted);">Destination: ${b.destination}</div>
            </div>
          </div>
          <div class="card interactive" style="display:flex; justify-content:space-between; align-items:center;" onclick="openInvestigationDetail('${b.invId}')">
            <div>
              <div style="font-weight:700; font-size:15.5px;">${b.invId} • ${b.invStatus}</div>
              <div style="font-size:12.5px; color:var(--muted); margin-top:4px;">${pluralize(b.handoffs || 0, 'handoff', 'handoffs')} logged • Tap to open case</div>
            </div>
            <span style="color:var(--muted); font-size:20px;">›</span>
          </div>
        </div>
      `;
      ['home', 'batches', 'investigations', 'quality', 'inv-detail'].forEach(s => document.getElementById('screen-' + s).style.display = 'none');
      document.getElementById('screen-batch-detail').style.display = 'block';
      routeTo('#batch/' + encodeURIComponent(b.code));
    }

    function renderInvestigations() {
      const vis = appData.investigations.filter(matchesSearch);
      const openInv = vis.filter(i => i.state !== 'Closed');
      document.getElementById('invOpenCount').innerText = openInv.length;
      const assignedEl = document.getElementById('invAssignedCount');
      if (assignedEl) assignedEl.innerText = openInv.filter(i => i.assignee && i.assignee !== 'Unassigned').length;
      const byState = s => vis.filter(i => i.state === s).length;
      const counts = { 'Open': byState('Open'), 'In progress': byState('In progress'), 'Under review': byState('Under review'), 'Closed': byState('Closed') };
      const total = Math.max(1, vis.length);
      [['Open', 'progOpen'], ['In progress', 'progProgress'], ['Under review', 'progReview'], ['Closed', 'progClosed']].forEach(([st, id]) => {
        const seg = document.getElementById(id); if (seg) seg.style.width = (100 * counts[st] / total) + '%';
        const lbl = document.getElementById(id + 'Lbl'); if (lbl) lbl.innerText = `${st} ${counts[st]}`;
      });
      loadInsights();
      document.getElementById('invIncidentCount').innerText = `${vis.length} incidents`;
      document.getElementById('investigationsList').innerHTML = vis.map(inv => `
        <div class="card interactive" style="padding:16px;" onclick="openInvestigationDetail('${inv.id}')">
          <div style="display:flex; justify-content:space-between; align-items:center; gap:10px;">
            <div style="display:flex; gap:12px; align-items:center;">
              <div class="row-icon ${inv.state === 'Closed' ? 'ok' : 'warn'}">${inv.state === 'Closed' ? '✓' : '⚠️'}</div>
              <div>
                <div style="font-weight:700; font-size:15.5px;">${inv.batchCode} <span style="font-weight:500; color:var(--muted); font-size:13px;">${inv.id}</span>${(insightsCache && (insightsCache.overdue || []).some(o => o.case_id === inv.id)) ? ' <span class="badge high">Overdue</span>' : ''}</div>
                <div style="font-size:12.5px; color:var(--muted); margin-top:2px;">${inv.unitName} • ${inv.reason}</div>
                <div style="font-size:12px; color:var(--muted); margin-top:5px;">🌡 ${inv.temp.toFixed(1)}°C &nbsp;•&nbsp; 📦 ${inv.units} units &nbsp;•&nbsp; 👤 ${inv.statusText}</div>
              </div>
            </div>
            <div style="text-align:right;">
              <span class="badge ${inv.state === 'Closed' ? 'ok' : (inv.priority === 'High' ? 'high' : 'medium')}">${inv.state === 'Closed' ? 'Closed' : inv.priority + ' ›'}</span>
              <div style="font-size:11.5px; color:var(--muted); margin-top:6px;" ${inv.createdAt ? `data-ts="${escapeHtml(inv.createdAt)}"` : ''}>${escapeHtml(inv.age)}</div>
            </div>
          </div>
        </div>
      `).join('');
    }

    function renderQualityAndVault() {
      document.getElementById('evidenceVaultList').innerHTML = appData.investigations.map(inv => `
        <div class="list-row" onclick="openInvestigationDetail('${inv.id}')">
          <div class="row-icon info">🔐</div>
          <div class="row-main">
            <div class="row-title">${inv.id} • ${inv.batchCode} (${inv.unitName})</div>
            <div class="row-sub mono hash">SHA-256: ${escapeHtml(inv.sha256)}</div>
            <div style="display:flex; gap:10px; align-items:center; margin-top:6px; font-size:12px;">
              <button type="button" class="btn-reset-filter" onclick="event.stopPropagation(); verifyCase('${inv.id}', this)">Verify audit chain</button>
              <a href="/api/cases/${encodeURIComponent(inv.id)}/events" target="_blank" rel="noopener" onclick="event.stopPropagation()" style="color:var(--orange); font-weight:600; text-decoration:none;">Event log (JSON)</a>
            </div>
          </div>
          <span class="badge ok">✓ Sealed</span>
        </div>
      `).join('');
    }

    function openInvestigationDetail(invId) {
      selectedInvId = invId;
      const inv = appData.investigations.find(x => x.id === invId) || appData.investigations[0];
      if (!inv) return;
      document.getElementById('mainHeader').style.display = 'none';
      document.getElementById('idCode').innerText = inv.batchCode;
      document.getElementById('idState').innerText = inv.state;
      document.getElementById('idState').style.color = inv.state === 'Closed' ? 'var(--green)' : 'var(--orange)';
      document.getElementById('idSubtitle').innerText = `${inv.id} • ${inv.unitName} • ${inv.reason}`;

      const timelineHTML = (inv.timeline || []).map(ev => `
        <div style="display:flex; gap:12px; padding:12px 0; border-bottom:1px solid #F1F5F9;">
          <div class="row-icon ${ev.tone || 'warn'}">${ev.icon || '•'}</div>
          <div style="flex:1;">
            <div style="display:flex; justify-content:space-between; gap:8px;">
              <strong style="font-size:14px;">${ev.title}</strong>
              <span style="font-size:11.5px; color:var(--muted);">${ev.time}</span>
            </div>
            <div style="font-size:13px; color:#334155; margin-top:3px;">${ev.detail}</div>
            <div style="font-size:11.5px; color:var(--muted); margin-top:3px;">${ev.source}</div>
          </div>
        </div>
      `).join('');

      document.getElementById('invDetailBody').innerHTML = `
        <div class="detail-actions">
          <button class="btn-orange" onclick="openAssignModal('${inv.id}')">⚡ Take action</button>
          <button class="btn-ask-ai" onclick="askNvidiaAI('${inv.id}')">✦ Ask AI</button>
          <button class="btn-ask-ai" onclick="resolveCase('${inv.id}')">✓ Resolve</button>
        </div>

        <div class="card">${stepperHTML(inv.state === 'Closed' ? 3 : 2, { closed: inv.state === 'Closed' })}</div>

        <div class="home-grid">
          <div class="card">
            <div class="sub-tabs">
              ${['Timeline', 'Details', 'Team', 'Files (3)'].map(t => `<button class="sub-tab ${invSubTab === t ? 'active' : ''}" onclick="invSubTab='${t}'; openInvestigationDetail('${inv.id}')">${t}</button>`).join('')}
            </div>
            ${invSubTab === 'Timeline' ? timelineHTML + '<div id="caseLogTimeline"></div>' : ''}
            ${invSubTab === 'Details' ? `<div style="font-size:13px; line-height:1.7;">
              <div><strong>Evidence SHA-256:</strong> <span class="mono hash">${escapeHtml(inv.sha256)}</span></div>
              <div><strong>Assigned Owner:</strong> ${inv.assignee}</div>
              <div><strong>Linked Shipment:</strong> ${inv.shipmentId} (${inv.state === 'Closed' ? 'Released' : 'On hold'})</div>
            </div>` : ''}
            ${invSubTab === 'Team' ? `<div style="font-size:13px; line-height:1.6;">Assigned to <strong>${inv.assignee}</strong>. Click <b>Take action</b> to reassign or log a handoff note.</div>` : ''}
            ${invSubTab === 'Files (3)' ? `<div style="font-size:13px; line-height:1.8;">• sensor_evidence_${inv.batchCode}.json (SHA-256 verified)<br>• cold_chain_labeled_2022_2026_slice.csv<br>• qa_coldchain_sop_v4.pdf</div>` : ''}
          </div>

          <div class="ai-card" style="margin-top:0;">
            <div style="display:flex; justify-content:space-between; align-items:center;">
              <strong style="font-size:15.5px;">✦ ColdChain AI triage</strong>
              <span class="badge progress">NVIDIA NIM</span>
            </div>
            <div style="font-size:12px; color:var(--muted); margin-top:3px;">Grounded triage agent for ${inv.id}</div>
            <div class="ai-chips">
              <span class="ai-chip" data-case-chip>📦 ${appData.batches.filter(b => b.invId === inv.id && b.status === 'Out of range').length} flagged batch(es)</span>
              <span class="ai-chip" data-case-chip>🚚 ${appData.batches.filter(b => b.invId === inv.id && b.held).length} held shipment(s)</span>
              <span class="ai-chip" id="caseEventsChip">🔗 case log loading…</span>
            </div>
            <div style="font-size:12px; color:var(--muted); margin-bottom:10px;">AI-generated summary grounded in sealed sensor evidence. Human review required before closing.</div>
            <div id="aiNarrative" style="font-size:13px; line-height:1.55; background:#FFFFFF; padding:14px; border-radius:14px; border:1px solid var(--border); white-space:pre-wrap;">${inv.aiSummary}</div>
          </div>
        </div>
      `;
      ['home', 'batches', 'investigations', 'quality', 'batch-detail'].forEach(s => document.getElementById('screen-' + s).style.display = 'none');
      document.getElementById('screen-inv-detail').style.display = 'block';
      loadCaseLog(inv.id);
      ['home', 'batches', 'investigations', 'quality'].forEach(t => { const sb = document.getElementById('snav-' + t); if (sb) sb.classList.toggle('active', t === 'investigations'); });
      routeTo('#inv/' + encodeURIComponent(inv.id));
    }

    async function resolveCase(invId) {
      if (!window.confirm(`Resolve and close investigation ${invId}? This action logs final QA closure.`)) return;
      try {
        await apiFetch('/api/ui/investigations/' + invId + '/resolve', { method: 'POST', headers: headers() }, `Resolve ${invId} failed`);
        showToast(`✓ ${invId} resolved & closed`);
        await refreshAll();
      } catch (_) {}
    }

    let aiRequestInFlight = false;

    async function askNvidiaAI(invId) {
      if (aiRequestInFlight) return;
      aiRequestInFlight = true;
      const box = document.getElementById('aiNarrative');
      const prev = box.innerText;
      box.innerText = 'Querying NVIDIA NIM model with sealed sensor evidence...';
      try {
        const res = await apiFetch('/api/ui/investigations/' + invId + '/ask-ai', { method: 'POST', headers: headers() }, 'NVIDIA NIM analysis failed');
        const data = await res.json();
        box.innerText = data.narrative || 'AI triage updated.';
        showToast('✦ NVIDIA NIM analysis updated');
        await refreshAll();
      } catch (_) {
        box.innerText = prev;
      } finally {
        aiRequestInFlight = false;
      }
    }

    function openSimModal(locationId) {
      const u = appData.units.find(x => x.locationId === locationId);
      if (!u) return;
      selectedSimUnit = u;
      document.getElementById('simLocLabel').innerText = `STORAGE LOCATION • ${u.shortCode}`;
      document.getElementById('simUnitTitle').innerText = u.unitName;
      document.getElementById('simUnitSub').innerText = `${u.siteName} • Pharma band 2°C–8°C / Cold ≤ 2°C`;
      document.getElementById('simChartBox').innerHTML = `
        <div style="display:flex; justify-content:space-between; margin-bottom:8px;">
          <span style="font-size:12.5px; color:var(--muted);">Warmest batch ${u.warmestBatch}</span>
          <strong class="mono" style="color:${u.temp > 2 ? 'var(--red)' : 'var(--blue)'};">${u.temp.toFixed(1)}°C</strong>
        </div>
        ${sparklineHTML(u.series, 76)}
      `;
      document.getElementById('simModal').classList.add('open');
    }

    function closeSimModal() {
      document.getElementById('simModal').classList.remove('open');
    }

    async function triggerFault(kind) {
      if (!selectedSimUnit) return;
      const target = selectedSimUnit;
      closeSimModal();
      showToast(`⚡ Injecting ${kind} into ${target.locationId}...`);
      try {
        await apiFetch('/api/demo/inject', {
          method: 'POST',
          headers: headers(),
          body: JSON.stringify({ location_id: target.locationId, kind })
        }, 'Fault injection failed');
        await refreshAll();
        showToast(`✓ Alert triggered on ${target.unitName}`);
      } catch (_) {}
    }

    function openAssignModal(invId) {
      selectedStaff = '';
      selectedInvId = invId;
      const stepEl = document.getElementById('assignStepLabel');
      if (stepEl) stepEl.innerText = `${invId} • Step 1`;
      const listEl = document.getElementById('staffList');
      listEl.setAttribute('role', 'radiogroup');
      listEl.innerHTML = STAFF.map((s, idx) => {
        const checked = selectedStaff === s.name;
        const safeName = s.name.replace(/'/g, "\\'");
        const safeInv = String(invId).replace(/'/g, "\\'");
        return `
        <div class="staff-row ${checked ? 'selected' : ''}" role="radio" aria-checked="${checked}" tabindex="${idx === 0 ? '0' : '-1'}" onclick="selectedStaff='${safeName}'; openAssignModal('${safeInv}')" onkeydown="if(event.key==='Enter'||event.key===' '){event.preventDefault();selectedStaff='${safeName}';openAssignModal('${safeInv}');}">
          <div class="avatar">${escapeHtml(s.initials)}</div>
          <div>
            <div style="font-weight:600; font-size:14px;">${escapeHtml(s.name)}</div>
            <div style="font-size:12px; color:var(--muted);">${escapeHtml(s.role)}</div>
          </div>
        </div>`;
      }).join('');
      const modalEl = document.getElementById('assignModal');
      modalEl.classList.add('open');
      const firstRadio = listEl.querySelector('[role="radio"]');
      if (firstRadio) firstRadio.focus();
    }

    function closeAssignModal() {
      document.getElementById('assignModal').classList.remove('open');
    }

    async function submitAssignment() {
      if (!selectedStaff) {
        showToast('✕ Select a team member before assigning');
        return;
      }
      const note = document.getElementById('handoffNote').value.trim() || 'Inspect unit and verify physical temperature.';
      try {
        await apiFetch('/api/ui/investigations/' + selectedInvId + '/assign', {
          method: 'POST',
          headers: headers(),
          body: JSON.stringify({ assignee: selectedStaff, note })
        }, 'Assignment failed');
        document.getElementById('handoffNote').value = '';
        closeAssignModal();
        showToast(`👤 Assigned to ${selectedStaff}`);
        await refreshAll();
      } catch (_) {}
    }

    async function replay14d() {
      showToast('⏳ Replaying cold_chain_labeled_2022_2026.csv...');
      try {
        const res = await apiFetch('/api/demo/replay', { method: 'POST', headers: headers() }, 'CSV replay failed');
        const data = await res.json();
        await refreshAll();
        showToast(`✓ Replayed ${data.rows_processed ?? 0} rows (${data.alerts_total ?? 0} alerts)`);
      } catch (_) {}
    }

    refreshAll();

document.addEventListener('DOMContentLoaded', () => {
  const bind = (id, ev, fn) => { const el = document.getElementById(id); if (el) el.addEventListener(ev, fn); };
  bind('snav-home', 'click', () => switchTab('home'));
  bind('snav-batches', 'click', () => switchTab('batches'));
  bind('snav-investigations', 'click', () => switchTab('investigations'));
  bind('snav-quality', 'click', () => switchTab('quality'));
  bind('tab-home', 'click', () => switchTab('home'));
  bind('tab-batches', 'click', () => openFlaggedBatches());
  bind('tab-investigations', 'click', () => switchTab('investigations'));
  bind('tab-quality', 'click', () => switchTab('quality'));
  bind('globalSearch', 'input', (e) => handleSearch(e.target.value));
  bind('sortHottest', 'click', () => setBatchSort('hottest'));
  bind('sortNewest', 'click', () => setBatchSort('newest'));

  document.querySelectorAll('.mascot').forEach(el => el.addEventListener('click', toggleConfig));
  document.querySelectorAll('.back-btn').forEach(el => el.addEventListener('click', () => {
    if (document.getElementById('screen-batch-detail').style.display === 'block') goBackFromDetail();
    else switchTab('investigations');
  }));
});


    window.addEventListener('DOMContentLoaded', () => {
      const el = document.getElementById('apiKey');
      let saved = '';
      try { saved = (localStorage.getItem(API_KEY_STORAGE_KEY) || '').trim(); } catch (_) {}
      if (el) {
        if (saved && !el.value) el.value = saved;
        el.addEventListener('input', () => {
          try { localStorage.setItem(API_KEY_STORAGE_KEY, el.value.trim()); } catch (_) {}
        });
        el.addEventListener('change', () => {
          try { localStorage.setItem(API_KEY_STORAGE_KEY, el.value.trim()); } catch (_) {}
        });
      }
    });


function enhanceAccessibility() {
  const modal = document.getElementById('assignModal') || document.querySelector('[data-assign-modal], .assign-modal');
  const rows = document.querySelectorAll('.staff-row, [data-staff-row]');
  rows.forEach((row, idx) => {
    row.setAttribute('role', 'radio');
    row.setAttribute('tabindex', idx === 0 ? '0' : '-1');
    const selected = row.classList.contains('selected') || row.classList.contains('active');
    row.setAttribute('aria-checked', selected ? 'true' : 'false');
    if (!row.dataset.radioKeyBound) {
      row.dataset.radioKeyBound = '1';
      row.addEventListener('keydown', (ev) => {
        if (ev.key === 'ArrowDown' || ev.key === 'ArrowRight') {
          ev.preventDefault();
          const next = rows[(idx + 1) % rows.length];
          if (next) next.focus();
        } else if (ev.key === 'ArrowUp' || ev.key === 'ArrowLeft') {
          ev.preventDefault();
          const prev = rows[(idx - 1 + rows.length) % rows.length];
          if (prev) prev.focus();
        } else if (ev.key === ' ' || ev.key === 'Enter') {
          ev.preventDefault();
          row.click();
        }
      });
    }
  });
  if (modal && rows.length && (modal.style.display !== 'none' && !modal.hidden)) {
    const first = rows[0];
    if (first && document.activeElement !== first && !modal.contains(document.activeElement)) {
      first.focus();
    }
  }

  document.querySelectorAll('[data-ts]').forEach(el => {
    const raw = el.getAttribute('data-ts');
    const parsed = raw ? Date.parse(raw) : NaN;
    if (!Number.isNaN(parsed)) {
      const mins = Math.max(0, Math.round((Date.now() - parsed) / 60000));
      if (mins < 60) el.innerText = `${mins}m ago`;
      else if (mins < 1440) el.innerText = `${Math.round(mins / 60)}h ago`;
      else el.innerText = `${Math.round(mins / 1440)}d ago`;
    }
  });

}

if (typeof window !== 'undefined') {
  const origOpenAssign = window.openAssignModal;
  if (typeof origOpenAssign === 'function' && !origOpenAssign._v3Wrapped) {
    const wrapped = function(...args) {
      const res = origOpenAssign.apply(this, args);
      setTimeout(enhanceAccessibility, 0);
      return res;
    };
    wrapped._v3Wrapped = true;
    window.openAssignModal = wrapped;
  }

  document.addEventListener('DOMContentLoaded', () => setTimeout(enhanceAccessibility, 50));
}


// --- Insights MVP + audit-chain verification ------------------------------------------------
let insightsCache = null;
async function loadInsights(days = 30) {
  try {
    const res = await fetch('/api/insights?days=' + days);
    if (!res.ok) return;
    const first = !insightsCache;
    insightsCache = await res.json();
    renderInsights(insightsCache);
    if (first && typeof renderInvestigations === 'function') renderInvestigations();  // adds Overdue chips once data arrives
  } catch (e) { console.error(e); }
}

function fmtHours(h) {
  if (h === null || h === undefined) return '—';
  if (h < 1) return Math.round(h * 60) + 'm';
  if (h < 48) return `${Math.floor(h)}h ${Math.round((h % 1) * 60)}m`;
  return (h / 24).toFixed(1) + 'd';
}

function renderInsights(d) {
  const ct = d.cycle_time || {};
  const avgEl = document.getElementById('invAvgClose');
  if (avgEl) avgEl.innerText = fmtHours(ct.median_h);
  const avgLbl = document.getElementById('invAvgCloseLbl');
  if (avgLbl) avgLbl.innerText = `median • avg ${fmtHours(ct.avg_h)} (n=${ct.n || 0})`;
  const panel = document.getElementById('insightsPanel');
  if (!panel) return;
  document.getElementById('insightsMeta').innerText =
    `Last ${d.window_days} days • ${d.live_cases} live + ${d.synthetic_cases} synthetic cases`;
  const freq = d.exception_frequency_by_location || {};
  const kinds = ['TEMP_EXCURSION', 'COOLING_FAILURE', 'SENSOR_DROPOUT'];
  const label = k => ({ TEMP_EXCURSION: 'Temp excursion', COOLING_FAILURE: 'Cooling failure', SENSOR_DROPOUT: 'Sensor dropout' }[k] || k);
  const freqRows = Object.keys(freq).sort().map(loc => `<tr><td>${escapeHtml(loc)}</td>${kinds.map(k => `<td class="mono">${freq[loc][k] || 0}</td>`).join('')}<td class="mono"><b>${freq[loc].total || 0}</b></td></tr>`).join('');
  const d2r = d.detection_to_review || {};
  const weeks = Object.entries(d.throughput_per_week || {});
  const bd = d.burndown || [];
  const maxOpen = Math.max(1, ...bd.map(x => Math.max(x.open, x.ideal_remaining)));
  const w = 320, h = 90, step = bd.length > 1 ? w / (bd.length - 1) : w;
  const pts = key => bd.map((x, i) => `${(i * step).toFixed(1)},${(h - (x[key] / maxOpen) * h).toFixed(1)}`).join(' ');
  panel.innerHTML = `
    <div class="kpi-4" style="margin-bottom:14px;">
      <div class="kpi-mini"><div class="lbl">Detection → review</div><div class="num mono">${fmtHours(d2r.median_h)}</div><div class="lbl">median • avg ${fmtHours(d2r.avg_h)}</div></div>
      <div class="kpi-mini"><div class="lbl">Cycle time</div><div class="num mono">${fmtHours(ct.median_h)}</div><div class="lbl">median • avg ${fmtHours(ct.avg_h)}</div></div>
      <div class="kpi-mini"><div class="lbl">Unresolved</div><div class="num mono">${d.unresolved}</div><div class="lbl">${(d.overdue || []).length} overdue</div></div>
      <div class="kpi-mini"><div class="lbl">Throughput</div><div class="num mono">${weeks.length ? weeks[weeks.length - 1][1] : 0}</div><div class="lbl">closed this week</div></div>
    </div>
    <div class="sec-head"><h2 style="font-size:14px;">Exception frequency by location</h2></div>
    <table><thead><tr><th>Location</th>${kinds.map(k => `<th>${label(k)}</th>`).join('')}<th>Total</th></tr></thead><tbody>${freqRows || '<tr><td colspan="5">No exceptions in window</td></tr>'}</tbody></table>
    <div class="sec-head" style="margin-top:14px;"><h2 style="font-size:14px;">Backlog burndown</h2><span class="sec-meta">open cases vs ideal</span></div>
    <svg viewBox="0 0 ${w} ${h + 4}" style="width:100%; max-width:100%; height:auto;" role="img" aria-label="Backlog burndown chart">
      <polyline points="${pts('ideal_remaining')}" fill="none" stroke="#CBD5E1" stroke-width="2" stroke-dasharray="4 4"/>
      <polyline points="${pts('open')}" fill="none" stroke="var(--orange)" stroke-width="2.5"/>
    </svg>
    <div class="sec-head" style="margin-top:14px;"><h2 style="font-size:14px;">Overdue cases</h2><span class="sec-meta">review or close SLA breached</span></div>
    ${(d.overdue || []).length > 6 ? `<div class="row-sub" style="margin-bottom:6px;">Showing 6 of ${(d.overdue || []).length}, live cases first</div>` : ''}
    ${[...(d.overdue || [])].sort((a, b) => (String(a.case_id).startsWith('SYN-') - String(b.case_id).startsWith('SYN-')) || (b.age_h - a.age_h)).slice(0, 6).map(o => `<div class="list-row"><div class="row-icon warn">⏱</div><div class="row-main"><div class="row-title">${escapeHtml(o.case_id)} • ${escapeHtml(o.location_id)}${String(o.case_id).startsWith('SYN-') ? '' : ' <span class="badge high">Live</span>'}</div><div class="row-sub">${label(o.kind)} • ${escapeHtml(o.priority)} • ${fmtHours(o.age_h)} old • ${o.reasons.map(r => r.replace('_', ' ')).join(', ')}</div></div></div>`).join('') || '<div class="row-sub">No overdue cases 🎉</div>'}
    <div style="font-size:11.5px; color:var(--muted); margin-top:10px;">Computed from timestamped case events (GET /api/insights). Synthetic cases replay labelled episodes with simulated handling times.</div>`;
}

async function verifyCase(caseId, btn) {
  btn.disabled = true; btn.textContent = 'Verifying…';
  try {
    const res = await fetch('/api/cases/' + encodeURIComponent(caseId) + '/events');
    if (!res.ok) throw new Error('HTTP ' + res.status);
    const d = await res.json();
    btn.textContent = d.chain_valid ? `✓ Chain intact (${d.events.length} events)` : '✕ Chain broken';
    btn.style.color = d.chain_valid ? 'var(--green)' : 'var(--red)';
  } catch (e) {
    btn.textContent = '✕ ' + e.message;
  } finally { btn.disabled = false; }
}


// --- Case log in investigation detail (hash-chained events from GET /api/cases/{id}/events) ---
async function loadCaseLog(caseId) {
  try {
    const res = await fetch('/api/cases/' + encodeURIComponent(caseId) + '/events');
    if (!res.ok) return;
    const d = await res.json();
    const evs = d.events || [];
    const chip = document.getElementById('caseEventsChip');
    if (chip) chip.innerText = `🔗 ${evs.length} case event${evs.length === 1 ? '' : 's'} • ${d.chain_valid ? 'chain intact' : 'chain broken'}`;
    const box = document.getElementById('caseLogTimeline');
    if (!box) return;
    const fmt = ts => { const t = new Date(ts); return isNaN(t) ? escapeHtml(ts) : t.toLocaleString([], { year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }); };
    box.innerHTML = `<div style="font-size:12px; font-weight:700; color:var(--muted); margin:14px 0 2px;">Case log • hash-chained (${d.chain_valid ? '✓ intact' : '✕ broken'})</div>` +
      evs.map(e => `
        <div style="display:flex; gap:12px; padding:10px 0; border-bottom:1px solid #F1F5F9;">
          <div class="row-icon info">🔗</div>
          <div style="flex:1;">
            <div style="display:flex; justify-content:space-between; gap:8px;">
              <strong style="font-size:14px;">${escapeHtml(e.event.replace('_', ' '))} → ${escapeHtml(e.to_state || '')}</strong>
              <span style="font-size:11.5px; color:var(--muted);">${fmt(e.ts)}</span>
            </div>
            <div style="font-size:13px; color:#334155; margin-top:3px;">${escapeHtml(e.note || '')}</div>
            <div style="font-size:11.5px; color:var(--muted); margin-top:3px;">${escapeHtml(e.actor || '')} • <span class="mono">${escapeHtml(String(e.hash).slice(0, 12))}…</span></div>
          </div>
        </div>`).join('');
  } catch (e) { console.error(e); }
}
