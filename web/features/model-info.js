// Model-info modal (IDEAS §6.2 "Model-caveat panel", shipped v2.11; v2.14
// repositioned): an ⓘ button embedded top-right of the view pane opens a
// native <dialog> that tells the truth about what is on screen — the served
// model behind each layer of the active context, the exact VirES expression
// it evaluates (copyable, linked to the viresclient model catalogue), its
// degree range and validity (manifest v4 "models"), the grid/cadence/storage
// ranges, and one honest caveat paragraph per model. It also lists what VirES serves that
// this app deliberately does not evaluate, so the catalog coverage is
// auditable from the UI itself.
//
// attach()-only: the dialog holds no permalink state. <dialog>.showModal()
// gives the focus trap, Esc handling, focus restore and top-layer rendering
// for free — no contest with the app's z-index:1 overlays, no dependencies.
// The #globe anchor is static HTML, so this works on every flag shape.

import { FIELD_LABELS } from '../ui.js';
import { FAMILY_LABELS, FAMILY_ATTRIBUTION } from './studies.js';

// One honest paragraph per served model (IDEAS §6.2), keyed by the name in
// manifest.models / manifest.series[*].models. Static trusted text.
const MODEL_NOTES = {
  MCO_SHA_2C: 'Comprehensive Inversion core field, co-estimated with the '
    + 'other CI sources from Swarm and observatory data. Its spline '
    + 'time-dependence resolves changes down to the jerk limit (~1 yr), '
    + 'no faster.',
  MCO_SHA_2D: 'Dedicated-chain core field, estimated independently of the '
    + 'other sources. The product line stopped updating — its validity is '
    + 'frozen at 2013–2018.',
  'CHAOS-Core': 'CHAOS time-dependent core field (degree ≤ 20), order-6 '
    + 'spline time-dependence. The highest degrees are least constrained '
    + 'near the ends of the data window.',
  IGRF: 'The IAGA reference field: degree ≤ 13, piecewise-linear in 5-year '
    + 'generations — exact at the knots, interpolated between them, and '
    + 'predictive beyond the newest generation.',
  MLI_SHA_2C: 'CI lithospheric field, a truncated spherical-harmonic '
    + 'window. Everything shorter-wavelength than the truncation — most of '
    + 'the crustal signal up close — is absent by construction.',
  MLI_SHA_2D: 'Dedicated-chain lithospheric field (degree 16–133): an '
    + 'independent estimate of the same truncated crustal window.',
  'CHAOS-Static': 'CHAOS static internal field, degree 21–185: the crustal '
    + 'window left once the core field takes degrees ≤ 20.',
  'LCS-1': 'Lithospheric model from CHAMP & Swarm gradient data, degree '
    + '≤ 185 — the sharpest crustal model here, and slightly beyond what '
    + 'the 1° grid fully samples; geology-scale anomalies live far above '
    + 'degree 185 regardless.',
  MF7: 'CHAMP-era crustal field (degree 16–133) from the final '
    + 'low-altitude year of the mission.',
  MIO_SHA_2C: 'CI ionospheric (Sq) field: a quiet-time climatology '
    + 'parameterized by season, local time and solar flux — real '
    + 'ionospheric weather (storms, substorms) is not in it.',
  MIO_SHA_2D: 'Dedicated-chain ionospheric Sq climatology (degree ≤ 60), '
    + 'served as primary + induced parts summed. Quiet-time only, like the '
    + 'CI product.',
  MMA_SHA_2C: 'CI magnetospheric field: the large-scale (degree ≤ 2) '
    + 'ring-current signal at 15-min cadence — no substorm structure, no '
    + 'small-scale current systems.',
  MMA_SHA_2F: 'Fast-track magnetospheric field, degree 1 only: the '
    + 'dominant ring-current term at 15-min cadence, produced at low '
    + 'latency.',
  'CHAOS-MMA': 'CHAOS magnetospheric field (degree ≤ 2, primary + '
    + 'induced), co-estimated with CHAOS-Core.',
};

const SV_NOTE = 'Shown as dB/dt: a centered ±6-month finite difference of '
  + 'the model — smoothed, honest secular variation, not instantaneous '
  + 'change.';

// What VirES serves that this app does not render (v2.11 probe record,
// docs/v211_model_probe.json) — the coverage statement.
const ALSO_SERVED = 'VirES also serves models this app deliberately does '
  + 'not evaluate: CHAOS-MIO (the CHAOS family ships without an '
  + 'ionospheric layer — decision 2026-06-12), AMPS (an average polar '
  + 'ionospheric-current model, not a global field) and MLI_SHA_2E '
  + '(degree 600, beyond the 1° grid). The remaining catalog names are '
  + 'covered indirectly: MCO_SHA_2X ≡ CHAOS-Core, the CHAOS and SwarmCI '
  + 'composites are sums of layers shown here, and the -Primary/-Secondary '
  + 'halves are folded into their served MIO/MMA/CHAOS-MMA composites.';

const esc = (s) => String(s)
  .replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;');

