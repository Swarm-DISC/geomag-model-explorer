// Study tabs (PLAN v2.3 + v2.9; IDEAS §9.4/§9.7): a tab binds a time axis +
// the controls that make sense for it, over the one shared globe. With the
// `families` flag off the strip is exactly v2.3-v2.8: Daily ≡ v1 (date
// picker, 97 15-min steps) and Ionosphere (Seasonal) playing an annual
// series. With `families` on (v2.9) the strip reads per-source — Combined
// models · Core · Ionosphere — under a page-level "Model series" selector
// (Swarm CI / CHAOS). Family is a lens: it filters which series each tab
// offers; the day cache is CI-only, so Combined×CHAOS swaps the date picker
// for a curated diurnal-series select. Layers a family lacks grey out with
// a family-aware tooltip (CHAOS has no ionospheric layer — by decision, not
// omission). The Core tab shows exactly one field at a time via a B ↔ dB/dt
// radio (the units rule: nT/yr never sums with nT), clearing the colorbar
// lock on unit changes.
//
// The tab strip gates controls (IDEAS §8.2 control budget): outside
// Daily×CI the date picker is hidden and a series <select> takes its slot.
// Each tab snapshots {day, pos, enabled, shell} per family on leave and
// restores it on return. Tab ids are permalink keys — labels can change,
// ids cannot.

import { FIELD_LABELS, fmtTime, R_SURFACE_M } from '../ui.js';
import { seriesUT } from '../sun.js';

const DAY_MS = 86400000;

const V1_TABS = [
  { id: 'daily', label: 'Daily' },
  { id: 'seasons', label: 'Ionosphere (Seasonal)', kind: 'annual',
    fields: ['iono'],
    defaults: { core: false, crust: false, iono: true, magneto: false } },
];

// v2.9 lineup (checkpoint outcome, PLAN v2.9): same ids, per-source labels.
// `daily` keeps no kind — it hosts real days (CI) and diurnal series (other
// families). `exclusive` marks the one-field-at-a-time B ↔ dB/dt tab.
const FAMILY_TABS = [
  { id: 'daily', label: 'Combined models' },
  { id: 'core', label: 'Core', kind: 'secular',
    fields: ['core', 'core-sv'], exclusive: true,
    defaults: { core: true, crust: false, iono: false, magneto: false,
                'core-sv': false } },
  { id: 'seasons', label: 'Ionosphere', kind: 'annual',
    fields: ['iono'],
    defaults: { core: false, crust: false, iono: true, magneto: false,
                'core-sv': false } },
];

const FAMILY_LABELS = { ci: 'Swarm CI', chaos: 'CHAOS' };
const FAMILY_ATTRIBUTION = {
  ci: 'Comprehensive Inversion models '
    + '(MCO/MLI/MIO/MMA_SHA_2C; DTU Space, IPGP et al.)',
  chaos: 'CHAOS model series (CHAOS-Core/-Static/-MMA; DTU Space)',
};

let TABS = V1_TABS;                  // set per flag in restore()

function familyOf(rec) { return rec?.family ?? 'ci'; }

function seriesOfKind(manifest, kind, family = null) {
  return Object.keys(manifest.series ?? {})
    .filter((id) => manifest.series[id].kind === kind
      && (family === null || familyOf(manifest.series[id]) === family));
}

// Families offered by the page: ci always (the day cache), plus every
// family some exported series carries — data-driven, no FAMILIES mirror.
function familiesPresent(manifest) {
  const fams = new Set(['ci']);
  for (const rec of Object.values(manifest.series ?? {})) {
    fams.add(familyOf(rec));
  }
  return [...fams];
}

function tabOf(state, manifest) {
  const rec = manifest.series?.[state.day];
  return rec ? (TABS.find((t) => t.kind === rec.kind)?.id ?? 'daily')
             : 'daily';
}

