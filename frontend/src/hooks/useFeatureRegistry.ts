// Runtime feature registry hook — aligns frontend navigation with backend FEATURE_* flags.
// Fail-open while the registry is loading/unavailable so direct pages can still show
// their own degraded/feature-disabled states instead of breaking the shell.
import { useEffect, useMemo, useState } from 'react';
import type { PageId } from '../App';
import { advancedFeatureForPage } from '../lib/featureFlags';
import { getFeatureRegistry, type FeatureRegistryResponse } from '../services/api';

export interface RuntimeFeatureRegistryState {
  loaded: boolean;
  loading: boolean;
  unavailable: boolean;
  flags: Record<string, boolean>;
  pages: Record<string, boolean>;
}

const EMPTY: RuntimeFeatureRegistryState = {
  loaded: false,
  loading: false,
  unavailable: false,
  flags: {},
  pages: {},
};

let cached: RuntimeFeatureRegistryState | null = null;
let inFlight: Promise<RuntimeFeatureRegistryState> | null = null;

function normalize(data: FeatureRegistryResponse): RuntimeFeatureRegistryState {
  const flags: Record<string, boolean> = {};
  const pages: Record<string, boolean> = {};
  for (const item of data.features ?? []) {
    if (!item.backend_flag) continue;
    flags[item.backend_flag] = Boolean(item.enabled);
    if (item.page) pages[item.page] = Boolean(item.enabled);
  }
  return { loaded: true, loading: false, unavailable: false, flags, pages };
}

function loadRegistry(): Promise<RuntimeFeatureRegistryState> {
  if (cached) return Promise.resolve(cached);
  if (inFlight) return inFlight;
  inFlight = getFeatureRegistry()
    .then((data) => {
      cached = normalize(data);
      return cached;
    })
    .catch(() => {
      // Registry itself should not become a single point of failure for the UI shell.
      cached = { ...EMPTY, loaded: true, unavailable: true };
      return cached;
    })
    .finally(() => { inFlight = null; });
  return inFlight;
}

export function useFeatureRegistry(): RuntimeFeatureRegistryState {
  const [state, setState] = useState<RuntimeFeatureRegistryState>(cached ?? { ...EMPTY, loading: true });

  useEffect(() => {
    let mounted = true;
    loadRegistry().then((next) => { if (mounted) setState(next); });
    return () => { mounted = false; };
  }, []);

  return useMemo(() => state, [state]);
}

export function isRuntimePageEnabled(page: PageId, registry: RuntimeFeatureRegistryState): boolean {
  const feature = advancedFeatureForPage(page);
  if (!feature) return true;
  if (!feature.envEnabled) return false;
  // While loading/unavailable, fail open: page components still handle 404 with FeatureDisabledState.
  if (!registry.loaded || registry.unavailable) return true;
  const byBackend = registry.flags[feature.backendFlag];
  if (byBackend === false) return false;
  const byPage = registry.pages[page];
  if (byPage === false) return false;
  return true;
}
