// Controls: field toggles, component radios, shell slider, date picker,
// bottom-docked time bar, colorbar. Pure DOM wiring — no three.js here.

export const FIELD_LABELS = {
  core: 'Core', crust: 'Crust', iono: 'Ionosphere', magneto: 'Magnetosphere',
  'core-sv': 'Core dB/dt',
};
// Display names only — 'N'/'E'/'Up'/'F' stay the keys in state.component,
// the c= permalink, COMPONENT_MASK and the radio values/ids (v2.12).
export const COMPONENT_LABELS = {
  N: 'Northward', E: 'Eastward', Up: 'Upward', F: 'Intensity',
};
export const R_SURFACE_M = 6371000;

export function shellLabel(slug, radiusM) {
  if (slug === 'cmb') return 'CMB −2891 km';
  const altKm = Math.round((radiusM - R_SURFACE_M) / 1000);
  if (altKm === 0) return 'surface';
  return altKm > 0 ? `+${altKm} km` : `−${-altKm} km`;
}

// Shell ladder: union of the enabled fields' radii (all fields' if none
// on). Module-scope (v2.13) so features/timeseries.js snaps typed radii
// against the very ladder the slider offers.
export function shellUnion(state, manifest, hooks) {
  const on = Object.entries(state.enabled)
    .filter(([, v]) => v).map(([f]) => f);
  const fields = on.length ? on : Object.keys(manifest.fields);
  const byRadius = new Map();
  for (const f of fields) {
    // a series may carry a shell subset; fields without data here keep
    // their full ladder (they are disabled by the toggles, not the slider)
    const subset = hooks.frameSource(f)?.shells;
    for (const [slug, r] of Object.entries(manifest.fields[f].shells)) {
      if (subset && !subset.includes(slug)) continue;
      byRadius.set(r, slug);
    }
  }
  return [...byRadius.entries()].sort((a, b) => a[0] - b[0])
    .map(([r, slug]) => [slug, r]);
}

export function fmtTime(minutes) {
  const h = String(Math.floor(minutes / 60) % 24).padStart(2, '0');
  const m = String(Math.floor(minutes % 60)).padStart(2, '0');
  return `${h}:${m}`;
}

