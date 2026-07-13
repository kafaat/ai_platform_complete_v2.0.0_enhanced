import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

const root = process.cwd();
const api = readFileSync(join(root, 'src/services/api.ts'), 'utf8');
const hooks = readFileSync(join(root, 'src/hooks/useApi.ts'), 'utf8');
const card = readFileSync(join(root, 'src/components/fieldview/SoilGovernanceCard.tsx'), 'utf8');
const mapHub = readFileSync(join(root, 'src/sections/MapHub.tsx'), 'utf8');

// Regression guard: the P4 soil closed-loop governance must stay wired end-to-end
// from the canonical soil-service endpoints through the /api/soil proxy into FieldView.
describe('SoilGovernanceCard wiring', () => {
  it('api.ts calls the canonical soil-service governance endpoints via the soil proxy', () => {
    expect(api).toContain('fetchSoilProfileSnapshot');
    expect(api).toContain('fetchSoilClosedLoop');
    expect(api).toContain('/v1/fields/${fieldId}/soil/profile');
    expect(api).toContain('/v1/fields/${fieldId}/soil/closed-loop');
    // Must hit the deployed soil-service via the platform proxy client, not the raster host.
    expect(card).not.toContain('rasterApi');
  });

  it('useSoilWorkspace combines profile + closed-loop into the summary', () => {
    expect(hooks).toContain('export function useSoilWorkspace');
    expect(hooks).toContain('buildSoilWorkspaceSummary');
  });

  it('SoilGovernanceCard is mounted in FieldView (MapHub) under expert mode', () => {
    expect(mapHub).toContain("import SoilGovernanceCard from '../components/fieldview/SoilGovernanceCard'");
    expect(mapHub).toContain('<SoilGovernanceCard');
    expect(card).toContain('data-testid="soil-governance"');
    // Honest empty state — never fabricates a profile when none exists.
    expect(card).toContain('لا لقطة تربة كنسيّة');
  });
});
