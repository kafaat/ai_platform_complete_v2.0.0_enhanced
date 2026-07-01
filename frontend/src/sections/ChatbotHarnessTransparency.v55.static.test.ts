// حارس ساكن (V55 المرحلة ٥): تُظهر واجهة الشات شفافيّة الوكيل — ماذا يرى، قدراته،
// الأدوات المستخدمة، والموافقات المعلَّقة — من حقل ``harness`` في ردّ الـruntime.
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

const here = dirname(fileURLToPath(import.meta.url));
const chatbot = readFileSync(join(here, 'ChatbotPage.tsx'), 'utf8');

describe('ChatbotPage: شفافيّة الوكيل V55', () => {
  it('يعرّف عقد الشفافيّة ويقرأه من ردّ الـruntime', () => {
    expect(chatbot).toContain('interface HarnessTransparency');
    expect(chatbot).toContain('harness?: HarnessTransparency');
    expect(chatbot).toContain('harness: data.harness || undefined');
  });

  it('يعرض لوحة الشفافيّة (رؤية/قدرات/أدوات/موافقات)', () => {
    expect(chatbot).toContain('data-testid="ai-harness-transparency"');
    expect(chatbot).toContain('رؤية منقوصة');
    expect(chatbot).toContain('data-testid="ai-harness-tools"');
    expect(chatbot).toContain('data-testid="ai-harness-approvals"');
    expect(chatbot).toContain('بانتظار موافقة');
  });
});
