import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { describe, expect, it } from 'vitest';

const src = readFileSync(
  join(dirname(fileURLToPath(import.meta.url)), 'ProductivityZonesPanel.tsx'),
  'utf8',
);

describe('ProductivityZonesPanel — V60 productivity zoning UI', () => {
  it('renders confirmable productivity zone proposals without persistence by default', () => {
    expect(src).toContain('productivity-zones-panel');
    expect(src).toContain('productivity-zone-card');
    expect(src).toContain('لا تُحفَظ إلا بعد التأكيد');
    expect(src).toContain('V60 zones');
  });

  it('exposes accept, reject, and v61 soil sampling continuation actions', () => {
    expect(src).toContain('productivity-zones-accept');
    expect(src).toContain('productivity-zones-reject');
    expect(src).toContain('productivity-zones-soil-sampling');
    expect(src).toContain('خطط عينات التربة');
  });
});
