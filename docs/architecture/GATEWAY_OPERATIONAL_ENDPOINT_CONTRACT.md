# Gateway Operational Endpoint Contract

Status: **Accepted** · 2026-08-03

The canonical infrastructure endpoints are exact paths:

- `GET /healthz` — public liveness response at the gateway.
- `GET /readyz` — private/operator-only readiness, proxied to `sahool-platform`.
- `GET /runtime-identity` — private/operator-only immutable build identity, proxied to `sahool-platform`.
- `GET /metrics` — private monitoring surface.

These paths must never reach the SPA fallback. A request must receive the backend
response or an explicit gateway denial/error; `200 text/html` is forbidden. Exact
matching is required so domain paths such as `/fields/runtime-identity` are not
reclassified as infrastructure.

The frontend development/production-build gateway proxies `/readyz` and
`/runtime-identity` directly to the platform to preserve the same semantic
contract on port 3003. The production gateway restricts both paths to loopback
and RFC1918 operator networks.

## Assumption the ACL depends on — stated, not implied

`allow`/`deny` in nginx match **`$remote_addr`**, which is the address of the peer
that opened the TCP connection, not the originating client. The contract's privacy
claim therefore holds only while the gateway terminates client connections
directly — which is the current topology: `sahool-nginx` publishes `80:80` and
`443:443` in `docker-compose.v9.yml`, with nothing in front of it.

**Put a load balancer, CDN, or ingress controller in front and the claim inverts.**
`$remote_addr` becomes that proxy's address, which is itself typically RFC1918, so
the allow-list would admit every request it forwards — the whole internet, through
an ACL that still reads as private. The failure is silent: the configuration is
unchanged and the tests stay green, because both inspect the file, not the network.

Whoever introduces such a hop owns this contract with it, and must either switch the
decision to `realip_module` with an explicit `set_real_ip_from` for the trusted hop,
or move these paths off the public listener entirely. Do not widen the CIDR list to
make a new topology work — that is the same mistake with a larger blast radius.
