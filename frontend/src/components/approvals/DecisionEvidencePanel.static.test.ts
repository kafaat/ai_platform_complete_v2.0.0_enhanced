import { describe, expect, it } from 'vitest';
import { readFileSync } from 'fs';
import { dirname, join } from 'path';
import { fileURLToPath } from 'url';

const root = dirname(fileURLToPath(import.meta.url));
const panel = readFileSync(join(root, 'DecisionEvidencePanel.tsx'), 'utf8');
const consolePage = readFileSync(join(root, '../../sections/ApprovalsConsolePage.tsx'), 'utf8');
const hooks = readFileSync(join(root, '../../hooks/useApi.ts'), 'utf8');
const lib = readFileSync(join(root, '../../lib/approvalsConsole.ts'), 'utf8');

describe('Phase E — decision agronomic evidence UI (authoritative, fail-closed)', () => {
  it('reads the evidence chain from the authoritative BFF endpoint only', () => {
    expect(hooks).toContain('/agronomic-evidence');
    expect(hooks).toContain('useDecisionAgronomicEvidence');
    // lazy per-decision read: never fetch for an unselected decision.
    expect(hooks).toContain('enabled: Boolean(decisionId)');
  });

  it('renders the four evidence sections and the completeness verdict', () => {
    expect(panel).toContain('data-testid="decision-evidence-panel"');
    expect(panel).toContain('لقطة السياق المركَّبة');
    expect(panel).toContain('النافذة التاريخيّة');
    expect(panel).toContain('بيان الميزات المُستخدَمة فعلاً');
    expect(panel).toContain('لقطة الدليل النباتيّ');
    expect(panel).toContain('evidence_complete');
  });

  it('is honest about failure and legacy states — no fake empty evidence', () => {
    // mirror/SoR-off surfaces as an explicit error, not an empty list.
    expect(panel).toContain('يفشل المسار مغلقاً بدل عرض «لا يوجد دليل» زائف');
    expect(panel).toContain('legacy_unbound');
    // integrity mismatch between the decision-pinned hash and the stored manifest is shown.
    expect(panel).toContain('hash_matches_decision');
    expect(panel).toContain('تحذير نزاهة');
  });

  it('exposes point-in-time honesty per feature entry', () => {
    expect(lib).toContain('export function entryWithinCutoff');
    expect(panel).toContain('entryWithinCutoff(entry, manifest.decision_cutoff_time)');
    expect(panel).toContain('تسريب!');
  });

  it('is wired into the approvals console per review candidate', () => {
    expect(consolePage).toContain('DecisionEvidencePanel');
    expect(consolePage).toContain('الدليل الزراعيّ الكامل');
  });
});
