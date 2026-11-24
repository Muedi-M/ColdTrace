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
    }

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

    function sparklineHTML(series, height = 82) {
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
      const stroke = (last.v > 8.0 || last.v < 2.0) ? '#DC2626' : '#2563EB';
      const fill = (last.v > 8.0 || last.v < 2.0) ? 'rgba(220,38,38,0.08)' : 'rgba(37,99,235,0.08)';
      const areaPts = `0,${h} ${poly} ${(w - 30)},${h}`;
      const dots = coords.map(c => `<circle cx="${c.x.toFixed(1)}" cy="${c.y.toFixed(1)}" r="2.6" fill="#FFFFFF" stroke="${stroke}" stroke-width="1.6"><title>${c.v.toFixed(1)} °C</title></circle>`).join('');

      return `<svg width="100%" height="${h}" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none">
        <rect x="0" y="${yThresh}" width="${w - 30}" height="${h - yThresh}" fill="rgba(22,163,74,0.07)" />
        <polygon fill="${fill}" points="${areaPts}" />
        <line x1="0" y1="${yThresh}" x2="${w - 28}" y2="${yThresh}" stroke="#94A3B8" stroke-dasharray="3,3" stroke-width="1.2" />
        <text x="${w - 24}" y="${yThresh + 3}" font-size="9.5" font-weight="600" fill="#64748B">2°C</text>
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
        if (selectedInvId && document.getElementById('screen-inv-detail').style.display === 'block') {
          openInvestigationDetail(selectedInvId);
        }
      } catch (e) {
        console.error(e);
      }
    }

    function matchesSearch(obj) {
      if (!searchQuery) return true;
      return [obj.code, obj.id, obj.product, obj.category, obj.unit, obj.unitName, obj.site, obj.location, obj.batchCode, obj.shipmentId].filter(Boolean).some(v => String(v).toLowerCase().includes(searchQuery));
    }

    function renderHome() {
      const flagged = appData.batches.filter(b => b.status === 'Out of range');
      const totalUnits = flagged.reduce((acc, b) => acc + b.units, 0);
      document.getElementById('headerSub').innerText = `${flagged.length} batches affected • ${totalUnits} units`;
      document.getElementById('sideFlagCount').innerText = flagged.length;

      if (flagged.length) {
        const codes = flagged.slice(0, 3).map(b => b.code).join(', ');
        const peak = Math.max(...flagged.map(b => b.temp));
        document.getElementById('bannerHeadline').innerText = `Batches ${codes} exceeded temperature threshold`;
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
                <div style="font-size:12.5px; color:var(--muted);">${b.category} • ${b.product}</div>
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

    function renderBatches() {
      document.getElementById('storageUnitsGrid').innerHTML = appData.units.map(u => `
        <div class="unit-card" onclick="openSimModal('${u.locationId}')">
          <div style="display:flex; justify-content:space-between; font-size:13px; font-weight:700;">
            <span>${u.unitName}</span>
            <span style="color:${u.temp > 2 ? 'var(--red)' : 'var(--green)'};">●</span>
          </div>
          <div class="unit-temp mono" style="color:${u.temp > 2 ? 'var(--red)' : 'var(--blue)'};">${u.temp.toFixed(1)}°C</div>
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
                <div style="font-size:12.5px; color:var(--muted);">${b.category} • ${b.product}</div>
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
            <div>${sparklineHTML(b.series, 46)}</div>
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
          ${sparklineHTML(b.series, 92)}
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
    }

    function renderInvestigations() {
      const vis = appData.investigations.filter(matchesSearch);
      document.getElementById('invOpenCount').innerText = vis.filter(i => i.state !== 'Closed').length;
      document.getElementById('invIncidentCount').innerText = `${vis.length} incidents`;
      document.getElementById('investigationsList').innerHTML = vis.map(inv => `
        <div class="card interactive" style="padding:16px;" onclick="openInvestigationDetail('${inv.id}')">
          <div style="display:flex; justify-content:space-between; align-items:center; gap:10px;">
            <div style="display:flex; gap:12px; align-items:center;">
              <div class="row-icon ${inv.state === 'Closed' ? 'ok' : 'warn'}">${inv.state === 'Closed' ? '✓' : '⚠️'}</div>
              <div>
                <div style="font-weight:700; font-size:15.5px;">${inv.batchCode} <span style="font-weight:500; color:var(--muted); font-size:13px;">${inv.id}</span></div>
                <div style="font-size:12.5px; color:var(--muted); margin-top:2px;">${inv.unitName} • ${inv.reason}</div>
                <div style="font-size:12px; color:var(--muted); margin-top:5px;">🌡 ${inv.temp.toFixed(1)}°C &nbsp;•&nbsp; 📦 ${inv.units} units &nbsp;•&nbsp; 👤 ${inv.statusText}</div>
              </div>
            </div>
            <div style="text-align:right;">
              <span class="badge ${inv.state === 'Closed' ? 'ok' : (inv.priority === 'High' ? 'high' : 'medium')}">${inv.state === 'Closed' ? 'Closed' : inv.priority + ' ›'}</span>
              <div style="font-size:11.5px; color:var(--muted); margin-top:6px;">${inv.age}</div>
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
            <div class="row-sub mono">SHA-256: ${inv.sha256}</div>
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
            ${invSubTab === 'Timeline' ? timelineHTML : ''}
            ${invSubTab === 'Details' ? `<div style="font-size:13px; line-height:1.7;">
              <div><strong>Evidence SHA-256:</strong> <span class="mono">${inv.sha256}</span></div>
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
              <span class="ai-chip">📦 1 flagged batch</span>
              <span class="ai-chip">🚚 1 held shipment</span>
              <span class="ai-chip">🤝 ${inv.handoffs} handoffs</span>
            </div>
            <div style="font-size:12px; color:var(--muted); margin-bottom:10px;">AI-generated summary grounded in sealed sensor evidence. Human review required before closing.</div>
            <div id="aiNarrative" style="font-size:13px; line-height:1.55; background:#FFFFFF; padding:14px; border-radius:14px; border:1px solid var(--border); white-space:pre-wrap;">${inv.aiSummary}</div>
          </div>
        </div>
      `;
      ['home', 'batches', 'investigations', 'quality', 'batch-detail'].forEach(s => document.getElementById('screen-' + s).style.display = 'none');
      document.getElementById('screen-inv-detail').style.display = 'block';
    }

    async function resolveCase(invId) {
      if (!window.confirm(`Resolve and close investigation ${invId}? This action logs final QA closure.`)) return;
      try {
        await apiFetch('/api/ui/investigations/' + invId + '/resolve', { method: 'POST', headers: headers() }, `Resolve ${invId} failed`);
        showToast(`✓ ${invId} resolved & closed`);
        await refreshAll();
      } catch (_) {}
    }

    async function askNvidiaAI(invId) {
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
      if (selectedInvId !== invId) selectedStaff = '';
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
