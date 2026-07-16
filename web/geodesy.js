// WGS84 geodetic <-> geocentric conversion (PLAN v2.13). Pure math, no
// three.js, no DOM — features/timeseries.js owns the inputs that use it.
//
// The tiles are evaluated on geocentric spherical coordinates (fetch.py
// passes radius= to viresclient), so geocentric is the app's native
// convention; geodetic input is converted *before* sampling and the plotted
// components stay geocentric-NEC relabelings (spec'd: no NED rotation).
//
// Anchors (used by the browser test): geodetic 45°, h=0 -> geocentric
// 44.8076°, r = 6367.4895 km; equator and poles map to themselves; a
// round-trip through both functions agrees to < 1 mm.

const DEG = Math.PI / 180;

export const WGS84 = {
  a: 6378137.0,               // semi-major axis, m
  f: 1 / 298.257223563,       // flattening
};
const E2 = WGS84.f * (2 - WGS84.f);   // first eccentricity squared

// Geodetic latitude (deg) + height above the ellipsoid (m) -> geocentric
// latitude (deg) + radius from Earth's center (m). Longitude is unchanged
// by construction (both conventions share the spin axis).
export function geodeticToGeocentric(latDeg, heightM) {
  const lat = latDeg * DEG;
  const sin = Math.sin(lat), cos = Math.cos(lat);
  const n = WGS84.a / Math.sqrt(1 - E2 * sin * sin);  // prime vertical radius
  const p = (n + heightM) * cos;                      // distance from axis
  const z = (n * (1 - E2) + heightM) * sin;
  return { latDeg: Math.atan2(z, p) / DEG, radiusM: Math.hypot(p, z) };
}

// Inverse: geocentric latitude (deg) + radius (m) -> geodetic latitude
// (deg) + height (m). Fixed-point iteration on the classic closed form;
// converges to < 1e-12 rad in a handful of rounds at any Earth-like radius.
export function geocentricToGeodetic(latDeg, radiusM) {
  const gc = latDeg * DEG;
  const p = radiusM * Math.cos(gc);
  const z = radiusM * Math.sin(gc);
  if (p < 1) {                          // on the spin axis: closed form
    const b = WGS84.a * (1 - WGS84.f);
    return { latDeg: Math.sign(z) * 90, heightM: Math.abs(z) - b };
  }
  let lat = Math.atan2(z, p * (1 - E2));
  let n = WGS84.a, h = 0;
  for (let i = 0; i < 8; i++) {
    const sin = Math.sin(lat);
    n = WGS84.a / Math.sqrt(1 - E2 * sin * sin);
    h = p / Math.cos(lat) - n;
    const next = Math.atan2(z, p * (1 - E2 * n / (n + h)));
    if (Math.abs(next - lat) < 1e-13) { lat = next; break; }
    lat = next;
  }
  return { latDeg: lat / DEG, heightM: h };
}
