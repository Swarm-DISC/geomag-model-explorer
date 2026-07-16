// Bootstrap: manifest -> textures -> globe -> UI; render-on-demand rAF loop.
import * as THREE from 'three';
import { loadManifest, getTexture, getTextureSync, setDecodeHook, prefetch,
         cacheSize, lookup, frameSource, storageQrange } from './dataset.js';
import { createGlobe } from './globe.js';
import { FIELD_INDEX } from './shaders.js';
import { initUI, fmtTime, COMPONENT_LABELS, R_SURFACE_M } from './ui.js';

const state = {
  // v2.12 defaults: the full four-field sum, lit and displaced — the landing
  // view shows everything; permalinks can still express any off state.
  enabled: { core: true, crust: true, iono: true, magneto: true },
  component: 'Up',          // 'N' | 'E' | 'Up' | 'F'
  shell: 'h500',            // shell slug — 500 km altitude on initial load
  vmaxLock: null,           // nT: colorbar range frozen here; null = auto
  day: null,                // YYYY-MM-DD (manifest default)
  tab: null,                // active study id (feature `studies`; permalink
                            // key — lets kind-less tabs round-trip, v2.11)
  pos: 32,                  // float epoch index into the active timeline —
                            // boot at 08:00 UT: subsolar ~60°E puts ~3/4 of
                            // the landing disc in daylight, terminator on the
                            // Atlantic limb, and the Sq blob on screen
  sun: true,                // day/night sunlight shading (feature `sun`)
  relief: true,             // field-displaced surface (feature `relief`)
  frame: 'ecef',            // reference frame id (feature `frame`)
  playing: false,
  speed: 4,
  dirty: true,              // render-on-demand flag
};

// The time axis the transport (slider, playback) runs over. v1 has exactly
// one: the picked day's 97 15-min steps, so pos 0..96 maps to 00:00..24:00.
// Mutated in place when a timeline with different epochs takes over
// (IDEAS §9: series), so ui.js and the rAF loop always see the active one.
const timeline = {
  nEpochs: 97,
  subdiv: 15,                          // slider ticks per epoch (1 tick = 1 min)
  label: (pos) => fmtTime(pos * 15),
  sweepMs: 120000,                     // wall clock per full sweep at speed 1
};

function loadTexture(url) {
  return new Promise((resolve, reject) => {
    new THREE.TextureLoader().load(url, resolve, undefined, reject);
  });
}

const COMPONENT_MASK = {
  N: [1, 0, 0], E: [0, 1, 0], Up: [0, 0, -1], F: [0, 0, 0],
};

// Relief exaggeration: radial displacement in object-space radii at colorbar
// vmax (PLAN v2.6 — fixed, normalized by the same uVmax as the colors).
const RELIEF_RADII = 0.15;

// Deploy-time feature flags (PLAN v2.1 governance): modules load via dynamic
// import() only when ./api/features enables them; anything missing or broken
// degrades to v1 behavior. Contract: restore(ctx) runs before the UI exists
// (may mutate state + camera); attach(ctx) runs once the app is fully booted.
const FEATURE_MODULES = {
  permalink: () => import('./features/permalink.js'),
  studies: () => import('./features/studies.js'),
  // anchors are static index.html slots since v2.14 (no ordering constraint
  // on modelinfo anymore; entry order kept for stable attach telemetry)
  modelinfo: () => import('./features/model-info.js'),
  // before sun: frame's change listener poses the earth group that sun's
  // listener reads for the world-space light direction (listeners run in
  // insertion order)
  frame: () => import('./features/frame.js'),
  sun: () => import('./features/sun.js'),
  relief: () => import('./features/relief.js'),
};

async function loadFeatures() {
  const flags = await fetch('./api/features')
    .then((r) => (r.ok ? r.json() : {}))
    .catch(() => ({}));
  const mods = [];
  for (const [name, load] of Object.entries(FEATURE_MODULES)) {
    if (!flags[name]) continue;
    try {
      mods.push([name, await load()]);
    } catch (err) {
      console.warn(`feature ${name} failed to load:`, err);
    }
  }
  return { flags, mods };
}

