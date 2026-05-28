// architecture.js — project-dashboard skill template.
// Reads window.ARCH_DATA (from architecture.data.js) and window.PULSE_DATA (from pulse.data.js).
// Tabs are conditional: hidden when their data block is absent.
// Edit freely. Loaded via <script src> for file:// compatibility.

(() => {
  const D = window.ARCH_DATA || {};
  const P = window.PULSE_DATA || {};
  if (!window.ARCH_DATA && !window.PULSE_DATA) {
    document.body.innerHTML =
      '<p style="padding:28px;color:#f29191">No data loaded. Run <code>python architecture/build.py</code></p>';
    return;
  }

  // ---------- helpers ----------
  const $ = (sel, root = document) => root.querySelector(sel);
  const el = (tag, attrs = {}, ...kids) => {
    const n = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) {
      if (v == null || v === false) continue;
      if (k === 'class') n.className = v;
      else if (k === 'html') n.innerHTML = v;
      else if (k.startsWith('on')) n.addEventListener(k.slice(2), v);
      else n.setAttribute(k, v);
    }
    for (const k of kids.flat()) {
      if (k == null) continue;
      n.appendChild(typeof k === 'string' ? document.createTextNode(k) : k);
    }
    return n;
  };
  const copySpan = (text, cls = '') => {
    const s = el('span', { class: `mono copy ${cls}`.trim(), title: 'click to copy' }, text);
    s.addEventListener('click', async () => {
      try {
        await navigator.clipboard.writeText(text);
        s.classList.add('copied');
        setTimeout(() => s.classList.remove('copied'), 900);
      } catch (_) {}
    });
    return s;
  };
  const freshClass = days => days == null ? '' : days <= 7 ? 'green' : days <= 30 ? 'amber' : 'red';
  const phaseClass = blockers => blockers > 0 ? 'bad' : (P.status?.percent_done < 25 ? 'warn' : '');

  // ---------- url state (#tab?q=query) ----------
  const parseHash = () => {
    const h = location.hash.replace(/^#/, '');
    const [tab, qs] = h.split('?');
    const params = new URLSearchParams(qs || '');
    return { tab: tab || 'pulse', q: params.get('q') || '' };
  };
  const writeHash = (tab, q) => {
    const qs = q ? `?q=${encodeURIComponent(q)}` : '';
    history.replaceState(null, '', `#${tab}${qs}`);
  };

  // ---------- header ----------
  const projectName = D.project || P.project || 'project';
  const blockerCount = (P.blockers || []).length;
  const h1 = $('#hdr-title');
  h1.textContent = projectName;
  if (blockerCount > 0) h1.classList.add('bad');
  $('#hdr-sub').textContent = D.fullName || D.subtitle || P.status?.one_liner || '';
  const meta = $('#hdr-meta');
  const metaBits = [];
  if (D.version) metaBits.push(el('span', {}, 'v', el('strong', {}, D.version)));
  if (P.status?.phase) metaBits.push(el('span', {}, el('strong', {}, P.status.phase)));
  if (P.updated) metaBits.push(el('span', {}, 'pulse ', el('strong', {}, P.updated)));
  if (D.updated) metaBits.push(el('span', {}, 'arch ', el('strong', {}, D.updated)));
  if (P.git?.freshness_days != null) {
    const d = P.git.freshness_days;
    metaBits.push(el('span', { class: `freshness ${freshClass(d)}` },
      d === 0 ? 'touched today' : `${d}d since last commit`));
  }
  metaBits.push(el('span', {}, el('a', { href: 'architecture.json' }, 'architecture.json')));
  metaBits.push(el('span', {}, el('a', { href: 'pulse.json' }, 'pulse.json')));
  meta.replaceChildren(...metaBits);

  // ---------- tabs (conditional on data) ----------
  const TABS = [
    ['pulse',     'Pulse',     blockerCount || null, () => !!Object.keys(P).length, renderPulse],
    ['overview',  'Overview',  null,                  () => !!D.purpose || !!D.fullName, renderOverview],
    ['stack',     'Stack',     D.layers?.length,      () => (D.layers || []).length > 0, renderStack],
    ['contracts', 'Contracts', D.dataContracts?.length, () => (D.dataContracts || []).length > 0, renderContracts],
    ['privacy',   'Privacy',   null,                  () => !!D.privacyPosture, renderPrivacy],
    ['rules',     'Rules',     null,                  () => (D.rules || []).length > 0, renderRules],
    ['history',   'History',   P.decisions?.length,   () => (P.decisions || []).length > 0, renderHistory],
  ].filter(t => t[3]());

  const tabBar = $('#tabs');
  const panes = $('#panes');
  TABS.forEach(([id, label, count], i) => {
    const btn = el('button',
      { role: 'tab', 'data-tab': id, 'aria-selected': i === 0 ? 'true' : 'false' },
      label,
      count != null ? el('span', { class: 'count ' + (id === 'pulse' && count > 0 ? 'bad' : '') }, String(count)) : null,
      el('span', { class: 'key' }, String(i + 1)),
    );
    btn.addEventListener('click', () => switchTab(id));
    tabBar.appendChild(btn);
    panes.appendChild(el('div', { class: 'pane' + (i === 0 ? ' active' : ''), 'data-pane': id, id: 'pane-' + id }));
  });

  function switchTab(id) {
    document.querySelectorAll('[data-tab]').forEach(b =>
      b.setAttribute('aria-selected', b.dataset.tab === id ? 'true' : 'false'));
    document.querySelectorAll('.pane').forEach(p =>
      p.classList.toggle('active', p.dataset.pane === id));
    writeHash(id, '');
  }

  // restore from hash
  const { tab: initialTab } = parseHash();
  if (TABS.some(t => t[0] === initialTab)) switchTab(initialTab);

  // keyboard nav
  window.addEventListener('keydown', e => {
    if (e.metaKey || e.ctrlKey || e.altKey) return;
    const t = e.target;
    if (t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA')) return;
    const n = parseInt(e.key, 10);
    if (n >= 1 && n <= TABS.length) {
      switchTab(TABS[n - 1][0]);
      e.preventDefault();
    } else if (e.key === '/') {
      const cur = document.querySelector('[data-tab][aria-selected="true"]')?.dataset.tab;
      const inp = cur && document.querySelector(`#pane-${cur} input[type=search]`);
      if (inp) { inp.focus(); e.preventDefault(); }
    }
  });

  // ---------- render: PULSE ----------
  function renderPulse() {
    const root = $('#pane-pulse');
    const s = P.status || {};
    const pct = typeof s.percent_done === 'number' ? s.percent_done : null;

    const headline = el('section', { class: 'card' },
      el('div', { class: 'pulse-headline' },
        el('span', { class: 'phase' }, s.phase || ''),
        s.phase_label ? el('span', { class: 'muted' }, s.phase_label) : null,
        pct != null ? el('span', { class: 'pct' }, `${pct}% done`) : null,
      ),
      pct != null ? el('div', { class: 'bar' }, el('span', { style: `width:${pct}%` })) : null,
      s.one_liner ? el('p', {}, s.one_liner) : null,
      (P.tags || []).length > 0
        ? el('p', { style: 'margin-top:8px' },
            ...P.tags.map(t => el('span', { class: 'pill info', style: 'margin-right:4px' }, t)))
        : null,
    );

    const blockers = el('section', { class: 'card' },
      el('h2', {}, 'Blockers ', el('span', { class: 'num' }, `(${(P.blockers || []).length})`)),
      (P.blockers || []).length === 0
        ? el('div', { class: 'muted' }, 'none')
        : el('div', {}, ...(P.blockers || []).map(b =>
            el('div', { class: 'blocker' },
              el('div', {}, b.text || ''),
              el('div', { class: 'meta' },
                b.since ? `since ${b.since}` : '',
                b.owner ? ` · owner: ${b.owner}` : '',
              )))),
    );

    const milestone = P.next_milestone ? el('section', { class: 'card' },
      el('h2', {}, 'Next milestone'),
      el('p', {},
        el('strong', {}, P.next_milestone.label || ''),
        P.next_milestone.target_date ? el('span', { class: 'muted' }, ' · target ' + P.next_milestone.target_date) : null,
      ),
    ) : null;

    const inFlight = el('section', { class: 'card' },
      el('h2', {}, 'In flight ', el('span', { class: 'num' }, `(${(P.in_flight || []).length})`)),
      (P.in_flight || []).length === 0
        ? el('div', { class: 'muted' }, 'idle')
        : el('div', {}, ...(P.in_flight || []).map(f =>
            el('div', { class: 'in-flight-row' },
              el('span', { class: 'pill ' + ({ feature: 'ok', bugfix: 'bad', refactor: 'info', experiment: 'warn', docs: '' }[f.kind] || '') }, f.kind || '?'),
              el('span', {}, f.text || ''),
              f.branch ? el('span', { class: 'muted mono', style: 'margin-left:auto' }, f.branch) : null,
            ))),
    );

    const tests = P.test_status ? el('section', { class: 'card' },
      el('h2', {}, 'Test status'),
      el('div', { class: 'grid' },
        statTile('Pass', String(P.test_status.pass ?? '?'), 'ok'),
        statTile('Fail', String(P.test_status.fail ?? '?'), P.test_status.fail > 0 ? 'bad' : 'ok'),
        statTile('Skip', String(P.test_status.skip ?? '?'), ''),
        statTile('Last run', P.test_status.last_run || '?', ''),
      ),
      P.test_status.command ? el('pre', { style: 'margin-top:8px' }, P.test_status.command) : null,
    ) : null;

    const git = P.git ? el('section', { class: 'card' },
      el('h2', {}, 'Recent commits ',
        el('span', { class: 'num' }, `(${(P.git.recent_commits || []).length})`),
        P.git.dirty ? el('span', { class: 'pill bad', style: 'margin-left:8px' }, 'working tree dirty') : null,
        P.git.branch ? el('span', { class: 'pill', style: 'margin-left:6px' }, 'branch: ' + P.git.branch) : null,
      ),
      (P.git.recent_commits || []).length === 0
        ? el('div', { class: 'muted' }, 'no commits in window')
        : el('div', {}, ...(P.git.recent_commits || []).map(c =>
            el('div', { class: 'commit' },
              el('span', { class: 'date' }, c.date || ''),
              copySpan(c.sha || '', 'sha'),
              el('span', {}, c.subject || ''),
            ))),
    ) : null;

    const links = P.links && Object.keys(P.links).length > 0 ? el('section', { class: 'card' },
      el('h2', {}, 'Quick links'),
      el('ul', {}, ...Object.entries(P.links).map(([k, v]) =>
        el('li', {}, k + ': ', el('a', { href: v }, v)))),
    ) : null;

    root.replaceChildren(...[headline, blockers, milestone, inFlight, tests, git, links].filter(Boolean));
  }

  function statTile(k, v, cls) {
    return el('div', { class: 'stat' },
      el('div', { class: 'k' }, k),
      el('div', { class: 'v ' + cls }, v),
    );
  }

  // ---------- render: OVERVIEW ----------
  function renderOverview() {
    const root = $('#pane-overview');
    const cards = [];
    if (D.purpose) cards.push(el('section', { class: 'card' },
      el('h2', {}, 'What it is'), el('p', {}, D.purpose),
      (D.isNot || []).length > 0 ? el('div', {},
        el('h2', { style: 'margin-top:14px' }, 'What it is not'),
        el('ul', {}, ...D.isNot.map(s => el('li', { class: 'muted' }, s)))) : null,
    ));
    if (D.atAGlance) cards.push(el('section', { class: 'card' },
      el('h2', {}, 'At a glance'),
      el('div', { class: 'grid' }, ...Object.entries(D.atAGlance).map(([k, v]) =>
        el('div', { class: 'stat' },
          el('div', { class: 'k' }, k),
          el('div', { class: 'v' }, String(v))))),
    ));
    if (D.generatedFrom) cards.push(el('section', { class: 'card' },
      el('h2', {}, 'Generated from'),
      el('ul', {}, ...(D.generatedFrom || []).map(s => el('li', {}, copySpan(s)))),
    ));
    root.replaceChildren(...cards);
  }

  // ---------- render: STACK ----------
  function renderStack() {
    const root = $('#pane-stack');
    const toolbar = el('div', { class: 'toolbar' },
      el('input', { type: 'search', placeholder: 'Filter layers and modules…  (press /)', id: 'stack-search' }),
      el('span', { class: 'kbd' }, (D.layers || []).length + ' layers'),
    );
    const list = el('div', { id: 'stack-list' });
    function paint(q) {
      const Q = (q || '').toLowerCase().trim();
      list.replaceChildren();
      writeHash('stack', Q);
      (D.layers || []).forEach(L => {
        const mods = (L.modules || []).filter(m =>
          !Q || L.name?.toLowerCase().includes(Q) || L.id?.toLowerCase().includes(Q) ||
          (m.path || '').toLowerCase().includes(Q) || (m.role || '').toLowerCase().includes(Q));
        if (Q && mods.length === 0) return;
        const det = el('details', { class: 'layer', open: Q ? 'open' : null },
          el('summary', {},
            L.id ? el('span', { class: 'lid' }, L.id) : null,
            el('span', { class: 'lname' }, L.name || ''),
            el('span', { class: 'lpurp' }, L.purpose || ''),
          ),
          el('div', { class: 'body' },
            L.purpose ? el('p', { class: 'muted' }, L.purpose) : null,
            mods.length > 0 ? el('table', {},
              el('thead', {}, el('tr', {}, el('th', { style: 'width:42%' }, 'Module'), el('th', {}, 'Role'))),
              el('tbody', {}, ...mods.map(m =>
                el('tr', {}, el('td', {}, copySpan(m.path || '')), el('td', {}, m.role || ''))))) : null,
          ),
        );
        list.appendChild(det);
      });
      if (list.children.length === 0) list.appendChild(el('div', { class: 'empty' }, 'no matches'));
    }
    paint('');
    toolbar.querySelector('input').addEventListener('input', e => paint(e.target.value));
    root.replaceChildren(toolbar, list);
  }

  // ---------- render: CONTRACTS ----------
  function renderContracts() {
    const root = $('#pane-contracts');
    root.replaceChildren(...(D.dataContracts || []).map(c =>
      el('section', { class: 'card' },
        el('h2', {}, c.name || ''),
        c.description ? el('p', { class: 'muted' }, c.description) : null,
        c.schema ? el('pre', {}, JSON.stringify(c.schema, null, 2)) : null,
      )));
  }

  // ---------- render: PRIVACY ----------
  function renderPrivacy() {
    const root = $('#pane-privacy');
    const p = D.privacyPosture || {};
    const rows = Object.entries(p).filter(([k]) => k !== 'ADR');
    root.replaceChildren(el('section', { class: 'card' },
      el('h2', {}, 'Privacy posture'),
      el('table', {}, el('tbody', {}, ...rows.map(([k, v]) =>
        el('tr', {},
          el('td', { class: 'mono', style: 'width:200px;color:var(--muted)' }, k),
          el('td', {}, String(v)),
        )))),
      p.ADR ? el('p', { class: 'muted', style: 'margin-top:8px;font-size:12px' }, 'ADR: ', p.ADR) : null,
    ));
  }

  // ---------- render: RULES ----------
  function renderRules() {
    const root = $('#pane-rules');
    root.replaceChildren(el('section', { class: 'card' },
      el('h2', {}, 'Rules'),
      el('ul', {}, ...(D.rules || []).map(r =>
        el('li', {}, typeof r === 'string' ? r : (r.text || JSON.stringify(r))))),
    ));
  }

  // ---------- render: HISTORY (decisions) ----------
  function renderHistory() {
    const root = $('#pane-history');
    root.replaceChildren(el('section', { class: 'card' },
      el('h2', {}, 'Recent decisions ', el('span', { class: 'num' }, `(${(P.decisions || []).length})`)),
      ...(P.decisions || []).map(d =>
        el('div', { class: 'decision' },
          el('span', { class: 'date' }, d.date || ''),
          el('span', {}, d.decision || ''),
          d.why ? el('div', { class: 'why' }, 'Why: ' + d.why) : null,
        )),
    ));
  }

  // ---------- run ----------
  TABS.forEach(([, , , , render]) => render());

  // footer
  const updated = P.updated || D.updated || '';
  $('#footer-note').textContent =
    `${projectName} dashboard — pulse last edited ${updated}. Run \`python architecture/build.py\` after editing architecture.json or pulse.json.`;
})();
