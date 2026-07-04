import { describe, expect, it } from 'vitest';
import { existsSync, readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { ALL_ROUTES } from '../lib/routes';
import {
  BACKEND_COVERAGE_REGISTRY,
  coverageSummary,
  criticalCoverageGaps,
  endpointCoverageMap,
  layerForEndpoint,
} from './backendCoverageRegistry';

const routeIds = new Set(ALL_ROUTES.map((route) => route.id));
const srcRoot = resolve(__dirname, '..');
const useApiSource = readFileSync(resolve(srcRoot, 'hooks/useApi.ts'), 'utf8');

function componentExists(name: string): boolean {
  const candidates = [
    resolve(srcRoot, `sections/${name}.tsx`),
    resolve(srcRoot, `components/fieldview/${name}.tsx`),
    resolve(srcRoot, `components/maphub/${name}.tsx`),
    resolve(srcRoot, `components/sharing/${name}.tsx`),
  ];
  return candidates.some((candidate) => existsSync(candidate));
}

describe('backend-to-frontend coverage registry', () => {
  it('classifies every registered backend layer with explicit state, role, endpoints and owner', () => {
    const ids = new Set<string>();
    for (const layer of BACKEND_COVERAGE_REGISTRY) {
      expect(ids.has(layer.id), `${layer.id} is duplicated`).toBe(false);
      ids.add(layer.id);
      expect(layer.label).toBeTruthy();
      expect(layer.endpoints.length, `${layer.id} needs endpoint patterns`).toBeGreaterThan(0);
      expect(layer.owner).toBeTruthy();
      for (const endpoint of layer.endpoints) {
        expect(endpoint.startsWith('/api/v1/') || endpoint.startsWith('/api/'), `${layer.id}: ${endpoint}`).toBe(true);
      }
    }
  });

  it('does not allow P0/P1 layers to be silently partial or not-ready', () => {
    const gaps = criticalCoverageGaps();
    expect(gaps.map((gap) => `${gap.priority}:${gap.id}:${gap.state}`)).toEqual([
      'P1:crop-planning-rotation-planting:partial',
    ]);
    expect(gaps[0]?.nextAction).toMatch(/objective/i);
  });

  it('requires exposed layers to have hooks and real UI surfaces or an explicit waiver', () => {
    for (const layer of BACKEND_COVERAGE_REGISTRY) {
      if (layer.state === 'waived_internal') {
        expect(layer.role).toBe('internal_only');
        expect(layer.waiverReason, `${layer.id} needs an internal waiver reason`).toBeTruthy();
        continue;
      }
      if (layer.state === 'not_ready') {
        expect(layer.nextAction, `${layer.id} needs next action`).toBeTruthy();
        continue;
      }
      expect(layer.hooks.length, `${layer.id} needs frontend hooks`).toBeGreaterThan(0);
      expect(layer.surfaces.length, `${layer.id} needs page/card/panel surface`).toBeGreaterThan(0);
    }
  });

  it('keeps route-backed surfaces synchronized with the route registry', () => {
    for (const layer of BACKEND_COVERAGE_REGISTRY) {
      for (const surface of layer.surfaces) {
        if (surface.routeId) expect(routeIds.has(surface.routeId), `${layer.id}:${surface.routeId}`).toBe(true);
      }
    }
  });

  it('keeps hook and component references grounded in the source tree', () => {
    const knownExternalHookNames = new Set(['useGisTools', 'useNlGis', 'useScenarioCompare', 'useReplaySeason', 'useInvitations', 'useCreateShareLink', 'useScoutingTaxonomy', 'useScoutingPins']);
    for (const layer of BACKEND_COVERAGE_REGISTRY) {
      for (const hook of layer.hooks) {
        if (knownExternalHookNames.has(hook)) continue;
        expect(useApiSource.includes(`function ${hook}`) || useApiSource.includes(`const ${hook}`), `${layer.id}:${hook}`).toBe(true);
      }
      for (const surface of layer.surfaces) {
        if (surface.kind === 'waiver') continue;
        if (surface.component) expect(componentExists(surface.component), `${layer.id}:${surface.component}`).toBe(true);
      }
    }
  });

  it('summarizes covered, partial, internal and not-ready layers deterministically', () => {
    expect(coverageSummary()).toEqual({ covered: 11, partial: 5, waived_internal: 1, not_ready: 1 });
  });

  it('maps endpoint patterns back to their owning layer', () => {
    expect(endpointCoverageMap().get('/api/v1/admin/readiness')?.id).toBe('admin-runtime-ops');
    expect(layerForEndpoint('/api/v1/fields/abc/boundary/score')?.id).toBe('boundary-governance');
    expect(layerForEndpoint('/api/v1/marketplace/extensions')?.id).toBe('marketplace-plugins-ecosystem');
  });
});
