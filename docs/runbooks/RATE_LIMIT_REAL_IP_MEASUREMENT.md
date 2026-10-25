# Rate-limit key: does Railway's edge overwrite X-Real-IP? (owner-run measurement)

Gap: `RATE-LIMIT-KEY-IS-A-RAILWAY-NODE-NOT-THE-CLIENT-01` (`sahool-brain/gaps/registry.md`).
Owner decision 2026-10-25: prepare the measurement branch and do not merge it.

> **Merging the log change deploys the gateway.** `frontend/nginx.conf` is the Railway
> gateway (`deploy/railway/Dockerfile.frontend` copies it, `deploy/railway/render_frontend.py`
> renders it). The frontend deploys from `main` to production automatically (registry row
> above; `docs/runbooks/RAILWAY_FRONTEND_DEPLOYMENT.md:17`). A merge is a production change
> to the public gateway, even though it only changes what is logged. Deploying this branch
> to staging alone is the owner's call and is a separate step.

## Why this measurement

Measured on staging 2026-10-18 (`certification/evidence/edge_hop_measure_staging_20261018/README.md`):

- `X-Forwarded-For` reaches the gateway as `"<client>, <152.233.30.x>"`. The right-most
  element is one of three Railway nodes (`.101`, `.102`, `.104`), whatever the client.
- The gateway limiter keys on the **last** XFF element (`frontend/nginx.conf`, map
  `$http_x_forwarded_for $sahool_client_addr`, then `$sahool_rl_key` in the three
  `limit_req_zone` lines). So it keys on a Railway node: three shared buckets.
- Auth (`services/auth/client_address.py`, `resolve_client_ip`) walks XFF from the right,
  skips the trusted `100.64.0.y` hop the gateway appends, and stops at `152.233.30.x`,
  which is not trusted. Auth keys on a Railway node too.
- Railway documents `X-Real-IP` as the client header. The gateway overwrites it upstream
  (`proxy_set_header X-Real-IP $remote_addr;`), and the old log format did not record it.

Keying on `X-Real-IP` is only safe if Railway's edge **overwrites** whatever the client
sends in it. If the edge passes a client value through, any client picks its own bucket.
That single fact was not measured, and this branch exists to measure it.

## What the branch changes

| File | Change |
|---|---|
| `frontend/nginx.conf` | New `log_format sahool_edge` (the image's `main` format, then `xrip="$http_x_real_ip" rl_key="$sahool_rl_key"`), used by the gateway server's `access_log /dev/stdout sahool_edge;`. No key, map, zone or `proxy_set_header` changes. |
| `tests_v9/test_gateway_real_ip_access_log.py` | Asserts the format carries `$http_x_forwarded_for`, `$http_x_real_ip` and the limiter key in the source and the Railway-rendered config. Pins every `limit_req_zone`, both key maps, the loopback exemption and all 26 `X-Real-IP` / `X-Forwarded-For` header lines to `main@eb0be3977`. Red on main for the log; each pinned item has its own mutation that turns it red. |
| `scripts/staging/rate_limit_real_ip_probe.py` | Owner-run probe: two `GET /` requests, one with a spoofed `X-Real-IP`. It refuses to run without `--i-am-the-owner-run` and `--target`, and it refuses when `CI`/`GITHUB_ACTIONS` is set. |
| `tests_v9/test_rate_limit_real_ip_probe.py` | Refusal tests with no network, plus a check that no file under `.github/` names the probe. |

A gateway log line now ends like this:

```
... "<User-Agent>" "<X-Forwarded-For>" xrip="<X-Real-IP as received>" rl_key="<limiter key>"
```

`xrip` is the header as the gateway **receives** it from Railway's edge, before the gateway
overwrites it for the backends. `-` means it was absent. nginx escapes client-supplied
bytes in log values (`\xHH`).

## The measurement (owner only, after the log change is live on staging)

1. Confirm the staging gateway (`sahool-frontend`, staging) runs a build that contains
   this log format. Any logged request (everything except `access_log off` locations such
   as `/healthz`) should end with `xrip="..." rl_key="..."`.
2. From a machine you control, run once:

   ```bash
   python3 scripts/staging/rate_limit_real_ip_probe.py --i-am-the-owner-run \
     --target https://<staging gateway host>
   ```

   It sends `GET /?sahool_real_ip_probe=<tag>-spoofed` with `X-Real-IP: 203.0.113.7`
   (TEST-NET-3, never a real client), then `GET /?sahool_real_ip_probe=<tag>-plain` without
   it. It prints the tag and what to look for, then exits. It reads no logs and holds no
   credentials. `GET /` is the SPA shell: no backend, no auth, no rate-limited location.
3. Read the staging gateway's logs (deployment logs, read-only) for the two tagged lines.
   Note `srcIp` from Railway's HTTP log for the same requests if available.
4. Keep the two raw lines (and the `srcIp`) as evidence beside the 2026-10-18 measurement.

## Reading the result, and which key each outcome selects

| Outcome in the two lines | Meaning | Key to adopt (follow-up change, its own witness) |
|---|---|---|
| **A.** `spoofed` and `plain` have the same `xrip`, equal to your real address (the left XFF element / Railway `srcIp`), and `203.0.113.7` appears in neither | The edge **overwrites** `X-Real-IP` | **`X-Real-IP`.** The gateway keys `limit_req` on the received `$http_x_real_ip` and forwards it to auth instead of `$remote_addr`. Auth reads it only from a trusted peer. |
| **B.** `spoofed` has `xrip` containing `203.0.113.7` | The edge passes a client value through, so a client picks its own bucket | **Not `X-Real-IP`.** Use the **second-from-right** `X-Forwarded-For` element (the one left of `152.233.30.x`) at the gateway, and add `152.233.30.0/24` to `AUTH_TRUSTED_PROXY_CIDRS` so auth's right-to-left walk skips `100.64.0.y` and `152.233.30.x` and stops at the client. |
| **C.** `plain` has `xrip="-"` | The edge does not set `X-Real-IP` | Same as B. |
| Lines missing, or values that differ between two runs | Inconclusive | Run again; decide nothing. |

Limits to state with whichever result you get:

- `152.233.30.0/24` is trusted because of its position and stability in the 2026-10-18 log,
  not because Railway names it. Under B/C, check that the same range appears on
  production (read-only log) before trusting it there. A Railway node outside that range
  would put its users back in a shared bucket. It would not let a client choose a bucket.
- Staging is not production. The probe measures the staging edge only.
- No 429 is driven here. Two real clients ending up in separate buckets is a witness for
  the follow-up key change, not for this measurement.

## What this branch does not do

It changes no rate-limit key, no `proxy_set_header`, no auth code and no trust list. It runs
nothing against staging or production, and no workflow runs the probe. The key change
comes after the owner reads the result. It needs its own PR and its own witness.
