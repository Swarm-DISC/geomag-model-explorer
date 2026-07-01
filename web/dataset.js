// Tile fetch + decode -> RGBA16F textures, with an LRU cache and prefetch.
// All URLs are relative so the app works behind /foundry/geomag-model-explorer/.
import * as THREE from 'three';

const BASE = './data/';
const MAX_ENTRIES = 64;   // ≈ 33 MB GPU at the largest grid

let manifest = null;
const cache = new Map();    // key -> Promise<{tex, i16}>; Map order = LRU
const resolved = new Map(); // key -> {tex, i16} once decoded (sync access)
let decodeHook = null;      // called with each new texture (GPU pre-upload)

export function setDecodeHook(fn) { decodeHook = fn; }

export async function loadManifest() {
  const resp = await fetch(BASE + 'manifest.json');
  if (!resp.ok) throw new Error(`manifest.json: HTTP ${resp.status}`);
  manifest = await resp.json();
  return manifest;
}

export function getManifest() { return manifest; }

export function cacheSize() { return cache.size; }

// The day directory a field's tiles live in ("static" for crust). state.day
// may also hold a series id (IDEAS §9.1) — series ids share the day path
// slot and pass through unchanged. A series the field is a *member* of wins
// over the static shortcut: the CHAOS day series carries its own crust
// (CHAOS-Static) tiles, which must never resolve to the MLI static/ dir.
export function fieldDay(field, day) {
  if (manifest.series?.[day]?.fields.includes(field)) return day;
  return manifest.fields[field].cadence === 'static' ? 'static' : day;
}

export function tileURL(field, shell, day, step) {
  // pad by the *resolved* directory: a static field on a series day still
  // reads its 2-digit static tile
  const dir = fieldDay(field, day);
  const nn = String(step).padStart(manifest.series?.[dir] ? 3 : 2, '0');
  return `${BASE}${field}/${shell}/${dir}/t${nn}.i16`;
}

// The storage range a field's tiles at this day/series were quantized with:
// a series may override the field default (v2.9 — CHAOS-Core at the CMB).
// Every descale site (GPU uScale, CPU hover) must go through this.
export function storageQrange(field, day) {
  return manifest.series?.[day]?.qrange_nT?.[field]
    ?? manifest.fields[field].qrange_nT;
}

// The tile sequence a field plays at the current state.day, or null when the
// field has no data there: {stepped, n: epoch count, shells: [slugs]}. This
// is the one availability rule shared by rendering, prefetch, hover and the
// controls — a real day plays the v1 15-min steps, an active series plays
// its epoch list, static crust is a single timeless tile.
export function frameSource(state, field) {
  const spec = manifest.fields[field];
  if (!spec) return null;            // manifest predates this field
  // Series membership outranks the static shortcut (same rule as fieldDay);
  // single_step members (v2.9) carry one timeless tile, like static crust.
  const series = manifest.series?.[state.day];
  if (series?.fields.includes(field)) {
    if (series.single_step?.includes(field)) {
      return { stepped: false, n: 1, shells: series.shells[field] };
    }
    return { stepped: true, n: series.epochs.length,
             shells: series.shells[field] };
  }
  if (spec.cadence === 'static') {
    return manifest.static_done
      ? { stepped: false, n: 1, shells: Object.keys(spec.shells) } : null;
  }
  if (series) return null;           // non-member on an active series
  if (!(state.day in manifest.days)) return null;
  // per-day stats are the proof a field was fetched for this day — without
  // this, series-only fields (core-sv) would claim every cached day
  if (!manifest.days[state.day].stats?.[field]) return null;
  return { stepped: spec.cadence === '15min', n: spec.n_steps,
           shells: Object.keys(spec.shells) };
}

