// AUTO-GENERATED from platform_catalog.generated.json — do not edit by hand.
// Regenerate: python scripts/architecture/build_platform_catalog.py
// Drift guard (--check) blocks divergence from the deterministic compiler.
// Honesty: `wired`/`tested` are static-derived; configured/activated are
// runtime-only and NEVER asserted here — the UI must degrade on live /readyz.

export interface CatalogComponent {
  id: string;
  type: string;
  domain: string;
  wired: boolean | null;
  wiringDisposition: string | null;
  tested: boolean | null;
  capabilityCount: number;
}

export const PLATFORM_CATALOG_FINGERPRINT = '7fd533f9c65b21c4e264388fad05175a15dea0070b74c27260601da3ed922fe4';

export const PLATFORM_CATALOG_COUNTS = {
  "backend_components": 32,
  "capabilities": 832,
  "capabilities_approval_gated": 8,
  "capabilities_field_scoped": 95,
  "capabilities_idempotent": 47,
  "capabilities_season_scoped": 10,
  "capabilities_tenant_scoped": 478,
  "components": 36,
  "cross_service_duplicate_method_paths": 12,
  "duplicate_groups_classified": 12,
  "indicator_products": 34,
  "ownership_conflicts": 0,
  "route_rows": 1123,
  "ui_waivers": 53,
  "unique_method_path": 1004
} as const;

