# Gateway Reachability and Security Boundary

**Static evidence only — no live gateway verification.**

| Metric | Value |
|---|---:|
| Configurations | 4 |
| Upstreams | 51 |
| Proxied locations | 74 |
| Gateway-authenticated locations | 11 |
| Authenticated + trusted tenant injection | 11 |
| Hard configuration errors | 0 |
| Review findings | 11 |

## Per configuration

### `nginx/nginx.v9.conf`

- Upstreams: 18
- Proxied locations: 37
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

Content SHA-256: `8d4d341eb2f89612d8641b69b1a37b0e2cf635c642dc867bd31413079e2e2558`
