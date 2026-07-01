import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { describe, expect, it } from 'vitest';

const src = readFileSync(
  join(dirname(fileURLToPath(import.meta.url)), 'FieldBoundaryProposalPanel.tsx'),
  'utf8',
);

describe('FieldBoundaryProposalPanel — V59 boundary confirmation UI', () => {
  it('renders proposal cards with confidence and area without persistence by default', () => {
    expect(src).toContain('field-boundary-proposal-panel');
    expect(src).toContain('field-boundary-proposal-card');
    expect(src).toContain('لا تُحفَظ إلا بعد التأكيد');
    expect(src).toContain('confidence');
    expect(src).toContain('area_ha');
  });

  it('exposes accept/edit/reject actions for human confirmation', () => {
    expect(src).toContain('field-boundary-accept');
    expect(src).toContain('field-boundary-edit');
    expect(src).toContain('field-boundary-reject');
  });
});
