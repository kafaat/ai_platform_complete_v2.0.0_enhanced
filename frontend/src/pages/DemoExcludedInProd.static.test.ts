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

// ═══════════════════════════════════════════════════════════════════════════
// FE-08 — إثبات أثر البناء مقفول في المستودع.
// vitest لا يشغّل بناءً كاملاً، فلا يمكنه فحص الحزمة المُصدَّرة هنا. لكنّ الإثبات
// الحقيقيّ (بناء الإنتاج + تفتيش assets/*.js عن البصمات التجريبيّة) يعيش في
// scripts/verify-no-demo-in-build.mjs ويُشغَّل عبر npm run verify:no-demo. هذا
// الفحص يضمن بقاء ذينك المصدرين موجودَين (منع انحدار صامت لدليل الأثر).
// ═══════════════════════════════════════════════════════════════════════════
describe('FE-08 — build-artifact proof is locked into the repo', () => {
  const verifyScript = read('scripts/verify-no-demo-in-build.mjs');

  it('the verify-no-demo build-artifact script exists and greps emitted JS', () => {
    // يبني الإنتاج (أو يستهلك dist) ثمّ يفتّش كلّ assets/*.js.
    expect(verifyScript).toContain('assets');
    expect(verifyScript).toMatch(/vite/i);
    expect(verifyScript).toContain('process.exit(1)');
  });

  it('the script checks the demo sentinels unique to the demo-login path', () => {
    // بصمات حصريّة لمسار الدخول التجريبيّ (لا demo_token_not_real ولا loginDemo،
    // فهما يُشحنان شرعيّاً في الإنتاج عبر jwt.ts / مفاتيح متجر zustand).
    expect(verifyScript).toContain('demo_tenant');
    expect(verifyScript).toContain('demo@sahool.ye');
    expect(verifyScript).toContain('مستخدم تجريبي');
    expect(verifyScript).toContain('دخول تجريبي (بيانات افتراضية)');
  });

  it('package.json wires the verify:no-demo npm script', () => {
    const pkg = JSON.parse(read('package.json'));
    expect(pkg.scripts['verify:no-demo']).toBe('node scripts/verify-no-demo-in-build.mjs');
  });
});
