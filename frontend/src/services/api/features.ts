// ═══════════════════════════════════════════════════════════════
// SAHOOL UI-3B — Runtime Feature Registry API module
// Central source for backend feature flags used by navigation/route guards.
// ═══════════════════════════════════════════════════════════════

import { kongApi } from './client';

// ══════════════════════════════════════════════════════════════════
// FEATURE REGISTRY — backend/runtime feature flags for navigation alignment
// ══════════════════════════════════════════════════════════════════
export interface FeatureRegistryItem {
  backend_flag: string;
  enabled: boolean;
  description?: string;
  page?: string | null;
  frontend_flag?: string | null;
  source?: string;
}

export interface FeatureRegistryResponse {
  features: FeatureRegistryItem[];
  truthy?: string[];
  default?: string;
}

export const getFeatureRegistry = (): Promise<FeatureRegistryResponse> =>
  kongApi.get<FeatureRegistryResponse>('/api/v1/features').then(r => r.data);
