import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

// العطل الذي وُجد هذا لأجله (2026-11-02): مُحدِّد «7 أيام/30 يوم/3 أشهر/سنة» في لوحة المؤشّرات
// كان يغيّر حالةً لا يقرؤها أحد — useDashboardKPIs() بلا معامل فترة، والخادم
// (GET /api/v1/indicators/dashboard) لا يقبل واحداً. زرّ مدّةٍ لا يغيّر النتيجة يكذب على المستخدم.
const page = readFileSync(join(process.cwd(), 'src/sections/HybridIndexPage.tsx'), 'utf8');
const hook = readFileSync(join(process.cwd(), 'src/hooks/useIndicators.ts'), 'utf8');

describe('HybridIndexPage has no inert period selector', () => {
  it('does not render a period select whose value nothing reads', () => {
    expect(page).not.toMatch(/setPeriod/);
    expect(page).not.toMatch(/<option value="(7d|30d|90d|1y)"/);
  });

  it('would need the KPI hook to accept a period before a selector can return', () => {
    // إن أُعيد المُحدِّد يوماً فيجب أن يصل إلى الاستعلام — هذا الاختبار يحمرّ ليذكّر بذلك.
    expect(hook).toMatch(/export function useDashboardKPIs\(\)/);
  });
});
