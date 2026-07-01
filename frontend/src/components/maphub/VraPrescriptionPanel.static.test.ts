import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const source = readFileSync(
  join(dirname(fileURLToPath(import.meta.url)), 'VraPrescriptionPanel.tsx'),
  'utf8',
);

describe('VraPrescriptionPanel — V62 VRA UI', () => {
  it('renders proposal-only VRA state and guarded export action', () => {
    expect(source).toContain('data-testid="vra-prescription-panel"');
    expect(source).toContain('data-testid="vra-rate"');
    expect(source).toContain('data-testid="vra-export-disabled"');
    expect(source).toContain('لا تُحفظ ولا تُصدّر للآلة إلا بعد الموافقة');
  });
});