// Mutate the shared timeline descriptor to match state.day (a real day or a
// series id). Series sliders tick in days (capped so yearly series stay
// scrubbable); labels interpolate the epoch dates. Sub-daily (diurnal)
// series tick and label exactly like a real day.
function applyTimeline(timeline, manifest, state) {
  const rec = manifest.series?.[state.day];
  if (!rec) {
    Object.assign(timeline, {
      nEpochs: 97, subdiv: 15,
      label: (pos) => fmtTime(pos * 15),
      sweepMs: 120000,
    });
    return;
  }
  const stepMs = rec.epochs.length > 1
    ? Date.parse(rec.epochs[1]) - Date.parse(rec.epochs[0]) : DAY_MS;
  if (stepMs < DAY_MS) {
    const stepMin = stepMs / 60000;
    Object.assign(timeline, {
      nEpochs: rec.epochs.length, subdiv: stepMin,
      label: (pos) => fmtTime(pos * stepMin),
      sweepMs: 120000,
    });
  } else {
    Object.assign(timeline, {
      nEpochs: rec.epochs.length,
      subdiv: Math.max(1, Math.min(10, Math.round(stepMs / DAY_MS))),
      // same instant the sun overlay uses (seriesUT, parsed as UT and snapped
      // to whole days), so the label and the terminator always agree
      label: (pos) => seriesUT(rec, pos).toISOString().slice(0, 10),
      sweepMs: 120000,
    });
  }
  state.pos = Math.max(0, Math.min(state.pos, rec.epochs.length - 1));
}

export function restore({ state, manifest, timeline, features }) {
  TABS = features?.families ? FAMILY_TABS : V1_TABS;
  const rec = manifest.series?.[state.day];
  // a series whose kind has no tab under the active flags must not leak a
  // foreign timeline onto the Daily tab (permalink gates this too — F6 —
  // but a cheap second fence keeps garbage out)
  if (rec && rec.kind !== 'diurnal' && !TABS.find((t) => t.kind === rec.kind)) {
    state.day = manifest.default_day;
    state.pos = 0;
  }
  if (rec && rec.kind === 'diurnal' && !features?.families) {
    state.day = manifest.default_day;
    state.pos = 0;
  }
  if (features?.families) {
    // an active series pins the lens; otherwise keep what the permalink
    // set (family= without series=), defaulting to ci
    const active = manifest.series?.[state.day];
    if (active) state.family = familyOf(active);
    else if (state.family === undefined) state.family = 'ci';
  }
  // permalink restore (which runs first) may have landed on a series day;
  // the timeline must match before the UI builds its slider from it.
  applyTimeline(timeline, manifest, state);
}

