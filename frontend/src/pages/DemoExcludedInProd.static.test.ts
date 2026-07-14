import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

// ═══════════════════════════════════════════════════════════════════════════
// FE-08 (forensic P0) — «Demo excluded from production».
// حارس ثابت: يضمن أنّ مسار الدخول التجريبيّ (loginDemo) غير قابل للوصول في بناء
// الإنتاج. دفاع بطبقتين: (1) زرّ الدخول التجريبيّ في LoginPage مغلَّف بـ
// !import.meta.env.PROD فيُقصّه Vite (tree-shake) من حزمة الإنتاج؛ (2) الدالة
// loginDemo نفسها تفشل بصلابة (throw) إن استُدعيت في الإنتاج — فلا يوجد مدخل
// تجريبيّ حتى لو نُودي برمجيّاً. يبقى الوضع التجريبيّ متاحاً في التطوير.
// ═══════════════════════════════════════════════════════════════════════════
const root = process.cwd();
const read = (p: string) => readFileSync(join(root, p), 'utf8');

const login = read('src/pages/LoginPage.tsx');
const auth = read('src/hooks/useAuth.ts');

// كتلة تنفيذ loginDemo (من مفتاح التنفيذ حتى تنفيذ logout) — لا تعريف الواجهة.
const demoBlock = auth.slice(
  auth.indexOf('loginDemo: () => {'),
  auth.indexOf('logout: () => {'),
);

describe('FE-08 — demo entry is compiled out of production (LoginPage)', () => {
  it('the demo login button is wrapped in a !import.meta.env.PROD branch', () => {
    // فرع يُقيَّم ثابتاً بواسطة Vite ⇒ يُحذف بالكامل من بناء الإنتاج.
    expect(login).toContain('!import.meta.env.PROD');
    // والزرّ التجريبيّ يستدعي loginDemo داخل ذلك الفرع.
    expect(login).toContain('onClick={loginDemo}');
    const guardIdx = login.indexOf('!import.meta.env.PROD');
    const demoBtnIdx = login.indexOf('onClick={loginDemo}');
    expect(guardIdx).toBeGreaterThanOrEqual(0);
    expect(demoBtnIdx).toBeGreaterThan(guardIdx);
  });
});

describe('FE-08 — demo login hard-disabled at runtime in production (useAuth)', () => {
  it('loginDemo throws when import.meta.env.PROD is true', () => {
    expect(demoBlock).toContain('import.meta.env.PROD');
    expect(demoBlock).toMatch(/if\s*\(import\.meta\.env\.PROD\)\s*\{[\s\S]*throw/);
  });

  it('the fabricated demo token/tenant sit AFTER the production guard', () => {
    const guardIdx = demoBlock.indexOf('import.meta.env.PROD');
    const demoTokenIdx = demoBlock.indexOf("'demo_token_not_real'");
    expect(guardIdx).toBeGreaterThanOrEqual(0);
    expect(demoTokenIdx).toBeGreaterThan(guardIdx);
  });
});
