// Relief mode (PLAN v2.6 step B): render the field as a displaced surface —
// a display mode next to the component picker, available on every study tab,
// not a tab of its own. All the machinery (shader displacement, mesh swap,
// fixed exaggeration) lives behind hooks.setRelief from step B1; this module
// is just the checkbox + the r=1 permalink key (written by
// features/permalink.js, read here so the key dies with the flag).

export function restore({ state }) {
  const p = new URLSearchParams(window.location.hash.slice(1));
  // '1' predates the v2.12 on-default (old links must keep working);
  // '0' is how a link expresses off now that on is the default.
  if (p.get('r') === '1') state.relief = true;
  if (p.get('r') === '0') state.relief = false;
}

export function attach({ state, hooks }) {
  const label = document.createElement('label');
  label.className = 'field-toggle';
  const cb = document.createElement('input');
  cb.type = 'checkbox';
  cb.id = 'relief-toggle';
  cb.checked = state.relief;
  cb.addEventListener('change', () => hooks.setRelief(cb.checked));
  label.append(cb, document.createTextNode('Relief'));
  document.getElementById('slot-flags').append(label);

  if (state.relief) hooks.setRelief(true);   // restored from the permalink
}
