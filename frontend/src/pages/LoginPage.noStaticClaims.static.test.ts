import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

// ═══════════════════════════════════════════════════════════════════════════
// RW-05 (مراجعة Railway 2026-09-20) — «ادّعاءٌ ثابتٌ في الواجهة».
// صفحةُ الدخول كانت تعرض `SAHOOL v8.0 · 47/47 اختبار ✅` نصّاً ثابتاً في المصدر: لا يرتبط
// بأيّ تشغيل CI ولا بهويّة النشر، ويُقرأ دليلَ جاهزيّةٍ وهو ليس كذلك. الحارسُ الثابت
// يفحص نصَّ JSX المُصدَّر بعد إسقاط التعليقات (التعليقُ الذي يوثّق الإزالة يذكر النصَّ
// القديم عمداً، فلا يجوز أن يُحمِّر الشاهدَ ولا أن يُخضِّره).
// ═══════════════════════════════════════════════════════════════════════════
const root = process.cwd();
const login = readFileSync(join(root, 'src/pages/LoginPage.tsx'), 'utf8');
const rendered = login
  .replace(/\{\/\*[\s\S]*?\*\/\}/g, '')
  .replace(/\/\*[\s\S]*?\*\//g, '')
  .replace(/^\s*\/\/.*$/gm, '');

describe('RW-05 — the login page renders no static test-count claim', () => {
  it('no "N/N اختبار" text is rendered', () => {
    expect(rendered).not.toMatch(/\d+\s*\/\s*\d+\s*اختبار/);
  });

  it('no check-mark badge stands in for evidence', () => {
    expect(rendered).not.toContain('✅');
  });

  it('the removal is documented next to where the claim stood (not silently dropped)', () => {
    expect(login).toContain('RW-05');
  });
});
