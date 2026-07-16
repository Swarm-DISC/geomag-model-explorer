// Timeline viewer (PLAN v2.13): time series at a pinned location. Adds a
// Globe | Time series | Combined view toggle; a point is pinned by clicking
// the globe or typing coordinates (geocentric or WGS84 geodetic); three
// stacked chart panels (vendored uPlot) plot the summed enabled fields at
// the pin over the active timeline — same tiles, same availability rule
// (hooks.frameSource) as the globe, so the two views can never disagree.
//
// The pin rides the globe's shell: a typed radius/height snaps to the
// nearest rung of the slider's own ladder (ui.js shellUnion) and moves the
// slider, so the globe, hover readout and charts always sample the same
// surface. Geocentric is the native convention (the tiles are evaluated on
// geocentric radii); geodetic input converts on entry and the echoed
// geodetic latitude is re-derived from the authoritative geocentric pin.
//
// Assembly is texture-LRU-neutral (dataset.samplePoint), aborts stale runs,
// keeps a small result cache, and samples non-stepped fields (daily core,
// static crust, single_step series members) once per run. A tile that fails
// leaves a gap (null) at that epoch — never a partial sum, which would
// silently change the plotted quantity mid-series.
//
// Flag `timeseries`: with the flag off nothing here loads and the app is
// byte-identical v2.12 (the panel and toggle are module-created, not static
// HTML).

import * as THREE from 'three';
import uPlot from 'uplot';
import { samplePoint, storageGrid } from '../dataset.js';
import { geodeticToGeocentric, geocentricToGeodetic } from '../geodesy.js';
import { parseUT, seriesUT } from '../sun.js';
import { R_SURFACE_M, shellLabel, shellUnion } from '../ui.js';

const DEG = Math.PI / 180;
const CLICK_PX = 5;      // pointer travel beyond this is an orbit drag
const CLICK_MS = 500;
const POOL = 8;          // concurrent tile fetches per assembly
const CACHE_MAX = 8;     // assembled series kept for instant re-show
const DEBOUNCE_MS = 150; // settle time before an assembly starts
const CURSOR_MS = 100;   // time-cursor redraw throttle (~10 Hz playback)

const VIEWS = [
  { id: 'globe', label: 'Globe', title: 'Globe only (v1 view)' },
  { id: 'series', label: 'Time series',
    title: 'Charts of the pinned location over the active timeline' },
  { id: 'combined', label: 'Combined',
    title: 'Globe above, time-series charts below' },
];

const DATUMS = [
  { id: 'geocentric', label: 'geocentric', rh: 'r',
    title: 'geocentric latitude, radius from Earth center (native)' },
  { id: 'geodetic', label: 'geodetic', rh: 'h',
    title: 'WGS84 latitude, height above the ellipsoid' },
];

// Display conventions over the stored geocentric [N, E, C] sums (C = center,
// radially inward): pure sign relabelings, zero re-assembly on toggle.
const neg = (v) => (v == null ? null : -v);
const CONVENTIONS = {
  neu: { label: 'N/E/Up', title: 'Northward / Eastward / Upward',
         names: ['Northward', 'Eastward', 'Upward'],
         rows: (d) => [d.N, d.E, d.C.map(neg)] },
  rtp: { label: 'R/θ/φ', title: 'spherical: radial / colatitude / east',
         names: ['B_r (radial)', 'B_θ (southward)', 'B_φ (eastward)'],
         rows: (d) => [d.C.map(neg), d.N.map(neg), d.E] },
  nec: { label: 'NEC', title: 'as stored: north / east / center (down)',
         names: ['B_N', 'B_E', 'B_C (down)'],
         rows: (d) => [d.N, d.E, d.C] },
};

function fmtLatLon(lat, lon) {
  const f = (v) => Math.abs(v).toFixed(2);
  return `${f(lat)}°${lat >= 0 ? 'N' : 'S'}, ${f(lon)}°${lon >= 0 ? 'E' : 'W'}`;
}

