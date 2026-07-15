// Study selection (PLAN v2.3 + v2.9 + v2.10 + v2.11; IDEAS §9.4/§9.7): a
// study binds a time axis + the controls that make sense for it, over the
// one shared globe. v2.10 presents the choice as two dropdowns (inverting
// the v2.9 tab strip): a primary "Field to explore" select (All / Core /
// Crust / Ionosphere / Magnetosphere — v2.11) and, under `families`, a
// secondary "Model" select. Field is primary: pick a study, then a model
// that has data for it — a model missing the field greys out, and
// symmetrically a field the chosen model can't serve greys out (else
// picking it would silently discard the model choice). v2.11 covers
// every grid-evaluable VirES model: ci and chaos stay the only multi-field
// lenses; each remaining model is a single-field family riding one curated
// series (docs/v211_model_probe.json), and the served-but-unevaluated
// models (CHAOS-MIO, AMPS, MLI_SHA_2E) stay visible as permanently greyed
// entries. With `families` off only the field select shows, over the v1
// lineup. Model is a lens: it filters which series each study offers; the
// day cache is CI-only, so kind-less tabs under non-ci lenses swap the date
// picker for the family's diurnal series. The Core study shows exactly one
// field at a time via a B ↔ dB/dt radio (the units rule: nT/yr never sums
// with nT), clearing the colorbar lock on unit changes.
//
// The active study gates controls (IDEAS §8.2 control budget): outside
// All×CI the date picker is hidden and a series <select> takes its slot.
// Each study snapshots {day, pos, enabled, shell} per model on leave and
// restores it on return. Study ids (daily/core/crust/seasons/magneto) are
// permalink keys — labels can change, ids cannot. state.tab round-trips
// through the permalink so the two kind-less tabs (All, Magnetosphere) —
// indistinguishable from the data alone — restore faithfully (v2.11).

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
  { id: 'daily', label: 'All' },
  { id: 'core', label: 'Core', kind: 'secular',
    fields: ['core', 'core-sv'], exclusive: true,
    defaults: { core: true, crust: false, iono: false, magneto: false,
                'core-sv': false } },
  // v2.11: `crust` plays the timeless kind="static" series; `magneto` keeps
  // no kind like `daily` — it rides the day cache (CI) or any diurnal series
  // carrying a magnetosphere layer (the CHAOS day, the MMA_SHA_2F day), so
  // it needs no duplicate data.
  { id: 'crust', label: 'Crust', kind: 'static',
    fields: ['crust'],
    defaults: { core: false, crust: true, iono: false, magneto: false,
                'core-sv': false } },
  { id: 'seasons', label: 'Ionosphere', kind: 'annual',
    fields: ['iono'],
    defaults: { core: false, crust: false, iono: true, magneto: false,
                'core-sv': false } },
  { id: 'magneto', label: 'Magnetosphere',
    fields: ['magneto'],
    defaults: { core: false, crust: false, iono: false, magneto: true,
                'core-sv': false } },
];

export const FAMILY_LABELS = {
  ci: 'Swarm CI', chaos: 'CHAOS',
  mco2d: 'MCO_SHA_2D', igrf: 'IGRF',
  lcs1: 'LCS-1', mf7: 'MF7', mli2d: 'MLI_SHA_2D',
  mio2d: 'MIO_SHA_2D', mma2f: 'MMA_SHA_2F',
  mli2e: 'MLI_SHA_2E', amps: 'AMPS',
};
// Model dropdown order (v2.11): the multi-field lenses first, then the
// single-model families by layer (core, crust, iono, magneto), the
// unevaluated entries last. familiesPresent() sorts by this; unknown
// families sort after everything curated.
const FAMILY_ORDER = ['ci', 'chaos', 'mco2d', 'igrf', 'lcs1', 'mf7',
                      'mli2d', 'mio2d', 'mma2f', 'mli2e', 'amps'];
