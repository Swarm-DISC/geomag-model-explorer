# geomag-model-explorer

plan this in phases. first flesh out the plan here. then review these to get an idea of context and other things to include:
- vizlab
- an internal web-client framework (the old ESA VirES web client; prior art)
then produce new plan including those. Then we will discuss. The commit it as a PLAN.md to iterate on later

browser based interactive 3d visualisation of geomagnetic fields

can be displaying 4 geomagnetic field types: core, crust, magnetosphere, ionosphere

use viresclient to fetch model evaluations (will need to be precomputed and stored)

 render using paraview, vtk, three.js, cesium...? display field component on a globe surface (no fieldlines etc - could be a later task)

interactive to toggle which field (or fields - they can be summed together) to display, which component

slider to display model at different altitudes/depths (on a translucent shell?)

date/time selector and slider. including animation controls to play through time at chosen speed

checks: verify that you have access to the headless browser to test and debug this, and what other stuff we should set up to ensure this development can go ahead unhindered
