# Portal wiring for geomag-model-explorer

Live state (set up 2026-06-11, Phase 1):

- **Service:** `geomag-model-explorer-web.service` (systemd `--user`; reference copy in
  this directory) serving `0.0.0.0:8212` via
  `uv run --extra fetch uvicorn serve:app`.
- **Portal proxy:** `/home/ivaldi/portal/nginx.conf` has a
  `location /foundry/geomag-model-explorer/` block — prefix-stripping
  `proxy_pass http://host.containers.internal:8212/`, `X-Forwarded-Prefix`,
  `proxy_intercept_errors on`, `error_page 502 503 504 = @geomag_model_explorer_down`
  falling back to the static stub
  `/home/ivaldi/portal/web/foundry/geomag-model-explorer/index.html`. Modeled on the
  huginn/muninn blocks.
- **Stub + link-card:** already existed before Phase 1
  (`portal/web/foundry/geomag-model-explorer/index.html`, card on
  `portal/web/foundry/index.html`).
- **Reload mechanism:** after editing `nginx.conf`, run
  `systemctl --user restart portal.service` (the conf is
  bind-mounted into the podman nginx container; a restart re-resolves the
  mount inode — `nginx -s reload` inside the container does NOT pick up the
  edit). Static files under `portal/web/` go live without a restart.

## Recovery / drift hazard (pre-existing, PLAN.md §2)

`/home/ivaldi/portal` is **not** a git repo; it is deployed by an internal
Ansible role (`roles/portal`), whose templates are stale
(know only vizlab) and are written with `force: true`. An Ansible re-run
would clobber both the foundry index (dropping the geomag-model-explorer card) and
`nginx.conf` (dropping the proxy block above). If that happens, re-apply:

1. The nginx block below (paste after the muninn block), then
   `systemctl --user restart portal.service`.
2. The geomag-model-explorer link-card on `portal/web/foundry/index.html` and the stub
   `portal/web/foundry/geomag-model-explorer/index.html` (both predate Phase 1; the card
   text may need its "(in planning)" suffix dropped).

```nginx
# Reverse-proxy /foundry/geomag-model-explorer/ → geomag-model-explorer's geomagnetic field globe on the host
# (:8212). Same shape — prefix-stripping proxy_pass + X-Forwarded-Prefix + fallback to
# the static stub. The app uses only relative URLs, so no upstream prefix handling.
location /foundry/geomag-model-explorer/ {
    proxy_pass http://host.containers.internal:8212/;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Forwarded-Host $host;
    proxy_set_header X-Forwarded-Prefix /foundry/geomag-model-explorer;
    proxy_connect_timeout 2s;
    proxy_read_timeout 30s;
    proxy_intercept_errors on;
    error_page 502 503 504 = @geomag_model_explorer_down;
}

location @geomag_model_explorer_down {
    try_files /foundry/geomag-model-explorer/index.html =503;
}
```

The durable fix is updating the Ansible role's templates — out of scope for
this repo; flagged in PLAN.md §2 for all foundry projects.

## Exposure / auth (REVIEW #6)

The day-fetch route `POST /api/days/{date}` triggers host VirES fetch/export
subprocesses (a real, expensive side effect). It is **token-gated in the app** —
not relying on nginx. The POST requires the shared foundry secret in the
`X-Foundry-Token` header (or `Authorization: Bearer <token>`), constant-time
compared, plus a per-IP rate limit (default 10/min, override via
`FOUNDRY_RATE_LIMIT` / `FOUNDRY_RATE_WINDOW_S`). The secret is resolved at
request time from `$FOUNDRY_API_TOKEN` or `~/.config/foundry/api-token` (outside
the repo, never committed/served); with no secret configured the route **fails
closed** (401). The existing date-validity + single-job-queue guards are kept.
The frontend prompts for the token once and caches it in `localStorage` — never
embedded in the page. The read-only routes (`/`, `/api/features`, `/api/days`,
the tile mounts) are unchanged.
