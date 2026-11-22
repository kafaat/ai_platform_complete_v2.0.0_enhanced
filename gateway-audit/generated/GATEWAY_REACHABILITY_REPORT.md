# Gateway Reachability and Security Boundary

**Static evidence only — no live gateway verification.**

| Metric | Value |
|---|---:|
| Configurations | 4 |
| Upstreams | 53 |
| Proxied locations | 82 |
| Gateway-authenticated locations | 18 |
| Authenticated + trusted tenant injection | 12 |
| Hard configuration errors | 0 |
| Review findings | 11 |

## Per configuration

### `nginx/nginx.v9.conf`

- Upstreams: 20
- Proxied locations: 45
- Review findings: 6
- Upstream hosts absent from compose inventory: none

### `nginx/nginx.unified.conf`

- Upstreams: 15
- Proxied locations: 17
- Review findings: 2
- Upstream hosts absent from compose inventory: actuator-service, agriai-engine, auth-service, edge-inference, erp-bridge, fastbee, frontend, local-ai-rag, market-mcp, sentinel-hub-mcp, supervisor-agent, video-processor, weather-mcp, wofost-mcp, zlmediakit

### `nginx/nginx.light.conf`

- Upstreams: 7
- Proxied locations: 8
- Review findings: 1
- Upstream hosts absent from compose inventory: sahool-actuator, sahool-supervisor

### `nginx/nginx.fixed.conf`

- Upstreams: 11
- Proxied locations: 12
- Review findings: 2
- Upstream hosts absent from compose inventory: none

## Boundary

Static Nginx and Compose evidence only. Service-level authentication and live route behavior require runtime probes.

Content SHA-256: `b323c89143ed3f2d300b4e739178d475232f5f5b09e1e8504348912f3e3b4d85`