// Served by VirES but deliberately not evaluated (v2.11 probe record,
// docs/v211_model_probe.json): permanently greyed Model options, so the
// dropdown is honest about what VirES serves vs what this app renders.
const UNEVALUATED_FAMILIES = {
  mli2e: 'MLI_SHA_2E is served by VirES but not evaluated here: degree '
    + '16–600 far exceeds what the 1° pipeline grid can resolve',
  amps: 'AMPS is served by VirES but not evaluated here: an average polar '
    + 'ionospheric-current model, not a global spherical-harmonic field',
};
// Layer-specific footnotes for the grey-out tooltips (v2.11): the one
// VirES model skipped inside an otherwise-covered family.
const FAMILY_FIELD_NOTES = {
  'chaos:iono': ' (CHAOS-MIO is served by VirES but deliberately '
    + 'unevaluated — decision 2026-06-12)',
};
// Model-series attribution (#model-attribution). Static, trusted HTML set via
// innerHTML: each model name links to its reference page — the Swarm handbook
// catalogue for the CI products, the CHAOS-8 release for the CHAOS series.
const swCat = (label, code) =>
  `<a href="https://swarmhandbook.earth.esa.int/catalogue/${code}"`
  + ` target="_blank" rel="noopener">${label}</a>`;
export const FAMILY_ATTRIBUTION = {
  ci: 'Comprehensive Inversion models ('
    + ['MCO', 'MLI', 'MIO', 'MMA']
      .map((a) => swCat(a, `sw_${a.toLowerCase()}_sha_2c`)).join('/')
    + '_SHA_2C; DTU Space et al.)',
  chaos: 'CHAOS model series (<a href="https://www.spacecenter.dk/files/'
    + 'magnetic-models/CHAOS-8/" target="_blank" rel="noopener">'
    + 'CHAOS-Core/-Static/-MMA</a>; DTU Space)',
  mco2d: 'Dedicated core field model ('
    + swCat('MCO_SHA_2D', 'sw_mco_sha_2d') + '; ESA Swarm L2)',
  igrf: 'International Geomagnetic Reference Field ('
    + '<a href="https://www.ncei.noaa.gov/products/'
    + 'international-geomagnetic-reference-field" target="_blank"'
    + ' rel="noopener">IGRF</a>; IAGA V-MOD)',
  lcs1: 'Lithospheric model from CHAMP & Swarm ('
    + '<a href="https://www.spacecenter.dk/files/magnetic-models/LCS-1/"'
    + ' target="_blank" rel="noopener">LCS-1</a>; Olsen et al. 2017)',
  mf7: 'Crustal field model from CHAMP ('
    + '<a href="https://geomag.us/models/MF7.html" target="_blank"'
    + ' rel="noopener">MF7</a>; Maus et al., CIRES/NGDC)',
  mli2d: 'Dedicated lithospheric model ('
    + swCat('MLI_SHA_2D', 'sw_mli_sha_2d') + '; ESA Swarm L2)',
  mio2d: 'Dedicated ionospheric model ('
    + swCat('MIO_SHA_2D', 'sw_mio_sha_2d') + '; ESA Swarm L2)',
  mma2f: 'Fast-track magnetospheric model ('
    + swCat('MMA_SHA_2F', 'sw_mma_sha_2f') + '; ESA Swarm L2)',
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
  // curated order, not manifest-insertion (= export-completion) order —
  // the dropdown must not reshuffle between deploys (v2.11)
  const rank = (f) => {
    const i = FAMILY_ORDER.indexOf(f);
    return i < 0 ? FAMILY_ORDER.length : i;
  };
  return [...fams].sort((a, b) => rank(a) - rank(b));
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
  // An explicit tab= permalink key wins when it can host the restored
  // day/series — the two kind-less tabs (All, Magnetosphere) are
  // indistinguishable from the data alone (v2.11).
  function tabAccepts(tab, day) {
    const rec = manifest.series?.[day];
    return tab.kind ? rec?.kind === tab.kind
                    : !rec || rec.kind === 'diurnal';
  }
  const wanted = TABS.find((t) => t.id === state.tab);
  let current = wanted && tabAccepts(wanted, state.day)
    ? wanted.id : tabOf(state, manifest);
  state.tab = current;
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
  // stand in for the day cache on kind-less tabs under non-ci families. A
  // field-gated kind-less tab (Magnetosphere) keeps only the diurnal series
  // that carry its field — reusing e.g. the CHAOS day's magnetosphere layer
  // rather than duplicating it into a dedicated series (v2.11).
  function contextSeries(tabId = current, family = state.family) {
    const tab = TABS.find((t) => t.id === tabId);
    if (tab.kind) return seriesOfKind(manifest, tab.kind, family);
    const ids = family === 'ci' ? []
      : seriesOfKind(manifest, 'diurnal', family);
    if (!tab.fields) return ids;
    return ids.filter((id) =>
      tab.fields.some((f) => manifest.series[id].fields.includes(f)));
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
          + `${FAMILY_LABELS[state.family] ?? state.family} model series`
          + (FAMILY_FIELD_NOTES[`${state.family}:${field}`] ?? ''));
  }

  // Primary selector: "Field to explore" (v2.10) — a dropdown over the study
  // ids (All / Core / Ionosphere). Ids are permalink keys; labels can vary.
  const fieldBar = document.createElement('label');
  fieldBar.id = 'field-bar';
  fieldBar.append('Field to explore ');
  const fieldSelect = document.createElement('select');
  fieldSelect.id = 'field-select';
  const rendered = new Set();
  for (const tab of TABS) {
    if (tab.kind && !seriesOfKind(manifest, tab.kind).length) continue;
    const opt = document.createElement('option');
    opt.value = tab.id;
    opt.textContent = tab.label;
    fieldSelect.appendChild(opt);
    rendered.add(tab.id);
  }
  fieldSelect.value = current;
  fieldSelect.addEventListener('change', () => switchField(fieldSelect.value));
  fieldBar.appendChild(fieldSelect);
  document.getElementById('title').after(fieldBar);

  // Secondary selector: "Model" (v2.9 family lens) — sits AFTER the field
  // dropdown. A model with no data for the current field greys out; refresh()
  // maintains each option's disabled state + tooltip.
  let familySelect = null;
  if (familiesOn) {
    const wrap = document.createElement('label');
    wrap.id = 'family-bar';
    wrap.append('Model ');
    familySelect = document.createElement('select');
    familySelect.id = 'family-select';
    for (const fam of familiesPresent(manifest)) {
      const opt = document.createElement('option');
      opt.value = fam;
      opt.textContent = FAMILY_LABELS[fam] ?? fam;
      familySelect.appendChild(opt);
    }
    // served-but-unevaluated models (v2.11): visible, never selectable —
    // refresh() skips them so they stay disabled with their fixed tooltip
    for (const [fam, why] of Object.entries(UNEVALUATED_FAMILIES)) {
      const opt = document.createElement('option');
      opt.value = fam;
      opt.textContent = FAMILY_LABELS[fam] ?? fam;
      opt.disabled = true;
      opt.title = why;
      opt.dataset.unevaluated = '1';
      familySelect.appendChild(opt);
    }
    familySelect.value = state.family;
    familySelect.addEventListener('change', () =>
      switchFamily(familySelect.value));
    wrap.appendChild(familySelect);
    fieldBar.after(wrap);
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
    // Kind-less tabs (All, Magnetosphere) pin the day: the picker is locked
    // to the preconfigured time (the default day for CI, the diurnal
    // series' date otherwise) rather than fetching arbitrary days. Kind
    // tabs swap in the series <select> (Core/Crust/Ionosphere study picker).
    const pinned = !tab?.kind;
    dateEl.hidden = !pinned;
    select.hidden = pinned;
    if (pinned) {
      dateEl.disabled = true;
      dateEl.value = dayDisplayDate(state.day);
    } else {
      populateSelect(familiesOn ? contextSeries()
                                : seriesOfKind(manifest, 'annual'));
      select.value = state.day;
    }
    // a single-epoch context (the timeless Crust study) has no time axis —
    // hide the transport; main.js also refuses to advance a zero span
    const timebar = document.getElementById('timebar');
    if (timebar) timebar.hidden = timeline.nEpochs <= 1;
    if (timeline.nEpochs <= 1) state.playing = false;
    if (svBar) {
      svBar.hidden = !tab?.exclusive;
      document.getElementById('field-toggles').hidden = !!tab?.exclusive;
    }
    fieldSelect.value = current;
    if (familiesOn) {
      // grey out the fields the chosen model has no data for — symmetric
      // with the model grey-out below. Without this, picking such a field
      // silently swapped the model back to one that has it (e.g. All ×
      // MMA_SHA_2F offered Crust, which landed on Swarm CI) — surprising,
      // and it discarded the user's model choice. The active field stays
      // enabled by construction (every entry path lands on an available
      // tab first).
      for (const opt of fieldSelect.options) {
        const ok = opt.value === current
          || tabAvailable(opt.value, state.family);
        opt.disabled = !ok;
        const target = TABS.find((t) => t.id === opt.value);
        opt.title = ok ? '' : `no ${target.label} data in the `
          + `${FAMILY_LABELS[state.family] ?? state.family} model series`
          + (target.fields ?? [])
            .map((f) => FAMILY_FIELD_NOTES[`${state.family}:${f}`] ?? '')
            .join('');
      }
    }
    if (familiesOn && familySelect) {
      // grey out the models that have no data for the chosen field; the
      // unevaluated entries stay disabled with their fixed tooltip (v2.11)
      for (const opt of familySelect.options) {
        if (opt.dataset.unevaluated) continue;
        const ok = tabAvailable(current, opt.value);
        opt.disabled = !ok;
        opt.title = ok ? '' : `no ${TABS.find((t) => t.id === current).label} `
          + `data in the ${FAMILY_LABELS[opt.value] ?? opt.value} model series`
          + (tab?.fields ?? [])
            .map((f) => FAMILY_FIELD_NOTES[`${opt.value}:${f}`] ?? '')
            .join('');
      }
      familySelect.value = state.family;
    }
    const attribution = document.getElementById('model-attribution');
    if (familiesOn && attribution) {
      attribution.innerHTML =
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
    state.tab = id;                  // permalink key (v2.11)
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

  // Field is the primary selector: choose a study, keep the current model if
  // it has data for it, else fall the model back to the first that does.
  function switchField(id) {
    if (id === current) return;
    saved[snapKey(current)] = { day: state.day, pos: state.pos,
                                enabled: { ...state.enabled },
                                shell: state.shell };
    if (familiesOn && !tabAvailable(id, state.family)) {
      state.family = familiesPresent(manifest)
        .find((f) => tabAvailable(id, f)) ?? 'ci';
      if (familySelect) familySelect.value = state.family;
    }
    enterContext(id);
  }

  function bestField(preferred) {
    return tabAvailable(preferred) ? preferred
      : TABS.find((t) => rendered.has(t.id) && tabAvailable(t.id))?.id
        ?? 'daily';
  }

  function switchFamily(family) {
    if (family === state.family) return;
    saved[snapKey(current)] = { day: state.day, pos: state.pos,
                                enabled: { ...state.enabled },
                                shell: state.shell };
    state.family = family;
    if (familySelect) familySelect.value = family;
    // field stays put when its data survives the model switch (disabled
    // options guarantee it); bestField is a dead safety net
    enterContext(bestField(current));
  }

  if (familiesOn && state.family !== 'ci' && !manifest.series?.[state.day]) {
    // a lens-only permalink (family= without series=): the restored day is
    // CI data — land on the family's default context instead
    enterContext(bestField(current));
  } else {
    refresh();
  }
}