export function initUI(state, manifest, hooks, timeline) {
  const $ = (id) => document.getElementById(id);

  // --- data availability -------------------------------------------------
  // hooks.frameSource is the one availability rule (dataset.js): which tile
  // sequence, if any, a field has at the current day/series + shell.
  function fieldAvailable(field) {
    const src = hooks.frameSource(field);
    return !!src && src.shells.includes(state.shell);
  }

  // --- field toggles ------------------------------------------------------
  const togglesEl = $('field-toggles');
  const checkboxes = {};
  for (const field of Object.keys(manifest.fields)) {
    // The units rule (IDEAS §9.6) as code: the checkboxes sum on the GPU,
    // so only nT fields get one. nT/yr fields display via tab gating only.
    if ((manifest.fields[field].units ?? 'nT') !== 'nT') continue;
    const label = document.createElement('label');
    label.className = `field-toggle field-${field}`;
    const cb = document.createElement('input');
    cb.type = 'checkbox';
    cb.id = `toggle-${field}`;
    cb.checked = state.enabled[field];
    cb.addEventListener('change', () => {
      state.enabled[field] = cb.checked;
      refreshShellSlider();
      refreshColorbar();
      hooks.applyTextures();
    });
    label.append(cb, document.createTextNode(FIELD_LABELS[field]));
    togglesEl.appendChild(label);
    checkboxes[field] = cb;
  }
  function refreshToggles() {
    for (const [field, cb] of Object.entries(checkboxes)) {
      const ok = fieldAvailable(field);
      cb.disabled = !ok;
      cb.parentElement.classList.toggle('unavailable', !ok);
      // a feature may know *why* a field is out (family lacks the layer)
      cb.parentElement.title = ok ? ''
        : hooks.unavailableTitle?.(field)
          ?? `${FIELD_LABELS[field]}: no data at this shell/day`;
    }
  }

  // --- component radios ----------------------------------------------------
  for (const comp of ['N', 'E', 'Up', 'F']) {
    const label = document.createElement('label');
    label.className = 'comp-radio';
    const rb = document.createElement('input');
    rb.type = 'radio';
    rb.name = 'component';
    rb.value = comp;
    rb.id = `comp-${comp}`;
    rb.checked = state.component === comp;
    rb.addEventListener('change', () => {
      state.component = comp;
      hooks.applyComponent();
    });
    label.append(rb, document.createTextNode(COMPONENT_LABELS[comp]));
    $('component-radios').appendChild(label);
  }

  // --- shell slider ---------------------------------------------------------
  // Snaps to the union of the enabled fields' radii (all fields' if none on).
  const shellSlider = $('shell-slider');
  const shellLabelEl = $('shell-label');
  let shellRadii = [];   // [[slugOrNull, radius_m], ...] ascending

  function refreshShellSlider() {
    shellRadii = shellUnion(state, manifest, hooks);
    shellSlider.max = String(shellRadii.length - 1);
    let idx = shellRadii.findIndex(([slug]) => slug === state.shell);
    if (idx < 0) {                 // current shell gone: snap to nearest
      idx = 0;
      state.shell = shellRadii[0][0];
    }
    shellSlider.value = String(idx);
    shellLabelEl.textContent = shellLabel(...shellRadii[idx]);
    refreshToggles();
  }
  // Slider drags fire per input event (up to display rate); the label/state
  // updates are cheap but the texture pass is not — coalesce to one
  // applyTextures per frame, flagged as a scrub so superseded tile fetches
  // are aborted instead of piling onto the server.
  let applyQueued = false;
  function scheduleScrubApply() {
    if (applyQueued) return;
    applyQueued = true;
    requestAnimationFrame(() => {
      applyQueued = false;
      hooks.applyTextures({ scrub: true });
    });
  }

  shellSlider.addEventListener('input', () => {
    const [slug, radiusM] = shellRadii[Number(shellSlider.value)];
    state.shell = slug;
    shellLabelEl.textContent = shellLabel(slug, radiusM);
    refreshToggles();
    refreshColorbar();
    hooks.setShell(radiusM / R_SURFACE_M);
    scheduleScrubApply();
  });

  // --- date picker -----------------------------------------------------------
  const dateEl = $('date-picker');
  dateEl.value = state.day;
  if (manifest.validity) {
    dateEl.min = manifest.validity.start.slice(0, 10);
    dateEl.max = manifest.validity.end.slice(0, 10);
  }
  dateEl.addEventListener('change', () => {
    if (!dateEl.value) return;
    hooks.pickDay ? hooks.pickDay(dateEl.value) : setDay(dateEl.value);
  });
  function setDay(day) {
    state.day = day;
    dateEl.value = day;
    refreshToggles();
    refreshColorbar();
    hooks.applyTextures();
  }

  const chipEl = $('fetch-chip');
  function showFetchChip(text, isError = false) {
    chipEl.textContent = text;
    chipEl.hidden = false;
    chipEl.classList.toggle('error', isError);
  }
  function hideFetchChip() { chipEl.hidden = true; }

  // --- bottom time bar --------------------------------------------------------
  // The slider runs in ticks of the active timeline (state.pos × subdiv), so
  // a timeline change only has to update `timeline` and call refreshTimeBar.
  const timeSlider = $('time-slider');
  const timeLabel = $('time-label');
  const playBtn = $('play-btn');
  function refreshTimeBar() {
    timeSlider.max = String((timeline.nEpochs - 1) * timeline.subdiv);
  }
  timeSlider.addEventListener('input', () => {
    state.pos = Number(timeSlider.value) / timeline.subdiv;
    timeLabel.textContent = timeline.label(state.pos);
    scheduleScrubApply();
  });
  playBtn.addEventListener('click', () => {
    state.playing = !state.playing;
    playBtn.textContent = state.playing ? '⏸' : '⏵';
  });
  $('speed-select').addEventListener('change', (e) => {
    state.speed = Number(e.target.value);
  });
  function onTimeAdvance() {
    timeSlider.value = String(Math.floor(state.pos * timeline.subdiv));
    timeLabel.textContent = timeline.label(state.pos);
  }

  // --- colorbar -----------------------------------------------------------------
  function refreshColorbar() {
    const vmax = hooks.displayVmax();
    const units = hooks.displayUnits?.() ?? 'nT';
    const label = vmax.toLocaleString('en-US',
                                     { maximumSignificantDigits: 3 });
    $('colorbar-min').textContent = `−${label} ${units}`;
    $('colorbar-max').textContent = `+${label} ${units}`;
  }

  // Scale lock: freeze the colorbar range at its current value so magnitude
  // changes stay visible while stepping shells/days; click again for auto.
  const lockBtn = $('colorbar-lock');
  function refreshLockBtn() {
    const locked = state.vmaxLock != null;
    lockBtn.textContent = locked ? '🔒' : '🔓';
    lockBtn.setAttribute('aria-pressed', String(locked));
    lockBtn.title = locked ? 'unlock colour scale (auto range)'
                           : 'lock colour scale';
  }
  lockBtn.addEventListener('click', () => {
    state.vmaxLock = state.vmaxLock == null ? hooks.displayVmax() : null;
    refreshLockBtn();
    refreshColorbar();
    hooks.applyTextures();
  });
  refreshLockBtn();

  // --- collapsible chrome (v2.14: mobile) ---------------------------------
  // The header and the vis-options box fold away to reclaim globe space;
  // small screens boot collapsed. Pure chrome — never in the permalink.
  function wireCollapse(boxId, btnId, glyphs, label) {
    const box = $(boxId);
    const btn = $(btnId);
    if (!box || !btn) return;
    const apply = (collapsed) => {
      box.classList.toggle('collapsed', collapsed);
      btn.setAttribute('aria-expanded', String(!collapsed));
      btn.textContent = collapsed ? glyphs[0] : glyphs[1];
      btn.title = `${collapsed ? 'Show' : 'Hide'} ${label}`;
      // the globe pane grows/shrinks with the header — reuse the window
      // resize path (globe.js listens there)
      window.dispatchEvent(new Event('resize'));
    };
    btn.addEventListener('click', () =>
      apply(!box.classList.contains('collapsed')));
    if (window.matchMedia('(max-width: 640px)').matches) apply(true);
  }
  wireCollapse('controls', 'controls-toggle', ['☰', '▴'], 'controls');
  wireCollapse('vis-options', 'vis-options-toggle', ['⚙', '✕'],
               'visualisation options');

  refreshShellSlider();
  refreshColorbar();
  refreshTimeBar();
  onTimeAdvance();

  return { onTimeAdvance, setDay, refreshToggles, refreshShellSlider,
           refreshColorbar, refreshTimeBar, showFetchChip, hideFetchChip };
}