async function main() {
  const featuresPromise = loadFeatures();
  const manifest = await loadManifest();
  state.day = manifest.default_day;
  // Fields newer than the seed list (core-sv, v2.9) start disabled — before
  // feature restore, so a permalink can enable them.
  for (const field of Object.keys(manifest.fields)) {
    if (!(field in state.enabled)) state.enabled[field] = false;
  }

  const [lut, coast] = await Promise.all([
    loadTexture('./textures/colormap_nio.png'),
    loadTexture('./textures/coastlines.png'),
  ]);
  lut.colorSpace = THREE.SRGBColorSpace;
  coast.colorSpace = THREE.SRGBColorSpace;

  const globe = createGlobe(document.getElementById('globe'), lut, coast);
  // Upload each texture to the GPU as it decodes, off the playback hot path,
  // so the first frame that binds it doesn't stall.
  setDecodeHook((tex) => globe.renderer.initTexture(tex));
  globe.controls.addEventListener('change', () => { state.dirty = true; });
  window.addEventListener('resize', () => { state.dirty = true; });
  // Reset chip (v2.14): back to the full boot defaults — every selection,
  // overlay and the camera. The boot path IS the definition of the default
  // state, so wipe the permalink hash and reload rather than duplicating
  // per-feature reset logic that would drift.
  document.getElementById('view-reset').addEventListener('click', () => {
    history.replaceState(null, '', window.location.pathname
                                   + window.location.search);
    window.location.reload();
  });

  // Feature restore stage: before the UI is built, so controls initialize
  // from the (possibly feature-mutated) state.
  const { flags: features, mods: featureMods } = await featuresPromise;
  for (const [name, mod] of featureMods) {
    try {
      mod.restore?.({ state, manifest, globe, timeline, features });
    } catch (err) {
      console.warn(`feature ${name} restore failed:`, err);
    }
  }
  // initUI never moves the shell mesh for the *initial* shell — do it here
  // in case a feature restored a non-surface shell.
  const shellRadiusM = Object.values(manifest.fields)
    .map((spec) => spec.shells[state.shell])
    .find((r) => r !== undefined);
  if (shellRadiusM !== undefined) globe.setShell(shellRadiusM / R_SURFACE_M);

  const u = globe.fieldMaterial.uniforms;
  for (const [field, spec] of Object.entries(manifest.fields)) {
    const i = FIELD_INDEX[field];
    if (i === undefined) continue;   // manifest newer than this build
    u.uScale.value[i] = spec.qrange_nT;
    u.uGrid.value[i].set(spec.grid[0], spec.grid[1],
                         1 / spec.grid[0], 1 / spec.grid[1]);
  }

  // Display range per field at the current shell: the day's p99 of
  // |components| (computed at export; ≈ the prior-art defaults at the
  // surface, and the only usable range at the CMB where the raw max
  // saturates 37×). Falls back to the static default.
  function fieldVmax(field) {
    const spec = manifest.fields[field];
    // series membership outranks the static shortcut (the same rule as
    // fieldDay/frameSource): a series' crust — CHAOS-Static, LCS-1, MF7 —
    // must use its own stats, never the MLI static ones (v2.11)
    const rec = manifest.series?.[state.day];
    const stats = rec?.fields.includes(field)
      ? rec.stats?.[field]?.[state.shell]
      : spec.cadence === 'static'
        ? spec.stats?.[state.shell]
        : manifest.days[state.day]?.stats?.[field]?.[state.shell];
    return stats?.p99 ?? spec.vmax_nT;
  }

  // PLAN §9.5: colorbar range = sum of the enabled-and-present fields' —
  // unless locked, which pins the colour mapping so magnitude changes
  // across shells/days stay visible.
  function displayVmax() {
    if (state.vmaxLock != null) return state.vmaxLock;
    let v = 0;
    for (const [field, on] of Object.entries(state.enabled)) {
      const src = frameSource(state, field);
      if (on && src && src.shells.includes(state.shell)) v += fieldVmax(field);
    }
    return v || 1;
  }

  // Units of what is on screen (v2.9): the enabled-and-present fields all
  // share one unit — the tab gating guarantees nT/yr never mixes with nT.
  function displayUnits() {
    for (const [field, on] of Object.entries(state.enabled)) {
      if (!on) continue;
      const src = frameSource(state, field);
      if (src && src.shells.includes(state.shell)) {
        return manifest.fields[field].units ?? 'nT';
      }
    }
    return 'nT';
  }

  function applyComponent() {
    const mask = COMPONENT_MASK[state.component];
    u.uMask.value.set(...mask);
    u.uUseMag.value = state.component === 'F' ? 1 : 0;
  }

  // The floor timestep whose texture pair (uTexA/uTexB) is currently bound;
  // uMix may only track the clock while the bound pair matches it.
  let boundStep = -1;

  // Set the floor/ceil timestep textures for every enabled field at the
  // current shell; disables fields without data there.
  async function applyTextures() {
    const step = state.pos;
    const loads = [];
    for (const field of Object.keys(manifest.fields)) {
      const i = FIELD_INDEX[field];
      if (i === undefined) continue;
      const src = frameSource(state, field);
      const on = state.enabled[field] && src &&
        src.shells.includes(state.shell);
      u.uEnable.value[i] = on ? 1 : 0;
      // the active series may store this field at a different range than
      // the field default (v2.9) — descale must follow the tiles
      u.uScale.value[i] = storageQrange(field, state.day);
      if (!on) continue;
      const a = src.stepped ? Math.min(Math.floor(step), src.n - 2) : 0;
      const b = src.stepped ? a + 1 : 0;
      loads.push(Promise.all([
        getTexture(field, state.shell, state.day, a),
        getTexture(field, state.shell, state.day, b),
      ]).then(([ta, tb]) => {
        u[`uTexA${i}`].value = ta.tex;
        u[`uTexB${i}`].value = tb.tex;
      }));
    }
    u.uVmax.value = displayVmax();
    applyComponent();
    await Promise.all(loads);
    const stepFloor = Math.min(Math.floor(step), timeline.nEpochs - 2);
    boundStep = stepFloor;
    u.uMix.value = Math.max(0, Math.min(1, step - stepFloor));
    state.dirty = true;
  }

  // Per-frame playback advance, fully synchronous: swap to the new floor/ceil
  // pair only once every active 15-min field has both tiles decoded (prefetch
  // keeps them ahead). Until then hold the bound pair at its edge — never
  // render a fresh uMix against stale textures (a visible backwards twitch
  // at every step boundary).
  function advancePlayback() {
    const step = state.pos;
    const a = Math.min(Math.floor(step), timeline.nEpochs - 2);
    if (a !== boundStep) {
      const binds = [];
      let ready = true;
      for (const field of Object.keys(manifest.fields)) {
        if (!frameSource(state, field)?.stepped) continue;
        const i = FIELD_INDEX[field];
        if (i === undefined || !u.uEnable.value[i]) continue;
        const ea = getTextureSync(field, state.shell, state.day, a);
        const eb = getTextureSync(field, state.shell, state.day, a + 1);
        if (!ea || !eb) { ready = false; break; }
        binds.push([i, ea.tex, eb.tex]);
      }
      if (ready) {
        for (const [i, ta, tb] of binds) {
          u[`uTexA${i}`].value = ta;
          u[`uTexB${i}`].value = tb;
        }
        boundStep = a;
      }
    }
    if (boundStep === a) {
      u.uMix.value = step - a;
    } else if (boundStep >= 0) {
      // tiles still decoding: freeze at the nearest edge of the bound pair
      u.uMix.value = a > boundStep ? 1 : 0;
    }
    state.dirty = true;
  }

  async function refreshManifest() {
    Object.assign(manifest, await loadManifest());
  }

  // Async day picking (PLAN §9.2): an uncached day starts a background
  // fetch job; the user keeps exploring the current day while the chip
  // shows progress polled from ./api/days.
  let pollTimer = null;
  function pollJob(day) {
    if (pollTimer) clearInterval(pollTimer);
    pollTimer = setInterval(async () => {
      try {
        const d = await (await fetch('./api/days')).json();
        if (d.days.includes(day)) {
          clearInterval(pollTimer);
          pollTimer = null;
          await refreshManifest();
          ui.hideFetchChip();
          ui.setDay(day);
        } else if (d.job?.date === day && d.job.state === 'error') {
          clearInterval(pollTimer);
          pollTimer = null;
          ui.showFetchChip(`${day}: fetch failed — ${d.job.error}`, true);
        } else if (d.job?.date === day) {
          const pct = d.job.total
            ? ` ${Math.round(100 * d.job.done / d.job.total)}%` : '';
          ui.showFetchChip(`fetching ${day} …${pct}`);
        } else if (d.queue.includes(day)) {
          ui.showFetchChip(`queued ${day}`);
        }
      } catch { /* transient poll failure: keep trying */ }
    }, 2000);
  }

  async function pickDay(day) {
    if (day in manifest.days) { ui.setDay(day); return; }
    // The day-fetch POST is gated by the foundry token: cached in localStorage (never embedded
    // in the page) and sent as the X-Foundry-Token header only when already cached — never
    // prompted proactively. A 401 clears the cache, prompts once, and retries once.
    const post = (token) => fetch(`./api/days/${encodeURIComponent(day)}`,
                                  { method: 'POST',
                                    headers: token ? { 'X-Foundry-Token': token } : {} });
    let resp = await post(localStorage.getItem('foundry_token') || '');
    if (resp.status === 401) {
      localStorage.removeItem('foundry_token');
      const token = (window.prompt(
        'Foundry API token (stored locally for gated day fetches):') || '').trim();
      if (token) {
        localStorage.setItem('foundry_token', token);
        resp = await post(token);
      }
    }
    const body = await resp.json().catch(() => ({}));
    ui.setDay(state.day);              // stay on the current day meanwhile
    if (resp.status === 401) {
      localStorage.removeItem('foundry_token');
      ui.showFetchChip(`${day}: token rejected — re-enter it`, true);
      return;
    }
    if (!resp.ok) {
      ui.showFetchChip(`${day}: ${body.error ?? resp.status}`, true);
      return;
    }
    if (body.status === 'cached') {    // raced an in-flight export
      await refreshManifest();
      ui.setDay(day);
      return;
    }
    ui.showFetchChip(`queued ${day}`);
    pollJob(day);
  }

  const hooks = {
    applyTextures,
    applyComponent: () => { applyComponent(); state.dirty = true; },
    setShell: (radiusRe) => { globe.setShell(radiusRe); state.dirty = true; },
    setRelief: (on) => {
      state.relief = on;
      globe.setReliefMesh(on);
      u.uRelief.value = on ? RELIEF_RADII : 0;
      state.dirty = true;
    },
    displayVmax,
    displayUnits,
    pickDay,
    frameSource: (field) => frameSource(state, field),
  };
  const ui = initUI(state, manifest, hooks, timeline);

  await applyTextures();

  // Feature attach stage: the app is fully booted; features may register
  // for change notifications (fired from the render loop after each
  // dirty-triggered frame — the single chokepoint all state changes hit).
  const changeListeners = [];
  for (const [name, mod] of featureMods) {
    try {
      mod.attach?.({ state, manifest, globe, ui, hooks, timeline, features,
                     onChange: (fn) => changeListeners.push(fn) });
    } catch (err) {
      console.warn(`feature ${name} attach failed:`, err);
    }
  }

  // Hover readout: raycast -> lat/lon -> CPU lookup of the cached int16
  // tiles (full quantization precision, unlike the half-float GPU path).
  const readoutEl = document.getElementById('readout');
  const raycaster = new THREE.Raycaster();
  let hoverSeq = 0;
  async function updateReadout(event) {
    const rect = globe.renderer.domElement.getBoundingClientRect();
    const ndc = new THREE.Vector2(
      ((event.clientX - rect.left) / rect.width) * 2 - 1,
      -((event.clientY - rect.top) / rect.height) * 2 + 1);
    raycaster.setFromCamera(ndc, globe.camera);
    const hit = raycaster.intersectObject(globe.shell, false)[0];
    const seq = ++hoverSeq;
    if (!hit) { readoutEl.hidden = true; return; }
    // World hit -> Earth-fixed lat/lon: undo the reference-frame pose
    // (identity in ECEF) so the readout stays geographic under rotation.
    const p = hit.point.clone()
      .applyQuaternion(globe.earth.quaternion.clone().invert()).normalize();
    const lat = THREE.MathUtils.radToDeg(Math.asin(
      Math.min(1, Math.max(-1, p.y))));
    const lon = THREE.MathUtils.radToDeg(Math.atan2(p.x, p.z));
    const stepNear = Math.round(state.pos);
    const sum = [0, 0, 0];
    let any = false;
    for (const [field, on] of Object.entries(state.enabled)) {
      const src = frameSource(state, field);
      if (!on || !src || !src.shells.includes(state.shell)) continue;
      const s = src.stepped ? Math.min(stepNear, src.n - 1) : 0;
      try {
        const nec = await lookup(field, state.shell, state.day, s, lat, lon);
        for (let c = 0; c < 3; c++) sum[c] += nec[c];
        any = true;
      } catch { /* tile not cached yet — skip this field */ }
    }
    if (seq !== hoverSeq) return;      // a newer hover superseded this one
    if (!any) { readoutEl.hidden = true; return; }
    const value = {
      N: sum[0], E: sum[1], Up: -sum[2],
      F: Math.hypot(...sum),
    }[state.component];
    const fmt = (v, digits = 1) => v.toLocaleString('en-US',
      { maximumFractionDigits: digits });
    readoutEl.textContent =
      `${fmt(Math.abs(lat))}°${lat >= 0 ? 'N' : 'S'}, ` +
      `${fmt(Math.abs(lon))}°${lon >= 0 ? 'E' : 'W'} — ` +
      `${COMPONENT_LABELS[state.component]} ${fmt(value)} ${displayUnits()}`;
    readoutEl.hidden = false;
  }
  globe.renderer.domElement.addEventListener('pointermove', (e) => {
    updateReadout(e).catch(() => {});
  });
  globe.renderer.domElement.addEventListener('pointerleave', () => {
    readoutEl.hidden = true;
  });

  let last = performance.now();
  function frame(now) {
    requestAnimationFrame(frame);
    const dtMs = now - last;
    last = now;
    if (state.playing) {
      // speed 1 sweeps the whole timeline in ~2 minutes of wall clock;
      // a single-epoch timeline (static series, v2.11) has nothing to
      // sweep — advancing would divide by a zero span (NaN pos)
      const span = timeline.nEpochs - 1;
      if (span > 0) {
        state.pos = (state.pos + dtMs * (span / timeline.sweepMs) * state.speed) % span;
        ui.onTimeAdvance();
        advancePlayback();
        prefetch(state);
      }
    }
    if (state.dirty) {
      state.dirty = false;
      globe.render();
      for (const fn of changeListeners) fn();
    }
  }
  requestAnimationFrame(frame);

  // Debug/test handle (Playwright).
  window.geomagModelExplorer = {
    state, manifest, globe, features, timeline,
    renderer: globe.renderer,
    cacheSize,
    // what the shader is actually showing, in timestep units (0..96)
    timePos: () => boundStep + u.uMix.value,
    renderOnce: () => globe.render(),
    readPixel: (x, y) => {
      const c = document.createElement('canvas');
      c.width = 1; c.height = 1;
      const ctx = c.getContext('2d');
      ctx.drawImage(globe.renderer.domElement, x, y, 1, 1, 0, 0, 1, 1);
      return Array.from(ctx.getImageData(0, 0, 1, 1).data);
    },
  };
}

main().catch((err) => {
  console.error(err);
  const el = document.getElementById('error');
  if (el) { el.textContent = String(err); el.hidden = false; }
});
