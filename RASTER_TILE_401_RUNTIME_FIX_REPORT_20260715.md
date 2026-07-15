# Raster Tile 401 Runtime Fix — 2026-07-15

## Confirmed root cause

The frontend is served at `http://127.0.0.1:3003` using a production Vite bundle. Production tile URLs intentionally omit `access_token` and tenant query parameters. Leaflet loads tiles as `<img>` requests, so no Authorization header is attached. The gateway therefore depends on the HttpOnly `sahool_at` cookie.

The auth container previously defaulted `AUTH_COOKIE_SECURE=1`. Browsers do not send Secure cookies over HTTP, so `auth_request /_auth_verify` received no token and returned 401 for every `/api/raster/.../cdse-tiles/...png` request.

## Implemented fix

- `AUTH_COOKIE_SECURE=auto` by default.
- Cookie Secure is derived from `X-Forwarded-Proto`, then request scheme.
- Local HTTP receives a non-Secure HttpOnly cookie.
- Production HTTPS receives a Secure HttpOnly cookie.
- Login, refresh, registration, invitation acceptance and logout pass the request context to the cookie helper.
- Raster nginx proxies forward the verified token source (`$fwd_auth`) downstream instead of the absent `<img>` Authorization header.
- Added regression guard `test_raster_tile_http_cookie_runtime_fix_20260715.py`.

## Verification

- 28 related tests passed.
- Python compileall passed for auth service.
- Both Compose YAML files parsed successfully.

## Deployment note

Existing browser sessions created before this fix do not have a usable HTTP tile cookie. After rebuilding/restarting auth and frontend, log out and log in again (or clear site cookies) so `sahool_at` is issued with the corrected attributes.

## Separate stale tests

`tests_v9/test_tilejson_nginx_runtime_fix_20260626.py` contains two static assertions against an older in-file compatibility implementation. The current direct runtime path is frontend nginx `/api/raster/` to raster-service and is covered by the passing gateway guards above. These stale assertions are not part of the tile 401 root cause.
