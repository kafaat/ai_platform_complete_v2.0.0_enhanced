# Gateway Reachability and Security Boundary

**Static evidence only — no live gateway verification.**

| Metric | Value |
|---|---:|
| Configurations | 4 |
| Upstreams | 51 |
| Proxied locations | 72 |
| Gateway-authenticated locations | 10 |
| Authenticated + trusted tenant injection | 10 |
| Hard configuration errors | 0 |
| Review findings | 10 |

## Per configuration

### `nginx/nginx.v9.conf`

- Upstreams: 18
- Proxied locations: 35
- Review findings: 5
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

Content SHA-256: `0349fddfcaa96be2bd0f129a1473ebbe02efb082594ee4043ddd6d4cef300c7b`