export function attach({ state, manifest, ui, hooks, timeline, features }) {
  const familiesOn = !!features?.families;
  const anySeries = Object.keys(manifest.series ?? {}).length > 0;
  if (!(familiesOn ? anySeries : seriesOfKind(manifest, 'annual').length)) {
    return;                          // nothing exported yet: stay v1
  }

  if (state.family === undefined) state.family = 'ci';
  let current = tabOf(state, manifest);
  const saved = {};                  // `${tab}@${family}` -> snapshot
  const snapKey = (tab) => `${tab}@${familiesOn ? state.family : 'ci'}`;

  // Which fields a family carries at all (data-driven: ci carries every
  // catalog field via the day cache; other families carry what their
  // exported series mention). Drives the "missing layer" tooltips.
  function familyHasField(family, field) {
    if (family === 'ci') return true;
    return Object.values(manifest.series ?? {}).some((rec) =>
      familyOf(rec) === family && rec.fields.includes(field));
  }

  // The series ids the active (tab, family) context offers: diurnal series
  // stand in for the day cache on Combined under non-ci families.
  function contextSeries(tabId = current, family = state.family) {
    const tab = TABS.find((t) => t.id === tabId);
    if (tab.kind) return seriesOfKind(manifest, tab.kind, family);
    return family === 'ci' ? [] : seriesOfKind(manifest, 'diurnal', family);
  }

  function tabAvailable(tabId, family = state.family) {
    if (!familiesOn) return true;
    const tab = TABS.find((t) => t.id === tabId);
    if (!tab.kind && family === 'ci') return true;   // the day cache
    return contextSeries(tabId, family).length > 0;
  }

  // Decorate the availability rule with the active tab's field gate, so the
  // controls (toggles, shell union) see fields outside the study as having
  // no data — and stay that way through every ui refresh.
  const baseFrameSource = hooks.frameSource;
  hooks.frameSource = (field) => {
    const tab = TABS.find((t) => t.id === current);
    return tab?.fields && !tab.fields.includes(field)
      ? null : baseFrameSource(field);
  };
  if (familiesOn) {
    hooks.unavailableTitle = (field) =>
      (familyHasField(state.family, field) ? null
        : `${FIELD_LABELS[field] ?? field}: not part of the `
          + `${FAMILY_LABELS[state.family] ?? state.family} model series`);
  }

  const nav = document.createElement('nav');
  nav.id = 'study-tabs';
  nav.setAttribute('aria-label', 'study');
  const buttons = {};
  for (const tab of TABS) {
    if (tab.kind && !seriesOfKind(manifest, tab.kind).length) continue;
    const b = document.createElement('button');
    b.id = `tab-${tab.id}`;
    b.textContent = tab.label;
    b.addEventListener('click', () => switchTab(tab.id));
    nav.appendChild(b);
    buttons[tab.id] = b;
  }
  document.getElementById('title').after(nav);

  // Page-level "Model series" selector (v2.9) — sits before the tab strip.
  let familySelect = null;
  if (familiesOn) {
    const wrap = document.createElement('label');
    wrap.id = 'family-bar';
    wrap.append('Model series ');
    familySelect = document.createElement('select');
    familySelect.id = 'family-select';
    for (const fam of familiesPresent(manifest)) {
      const opt = document.createElement('option');
      opt.value = fam;
      opt.textContent = FAMILY_LABELS[fam] ?? fam;
      familySelect.appendChild(opt);
    }
    familySelect.value = state.family;
    familySelect.addEventListener('change', () =>
      switchFamily(familySelect.value));
    wrap.appendChild(familySelect);
    nav.before(wrap);
  }

  const select = document.createElement('select');
  select.id = 'series-select';
  select.addEventListener('change', () => {
    state.day = select.value;
    state.pos = 0;
    refresh();
  });
  const dateEl = document.getElementById('date-picker');
  dateEl.before(select);             // same header slot, swapped per tab

  function populateSelect(ids) {
    select.replaceChildren();
    for (const id of ids) {
      const opt = document.createElement('option');
      opt.value = id;
      opt.textContent = manifest.series[id].label ?? id;
      select.appendChild(opt);
    }
  }
  populateSelect(familiesOn ? contextSeries()
                            : seriesOfKind(manifest, 'annual'));

  // The day shown by the locked Combined picker: a real day is itself; a
  // (CHAOS) diurnal series resolves to its first epoch's calendar date.
  function dayDisplayDate(day) {
    const rec = manifest.series?.[day];
    return rec ? rec.epochs[0].slice(0, 10) : day;
  }

  // Core tab control (v2.9): one displayed field, B or dB/dt — replaces the
  // summing checkboxes in the same header slot (control budget by swap).
  let svBar = null;
  if (familiesOn) {
    svBar = document.createElement('div');
    svBar.id = 'sv-toggle';
    svBar.hidden = true;
    for (const [val, text, title] of [
      ['core', 'B', 'main field, nT'],
      ['core-sv', 'dB/dt', 'secular variation, nT/yr — '
        + 'F shows |dB/dt|, not dF/dt'],
    ]) {
      const label = document.createElement('label');
      label.className = 'comp-radio';
      label.title = title;
      const rb = document.createElement('input');
      rb.type = 'radio';
      rb.name = 'sv';
      rb.value = val;
      rb.id = `sv-${val === 'core' ? 'b' : 'dbdt'}`;
      rb.addEventListener('change', () => {
        for (const f of Object.keys(state.enabled)) state.enabled[f] = false;
        state.enabled[val] = true;
        state.vmaxLock = null;       // an nT lock is meaningless in nT/yr
        refresh();
      });
      label.append(rb, document.createTextNode(text));
      svBar.appendChild(label);
    }
    const togglesEl = document.getElementById('field-toggles');
    togglesEl.after(svBar);
  }

  function refresh() {
    applyTimeline(timeline, manifest, state);
    const tab = TABS.find((t) => t.id === current);
    const gate = tab?.fields;
    if (gate) {                      // covers permalinks like f=crust,iono too
      for (const field of Object.keys(state.enabled)) {
        if (!gate.includes(field)) state.enabled[field] = false;
      }
    }
    if (tab?.exclusive) {            // exactly one of B / dB/dt
      if (state.enabled['core-sv']) state.enabled.core = false;
      if (!state.enabled.core && !state.enabled['core-sv']) {
        state.enabled.core = true;
      }
      const dbdt = document.getElementById('sv-dbdt');
      const b = document.getElementById('sv-b');
      if (dbdt && b) {
        dbdt.checked = !!state.enabled['core-sv'];
        b.checked = !dbdt.checked;
      }
    }
    // The Combined ("daily") tab pins the day: the picker is locked to the
    // preconfigured time (the default day for CI, the diurnal series' date for
    // CHAOS) rather than fetching arbitrary days. CHAOS folds into that same
    // locked field, so the series <select> is now only the Core/Ionosphere
    // study picker.
    const onDaily = current === 'daily';
    dateEl.hidden = !onDaily;
    select.hidden = onDaily;
    if (onDaily) {
      dateEl.disabled = true;
      dateEl.value = dayDisplayDate(state.day);
    } else {
      populateSelect(familiesOn ? contextSeries()
                                : seriesOfKind(manifest, 'annual'));
      select.value = state.day;
    }
    if (svBar) {
      svBar.hidden = !tab?.exclusive;
      document.getElementById('field-toggles').hidden = !!tab?.exclusive;
    }
    for (const [id, b] of Object.entries(buttons)) {
      b.setAttribute('aria-selected', String(id === current));
      if (familiesOn) {
        const ok = tabAvailable(id);
        b.disabled = !ok;
        b.title = ok ? '' : `no ${TABS.find((t) => t.id === id).label} data `
          + `in the ${FAMILY_LABELS[state.family] ?? state.family} `
          + 'model series';
      }
    }
    const attribution = document.getElementById('model-attribution');
    if (familiesOn && attribution) {
      attribution.textContent =
        FAMILY_ATTRIBUTION[state.family] ?? FAMILY_ATTRIBUTION.ci;
    }
    for (const field of Object.keys(state.enabled)) {
      const cb = document.getElementById(`toggle-${field}`);
      if (cb) cb.checked = state.enabled[field];
    }
    ui.refreshShellSlider();         // re-snaps state.shell if it vanished
    const radiusM = Object.values(manifest.fields)
      .map((spec) => spec.shells[state.shell])
      .find((r) => r !== undefined);
    if (radiusM !== undefined) hooks.setShell(radiusM / R_SURFACE_M);
    ui.refreshColorbar();
    ui.refreshTimeBar();
    ui.onTimeAdvance();
    hooks.applyTextures();
  }

  // Land a (tab, family) context on its default data: the day cache for
  // Combined×CI, the context's first series otherwise.
  function applyContextDefaults(tab) {
    const ids = contextSeries(tab.id);
    if (!tab.kind && (!familiesOn || state.family === 'ci')) {
      state.day = manifest.default_day;
    } else {
      state.day = ids[0] ?? manifest.default_day;
    }
    state.pos = 0;
    if (tab.defaults) Object.assign(state.enabled, tab.defaults);
  }

  function enterContext(id) {
    current = id;
    const tab = TABS.find((t) => t.id === id);
    const prev = saved[snapKey(id)];
    if (prev) {
      state.day = prev.day;
      state.pos = prev.pos;
      state.shell = prev.shell;
      Object.assign(state.enabled, prev.enabled);
    } else {
      applyContextDefaults(tab);
    }
    refresh();
  }

  function switchTab(id) {
    if (id === current || !tabAvailable(id)) return;
    saved[snapKey(current)] = { day: state.day, pos: state.pos,
                                enabled: { ...state.enabled },
                                shell: state.shell };
    enterContext(id);
  }

  function bestTab(preferred) {
    return tabAvailable(preferred) ? preferred
      : TABS.find((t) => buttons[t.id] && tabAvailable(t.id))?.id ?? 'daily';
  }

  function switchFamily(family) {
    if (family === state.family) return;
    saved[snapKey(current)] = { day: state.day, pos: state.pos,
                                enabled: { ...state.enabled },
                                shell: state.shell };
    state.family = family;
    if (familySelect) familySelect.value = family;
    // the active tab may have no data in the new family — fall over to the
    // first tab that does (Combined×CI always exists)
    enterContext(bestTab(current));
  }

  if (familiesOn && state.family !== 'ci' && !manifest.series?.[state.day]) {
    // a lens-only permalink (family= without series=): the restored day is
    // CI data — land on the family's default context instead
    enterContext(bestTab(current));
  } else {
    refresh();
  }
}
