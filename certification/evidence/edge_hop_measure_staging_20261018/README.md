# What the gateway and auth key their rate limits on, behind Railway (staging, 2026-10-18)

**Target:** `https://sahool-frontend-staging.up.railway.app` (staging only; no credentials, no secrets, no writes).
**Measured build:** the gateway (`sahool-frontend`) and `sahool-auth-main` on staging both run `main@ac1e48df4`
(Railway deployments `e42940ca` and `f7a6d13e`, SUCCESS 10:19Z). `services/auth/client_address.py` is in that build, and no
file under `services/auth/` or `shared/` changed between `ac1e48df4` and `main@1765d73a0`. So the auth fix was **already
deployed**; nothing was redeployed for this measurement.
**Method:** tagged `GET` requests from this session's egress, then the gateway's own nginx access log read back with
Railway `get-logs` (read-only). Raw lines: [`raw_gateway_access_log.txt`](raw_gateway_access_log.txt).

## Results

| Quantity (27 access-log lines, 12:59:09–12:59:52Z) | Measured |
|---|---|
| Client address (Railway's http log `srcIp`, and the left `X-Forwarded-For` element) | 14 distinct values in `160.79.106.0/24`: this session's proxy has many egress addresses |
| Right-most `X-Forwarded-For` element received by the gateway | only **3** values: `152.233.30.101` ×4, `.102` ×11, `.104` ×12, **independent of the client** |
| `$remote_addr` at the gateway (the hop the gateway appends for auth) | always in `100.64.0.0/10` (`100.64.0.2`–`.12`) |

`X-Forwarded-For` reaches the gateway as `"<client>, <152.233.30.x>"`. The client is on the **left** of a Railway hop, so the
`152.233.30.x` element is appended on Railway's side after the edge (a client-side proxy would sit to the left of the client).

## What this means

1. **Gateway limiter (`frontend/nginx.conf`, `$sahool_client_addr` = last `X-Forwarded-For` element):** the key is a Railway
   node from a set of three, not the client. Every client routed through the same node shares one `limit_req` bucket.
   The 2026-10-15 measurement (`gateway_live_probe_staging_20261015`) read "the last element is the real client"; with one
   egress it could not tell the two apart, and this run can.
2. **Auth limiter (`services/auth/client_address.py`):** auth receives `"<client>, <152.233.30.x>, <100.64.0.y>"`. Walking
   from the right it skips `100.64.0.y` (trusted by default, so that assumption is now measured: the hop is in
   `100.64.0.0/10`) and stops at `152.233.30.x`, which is not trusted. So **auth keys on the Railway node too**: three
   shared buckets instead of one per client. This is better than the single gateway bucket it replaced, but it is not
   per-client.
3. **Railway's documented client header is `X-Real-IP`** ("for identifying client's remote IP", Railway docs
   *Networking › Specs & Limits › Request Headers*), not the last `X-Forwarded-For` element. The gateway currently
   overwrites it upstream (`proxy_set_header X-Real-IP $remote_addr;`).

## Not measured (stated, not hidden)

- **Whether Railway's edge overwrites a client-supplied `X-Real-IP`.** That decides whether keying on it is safe. The
  gateway's log format does not include `$http_x_real_ip`, so this run cannot see it.
- **Two real clients exhausting separate buckets.** The rate-limit behaviour itself was not driven to 429 in this run.
- **Production:** not measured. It runs the same image from `main`, but its edge node set is not observed here.
- `152.233.30.x` is identified by position and stability, not by a Railway statement naming it.

## Effect on the registry

- `AUTH-IP-RATE-LIMIT-KEYS-ON-THE-GATEWAY-ADDRESS-01` stays **open**. Its "remaining" item is now measured: on Railway,
  auth keys on a Railway node, not the client.
- New gap `RATE-LIMIT-KEY-IS-A-RAILWAY-NODE-NOT-THE-CLIENT-01` (open) for both limiters.
- `RAILWAY-GATEWAY-HAS-NO-RATE-LIMIT-01` keeps its state: a limit exists and returns 429. The new row records that its key
  is not the client.
