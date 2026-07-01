// Sun overlay (PLAN v2.6 step A; IDEAS 1.1): subsolar glyph + day/night
// terminator derived from the displayed UT, so the Sq vortices visibly
// follow local noon during playback. Overlay contract (IDEAS §8.1): own
// scene objects + own checkbox, attach/update only. The single sanctioned
// field-shader touch is the v2.6 integration surface: while the relief
// flag is also on, the sun direction drives the hillshade's uLightDir
// (decided up front in PLAN v2.6 — otherwise the headlight default rules).
//
// Permalink key: sun=1 (read here; written by features/permalink.js).

import * as THREE from 'three';
import { displayedUT, subsolarPoint } from '../sun.js';

const DEG = Math.PI / 180;
const R_OVERLAY = 1.01;            // just off the surface shell
const SEGMENTS = 180;
const EPS = 1e-5;                  // quaternion/uniform settle threshold
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
  if (p.get('sun') === '1') state.sun = true;
}

export function attach({ state, manifest, globe, features, onChange }) {
  // Overlay group built once in a canonical pose: terminator circle in the
  // XY plane, glyph on +Z — pointing +Z at the subsolar direction is then
  // a single quaternion update per frame, no geometry rebuilds.
  const group = new THREE.Group();
  group.name = 'sun-overlay';

  const ring = new Float32Array(SEGMENTS * 3);
  for (let i = 0; i < SEGMENTS; i++) {
    const a = (i / SEGMENTS) * 2 * Math.PI;
    ring.set([Math.cos(a) * R_OVERLAY, Math.sin(a) * R_OVERLAY, 0], i * 3);
  }
  const terminatorGeom = new THREE.BufferGeometry();
  terminatorGeom.setAttribute('position', new THREE.BufferAttribute(ring, 3));
  const terminator = new THREE.LineLoop(
    terminatorGeom,
    new THREE.LineBasicMaterial({ color: 0xffd54f, transparent: true,
                                  opacity: 0.8 }));
  terminator.name = 'sun-terminator';

  const glyph = new THREE.Mesh(
    new THREE.SphereGeometry(0.018, 16, 8),
    new THREE.MeshBasicMaterial({ color: 0xffd54f }));
  glyph.name = 'sun-glyph';
  glyph.position.set(0, 0, R_OVERLAY);

  group.add(terminator, glyph);
  group.renderOrder = 2;           // over the field shell among transparents

  const sunDir = new THREE.Vector3(0, 0, 1);   // world-space, updated below

  function update() {
    const { lat, lon } = subsolarPoint(displayedUT(state, manifest));
    const dir = direction(lat, lon);
    if (dir.angleTo(sunDir) > EPS) {
      sunDir.copy(dir);
      group.quaternion.setFromUnitVectors(new THREE.Vector3(0, 0, 1), sunDir);
      state.dirty = true;
    }
    // uLightDir handoff (view-space): the relief hillshade follows the real
    // sun while both features are on; headlight otherwise. Epsilon-compared
    // so the post-render notification settles instead of spinning the loop.
    const light = globe.fieldMaterial.uniforms.uLightDir;
    if (!light) return;                        // pre-relief shader: no-op
    const target = features.relief && state.relief && state.sun
      ? sunDir.clone().transformDirection(globe.camera.matrixWorldInverse)
      : HEADLIGHT;
    if (target.distanceTo(light.value) > EPS) {
      light.value.copy(target);
      state.dirty = true;
    }
  }

  function setSun(on) {
    state.sun = on;
    if (on) globe.scene.add(group);
    else globe.scene.remove(group);
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
  label.append(cb, document.createTextNode('Sun'));
  document.getElementById('component-radios').after(label);

  onChange(() => { if (state.sun) update(); });
  if (state.sun) setSun(true);                 // restored from the permalink
}