// Permalink keys (written by features/permalink.js only under this flag,
// so they die with it): view= (≠ globe), pt=<lat>,<lon> (geocentric, 2 dp),
// ptc= (≠ neu). Unknown/invalid values degrade to defaults (the stability
// contract) — same pattern as features/sun.js / relief.js / frame.js.
export function restore({ state }) {
  const p = new URLSearchParams(window.location.hash.slice(1));
  const view = p.get('view');
  if (view === 'series' || view === 'combined') state.view = view;
  const pt = (p.get('pt') ?? '').split(',').map(Number);
  if (pt.length === 2 &&
      Number.isFinite(pt[0]) && Math.abs(pt[0]) <= 90 &&
      Number.isFinite(pt[1]) && Math.abs(pt[1]) <= 180) {
    state.point = { lat: pt[0], lon: pt[1] };
  }
  const c = p.get('ptc');
  if (c === 'rtp' || c === 'nec') state.tsConvention = c;
}

export function attach({ state, manifest, globe, ui, hooks, timeline,
                         onChange }) {
  state.view ??= 'globe';
  state.point ??= null;            // { lat, lon } geocentric degrees, or null
  state.tsConvention ??= 'neu';
  let datum = 'geocentric';

  // The radius the current shell slug sits at (any field that carries it).
  function shellRadiusM() {
    for (const spec of Object.values(manifest.fields)) {
      const r = spec.shells[state.shell];
      if (r !== undefined) return r;
    }
    return R_SURFACE_M;
  }

  // ---- panel DOM ----------------------------------------------------------
  const panel = document.createElement('div');
  panel.id = 'series-panel';
  panel.hidden = true;

  const controls = document.createElement('div');
  controls.id = 'ts-controls';

  const datumWrap = document.createElement('span');
  datumWrap.id = 'ts-datum';
  for (const d of DATUMS) {
    const label = document.createElement('label');
    label.className = 'comp-radio';
    label.title = d.title;
    const rb = document.createElement('input');
    rb.type = 'radio';
    rb.name = 'ts-datum';
    rb.value = d.id;
    rb.id = `ts-datum-${d.id}`;
    rb.checked = datum === d.id;
    rb.addEventListener('change', () => {
      datum = d.id;
      rhName.textContent = d.rh;
      syncInputs();                // re-express the pin in the new datum
    });
    label.append(rb, document.createTextNode(d.label));
    datumWrap.appendChild(label);
  }

  function numInput(id, min, max, title) {
    const el = document.createElement('input');
    el.type = 'number';
    el.id = id;
    el.min = String(min);
    el.max = String(max);
    el.step = 'any';
    el.title = title;
    return el;
  }
  const latEl = numInput('ts-lat', -90, 90, 'latitude, degrees north');
  const lonEl = numInput('ts-lon', -180, 180, 'longitude, degrees east');
  const rhEl = numInput('ts-rh', -3000, 1000000,
                        'snaps to the nearest available shell');
  const rhName = document.createElement('span');
  rhName.id = 'ts-rh-name';
  rhName.textContent = 'r';

  const wrapField = (text, el) => {
    const label = document.createElement('label');
    label.className = 'ts-field';
    if (typeof text === 'string') text = document.createTextNode(text);
    label.append(text, el);
    return label;
  };

  const pinBtn = document.createElement('button');
  pinBtn.id = 'ts-pin';
  pinBtn.textContent = 'Pin';
  pinBtn.title = 'pin the typed coordinates';

  const clearBtn = document.createElement('button');
  clearBtn.id = 'ts-clear';
  clearBtn.textContent = '×';
  clearBtn.title = 'clear the pinned point';

  const convWrap = document.createElement('span');
  convWrap.id = 'ts-conv';
  for (const [id, conv] of Object.entries(CONVENTIONS)) {
    const label = document.createElement('label');
    label.className = 'comp-radio';
    label.title = conv.title;
    const rb = document.createElement('input');
    rb.type = 'radio';
    rb.name = 'ts-conv';
    rb.value = id;
    rb.id = `ts-conv-${id}`;
    rb.checked = state.tsConvention === id;
    rb.addEventListener('change', () => {
      state.tsConvention = id;
      if (assembly) makePlots();   // relabel + re-sign, no re-assembly
      state.dirty = true;          // permalink sync
    });
    label.append(rb, document.createTextNode(conv.label));
    convWrap.appendChild(label);
  }

  const statusEl = document.createElement('span');
  statusEl.id = 'ts-status';
  statusEl.hidden = true;

  const snapEl = document.createElement('span');
  snapEl.id = 'ts-snap';

  const rhWrap = wrapField(rhName, rhEl);
  rhWrap.append(document.createTextNode('km'));
  controls.append(datumWrap,
                  wrapField('lat', latEl), wrapField('lon', lonEl),
                  rhWrap, pinBtn, clearBtn, convWrap, statusEl, snapEl);
  panel.appendChild(controls);

  const hint = document.createElement('div');
  hint.id = 'ts-hint';
  hint.textContent = 'Click the globe or enter coordinates to pin a location.';
  panel.appendChild(hint);

  const charts = document.createElement('div');
  charts.id = 'ts-charts';
  charts.hidden = true;
  const chartDivs = [];
  const valueEls = [];   // per-chart crosshair value (the legend's old job)
  for (let i = 0; i < 3; i++) {
    const div = document.createElement('div');
    div.className = 'ts-chart';
    const val = document.createElement('div');
    val.className = 'ts-value';
    div.appendChild(val);
    charts.appendChild(div);
    chartDivs.push(div);
    valueEls.push(val);
  }
  // One time readout under the lowest panel (4th flex child, so it hides
  // with the charts): the crosshair instant while hovering, the transport
  // instant (gold, matching the time cursor) otherwise.
  const readout = document.createElement('div');
  readout.id = 'ts-time-readout';
  charts.appendChild(readout);
  panel.appendChild(charts);

  document.getElementById('viewport').appendChild(panel);   // below the globe, above #timebar

  function status(text, isError = false) {
    statusEl.textContent = text;
    statusEl.hidden = !text;
    statusEl.classList.toggle('error', isError);
  }

  // ---- view toggle ---------------------------------------------------------
  const wrap = document.createElement('span');
  wrap.id = 'view-toggle';
  for (const view of VIEWS) {
    const label = document.createElement('label');
    label.className = 'comp-radio';
    label.title = view.title;
    const rb = document.createElement('input');
    rb.type = 'radio';
    rb.name = 'view';
    rb.value = view.id;
    rb.id = `view-${view.id}`;
    rb.checked = state.view === view.id;
    rb.addEventListener('change', () => setView(view.id));
    label.append(rb, document.createTextNode(view.label));
    wrap.appendChild(label);
  }
  document.getElementById('controls-primary').appendChild(wrap);

  function setView(mode) {
    state.view = mode;
    document.body.dataset.view = mode;
    panel.hidden = mode === 'globe';
    // #globe just changed size (or collapsed to nothing) — the globe's own
    // resize handler only fires on *window* resize.
    globe.resize();
    state.dirty = true;              // re-render + permalink sync
  }

  // ---- pinned-point marker -------------------------------------------------
  // Child of globe.earth so the frame feature's pose carries it; depth test
  // off so relief displacement (≤ 0.15 R above the shell) can't swallow it.
  let marker = null;
  function updateMarker() {
    if (!state.point) {
      if (marker) marker.visible = false;
      return;
    }
    if (!marker) {
      marker = new THREE.Mesh(
        new THREE.SphereGeometry(0.012, 16, 12),
        new THREE.MeshBasicMaterial({ color: 0xd4af37, depthTest: false }));
      marker.name = 'ts-marker';
      marker.renderOrder = 3;        // over the translucent shell pass
      globe.earth.add(marker);
    }
    marker.visible = true;
    const lat = state.point.lat * DEG, lon = state.point.lon * DEG;
    const r = shellRadiusM() / R_SURFACE_M * 1.002;
    // inverse of the readout's lat = asin(y), lon = atan2(x, z)
    marker.position.set(Math.cos(lat) * Math.sin(lon) * r,
                        Math.sin(lat) * r,
                        Math.cos(lat) * Math.cos(lon) * r);
  }

  // ---- pin state -------------------------------------------------------------
  function syncInputs() {
    if (!state.point) return;
    const rM = shellRadiusM();
    if (datum === 'geodetic') {
      const g = geocentricToGeodetic(state.point.lat, rM);
      latEl.value = g.latDeg.toFixed(2);
      rhEl.value = String(Math.round(g.heightM / 1000));
    } else {
      latEl.value = state.point.lat.toFixed(2);
      rhEl.value = String(Math.round(rM / 1000));
    }
    lonEl.value = state.point.lon.toFixed(2);
  }

  function refreshEcho() {
    if (!state.point) {
      snapEl.textContent = '';
      return;
    }
    const rM = shellRadiusM();
    const h = geocentricToGeodetic(state.point.lat, rM).heightM;
    snapEl.textContent = `${fmtLatLon(state.point.lat, state.point.lon)}` +
      ` · ${shellLabel(state.shell, rM)}` +
      ` (r ${Math.round(rM / 1000)} km · h≈${Math.round(h / 1000)} km)`;
  }

  function pinPoint(lat, lon) {
    state.point = { lat, lon };
    syncInputs();
    refreshEcho();
    updateMarker();
    hint.hidden = true;
    state.dirty = true;              // permalink sync + marker render
  }

  clearBtn.addEventListener('click', () => {
    state.point = null;
    updateMarker();
    refreshEcho();
    destroyPlots();
    assembly = null;
    shownKey = null;
    charts.hidden = true;
    hint.hidden = false;
    status('');
    state.dirty = true;
  });

  // Typed coordinates: convert (geodetic) then snap the radius to the
  // slider's ladder and drive the same path the slider handler drives, so
  // shell state stays single-source.
  pinBtn.addEventListener('click', () => {
    let lat = Number(latEl.value);
    const lon = Number(lonEl.value);
    if (!Number.isFinite(lat) || !Number.isFinite(lon)) return;
    lat = Math.max(-90, Math.min(90, lat));
    const lonWrapped = ((lon % 360) + 540) % 360 - 180;

    let radiusM;
    const rh = Number(rhEl.value) * 1000;
    if (datum === 'geodetic') {
      const g = geodeticToGeocentric(lat, Number.isFinite(rh) ? rh : 0);
      lat = g.latDeg;
      radiusM = g.radiusM;
    } else {
      radiusM = Number.isFinite(rh) && rhEl.value !== '' ? rh : shellRadiusM();
    }

    const ladder = shellUnion(state, manifest, hooks);
    let [slug, snappedM] = ladder[0];   // ascending: ties go to the lower rung
    for (const [s, r] of ladder) {
      if (Math.abs(r - radiusM) < Math.abs(snappedM - radiusM)) {
        slug = s;
        snappedM = r;
      }
    }
    if (slug !== state.shell) {
      state.shell = slug;
      ui.refreshShellSlider();
      ui.refreshColorbar();
      hooks.setShell(snappedM / R_SURFACE_M);
      hooks.applyTextures();
    }
    pinPoint(lat, lonWrapped);
  });

  // ---- click-to-pin -----------------------------------------------------------
  // Same raycast as the hover readout (main.js): NDC -> undisplaced shell
  // geometry -> undo the frame pose so lat/lon stays geographic under ECI.
  const raycaster = new THREE.Raycaster();
  const canvas = globe.renderer.domElement;
  let downAt = null;
  canvas.addEventListener('pointerdown', (e) => {
    downAt = { x: e.clientX, y: e.clientY, t: performance.now() };
  });
  canvas.addEventListener('pointerup', (e) => {
    if (!downAt) return;
    const moved = Math.hypot(e.clientX - downAt.x, e.clientY - downAt.y);
    const held = performance.now() - downAt.t;
    downAt = null;
    if (moved > CLICK_PX || held > CLICK_MS) return;   // that was an orbit
    const rect = canvas.getBoundingClientRect();
    const ndc = new THREE.Vector2(
      ((e.clientX - rect.left) / rect.width) * 2 - 1,
      -((e.clientY - rect.top) / rect.height) * 2 + 1);
    raycaster.setFromCamera(ndc, globe.camera);
    const hit = raycaster.intersectObject(globe.shell, false)[0];
    if (!hit) return;
    const p = hit.point.clone()
      .applyQuaternion(globe.earth.quaternion.clone().invert()).normalize();
    pinPoint(
      THREE.MathUtils.radToDeg(Math.asin(Math.min(1, Math.max(-1, p.y)))),
      THREE.MathUtils.radToDeg(Math.atan2(p.x, p.z)));
  });

  // ---- time axis --------------------------------------------------------------
  // Same instants the sun/labels use: series epochs via parseUT, plain days
  // as 97 15-min steps from UT midnight.
  function epochTimesSec() {
    const rec = manifest.series?.[state.day];
    const n = timeline.nEpochs;
    const xs = new Array(n);
    if (rec) {
      for (let i = 0; i < n; i++) xs[i] = parseUT(rec.epochs[i]) / 1000;
    } else {
      const t0 = parseUT(`${state.day}T00:00:00`) / 1000;
      for (let i = 0; i < n; i++) xs[i] = t0 + i * 900;
    }
    return xs;
  }

  function currentTimeSec() {
    const rec = manifest.series?.[state.day];
    if (rec) return seriesUT(rec, state.pos).getTime() / 1000;
    return parseUT(`${state.day}T00:00:00`) / 1000 + state.pos * 900;
  }

  // ---- time / value readouts ---------------------------------------------------
  let hoverT = null;   // crosshair instant (epoch sec), null = not hovering
  function fmtInstant(sec) {
    const iso = new Date(sec * 1000).toISOString();
    return `${iso.slice(0, 10)} ${iso.slice(11, 16)} UT`;
  }
  function refreshReadout() {
    readout.textContent = fmtInstant(hoverT ?? currentTimeSec());
    readout.classList.toggle('hover', hoverT != null);
  }

  // ---- series assembly ----------------------------------------------------------
  // Everything that changes what a chart epoch sums: the study tab (field
  // gate), day/series, shell, enabled fields, and the pin itself.
  function seriesKey() {
    const on = Object.keys(state.enabled)
      .filter((f) => state.enabled[f]).join(',');
    return `${state.tab}|${state.day}|${state.shell}|${on}` +
      `|${state.point.lat.toFixed(3)},${state.point.lon.toFixed(3)}`;
  }

  let assembly = null;             // { xs, N, E, C, gaps, units }
  let shownKey = null;             // key of the data in the charts
  let pendingKey = null;           // key being debounced/assembled
  let assemblySeq = 0;
  let assemblyAbort = null;
  let debounceTimer = null;
  const resultCache = new Map();   // seriesKey -> assembly (LRU, CACHE_MAX)

  // Charts are exact, the globe may approximate (efficiency review, 2026-07):
  // a bilinear sample between nodes is an interpolation, not a model value.
  // Snap the sampling point to the nearest node of the coarsest charted grid
  // — every grid is linspace(-180..180 / -90..90), so coarse nodes (2°: even
  // degrees) are shared by the finer 1°/0.5° grids and one snapped point is
  // an exact stored evaluation for every summed field. At exact nodes the
  // bilinear kernel degenerates to the node value (int16-exact).
  function snapPoint(lat, lon, fields) {
    let coarsest = null;
    for (const [field] of fields) {
      const g = storageGrid(field, state.day);
      if (!coarsest || g[0] < coarsest[0]) coarsest = g;
    }
    if (!coarsest) return { lat, lon, moved: false };
    const dlon = 360 / (coarsest[0] - 1);
    const dlat = 180 / (coarsest[1] - 1);
    const slon = Math.max(-180, Math.min(180,
      Math.round((lon + 180) / dlon) * dlon - 180));
    const slat = Math.max(-90, Math.min(90,
      Math.round((lat + 90) / dlat) * dlat - 90));
    return { lat: slat, lon: slon,
             moved: slat !== lat || slon !== lon };
  }

  async function assemble(signal) {
    const n = timeline.nEpochs;
    const xs = epochTimesSec();
    const sums = [new Array(n).fill(0), new Array(n).fill(0),
                  new Array(n).fill(0)];
    const bad = new Array(n).fill(false);

    const fields = [];
    for (const [field, on] of Object.entries(state.enabled)) {
      if (!on) continue;
      const src = hooks.frameSource(field);
      if (src && src.shells.includes(state.shell)) fields.push([field, src]);
    }
    if (!fields.length) bad.fill(true);
    const { lat, lon, moved } = snapPoint(state.point.lat, state.point.lon,
                                          fields);

    const jobs = [];
    for (const [field, src] of fields) {
      if (!src.stepped) {
        // one tile covers every epoch (daily core, static crust,
        // single_step series members) — sample once, broadcast
        jobs.push(async () => {
          try {
            const nec = await samplePoint(field, state.shell, state.day, 0,
                                          lat, lon, { signal });
            for (let i = 0; i < n; i++) {
              for (let c = 0; c < 3; c++) sums[c][i] += nec[c];
            }
          } catch (err) {
            if (err.name === 'AbortError') throw err;
            bad.fill(true);          // no partial sums
          }
        });
      } else {
        for (let i = 0; i < n; i++) {
          const step = Math.min(i, src.n - 1);   // readout's clamp
          jobs.push(async () => {
            try {
              const nec = await samplePoint(field, state.shell, state.day,
                                            step, lat, lon, { signal });
              for (let c = 0; c < 3; c++) sums[c][i] += nec[c];
            } catch (err) {
              if (err.name === 'AbortError') throw err;
              bad[i] = true;
            }
          });
        }
      }
    }

    let next = 0;
    await Promise.all(Array.from(
      { length: Math.min(POOL, jobs.length) }, async () => {
        while (next < jobs.length && !signal.aborted) await jobs[next++]();
      }));
    if (signal.aborted) throw new DOMException('aborted', 'AbortError');

    const mask = (arr) => arr.map((v, i) => (bad[i] ? null : v));
    return { xs, N: mask(sums[0]), E: mask(sums[1]), C: mask(sums[2]),
             gaps: bad.filter(Boolean).length, units: hooks.displayUnits(),
             snap: { lat, lon, moved } };
  }

  function maybeAssemble() {
    if (panel.hidden || !state.point) return;
    const key = seriesKey();
    if (key === shownKey || key === pendingKey) return;
    const cached = resultCache.get(key);
    if (cached) {
      resultCache.delete(key);
      resultCache.set(key, cached);  // refresh LRU position
      show(cached, key);
      return;
    }
    pendingKey = key;
    clearTimeout(debounceTimer);
    debounceTimer = setTimeout(() => runAssembly(key), DEBOUNCE_MS);
  }

  async function runAssembly(key) {
    assemblyAbort?.abort();
    const ac = new AbortController();
    assemblyAbort = ac;
    const seq = ++assemblySeq;
    status('assembling…');
    try {
      const res = await assemble(ac.signal);
      if (seq !== assemblySeq) return;         // a newer run superseded this
      resultCache.set(key, res);
      while (resultCache.size > CACHE_MAX) {
        resultCache.delete(resultCache.keys().next().value);
      }
      pendingKey = null;
      show(res, key);
    } catch (err) {
      if (seq !== assemblySeq || err.name === 'AbortError') return;
      pendingKey = null;
      status(`series failed: ${err.message}`, true);
    }
  }

  function show(res, key) {
    shownKey = key;
    assembly = res;
    charts.hidden = false;
    hint.hidden = true;
    const snapNote = res.snap?.moved
      ? `sampling grid node ${res.snap.lat.toFixed(2)}°, ` +
        `${res.snap.lon.toFixed(2)}° — exact stored values`
      : '';
    if (res.gaps === res.xs.length) {
      status('no enabled field has data at this shell', true);
    } else if (res.gaps) {
      status(`${res.gaps} of ${res.xs.length} epochs missing — gaps`);
    } else if (res.xs.length <= 1) {
      status('single-epoch timeline — one sample');
    } else {
      status(snapNote);
    }
    makePlots();
    refreshReadout();
  }

  // ---- charts ----------------------------------------------------------------
  let plots = [];
  let syncingX = false;

  function destroyPlots() {
    for (const u of plots) u.destroy();
    plots = [];
  }

  // Crosshairs sync via uPlot's cursor.sync. Drag-select zoom is disabled
  // (cursor.drag) — the one remaining span seam is programmatic setScale
  // (the browser tests' adaptive-label checks); this hook keeps the three
  // panels on a single x range whichever panel it lands on.
  function syncXScale(u, key) {
    if (key !== 'x' || syncingX) return;
    syncingX = true;
    const { min, max } = u.scales.x;
    for (const peer of plots) {
      if (peer !== u) peer.setScale('x', { min, max });
    }
    syncingX = false;
  }

  // Span-adaptive UT tick labels for the shared x axis (v2.13 addendum):
  // the year is always somewhere on the axis. Single-line on purpose — a
  // second label line costs ~18px and combined mode has no vertical room —
  // so the axis keeps size 30 and the flex calibration holds. Custom
  // values() only; the default splits generator already lands on calendar
  // boundaries (UTC via tzDate).
  const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                  'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  const pad2 = (n) => String(n).padStart(2, '0');
  function xTickValues(u, splits, axisIdx, foundSpace, foundIncr) {
    const YEAR = 365 * 86400, MONTH = 28 * 86400, DAY = 86400;
    let prevY = null;   // year carried on rollover, not only at January —
                        // quarter-spaced ticks (Sep Dec Mar Jun) never land
                        // on January, yet must not roll the year silently
    return splits.map((ts, i) => {
      const d = new Date(ts * 1000);   // UTC getters == tzDate Etc/UTC
      const y = d.getUTCFullYear(), mo = d.getUTCMonth(), dd = d.getUTCDate();
      const rolled = i === 0 || y !== prevY;
      prevY = y;
      if (foundIncr >= YEAR) return String(y);
      if (foundIncr >= MONTH)
        return rolled ? `${MONTHS[mo]} ${y}` : MONTHS[mo];
      if (foundIncr >= DAY)
        return rolled ? `${dd} ${MONTHS[mo]} ${y}` : `${dd} ${MONTHS[mo]}`;
      if (i === 0) return `${y}-${pad2(mo + 1)}-${pad2(dd)}`;
      return `${pad2(d.getUTCHours())}:${pad2(d.getUTCMinutes())}`;
    });
  }

  // Gold vertical line at the transport's current instant, redrawn (throttled)
  // as playback advances.
  function timeCursorPlugin() {
    return { hooks: { draw: (u) => {
      const t = currentTimeSec();
      const { min, max } = u.scales.x;
      if (t < min || t > max) return;
      const x = u.valToPos(t, 'x', true);
      u.ctx.save();
      u.ctx.strokeStyle = '#d4af37';
      u.ctx.lineWidth = 1;
      u.ctx.beginPath();
      u.ctx.moveTo(x, u.bbox.top);
      u.ctx.lineTo(x, u.bbox.top + u.bbox.height);
      u.ctx.stroke();
      u.ctx.restore();
    } } };
  }

  function plotSize(div) {
    return { width: Math.max(0, div.clientWidth),
             height: Math.max(0, div.clientHeight) };
  }

  function makePlots() {
    destroyPlots();
    if (!assembly) return;
    const conv = CONVENTIONS[state.tsConvention];
    const rows = conv.rows(assembly);
    const nPts = assembly.xs.length;
    // Rotated y-axis label: the component name with its parenthetical
    // stripped (a 96px-min panel can't fit "B_θ (southward) (nT/yr)"),
    // phrased as a rate when the SV display is active — the units are the
    // authority on which quantity is plotted.
    const svMode = assembly.units.endsWith('/yr');
    const axisLabel = (name) => {
      const base = name.replace(/\s*\(.*\)$/, '');
      const qty = !svMode ? base
        : base.startsWith('B_') ? `d${base}/dt` : `${base} dB/dt`;
      return `${qty} (${assembly.units})`;
    };
    const fmtVal = (v) => v.toLocaleString('en-US',
      { maximumFractionDigits: 1 });       // the hover readout's format
    hoverT = null;                         // stale crosshair dies with plots
    valueEls.forEach((el) => { el.textContent = ''; });
    plots = chartDivs.map((div, ci) => {
      const u = new uPlot({
        ...plotSize(div),
        // all app times are UT — uPlot would otherwise label in local time
        tzDate: (ts) => uPlot.tzDate(new Date(ts * 1e3), 'Etc/UTC'),
        cursor: { sync: { key: 'ts' }, drag: { x: false, y: false } },
        // uPlot auto-pads the right edge by 25 (half its default y-axis
        // size) only on panels whose bottom axis has nonzero size — the
        // size-0 axes below don't count, so without pinning it the bottom
        // panel sits 25 px narrower than the ones above (null = keep the
        // auto value for the other three sides).
        padding: [null, 25, null, null],
        scales: { x: { time: true } },
        legend: { show: false },   // the y-axis label carries the name now
        series: [
          {},
          // invisible with the legend off, but kept: the browser tests'
          // convention/units seam
          { label: `${conv.names[ci]} (${assembly.units})`,
            stroke: '#8fa3cc', width: 1,
            points: { show: nPts <= 60 } },   // sparse series need dots
        ],
        axes: [
          // The x axis is drawn on every panel: uPlot auto-pads only the
          // sides that carry an axis, so a lone labeled bottom panel gets
          // ~25 px of right padding the others don't and sits shifted
          // against them. Same axis everywhere ⇒ same padding, and (with
          // the synced range and equal space) the same splits, so the
          // vertical gridlines align across the stack. Labels and tick
          // marks render on the bottom panel only at size 30 (size 0
          // above — combined mode has no vertical room to repeat them);
          // space 64 fits the widest single-line label ("1 Mar 2020").
          { size: ci === 2 ? 30 : 0, stroke: '#6b7693',
            values: ci === 2 ? xTickValues
                             : (u, splits) => splits.map(() => ''),
            space: 64, grid: { stroke: '#1c2438' },
            ticks: { stroke: '#1c2438', show: ci === 2 } },
          { stroke: '#6b7693', grid: { stroke: '#1c2438' },
            ticks: { stroke: '#1c2438' }, size: 68,
            // canvas-drawn in the axis stroke colour; non-bold to match
            // the tick font (uPlot's labelFont default is bold)
            label: axisLabel(conv.names[ci]),
            labelSize: 16, labelGap: 0,
            labelFont: '12px system-ui, sans-serif' },
        ],
        hooks: {
          setScale: [syncXScale],
          // cursor.sync delivers the same idx to all three panels: each
          // updates its own value corner; the shared time readout follows
          setCursor: [(u) => {
            const idx = u.cursor.idx;
            const v = idx == null ? null : rows[ci][idx];
            valueEls[ci].textContent =
              v == null ? '' : `${fmtVal(v)} ${assembly.units}`;
            hoverT = idx == null ? null : assembly.xs[idx];
            refreshReadout();
          }],
        },
        plugins: [timeCursorPlugin()],
      }, [assembly.xs, rows[ci]], div);

      // Click seeks the transport to the nearest epoch; a crosshair sweep
      // must not. Same travel gate as the globe.
      let chartDown = null;
      u.over.addEventListener('pointerdown', (e) => {
        chartDown = { x: e.clientX, y: e.clientY };
      });
      u.over.addEventListener('click', (e) => {
        if (!chartDown) return;
        const moved = Math.hypot(e.clientX - chartDown.x,
                                 e.clientY - chartDown.y);
        chartDown = null;
        if (moved > CLICK_PX || u.cursor.idx == null) return;
        state.pos = Math.max(0, Math.min(u.cursor.idx, timeline.nEpochs - 1));
        ui.onTimeAdvance();
        hooks.applyTextures();
      });
      return u;
    });
    resizePlots();
  }

  function resizePlots() {
    for (const u of plots) {
      const size = plotSize(u.root.parentElement);
      if (size.width > 0 && size.height > 40) u.setSize(size);
    }
  }
  new ResizeObserver(resizePlots).observe(charts);

  // ---- change plumbing ---------------------------------------------------------
  // One listener at the render chokepoint covers every trigger: pin moves,
  // day picks, study/family switches (new timeline), shell moves, field
  // toggles, playback (time cursor), view flips.
  let lastShell = state.shell;
  let lastCursorT = null;
  let cursorTimer = null;
  onChange(() => {
    if (state.shell !== lastShell) {
      lastShell = state.shell;
      if (state.point) {
        syncInputs();
        refreshEcho();
        updateMarker();
      }
    }
    maybeAssemble();
    if (!plots.length || panel.hidden) return;
    const t = currentTimeSec();
    if (t === lastCursorT || cursorTimer) return;
    cursorTimer = setTimeout(() => {   // trailing: the final pos always draws
      cursorTimer = null;
      lastCursorT = currentTimeSec();
      for (const u of plots) u.redraw();
      refreshReadout();                // transport fallback tracks playback
    }, CURSOR_MS);
  });

  // window.geomagModelExplorer is assigned after the attach stage — expose
  // our own seam for the browser tests.
  window.__timeseries = {
    plots: () => plots,
    last: () => assembly,
    key: () => shownKey,
  };

  setView(state.view);
  updateMarker();
  if (state.point) {                 // restored from the permalink
    syncInputs();
    refreshEcho();
    hint.hidden = true;
  }
}
