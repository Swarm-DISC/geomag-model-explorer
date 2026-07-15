// three.js scene: field shell mesh + coastline reference sphere + controls.
// Scene unit = 1 Earth radius (R_SURFACE = 6371 km); CMB shell at r ≈ 0.546.
import * as THREE from 'three';
import { OrbitControls } from './vendor/OrbitControls.js';
import { buildFieldMaterial, buildCoastMaterial } from './shaders.js';

export const R_SURFACE_M = 6371000;

export function createGlobe(container, lut, coast) {
  const renderer = new THREE.WebGLRenderer({
    antialias: true,
    preserveDrawingBuffer: true,   // test pixel readback
  });
  renderer.setPixelRatio(1);       // SwiftShader-friendly; crisp enough
  container.appendChild(renderer.domElement);

  const scene = new THREE.Scene();
  scene.background = new THREE.Color(0x06080f);
  const camera = new THREE.PerspectiveCamera(45, 1, 0.01, 50);
  camera.position.set(0, 0.6, 2.8);

  // Everything Earth-fixed lives in one group, so a reference frame (feature
  // `frame`, v2.12) poses the whole Earth from a single quaternion. Identity
  // unless that feature rotates it.
  const earth = new THREE.Group();
  earth.name = 'earth';
  scene.add(earth);

  const fieldMaterial = buildFieldMaterial(lut, coast);
  const shell = new THREE.Mesh(new THREE.SphereGeometry(1, 128, 64),
                               fieldMaterial);
  shell.renderOrder = 1;           // after the reference sphere
  earth.add(shell);

  const coastMaterial = buildCoastMaterial(coast);
  const reference = new THREE.Mesh(new THREE.SphereGeometry(1, 128, 64),
                                   coastMaterial);
  reference.visible = false;       // only shown when the shell is off-surface
  earth.add(reference);

  const controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = false;  // render-on-demand without a damping loop
  controls.enablePan = false;
  controls.minDistance = 0.02;
  controls.maxDistance = 12;

  // Relief (PLAN v2.6 step B) displaces vertices, so the shell needs more of
  // them only while it is on: 128×64 (≈2.8°) would alias the 1° crust tiles.
  // The hover raycast keeps hitting this same undisplaced CPU geometry.
  const loGeometry = shell.geometry;
  let hiGeometry = null;
  function setReliefMesh(on) {
    if (on && !hiGeometry) hiGeometry = new THREE.SphereGeometry(1, 256, 128);
    shell.geometry = on ? hiGeometry : loGeometry;
  }

  function resize() {
    const w = container.clientWidth || 1;
    const h = container.clientHeight || 1;
    renderer.setSize(w, h);
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
  }
  resize();
  window.addEventListener('resize', resize);

  // radiusRe: shell radius in Earth radii. On-surface: opaque shell with
  // coastline overlay baked into the field shader. Off-surface: translucent
  // shell + the coastline reference sphere at r = 1.
  function setShell(radiusRe) {
    shell.scale.setScalar(radiusRe);
    const onSurface = Math.abs(radiusRe - 1) < 1e-6;
    const interior = radiusRe < 1 - 1e-6;
    fieldMaterial.uniforms.uCoastMix.value = onSurface ? 1 : 0;
    // Interior shells (CMB) render opaque beneath the faint reference sphere
    // (opaque pass comes first); exterior shells translucent over it, with
    // renderOrder forcing shell-after-reference among transparents.
    fieldMaterial.uniforms.uOpacity.value = interior || onSurface ? 1 : 0.82;
    fieldMaterial.transparent = !(interior || onSurface);
    fieldMaterial.depthWrite = interior || onSurface;
    reference.visible = !onSurface;
    coastMaterial.uniforms.uOpacity.value = interior ? 0.25 : 0.9;
  }
  setShell(1);

  return {
    renderer, scene, camera, controls, fieldMaterial, coastMaterial, shell,
    earth,
    setShell, setReliefMesh, resize,
    render: () => renderer.render(scene, camera),
  };
}
