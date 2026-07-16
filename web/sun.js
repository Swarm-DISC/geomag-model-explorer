// Solar position (PLAN v2.6 step A; IDEAS 1.1): subsolar point from the
// displayed UT. Pure math, no three.js — the overlay in features/sun.js owns
// the scene objects.
//
// Analytic low-accuracy ephemeris (NOAA/Meeus truncation): good to ~0.3°,
// far below the width of a terminator line on screen.

const DEG = Math.PI / 180;
const DAY_MS = 86400000;

// Epochs in the manifest carry no zone designator and mean UT; bare
// Date.parse would read them as *local* time (ES spec) and shift the sun
// by the host timezone. Exported (v2.13) so the timeline viewer builds its
// chart time axis from the same instants.
export function parseUT(iso) {
  return Date.parse(/[Zz]|[+-]\d{2}:\d{2}$/.test(iso) ? iso : iso + 'Z');
}

// The UT instant a series shows at a fractional epoch index (PLAN v2.8;
// features/studies.js builds its timeline labels from the same instant).
// When consecutive epochs sit a whole number of days apart — true for any
// fixed-time-of-day series — the interpolated offset snaps to whole days,
// so scrubbing holds the series' clock time instead of sweeping the sun
// through every intermediate hour.
export function seriesUT(rec, pos) {
  const i = Math.max(0, Math.min(Math.floor(pos), rec.epochs.length - 2));
  const a = parseUT(rec.epochs[i]);
  const b = parseUT(rec.epochs[i + 1] ?? rec.epochs[i]);
  const span = b - a;
  let off = span * (pos - i);
  if (span > 0 && span % DAY_MS === 0) {
    off = Math.round(off / DAY_MS) * DAY_MS;
  }
  return new Date(a + off);
}

// The UT instant the globe is showing: state.day is either a series id or a
// YYYY-MM-DD day whose 97 epochs are fixed 15-min steps from midnight.
export function displayedUT(state, manifest) {
  const rec = manifest.series?.[state.day];
  if (rec) return seriesUT(rec, state.pos);
  return new Date(parseUT(`${state.day}T00:00:00`) + state.pos * 15 * 60000);
}

// Subsolar latitude = solar declination; subsolar longitude from the UT
// hour angle corrected by the equation of time (q − ra, in degrees).
export function subsolarPoint(date) {
  const d = date.getTime() / 86400000 - 10957.5;   // days since J2000.0
  const g = (357.529 + 0.98560028 * d) * DEG;      // mean anomaly
  const q = 280.459 + 0.98564736 * d;              // mean longitude, deg
  const l = (q + 1.915 * Math.sin(g) + 0.020 * Math.sin(2 * g)) * DEG;
  const e = (23.439 - 0.00000036 * d) * DEG;       // obliquity of ecliptic
  const lat = Math.asin(Math.sin(e) * Math.sin(l)) / DEG;
  const ra = Math.atan2(Math.cos(e) * Math.sin(l), Math.cos(l)) / DEG;
  const eot = ((q - ra) % 360 + 540) % 360 - 180;  // equation of time, deg
  const hours = (date.getTime() / 3600000) % 24;   // UT decimal hours
  const lon = ((-15 * (hours - 12) - eot) % 360 + 540) % 360 - 180;
  return { lat, lon };
}
