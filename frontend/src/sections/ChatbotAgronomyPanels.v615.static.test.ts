import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const source = readFileSync(join(dirname(fileURLToPath(import.meta.url)), 'ChatbotPage.tsx'), 'utf8');

describe('ChatbotPage — V61.5 agronomy tool proposal panels', () => {
  it('wires field boundary, productivity zone, and soil sampling panels into harness results', () => {
    expect(source).toContain("import { FieldBoundaryProposalPanel }");
    expect(source).toContain("import { ProductivityZonesPanel }");
    expect(source).toContain("import { SoilSamplingPlannerPanel }");
    expect(source).toContain("toolDataFor(msg.harness, 'detect_field_boundaries')");
    expect(source).toContain("toolDataFor(msg.harness, 'generate_productivity_zones')");
    expect(source).toContain("toolDataFor(msg.harness, 'plan_soil_sampling')");
  });
});
