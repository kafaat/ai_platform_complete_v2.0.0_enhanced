// The chat header must not claim a live AI runtime it never checked.
// Before: a permanently pulsing green dot labelled "SAHOOL AI · RAG/KG/FieldState",
// shown even where the advisor is not deployed (production) or its RAG/KG are absent.
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { describe, expect, it } from 'vitest';

const src = readFileSync(
  join(dirname(fileURLToPath(import.meta.url)), 'ChatbotPage.tsx'),
  'utf8',
);

describe('ChatbotPage — advisor reach indicator', () => {
  it('probes the advisor liveness route instead of assuming it is up', () => {
    expect(src).toContain("kongApi.get('/api/ai-agronomist/healthz'");
  });

  it('has no unconditional pulsing green dot', () => {
    expect(src).not.toContain('<span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />');
  });

  it('says plainly when the advisor is unreachable', () => {
    expect(src).toContain('المستشار غير متاح في هذه البيئة');
    expect(src).toMatch(/advisorReach === 'up'\s*\?\s*'bg-emerald-400 animate-pulse'/);
  });

  it('does not claim RAG/KG grounding from a liveness probe', () => {
    // /healthz proves the process answers, not that RAG, the knowledge graph or field state
    // are ready; readiness is shown per answer (evidence ids + readiness warnings).
    expect(src).not.toContain('SAHOOL AI · أدلّة RAG/KG/حالة الحقل');
    expect(src).toContain('جاهزيّة الأدلّة تُعرَض مع كلّ إجابة');
  });

  it('explains why a chat request failed instead of one generic message', () => {
    expect(src).toContain('describeAdvisorFailure(err)');
    expect(src).not.toContain('تعذّر جلب أدلة المستشار الآن. تحقّق من الاتصال وتسجيل الدخول');
  });
});
