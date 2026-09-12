# Gateway Reachability and Security Boundary

**Static evidence only — no live gateway verification.**

| Metric | Value |
|---|---:|
| Configurations | 4 |
| Upstreams | 51 |
| Proxied locations | 71 |
| Gateway-authenticated locations | 9 |
| Authenticated + trusted tenant injection | 9 |
| Hard configuration errors | 0 |
| Review findings | 9 |

## Per configuration

### `nginx/nginx.v9.conf`

- Upstreams: 18
- Proxied locations: 34
- Review findings: 4
- Upstream hosts absent from compose inventory: none

### `nginx/nginx.unified.conf`

- Upstreams: 15
- Proxied locations: 17
- Review findings: 2
- Upstream hosts absent from compose inventory: none

### `nginx/nginx.light.conf`

- Upstreams: 7
- Proxied locations: 8
- Review findings: 1
- Upstream hosts absent from compose inventory: none

### `nginx/nginx.fixed.conf`

- Upstreams: 11
- Proxied locations: 12
- Review findings: 2
- Upstream hosts absent from compose inventory: none

## Boundary

Static Nginx and Compose evidence only. Service-level authentication and live route behavior require runtime probes.

Content SHA-256: `d116cda1b75e2260b4b736096a84305a9a6710e007f8b9c9c5be5e0fd96173a7`
