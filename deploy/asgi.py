"""ASGI entrypoint for the deployment-setup experimental tier.

Wraps the root-mounted `serve:app` so it can be served under ``$URL_PREFIX``
(e.g. ``/experimental/geomag-model-explorer``). deployment-setup proxies requests to the
container with the prefix intact — the contract is "respond at $URL_PREFIX/" — so we strip
``$URL_PREFIX`` from the incoming ASGI path and let the existing app (which uses only
relative URLs) handle the rest.

If a deployment instead strips the prefix upstream, the path simply won't start with it and
we pass the request through unchanged, so this is correct either way. With no ``$URL_PREFIX``
set it is a transparent pass-through (the local/portal setup is unaffected).
"""
from __future__ import annotations

import os

from serve import app as _app

_PREFIX = os.environ.get("URL_PREFIX", "").rstrip("/")


async def app(scope, receive, send):
    if _PREFIX and scope.get("type") in ("http", "websocket"):
        path = scope.get("path", "")
        if path == _PREFIX or path.startswith(_PREFIX + "/"):
            stripped = path[len(_PREFIX):] or "/"
            pb = _PREFIX.encode()
            raw = scope.get("raw_path") or path.encode()
            raw = (raw[len(pb):] or b"/") if raw.startswith(pb) else stripped.encode()
            # Strip the prefix and serve the app AT ROOT (it uses relative URLs). Do NOT also set
            # root_path=_PREFIX: that double-accounts the prefix and breaks Starlette's nested
            # Mount() routing (e.g. the /data static mount 404s under a prefix).
            scope = {**scope, "path": stripped, "raw_path": raw, "root_path": ""}
    await _app(scope, receive, send)
