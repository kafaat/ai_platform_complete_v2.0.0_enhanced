# Gateway Reachability and Security Boundary

**Static evidence only — no live gateway verification.**

| Metric | Value |
|---|---:|
| Configurations | 4 |
| Upstreams | 51 |
| Proxied locations | 68 |
| Gateway-authenticated locations | 8 |
| Authenticated + trusted tenant injection | 8 |
| Hard configuration errors | 0 |
| Review findings | 9 |

## Per configuration

### `nginx/nginx.v9.conf`

- Upstreams: 18
- Proxied locations: 31
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

Content SHA-256: `586b3c4c1f606b84729ab8f2450f99333c97a2ab1a23d6f297844af22e4d74f8`