export const PLATFORM_CATALOG_COMPONENTS: CatalogComponent[] = [
  {
    "capabilityCount": 3,
    "domain": "execution",
    "id": "actuator-service",
    "tested": true,
    "type": "service",
    "wired": true,
    "wiringDisposition": "consumed"
  },
  {
    "capabilityCount": 5,
    "domain": "simulation-experimental",
    "id": "agriai-engine",
    "tested": true,
    "type": "service",
    "wired": false,
    "wiringDisposition": "intentional-unconsumed"
  },
  {
    "capabilityCount": 10,
    "domain": "agents",
    "id": "ai_agronomist",
    "tested": true,
    "type": "service",
    "wired": true,
    "wiringDisposition": "consumed"
  },
  {
    "capabilityCount": 23,
    "domain": "identity",
    "id": "auth",
    "tested": true,
    "type": "service",
    "wired": true,
    "wiringDisposition": "consumed"
  },
  {
    "capabilityCount": 62,
    "domain": "decision-governance",
    "id": "decision-service",
    "tested": true,
    "type": "service",
    "wired": true,
    "wiringDisposition": "consumed"
  },
  {
    "capabilityCount": 3,
    "domain": "edge",
    "id": "edge-inference",
    "tested": true,
    "type": "service",
    "wired": true,
    "wiringDisposition": "consumed"
  },
  {
    "capabilityCount": 8,
    "domain": "erp-projection",
    "id": "erp-bridge",
    "tested": true,
    "type": "service",
    "wired": true,
    "wiringDisposition": "consumed"
  },
  {
    "capabilityCount": 2,
    "domain": "fields-internal",
    "id": "field-management-service",
    "tested": true,
    "type": "service",
    "wired": true,
    "wiringDisposition": "consumed"
  },
  {
    "capabilityCount": 1,
    "domain": "fields-boundary",
    "id": "field-segmentation",
    "tested": true,
    "type": "service",
    "wired": true,
    "wiringDisposition": "consumed"
  },
  {
    "capabilityCount": 0,
    "domain": "user-interface",
    "id": "frontend",
    "tested": null,
    "type": "frontend",
    "wired": null,
    "wiringDisposition": null
  },
  {
    "capabilityCount": 0,
    "domain": "gis-publication",
    "id": "gis-workflow-service",
    "tested": true,
    "type": "tool_bundle",
    "wired": null,
    "wiringDisposition": "standalone-job"
  },
  {
    "capabilityCount": 5,
    "domain": "decision-governance",
    "id": "guardrails-engine",
    "tested": true,
    "type": "service",
    "wired": true,
    "wiringDisposition": "consumed"
  },
  {
    "capabilityCount": 5,
    "domain": "indicators",
    "id": "indicators-service",
    "tested": true,
    "type": "service",
    "wired": true,
    "wiringDisposition": "consumed"
  },
  {
    "capabilityCount": 3,
    "domain": "knowledge",
    "id": "knowledge-graph",
    "tested": true,
    "type": "service",
    "wired": true,
    "wiringDisposition": "consumed"
  },
  {
    "capabilityCount": 2,
    "domain": "knowledge",
    "id": "local-ai-rag",
    "tested": true,
    "type": "service",
    "wired": true,
    "wiringDisposition": "consumed"
  },
  {
    "capabilityCount": 11,
    "domain": "agents-mcp",
    "id": "mcp_servers",
    "tested": true,
    "type": "service",
    "wired": true,
    "wiringDisposition": "consumed"
  },
  {
    "capabilityCount": 0,
    "domain": "user-interface",
    "id": "mobile",
    "tested": null,
    "type": "mobile",
    "wired": null,
    "wiringDisposition": null
  },
  {
    "capabilityCount": 0,
    "domain": "decision-governance",
    "id": "model-registry-adapter",
    "tested": true,
    "type": "worker_adapter",
    "wired": true,
    "wiringDisposition": "consumed"
  },
  {
    "capabilityCount": 0,
    "domain": "notifications",
    "id": "notification-agent",
    "tested": null,
    "type": "worker",
    "wired": null,
    "wiringDisposition": null
  },
  {
    "capabilityCount": 0,
    "domain": "knowledge",
    "id": "qdrant-seed",
    "tested": true,
    "type": "init_job",
    "wired": null,
    "wiringDisposition": "standalone-job"
  },
  {
    "capabilityCount": 2,
    "domain": "knowledge",
    "id": "rag-retrieval",
    "tested": true,
    "type": "service",
    "wired": true,
    "wiringDisposition": "consumed"
  },
  {
    "capabilityCount": 77,
    "domain": "remote-sensing-truth",
    "id": "raster-service",
    "tested": true,
    "type": "service",
    "wired": true,
    "wiringDisposition": "consumed"
  },
  {
    "capabilityCount": 1,
    "domain": "remote-sensing-truth",
    "id": "raster-tiler-service",
    "tested": false,
    "type": "service",
    "wired": true,
    "wiringDisposition": "consumed"
  },
  {
    "capabilityCount": 1,
    "domain": "remote-sensing-workspace",
    "id": "remote-sensing-workspace-bff",
    "tested": true,
    "type": "bff",
    "wired": true,
    "wiringDisposition": "consumed"
  },
  {
    "capabilityCount": 523,
    "domain": "platform-core",
    "id": "sahool-platform",
    "tested": true,
    "type": "service",
    "wired": true,
    "wiringDisposition": "consumed"
  },
  {
    "capabilityCount": 1,
    "domain": "fields-boundary",
    "id": "sam2-inference",
    "tested": false,
    "type": "service",
    "wired": true,
    "wiringDisposition": "consumed"
  },
  {
    "capabilityCount": 9,
    "domain": "ground-ingest",
    "id": "scout-ingest-service",
    "tested": true,
    "type": "service",
    "wired": true,
    "wiringDisposition": "consumed"
  },
  {
    "capabilityCount": 20,
    "domain": "soil",
    "id": "soil-service",
    "tested": true,
    "type": "service",
    "wired": true,
    "wiringDisposition": "consumed"
  },
  {
    "capabilityCount": 7,
    "domain": "agents",
    "id": "supervisor-agent",
    "tested": true,
    "type": "service",
    "wired": true,
    "wiringDisposition": "consumed"
  },
  {
    "capabilityCount": 0,
    "domain": "messaging-channel",
    "id": "telegram-bot",
    "tested": null,
    "type": "service",
    "wired": null,
    "wiringDisposition": null
  },
  {
    "capabilityCount": 4,
    "domain": "media",
    "id": "tts-service",
    "tested": true,
    "type": "service",
    "wired": true,
    "wiringDisposition": "consumed"
  },
  {
    "capabilityCount": 17,
    "domain": "vegetation-interpretation",
    "id": "vegetation-analysis-service",
    "tested": true,
    "type": "service",
    "wired": true,
    "wiringDisposition": "consumed"
  },
  {
    "capabilityCount": 4,
    "domain": "media",
    "id": "video-processor",
    "tested": true,
    "type": "service",
    "wired": true,
    "wiringDisposition": "consumed"
  },
  {
    "capabilityCount": 0,
    "domain": "weather-truth",
    "id": "weather-polygon-worker",
    "tested": false,
    "type": "worker",
    "wired": true,
    "wiringDisposition": "consumed"
  },
  {
    "capabilityCount": 22,
    "domain": "weather-truth",
    "id": "weather-service",
    "tested": true,
    "type": "service",
    "wired": true,
    "wiringDisposition": "consumed"
  },
  {
    "capabilityCount": 0,
    "domain": "weather-truth",
    "id": "weather-signal-engine",
    "tested": false,
    "type": "worker",
    "wired": true,
    "wiringDisposition": "consumed"
  }
];
