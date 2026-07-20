// Shader factory: one ShaderMaterial colormapping the sum of enabled fields.
//
// GLSL ES 3.00 forbids dynamic indexing of sampler arrays, so the 4-field
// sampling loop is unrolled in JS at source-build time (uTexA0..3 / uTexB0..3,
// A = floor timestep, B = ceil; B === A for static/daily fields).
//
// UV convention (shared by field tiles, coastline and the reference sphere):
// lon/lat are computed per-fragment from the object-space position; tiles are
// equirect grids with row 0 = lat −90 (v = 0, DataTexture flipY = false) and a
// duplicated ±180° column; UVs are texel-center aligned per field grid.
import * as THREE from 'three';

export const FIELD_INDEX = { core: 0, crust: 1, iono: 2, magneto: 3,
                             'core-sv': 4 };
export const N_FIELDS = 5;

// 1×1 half-float zero texture: keeps disabled fields' samplers valid.
export function zeroTexture() {
  const data = new Uint16Array(4).fill(0);
  data[3] = THREE.DataUtils.toHalfFloat(1);
  const tex = new THREE.DataTexture(data, 1, 1, THREE.RGBAFormat, THREE.HalfFloatType);
  tex.needsUpdate = true;
  return tex;
}

const VERTEX = /* glsl */ `
out vec3 vPos;
void main() {
  vPos = position;
  gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
}
`;

// Field sampling shared by the field material's VS and FS (PLAN v2.6 step B:
// the vertex shader displaces along the radius by the same scalar the
// fragment shader colors, so relief and colorbar always agree).
const FIELD_CHUNK = /* glsl */ `
${Array.from({ length: N_FIELDS }, (_, i) =>
  `uniform sampler2D uTexA${i};\nuniform sampler2D uTexB${i};`).join('\n')}
uniform float uEnable[${N_FIELDS}];  // 1 if field on AND has data at current shell
uniform float uScale[${N_FIELDS}];   // storage qrange per field (descale from [-1,1])
uniform float uMix;            // time fraction between A and B textures
uniform vec4 uGrid[${N_FIELDS}];  // (nlon, nlat, 1/nlon, 1/nlat) per field
uniform vec3 uMask;            // component selector; Up = (0,0,-1)
uniform float uUseMag;         // 1.0 -> |B| instead of dot(B, uMask)
uniform float uVmax;           // display range, nT
uniform float uRelief;         // radial displacement at vmax, object radii

vec2 lonlat(vec3 p) {
  vec3 n = normalize(p);
  float lat = degrees(asin(clamp(n.y, -1.0, 1.0)));
  float lon = degrees(atan(n.x, n.z));
  return vec2(lon, lat);
}

vec2 fieldUV(vec2 ll, vec4 grid) {
  // texel-center aligned: u = (col + 0.5) / nlon with col spanning nlon-1 steps
  return vec2(((ll.x + 180.0) / 360.0 * (grid.x - 1.0) + 0.5) * grid.z,
              ((ll.y +  90.0) / 180.0 * (grid.y - 1.0) + 0.5) * grid.w);
}

// Sum of the enabled fields, masked to the displayed component (signed) or
// |B|; the one scalar both the colormap and the relief displacement use.
float fieldScalar(vec2 ll) {
  vec3 B = vec3(0.0);
${Array.from({ length: N_FIELDS }, (_, i) => `  {
    vec2 uv = fieldUV(ll, uGrid[${i}]);
    B += uEnable[${i}] * uScale[${i}] *
         mix(texture(uTexA${i}, uv).xyz, texture(uTexB${i}, uv).xyz, uMix);
  }`).join('\n')}
  return mix(dot(B, uMask), length(B), uUseMag);
}
`;

// vPos stays the *undisplaced* position so lon/lat — field colors, coastlines,
// the hover raycast against the CPU sphere — drape onto the relief unchanged.
// uRelief == 0 multiplies position by exactly 1.0: bit-identical to VERTEX.
const FIELD_VERTEX = /* glsl */ `
${FIELD_CHUNK}
out vec3 vPos;
out vec3 vViewPos;
void main() {
  vPos = position;
  float s = clamp(fieldScalar(lonlat(position)) / uVmax, -1.0, 1.0);
  vec4 mv = modelViewMatrix * vec4(position * (1.0 + uRelief * s), 1.0);
  vViewPos = mv.xyz;
  gl_Position = projectionMatrix * mv;
}
`;

