// Static guard — IrrigationEngineeringWorkspace is wired to a real page + endpoint.
// The workspace was orphaned (built, never mounted). This locks the wiring:
//   page -> IrrigationEngineeringWorkspace + calculateIrrigationEngineering
//   service -> POST /api/v1/irrigation/engineering/calculate (real EngineeringResult)
//   App.tsx -> lazy import + switch case; routes.ts -> nav entry.
// No fabricated data: the summary comes from the server-side calculation.
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';
import { describe, it, expect } from 'vitest';

const here = dirname(fileURLToPath(import.meta.url));
const read = (p: string) => readFileSync(resolve(here, p), 'utf8');

describe('IrrigationEngineering wiring', () => {
  const page = read('./IrrigationEngineeringPage.tsx');
  const service = read('../services/api/irrigationEngineeringCalculator.ts');
  const app = read('../App.tsx');
  const routes = read('../lib/routes.ts');

  it('page renders the workspace with a real summary source', () => {
    expect(page).toContain("from './IrrigationEngineeringWorkspace'");
    expect(page).toContain('calculateIrrigationEngineering');
    expect(page).toContain('<IrrigationEngineeringWorkspace');
    expect(page).toContain('summary={summary}');
  });

  it('service calls the real engineering/calculate endpoint', () => {
    expect(service).toContain('/api/v1/irrigation/engineering/calculate');
    expect(service).toContain('calculateIrrigationEngineering');
  });

  it('App mounts the page via lazy import + switch case', () => {
    expect(app).toContain("import('./sections/IrrigationEngineeringPage')");
    expect(app).toContain("case 'irrigation-engineering': return <IrrigationEngineeringPage");
    expect(app).toContain("'irrigation-engineering'"); // PageId union member
  });

  it('routes register a nav entry with a resolvable path', () => {
    expect(routes).toContain("id: 'irrigation-engineering'");
    expect(routes).toContain("path: '/irrigation/engineering'");
  });
});
