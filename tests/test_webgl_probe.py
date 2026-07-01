"""Phase-0 prerequisite probe: WebGL2 under headless Chromium.

The planned renderer (three.js + custom ShaderMaterial) needs:
  - a WebGL2 context in headless Chromium (SwiftShader software GL), and
  - half-float (RGBA16F) texture upload with LINEAR filtering — the field
    tiles are decoded to half-float textures and sampled bilinearly.

Tries launch-arg configs in order and records the first that works in
`tests/webgl_probe_result.json` (committed; results quoted in HISTORY.md, v1 plan §7).
"""
import json
from pathlib import Path



RESULT_FILE = Path(__file__).parent / "webgl_probe_result.json"

# Probe page: 2x1 RGBA16F texture, red ramps 0.0 -> 1.0 across x, sampled
# with LINEAR into an RGBA8 canvas. Reading ~0.5 at the midpoint proves
# bilinear filtering of half-float textures; NEAREST would read 0 or 255.
PROBE_JS = """
() => {
  const out = {webgl2: false, renderer: null, vendor: null,
               max_texture_size: null, rgba16f_linear_ok: false,
               readback_r: null, error: null};
  try {
    const canvas = document.createElement('canvas');
    canvas.width = 16; canvas.height = 16;
    const gl = canvas.getContext('webgl2');
    if (!gl) { out.error = 'webgl2 context unavailable'; return out; }
    out.webgl2 = true;
    const dbg = gl.getExtension('WEBGL_debug_renderer_info');
    out.renderer = String(gl.getParameter(dbg ? dbg.UNMASKED_RENDERER_WEBGL
                                              : gl.RENDERER));
    out.vendor = String(gl.getParameter(dbg ? dbg.UNMASKED_VENDOR_WEBGL
                                            : gl.VENDOR));
    out.max_texture_size = gl.getParameter(gl.MAX_TEXTURE_SIZE);

    const tex = gl.createTexture();
    gl.bindTexture(gl.TEXTURE_2D, tex);
    // IEEE half floats: 0x0000 = 0.0, 0x3C00 = 1.0
    const data = new Uint16Array([0x0000, 0, 0, 0x3C00,
                                  0x3C00, 0, 0, 0x3C00]);
    gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA16F, 2, 1, 0,
                  gl.RGBA, gl.HALF_FLOAT, data);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);

    const vs = `#version 300 es
      in vec2 p; out vec2 uv;
      void main() { uv = p * 0.5 + 0.5; gl_Position = vec4(p, 0., 1.); }`;
    const fs = `#version 300 es
      precision highp float;
      uniform sampler2D t; in vec2 uv; out vec4 c;
      void main() { c = vec4(texture(t, uv).r, 0., 0., 1.); }`;
    const prog = gl.createProgram();
    for (const [type, src] of [[gl.VERTEX_SHADER, vs],
                               [gl.FRAGMENT_SHADER, fs]]) {
      const sh = gl.createShader(type);
      gl.shaderSource(sh, src);
      gl.compileShader(sh);
      if (!gl.getShaderParameter(sh, gl.COMPILE_STATUS))
        throw new Error(gl.getShaderInfoLog(sh));
      gl.attachShader(prog, sh);
    }
    gl.linkProgram(prog);
    if (!gl.getProgramParameter(prog, gl.LINK_STATUS))
      throw new Error(gl.getProgramInfoLog(prog));
    gl.useProgram(prog);

    const buf = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, buf);
    gl.bufferData(gl.ARRAY_BUFFER,
                  new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW);
    const loc = gl.getAttribLocation(prog, 'p');
    gl.enableVertexAttribArray(loc);
    gl.vertexAttribPointer(loc, 2, gl.FLOAT, false, 0, 0);
    gl.viewport(0, 0, 16, 16);
    gl.drawArrays(gl.TRIANGLES, 0, 3);

    const px = new Uint8Array(4);
    gl.readPixels(8, 8, 1, 1, gl.RGBA, gl.UNSIGNED_BYTE, px);
    out.readback_r = px[0];
    out.rgba16f_linear_ok = px[0] > 64 && px[0] < 192;
  } catch (e) {
    out.error = String(e);
  }
  return out;
}
"""

# Phase 0 probed a ladder of launch-arg configs with a standalone
# sync_playwright(); the default config passed (see webgl_probe_result.json),
# so this now uses the pytest-playwright fixture (standalone sync_playwright
# conflicts with the fixture's own loop when the whole suite runs).
def test_webgl2_half_float_linear(page):
    page.set_content("<!doctype html><html><body></body></html>")
    result = page.evaluate(PROBE_JS)
    report = {"ok_config": "default", "results": {"default": result}}
    RESULT_FILE.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    assert result["webgl2"] and result["rgba16f_linear_ok"], result