const FRAGMENT = /* glsl */ `
precision highp float;
in vec3 vPos;
in vec3 vViewPos;
out vec4 fragColor;

${FIELD_CHUNK}
uniform sampler2D uLut;        // 256x1 diverging nio colormap
uniform sampler2D uCoast;      // equirect coastlines, alpha = line
uniform float uCoastMix;       // coastline overlay strength
uniform float uOpacity;
uniform vec3 uLightDir;        // view-space; headlight unless the sun drives it
uniform vec3 uSunDir;          // unit subsolar direction, object space (= ECEF)
uniform float uSunlight;       // 1 while the Sunlight toggle is on (v2.12)
uniform float uStale;          // 1 while the bound tiles lag the target view

void main() {
  vec2 ll = lonlat(vPos);
  float v = fieldScalar(ll);
  float t = clamp(0.5 * v / uVmax + 0.5, 0.0, 1.0);
  vec3 col = texture(uLut, vec2(t, 0.5)).rgb;
  vec4 coast = texture(uCoast, vec2((ll.x + 180.0) / 360.0,
                                    (ll.y +  90.0) / 180.0));
  col = mix(col, coast.rgb, coast.a * uCoastMix);
  if (uSunlight != 0.0) {
    // Day/night from the undisplaced sphere normal, so the same term works
    // at every shell radius and under relief displacement; ~±5° soft
    // terminator band; the night floor keeps field colors readable —
    // clearly visible, just darker than the day side.
    // uSunlight == 0 leaves col untouched — bit-identical off path.
    float day = smoothstep(-0.09, 0.09, dot(normalize(vPos), uSunDir));
    col *= mix(0.55, 1.0, day);
  }
  if (uRelief != 0.0) {
    // The material is unlit, so face-on relief would be invisible: hillshade
    // from the displaced surface's screen-space derivatives, floored so the
    // unlit side stays readable when the sun (not the headlight) is the light.
    vec3 nrm = normalize(cross(dFdx(vViewPos), dFdy(vViewPos)));
    col *= 0.55 + 0.45 * clamp(dot(nrm, normalize(uLightDir)), 0.0, 1.0);
  }
  if (uStale != 0.0) {
    // The bound tiles belong to a superseded shell/day/step: desaturate and
    // darken so the lag reads as "loading", not as the new view's values
    // (applyTextures clears this on commit). Last color op so the dim wins
    // over sun/relief shading. uStale == 0 — bit-identical off path.
    float g = dot(col, vec3(0.299, 0.587, 0.114));
    col = mix(col, vec3(g * 0.55), 0.65 * uStale);
  }
  fragColor = vec4(col, uOpacity);
}
`;

const COAST_FRAGMENT = /* glsl */ `
precision highp float;
in vec3 vPos;
out vec4 fragColor;
uniform sampler2D uCoast;
uniform float uOpacity;
uniform vec3 uSunDir;          // unit subsolar direction, object space (= ECEF)
uniform float uSunlight;       // 1 while the Sunlight toggle is on (v2.12)

void main() {
  vec3 n = normalize(vPos);
  float lat = degrees(asin(clamp(n.y, -1.0, 1.0)));
  float lon = degrees(atan(n.x, n.z));
  vec4 coast = texture(uCoast, vec2((lon + 180.0) / 360.0,
                                    (lat +  90.0) / 180.0));
  vec3 col = coast.rgb;
  if (uSunlight != 0.0) {
    // Same day/night term as the field fragment, so the reference sphere
    // dims in step with an off-surface shell.
    float day = smoothstep(-0.09, 0.09, dot(n, uSunDir));
    col *= mix(0.55, 1.0, day);
  }
  fragColor = vec4(col, coast.a * uOpacity);
}
`;

export function buildFieldMaterial(lut, coast) {
  const zero = zeroTexture();
  const uniforms = {
    uEnable: { value: new Float32Array(N_FIELDS) },
    uScale: { value: new Float32Array(N_FIELDS).fill(1) },
    uMix: { value: 0 },
    uGrid: { value: Array.from({ length: N_FIELDS },
                               () => new THREE.Vector4(2, 2, 0.5, 0.5)) },
    uMask: { value: new THREE.Vector3(0, 0, -1) },   // Up
    uUseMag: { value: 0 },
    uVmax: { value: 1 },
    uRelief: { value: 0 },
    uLightDir: { value: new THREE.Vector3(0.35, 0.45, 0.85).normalize() },
    uSunDir: { value: new THREE.Vector3(0, 0, 1) },
    uSunlight: { value: 0 },
    uStale: { value: 0 },
    uLut: { value: lut },
    uCoast: { value: coast },
    uCoastMix: { value: 1 },
    uOpacity: { value: 1 },
  };
  for (let i = 0; i < N_FIELDS; i++) {
    uniforms[`uTexA${i}`] = { value: zero };
    uniforms[`uTexB${i}`] = { value: zero };
  }
  return new THREE.ShaderMaterial({
    glslVersion: THREE.GLSL3,
    vertexShader: FIELD_VERTEX,
    fragmentShader: FRAGMENT,
    uniforms,
  });
}

// Coastline-only reference sphere (Phase 4) — same lon/lat convention.
export function buildCoastMaterial(coast) {
  return new THREE.ShaderMaterial({
    glslVersion: THREE.GLSL3,
    vertexShader: VERTEX,
    fragmentShader: COAST_FRAGMENT,
    uniforms: {
      uCoast: { value: coast }, uOpacity: { value: 1 },
      uSunDir: { value: new THREE.Vector3(0, 0, 1) },
      uSunlight: { value: 0 },
    },
    transparent: true,
    depthWrite: false,
  });
}
