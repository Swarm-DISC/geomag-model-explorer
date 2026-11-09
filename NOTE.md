# geomag-model-explorer

plan this in phases. first flesh out the plan here. then review these to get an idea of context and other things to include:
- earlier in-house globe prototypes
- the old ESA VirES web client (WebClient-Framework; prior art)
then produce new plan including those. Then we will discuss. The commit it as a PLAN.md to iterate on later

browser based interactive 3d visualisation of geomagnetic fields

can be displaying 4 geomagnetic field types: core, crust, magnetosphere, ionosphere

use viresclient to fetch model evaluations (will need to be precomputed and stored)

 render using paraview, vtk, three.js, cesium...? display field component on a globe surface (no fieldlines etc - could be a later task)

interactive to toggle which field (or fields - they can be summed together) to display, which component

slider to display model at different altitudes/depths (on a translucent shell?)

date/time selector and slider. including animation controls to play through time at chosen speed

checks: verify that you have access to the headless browser to test and debug this, and what other stuff we should set up to ensure this development can go ahead unhindered

## Testing and fetching traps

- The app reads the URL hash only at boot. A Playwright `page.goto` to the same path with a new
  `#hash` is a same-document navigation and restores nothing: use a fresh page, `reload()`, or
  go through `about:blank`.
- Never run the same browser suite twice at once. The second `_wait_port` adopts the first
  run's server and both wedge.
- Never give a sandbox suite a fixed port. Another service may already hold it, and a suite
  whose uvicorn can't bind silently drives the foreign service until every readiness wait
  times out. Use `free_ports()` + `wait_port()` from `tests/_sandbox.py`.
- VirES occasionally drops multi-hour `fetch.py` sessions (`ConnectionResetError` 104).
  `fetch.py` is resume-safe (`snapshot_complete()`), so wrap long background fetches in a retry
  loop (e.g. 5 tries, 60 s apart).
