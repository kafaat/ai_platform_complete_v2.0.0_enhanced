import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { describe, expect, it } from 'vitest';

const src = readFileSync(
  join(dirname(fileURLToPath(import.meta.url)), 'SoilSamplingPlannerPanel.tsx'),
  'utf8',
);

describe('SoilSamplingPlannerPanel — V61 soil sampling UI', () => {
  it('renders confirmable soil sample plans without persistence by default', () => {
    expect(src).toContain('soil-sampling-planner-panel');
    expect(src).toContain('soil-sample-point-card');
    expect(src).toContain('لا تُحفَظ ولا تتحول إلى مهام إلا بعد التأكيد');
    expect(src).toContain('V61 sampling');
  });

  it('exposes accept, reject, and v62 VRA continuation actions', () => {
    expect(src).toContain('soil-sampling-accept');
    expect(src).toContain('soil-sampling-reject');
    expect(src).toContain('soil-sampling-vra-next');
    expect(src).toContain('إلى وصفات VRA');
  });
});
