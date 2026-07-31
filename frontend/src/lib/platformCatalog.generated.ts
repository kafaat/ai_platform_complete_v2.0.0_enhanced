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

export const PLATFORM_CATALOG_FINGERPRINT = 'ae78c4e14dddde1157002e39b24fa806fac00b68bc8943c7b6bc8e1097d87f02';

export const PLATFORM_CATALOG_COUNTS = {
  "backend_components": 32,
  "capabilities": 820,
  "capabilities_approval_gated": 8,
  "capabilities_field_scoped": 93,
  "capabilities_idempotent": 46,
  "capabilities_season_scoped": 10,
  "capabilities_tenant_scoped": 477,
  "components": 34,
  "cross_service_duplicate_method_paths": 12,
  "duplicate_groups_classified": 12,
  "indicator_products": 34,
  "ownership_conflicts": 0,
  "route_rows": 1105,
  "ui_waivers": 52,
  "unique_method_path": 998
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
    "capabilityCount": 4,
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
    "capabilityCount": 22,
    "domain": "identity",
    "id": "auth",
    "tested": true,
    "type": "service",
    "wired": true,
    "wiringDisposition": "consumed"
  },
  {
    "capabilityCount": 60,
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
    "type": "batch-job-tool",
    "wired": null,
    "wiringDisposition": "standalone-job"
  },
  {
    "capabilityCount": 3,
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
    "type": "adapter",
    "wired": true,
    "wiringDisposition": "consumed"
  },
  {
    "capabilityCount": 0,
    "domain": "knowledge",
    "id": "qdrant-seed",
    "tested": true,
    "type": "job",
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
    "capabilityCount": 74,
    "domain": "remote-sensing-truth",
    "id": "raster-service",
    "tested": true,
    "type": "service",
    "wired": true,
    "wiringDisposition": "consumed"
  },
  {
    "capabilityCount": 0,
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
    "capabilityCount": 522,
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
    "capabilityCount": 6,
    "domain": "agents",
    "id": "supervisor-agent",
    "tested": true,
    "type": "service",
    "wired": true,
    "wiringDisposition": "consumed"
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
