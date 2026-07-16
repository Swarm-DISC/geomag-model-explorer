// Sunlight (PLAN v2.12, superseding the v2.6 sun overlay; IDEAS 1.1): the
// globe surface is shaded by day/night from the displayed UT — the
// terminator is a lighting boundary now, not a drawn ring (the v2.6
// terminator circle + subsolar glyph are retired). The object-space uSunDir
// feeds the field and coast fragments, so the shading rides the globe under
// any reference frame (feature `frame`) for free. The v2.6 integration
// surface stands: while the relief flag is also on, the sun direction drives
// the hillshade's uLightDir (otherwise the headlight default rules) — that
// world-space direction is where the frame's earth quaternion enters.
//
// Permalink key: sun=1/0 (read here; written by features/permalink.js).

import * as THREE from 'three';
import { displayedUT, subsolarPoint } from '../sun.js';

const DEG = Math.PI / 180;
const EPS = 1e-5;                  // uniform settle threshold
const HEADLIGHT = new THREE.Vector3(0.35, 0.45, 0.85).normalize();

// Unit vector of a lat/lon on the globe — same convention as the shader's
// lonlat(): lat from +Y, lon = atan2(x, z).
function direction(lat, lon) {
  const cl = Math.cos(lat * DEG);
  return new THREE.Vector3(cl * Math.sin(lon * DEG), Math.sin(lat * DEG),
                           cl * Math.cos(lon * DEG));
}

export function restore({ state }) {
  const p = new URLSearchParams(window.location.hash.slice(1));
  // '1' predates the v2.12 on-default (old links must keep working);
  // '0' is how a link expresses off now that on is the default.
  if (p.get('sun') === '1') state.sun = true;
  if (p.get('sun') === '0') state.sun = false;
}

export function attach({ state, manifest, globe, features, onChange }) {
  const materials = [globe.fieldMaterial, globe.coastMaterial];
  const sunDir = new THREE.Vector3(0, 0, 1);   // object-space (= ECEF)

  function update() {
    const { lat, lon } = subsolarPoint(displayedUT(state, manifest));
    const dir = direction(lat, lon);
    if (dir.angleTo(sunDir) > EPS) {
      sunDir.copy(dir);
      for (const m of materials) m.uniforms.uSunDir.value.copy(sunDir);
      state.dirty = true;
    }
    // uLightDir handoff (view-space): the relief hillshade follows the real
    // sun while both features are on; headlight otherwise. The earth group's
    // quaternion (feature `frame`; identity in ECEF) turns the object-space
    // sun into the world-space one. Epsilon-compared so the post-render
    // notification settles instead of spinning the loop.
    const light = globe.fieldMaterial.uniforms.uLightDir;
    if (!light) return;                        // pre-relief shader: no-op
    const target = features.relief && state.relief && state.sun
      ? sunDir.clone().applyQuaternion(globe.earth.quaternion)
          .transformDirection(globe.camera.matrixWorldInverse)
      : HEADLIGHT;
    if (target.distanceTo(light.value) > EPS) {
      light.value.copy(target);
      state.dirty = true;
    }
  }

  function setSun(on) {
    state.sun = on;
    for (const m of materials) m.uniforms.uSunlight.value = on ? 1 : 0;
    update();
    state.dirty = true;
  }

  const label = document.createElement('label');
  label.className = 'field-toggle';
  const cb = document.createElement('input');
  cb.type = 'checkbox';
  cb.id = 'sun-toggle';
  cb.checked = state.sun;
  cb.addEventListener('change', () => setSun(cb.checked));
  label.append(cb, document.createTextNode('Sunlight'));
  document.getElementById('slot-flags').append(label);

  onChange(() => { if (state.sun) update(); });
  if (state.sun) setSun(true);                 // restored from the permalink
}
