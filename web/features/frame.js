// Reference frame (PLAN v2.12; IDEAS 1.4 ECEF/ECI subset): pose the globe
// from one quaternion about the +Y polar axis, derived from the displayed
// UT. ECEF = identity (v1 behavior); ECI turns the Earth eastward at the
// mean solar rate (15°/hr), so Daily playback shows rotation under a sun
// that holds still up to the equation of time (±4°). The FRAMES table is
// built for the deferred sun-fixed mode — exact subsolar pinning,
// frameAngle = (180 − subsolarPoint(ut).lon) * DEG, seasonal declination
// visible — one table row + one frameAngle case when wanted.
//
// Permalink key: frame=<id> (read here; written by features/permalink.js
// only while ≠ ecef, so pre-v2.12 links stay Earth-fixed).

import * as THREE from 'three';
import { displayedUT } from '../sun.js';

const DEG = Math.PI / 180;
const EPS = 1e-5;                  // quaternion settle threshold
const FRAMES = [
  { id: 'ecef', label: 'ECEF',
    title: 'Earth-fixed: the globe stands still' },
  { id: 'eci', label: 'ECI',
    title: 'Inertial: the globe rotates 15°/hr; the sun holds still' },
];

// Rotation about +Y posing the Earth in the chosen frame at a UT instant.
// A +Y rotation by a adds a to atan2(x, z) longitudes: the subsolar
// longitude sits at ≈ −15·(h − 12) − EoT, so adding 15·h parks the sun's
// world longitude at ≈ 180° − EoT — fixed — while the globe spins eastward.
function frameAngle(id, ut) {
  if (id === 'eci') return ((ut.getTime() / 3600000) % 24) * 15 * DEG;
  return 0;
}

export function restore({ state }) {
  const f = new URLSearchParams(window.location.hash.slice(1)).get('frame');
  if (FRAMES.some((fr) => fr.id === f)) state.frame = f;
}

export function attach({ state, manifest, globe, onChange }) {
  const Y = new THREE.Vector3(0, 1, 0);
  const q = new THREE.Quaternion();

  function update() {
    q.setFromAxisAngle(Y, frameAngle(state.frame,
                                     displayedUT(state, manifest)));
    if (q.angleTo(globe.earth.quaternion) > EPS) {
      globe.earth.quaternion.copy(q);
      state.dirty = true;
    }
  }

  const wrap = document.createElement('span');
  wrap.id = 'frame-toggle';
  for (const fr of FRAMES) {
    const label = document.createElement('label');
    label.className = 'comp-radio';
    label.title = fr.title;
    const rb = document.createElement('input');
    rb.type = 'radio';
    rb.name = 'frame';
    rb.value = fr.id;
    rb.id = `frame-${fr.id}`;
    rb.checked = state.frame === fr.id;
    rb.addEventListener('change', () => {
      state.frame = fr.id;
      update();
      state.dirty = true;          // even on a no-op pose: the hash must sync
    });
    label.append(rb, document.createTextNode(fr.label));
    wrap.appendChild(label);
  }
  document.getElementById('component-radios').after(wrap);

  onChange(update);
  update();                        // restored from the permalink
}
