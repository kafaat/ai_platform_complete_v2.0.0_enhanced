import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

// ═══════════════════════════════════════════════════════════════════════════
// FE-07 (forensic P0) — «Tenant fallback removed».
// حارس ثابت: يمنع انحدار useTenantId إلى الاحتياط الصامت 'default'. حين لا يوجد
// مستأجِر مُصادَق يجب أن يُعيد الخُطّاف null (fail-closed) لا سلسلة مستأجِرٍ وهميّة،
// ويجب أن يعامل المستهلكون null كـ«غير جاهز / يجب المصادقة» بدل القراءة/الكتابة على
// مستأجِر 'default'. أبقِ هذا أخضر عند لمس أيّ مسار هويّة مستأجِر.
// ═══════════════════════════════════════════════════════════════════════════
const root = process.cwd();
const read = (p: string) => readFileSync(join(root, p), 'utf8');

const auth = read('src/hooks/useAuth.ts');
const agronomy = read('src/components/fieldview/AgronomyConsistencyCard.tsx');
const learning = read('src/components/fieldview/LearningEvidenceCard.tsx');

// كتلة تعريف useTenantId (من التصدير حتى نهاية العبارة).
const tenantHookBlock = auth.slice(
  auth.indexOf('export const useTenantId'),
  auth.indexOf('export const useCurrentUser'),
);

describe('FE-07 — useTenantId fails closed (no silent \'default\' fallback)', () => {
  it('useTenantId does NOT fabricate a \'default\' tenant', () => {
    expect(tenantHookBlock).not.toMatch(/\|\|\s*['"]default['"]/);
    expect(tenantHookBlock).not.toContain("'default'");
    expect(tenantHookBlock).not.toContain('"default"');
  });

  it('useTenantId is typed nullable and returns the raw store value', () => {
    expect(tenantHookBlock).toContain('useTenantId = (): string | null');
    expect(tenantHookBlock).toContain('useAuthStore(s => s.tenantId)');
  });

  it('no silent \'?? default\' / \'|| default\' tenant fabrication survives in useAuth.ts', () => {
    // احتياط 'default' على مستأجِر ممنوع كليّاً في مصدر المصادقة.
    expect(auth).not.toMatch(/tenantId\s*(\|\||\?\?)\s*['"]default['"]/);
  });
});

describe('FE-07 — consumers treat a missing tenant as not-ready (fail-closed writes)', () => {
  it('AgronomyConsistencyCard gates the operation report on a present tenant', () => {
    // بوّابة الجاهزيّة تتطلّب tenantId، وحارس الإرسال يرفض غيابه — لا تقرير بمستأجِرٍ وهميّ.
    expect(agronomy).toContain('!!tenantId &&');
    expect(agronomy).toMatch(/if\s*\(!reportReady[^)]*!tenantId\)\s*return;/);
  });

  it('LearningEvidenceCard degrades a null tenant to empty (rejected by observationReady)', () => {
    // tenant_id فارغ ⇒ observationReady تُرجِع false ⇒ لا كتابة (fail-closed) بلا مستأجِر.
    expect(learning).toContain("tenant_id: tenantId ?? ''");
  });
});