function fmtValidity(meta) {
  if (!meta?.start || !meta?.end) return null;
  const s = meta.start.slice(0, 10);
  const e = meta.end.slice(0, 10);
  // the static models are served with sentinel 0001..4000 validity
  if (s <= '0001-12-31' && e >= '3000-01-01') return 'time-independent';
  return `${s} → ${e}`;
}

export function attach({ state, manifest }) {
  const btn = document.createElement('button');
  btn.id = 'model-info-btn';
  btn.type = 'button';
  btn.title = 'About the model on display';
  btn.setAttribute('aria-label', 'About the model on display');
  btn.textContent = 'ⓘ';
  // #viewport, not #globe: series view hides the globe, the ⓘ must stay.
  document.getElementById('viewport').appendChild(btn);

  const dialog = document.createElement('dialog');
  dialog.id = 'model-info';
  dialog.setAttribute('aria-labelledby', 'model-info-title');
  document.body.appendChild(dialog);
  dialog.addEventListener('click', (e) => {
    if (e.target === dialog) dialog.close();       // backdrop click
  });

  // Rebuilt on every open — showModal() blocks interaction underneath, so
  // the content can't go stale while visible.
  function render() {
    const rec = manifest.series?.[state.day];
    const fields = rec ? rec.fields
      : Object.keys(manifest.fields)
        .filter((f) => !manifest.fields[f].sv);    // core-sv is series-only
    const fam = state.family ?? 'ci';
    const famLabel = FAMILY_LABELS[fam] ?? fam;
    const ctxLabel = rec ? rec.label : `Day cache — ${state.day}`;

    const sections = fields.map((field) => {
      const spec = manifest.fields[field] ?? {};
      const model = rec?.models?.[field] ?? spec.model;
      const meta = manifest.models?.[model];
      const qrange = rec?.qrange_nT?.[field] ?? spec.qrange_nT;
      const grid = rec?.grid?.[field] ?? spec.grid;
      const units = spec.units ?? 'nT';
      const single = rec?.single_step?.includes(field);
      const cadence = rec
        ? (single ? 'single snapshot' : `${rec.epochs.length} epochs`)
        : spec.cadence === 'static' ? 'static'
          : spec.cadence === 'day' ? 'daily snapshot'
            : `${spec.n_steps} × 15 min`;
      const validity = fmtValidity(meta);
      const off = state.enabled?.[field]
        ? '' : ' <span class="mi-off">(not displayed)</span>';
      // the expression gets its own copyable row (v2.14): it is the exact
      // string handed to viresclient, so it must be verbatim and liftable.
      // The copy button needs the clipboard API (https/localhost only —
      // absent on the http LAN preview, where user-select:all still works).
      const canCopy = !!navigator.clipboard;
      const rows = [
        model && `<p class="mi-model"><strong>${esc(model)}</strong></p>`,
        meta?.expression && '<div class="mi-expr">'
          + `<code>${esc(meta.expression)}</code>`
          + (canCopy ? '<button class="mi-copy" type="button"'
            + ' title="copy the VirES model string">⧉</button>' : '')
          + '</div>',
        `<p class="mi-meta">${[
          validity && `valid ${esc(validity)}`,
          grid && `grid ${grid[0]}×${grid[1]}`,
          cadence,
          qrange && `stored ±${qrange} ${esc(units)}`,
        ].filter(Boolean).join(' · ')}</p>`,
        MODEL_NOTES[model] && `<p class="mi-note">${MODEL_NOTES[model]}</p>`,
        spec.sv && `<p class="mi-note">${SV_NOTE}</p>`,
      ].filter(Boolean).join('');
      return `<section><h3>${esc(FIELD_LABELS[field] ?? field)}${off}</h3>`
        + rows + '</section>';
    }).join('');

    dialog.innerHTML = '<div id="model-info-head">'
      + `<h2 id="model-info-title">${esc(famLabel)}</h2>`
      + '<button id="model-info-close" type="button" aria-label="Close">'
      + '✕</button></div>'
      + `<p class="mi-context">${esc(ctxLabel)}</p>`
      + sections
      + `<p class="mi-footer">${ALSO_SERVED}</p>`
      + '<p class="mi-docs">Each model string above is the exact expression '
      + 'evaluated via viresclient — see the <a href="https://viresclient.'
      + 'readthedocs.io/en/latest/available_parameters.html#models" '
      + 'target="_blank" rel="noopener">viresclient model catalogue</a>.</p>'
      + `<p class="mi-attr">${FAMILY_ATTRIBUTION[fam]
        ?? FAMILY_ATTRIBUTION.ci}</p>`;
    dialog.querySelector('#model-info-close')
      .addEventListener('click', () => dialog.close());
    // reads the sibling <code> rather than a data attribute: expressions
    // hold single quotes, which have no business inside HTML attributes
    for (const b of dialog.querySelectorAll('.mi-copy')) {
      b.addEventListener('click', () => {
        navigator.clipboard.writeText(b.previousElementSibling.textContent)
          .then(() => {
            b.textContent = '✓';
            setTimeout(() => { b.textContent = '⧉'; }, 1200);
          });
      });
    }
  }

  btn.addEventListener('click', () => {
    render();
    dialog.showModal();
  });
}
