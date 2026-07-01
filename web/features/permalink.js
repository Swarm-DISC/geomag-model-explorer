// Permalink state (PLAN v2.1; IDEAS §5.4): day / time / fields / component /
// shell / camera in the URL hash. restore() runs before the UI is built, so
// the controls pick the restored state up for free; attach() keeps the hash
// in sync afterwards via debounced history.replaceState.
//
// Stability contract (IDEAS §8.3): unknown keys and invalid values are
// silently ignored — an old or hand-mangled link degrades to defaults, never
// errors. Manual hash edits *after* load are not applied (reload instead).
//
//   #day=2020-01-01&t=09:30&f=core,iono&c=N&s=cmb&cam=0.000,0.600,2.800
//   (+ &vmax=<nT> while the colorbar scale is locked)
//   (+ tab=…&series=<id>&e=<ISO epoch> instead of day=/t= while a study tab
//      plays a series — IDEAS §9.4; only honored when the flag its kind
//      needs is on: annual ⇒ studies, secular/diurnal ⇒ families (so a
//      families-off deploy never lands a yearly timeline on the Daily tab))
//   (+ &family=<id> while the model-series lens ≠ ci — v2.9; a series link
//      carries its own family, which wins over this key)
//   (+ &sun=1 while the sun overlay is on — restored by features/sun.js,
//      so the key only round-trips when that flag is on)
//   (+ &r=1 while relief mode is on — restored by features/relief.js, same
//      flag-gating)

const DEBOUNCE_MS = 300;

// The study tab a series kind lands on (mirrors features/studies.js), and
// the feature flag that kind needs before a link to it is honored.
const TAB_OF_KIND = { annual: 'seasons', secular: 'core', diurnal: 'daily' };
const KIND_FLAG = { annual: 'studies', secular: 'families',
                    diurnal: 'families' };

let pendingDay = null;       // hash day not yet cached at restore() time

function parseHash() {
  return new URLSearchParams(window.location.hash.slice(1));
}

function fmtTime(minutes) {
  const h = String(Math.floor(minutes / 60) % 24).padStart(2, '0');
  const m = String(Math.floor(minutes % 60)).padStart(2, '0');
  return `${h}:${m}`;
}

// Integer index of the epoch nearest to a UTC millisecond timestamp.
function nearestEpoch(epochs, ms) {
  let best = 0;
  for (let i = 1; i < epochs.length; i++) {
    if (Math.abs(Date.parse(epochs[i]) - ms) <
        Math.abs(Date.parse(epochs[best]) - ms)) best = i;
  }
  return best;
}

export function restore({ state, manifest, globe, features }) {
  const p = parseHash();

  const day = p.get('day');
  if (day && /^\d{4}-\d{2}-\d{2}$/.test(day) && day !== state.day) {
    if (day in manifest.days) state.day = day;
    else pendingDay = day;             // picked via the day-fetch job later
  }

  const t = p.get('t');
  if (t && /^\d{1,2}:\d{2}$/.test(t)) {
    const [h, m] = t.split(':').map(Number);
    const minutes = h * 60 + m;
    if (minutes >= 0 && minutes < 1440) state.pos = minutes / 15;
  }

  // A series link wins over day=/t=; unknown ids, unknown kinds or a
  // disabled flag leave the v1 keys in charge (stability contract).
  const sid = p.get('series');
  const sidRec = manifest.series?.[sid];
  const sidGate = sidRec && KIND_FLAG[sidRec.kind];
  if (features?.studies && sidRec && sidGate && features[sidGate]) {
    state.day = sid;
    pendingDay = null;
    const when = Date.parse(p.get('e'));
    state.pos = Number.isFinite(when)
      ? nearestEpoch(sidRec.epochs, when) : 0;
    // family is pinned from the series record by studies.restore (which
    // runs after this) — an explicit family= key is ignored here
  } else if (features?.families && features?.studies) {
    // family without a series: a lens-only link (the studies feature lands
    // it on the family's default data). Garbage families are ignored.
    const fam = p.get('family');
    const present = new Set(['ci']);
    for (const rec of Object.values(manifest.series ?? {})) {
      present.add(rec.family ?? 'ci');
    }
    if (fam && present.has(fam)) state.family = fam;
  }

  const f = p.get('f');
  if (f !== null) {
    // a field is honored only if this deploy gives it UI: nT fields always
    // (their checkboxes), non-nT ones only under the families flag — else
    // f=core-sv on a families-off deploy blanks the globe with no recourse
    const usable = (x) => x in state.enabled
      && ((manifest.fields[x]?.units ?? 'nT') === 'nT' || features?.families);
    const on = new Set(f.split(',').filter(usable));
    if (on.size || f === '') {
      for (const field of Object.keys(state.enabled)) {
        state.enabled[field] = on.has(field);
      }
    }
  }

  const c = p.get('c');
  if (['N', 'E', 'Up', 'F'].includes(c)) state.component = c;

  const s = p.get('s');
  if (s && Object.values(manifest.fields).some((spec) => s in spec.shells)) {
    state.shell = s;
  }

  const vmax = Number(p.get('vmax'));
  if (Number.isFinite(vmax) && vmax > 0) state.vmaxLock = vmax;

  const cam = p.get('cam');
  if (cam) {
    const xyz = cam.split(',').map(Number);
    if (xyz.length === 3 && xyz.every(Number.isFinite) &&
        Math.hypot(...xyz) > globe.controls.minDistance) {
      globe.camera.position.set(...xyz);
      globe.controls.update();
    }
  }
}

export function attach({ state, manifest, globe, hooks, onChange }) {
  if (pendingDay) hooks.pickDay(pendingDay).catch(() => {});

  function encode() {
    // built by hand, not URLSearchParams: every value is hash-safe by
    // construction and `:`/`,` must stay readable in shared links
    const { x, y, z } = globe.camera.position;
    const rec = manifest.series?.[state.day];
    const when = rec
      ? { tab: TAB_OF_KIND[rec.kind] ?? rec.kind,
          series: state.day,
          e: rec.epochs[Math.max(0, Math.min(rec.epochs.length - 1,
                                             Math.round(state.pos)))]
            .slice(0, 16) }                       // trim to minutes
      : { day: state.day, t: fmtTime(state.pos * 15) };
    const pairs = {
      ...when,
      f: Object.keys(state.enabled)
        .filter((field) => state.enabled[field]).join(','),
      c: state.component,
      s: state.shell,
      cam: [x, y, z].map((v) => v.toFixed(3)).join(','),
    };
    if (state.vmaxLock != null) {            // only while the scale is locked
      pairs.vmax = state.vmaxLock.toPrecision(6);
    }
    if (state.family && state.family !== 'ci') {   // v2.9 lens; ci = absent,
      pairs.family = state.family;                 // so old links stay stable
    }
    if (state.sun) pairs.sun = '1';          // only set by the sun feature
    if (state.relief) pairs.r = '1';         // only set by the relief feature
    return '#' + Object.entries(pairs).map(([k, v]) => `${k}=${v}`).join('&');
  }

  let timer = null;
  onChange(() => {
    if (timer) return;
    timer = setTimeout(() => {
      timer = null;
      const hash = encode();
      if (hash !== window.location.hash) {
        history.replaceState(null, '', hash);
      }
    }, DEBOUNCE_MS);
  });
}