function decode(i16, nlon, nlat) {
  const n = nlon * nlat;
  const data = new Uint16Array(n * 4);
  const one = THREE.DataUtils.toHalfFloat(1);
  for (let i = 0; i < n; i++) {
    data[i * 4] = THREE.DataUtils.toHalfFloat(i16[i * 3] / 32767);
    data[i * 4 + 1] = THREE.DataUtils.toHalfFloat(i16[i * 3 + 1] / 32767);
    data[i * 4 + 2] = THREE.DataUtils.toHalfFloat(i16[i * 3 + 2] / 32767);
    data[i * 4 + 3] = one;
  }
  const tex = new THREE.DataTexture(data, nlon, nlat, THREE.RGBAFormat,
                                    THREE.HalfFloatType);
  tex.magFilter = THREE.LinearFilter;
  tex.minFilter = THREE.LinearFilter;
  tex.generateMipmaps = false;
  tex.wrapS = THREE.ClampToEdgeWrapping;
  tex.wrapT = THREE.ClampToEdgeWrapping;
  tex.needsUpdate = true;
  return tex;
}

function evict() {
  while (cache.size > MAX_ENTRIES) {
    const [oldKey, oldVal] = cache.entries().next().value;
    cache.delete(oldKey);
    resolved.delete(oldKey);
    oldVal.then((entry) => entry.tex.dispose()).catch(() => {});
  }
}

// Resolves to {tex, i16}; the Int16Array is kept for CPU hover readout.
export function getTexture(field, shell, day, step) {
  const url = tileURL(field, shell, day, step);
  if (cache.has(url)) {            // refresh LRU position
    const entry = cache.get(url);
    cache.delete(url);
    cache.set(url, entry);
    return entry;
  }
  const [nlon, nlat] = manifest.fields[field].grid;
  const promise = fetch(url).then(async (resp) => {
    if (!resp.ok) throw new Error(`${url}: HTTP ${resp.status}`);
    const i16 = new Int16Array(await resp.arrayBuffer());
    if (i16.length !== nlon * nlat * 3) {
      throw new Error(`${url}: ${i16.length} values, expected ${nlon * nlat * 3}`);
    }
    const entry = { tex: decode(i16, nlon, nlat), i16 };
    if (decodeHook) decodeHook(entry.tex);
    if (cache.has(url)) resolved.set(url, entry);  // not evicted meanwhile
    return entry;
  });
  promise.catch(() => cache.delete(url));   // don't cache failures
  cache.set(url, promise);
  evict();
  return promise;
}

// Already-decoded entry or null — never blocks, for the playback hot path.
export function getTextureSync(field, shell, day, step) {
  const url = tileURL(field, shell, day, step);
  const entry = resolved.get(url);
  if (entry && cache.has(url)) {   // refresh LRU position
    const p = cache.get(url);
    cache.delete(url);
    cache.set(url, p);
  }
  return entry ?? null;
}

// Warm the cache for upcoming timesteps of enabled stepped fields.
export function prefetch(state, ahead = 6) {
  for (const [field, on] of Object.entries(state.enabled)) {
    if (!on) continue;
    const src = frameSource(state, field);
    if (!src?.stepped || !src.shells.includes(state.shell)) continue;
    const step = Math.floor(state.pos);
    for (let k = 0; k <= ahead; k++) {
      const s = (step + k) % src.n;
      getTexture(field, state.shell, state.day, s).catch(() => {});
    }
  }
}

// CPU bilinear readout in nT (full int16 precision), for the hover readout.
export async function lookup(field, shell, day, step, lat, lon) {
  const { i16 } = await getTexture(field, shell, day, step);
  const spec = manifest.fields[field];
  const [nlon, nlat] = spec.grid;
  const x = (lon + 180) / 360 * (nlon - 1);
  const y = (lat + 90) / 180 * (nlat - 1);
  const x0 = Math.min(Math.floor(x), nlon - 2);
  const y0 = Math.min(Math.floor(y), nlat - 2);
  const fx = x - x0, fy = y - y0;
  const qrange = storageQrange(field, day);
  const out = [0, 0, 0];
  for (let c = 0; c < 3; c++) {
    const at = (yy, xx) => i16[(yy * nlon + xx) * 3 + c] / 32767 * qrange;
    out[c] = (1 - fy) * ((1 - fx) * at(y0, x0) + fx * at(y0, x0 + 1))
           + fy * ((1 - fx) * at(y0 + 1, x0) + fx * at(y0 + 1, x0 + 1));
  }
  return out;   // [N, E, C] nT
}
