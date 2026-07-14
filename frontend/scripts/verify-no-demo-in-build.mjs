#!/usr/bin/env node
// ═══════════════════════════════════════════════════════════════════════════
// FE-08 (forensic P0) — إثبات أثر البناء: مسار الدخول التجريبيّ غائب عن حزمة الإنتاج.
//
// الحارس الثابت (DemoExcludedInProd.static.test.ts) يثبت أنّ المصدر يُبنى دفاعاً
// بطبقتين: زرّ LoginPage خلف `!import.meta.env.PROD` (يُقصّه Vite)، وloginDemo
// يرمي (throw) قبل أيّ سطر تجريبيّ حين `import.meta.env.PROD`. لكنّه لا يفحص
// الخَرج المُصدَّر فعليّاً. هذا السكربت يسدّ الفجوة: يبني الإنتاج (أو يستهلك dist
// قائمة) ثمّ يفتّش كلّ ملفّ `assets/*.js` عن بصمات (sentinels) تجريبيّة لا تظهر
// إلّا لو شُحن مسار الدخول التجريبيّ. أيّ ظهور ⇒ خروج غير صفريّ (فشل).
//
// الاستعمال:
//   node scripts/verify-no-demo-in-build.mjs           # يبني ثمّ يفحص
//   node scripts/verify-no-demo-in-build.mjs --no-build # يفحص dist قائمة فقط
// ═══════════════════════════════════════════════════════════════════════════
import { spawnSync } from 'node:child_process';
import { readdirSync, readFileSync, existsSync, statSync } from 'node:fs';
import { join, dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const frontendRoot = resolve(__dirname, '..');
const distDir = join(frontendRoot, 'dist');
const assetsDir = join(distDir, 'assets');

// ── البصمات التجريبيّة (sentinels) ─────────────────────────────────────────
// نختار سلاسل نصّيّة *حصريّة* لمسار الدخول التجريبيّ — أي تعيش بعد حارس الرمي في
// loginDemo أو داخل فرع الزرّ المقصوص. لا نستعمل `demo_token_not_real` لأنّه يُشحن
// شرعيّاً في الإنتاج عبر jwt.ts (DEMO_TOKENS ⇒ isDemoToken)، ولا المعرّفات
// `loginDemo`/`isDemoMode` لأنّها مفاتيح/حقول في متجر zustand تبقى في الإنتاج.
const SENTINELS = [
  'demo_tenant',                    // useAuth.ts: tenantId التجريبيّ (بعد الحارس)
  'demo@sahool.ye',                 // useAuth.ts: بريد المستخدم التجريبيّ (بعد الحارس)
  'مستخدم تجريبي',                  // useAuth.ts: الاسم الكامل التجريبيّ (بعد الحارس)
  'دخول تجريبي (بيانات افتراضية)',  // LoginPage.tsx: نصّ الزرّ داخل فرع !PROD المقصوص
];

function log(msg) { process.stdout.write(msg + '\n'); }

function buildProd() {
  log('▶ vite build (production, import.meta.env.PROD=true) …');
  // `vite build` ⇒ mode=production ⇒ import.meta.env.PROD=true (قصّ الفروع + DCE).
  const res = spawnSync(
    process.execPath,
    [join(frontendRoot, 'node_modules', 'vite', 'bin', 'vite.js'), 'build'],
    { cwd: frontendRoot, stdio: 'inherit', env: { ...process.env, NODE_ENV: 'production' } },
  );
  if (res.status !== 0) {
    log('✗ فشل البناء (vite build) — لا يمكن إثبات نظافة الحزمة.');
    process.exit(res.status ?? 1);
  }
}

// كلّ ملفّات .js المُصدَّرة تحت dist/assets (تحزيم مسطّح: لا أدلّة فرعيّة عادةً،
// لكن نمشي متعدّي الأدلّة احتياطاً لأيّ chunks/workers متداخلة).
function collectJsFiles(dir) {
  const out = [];
  for (const name of readdirSync(dir)) {
    const p = join(dir, name);
    if (statSync(p).isDirectory()) out.push(...collectJsFiles(p));
    else if (name.endsWith('.js') || name.endsWith('.mjs')) out.push(p);
  }
  return out;
}

function main() {
  const doBuild = !process.argv.includes('--no-build');
  if (doBuild) buildProd();

  if (!existsSync(assetsDir)) {
    log(`✗ لا يوجد dist/assets — شغّل البناء أوّلاً (${assetsDir}).`);
    process.exit(1);
  }

  const jsFiles = collectJsFiles(assetsDir);
  if (jsFiles.length === 0) {
    log('✗ لا ملفّات JS مُصدَّرة تحت dist/assets — بناء مشبوه.');
    process.exit(1);
  }

  log(`\n▶ فحص ${jsFiles.length} ملفّ JS مُصدَّر عن ${SENTINELS.length} بصمات تجريبيّة …`);

  const leaks = [];
  for (const file of jsFiles) {
    const content = readFileSync(file, 'utf8');
    for (const sentinel of SENTINELS) {
      if (content.includes(sentinel)) {
        leaks.push({ file: file.slice(frontendRoot.length + 1), sentinel });
      }
    }
  }

  if (leaks.length > 0) {
    log('\n✗ فشل FE-08: مسار الدخول التجريبيّ تسرّب إلى حزمة الإنتاج!');
    for (const { file, sentinel } of leaks) {
      log(`    ✗ «${sentinel}» موجودة في ${file}`);
    }
    log('\nأصلِح تغليف مسار الدخول التجريبيّ كي يُقصّ (tree-shake) ثمّ أعِد الفحص.');
    process.exit(1);
  }

  log('\n✓ نجاح FE-08: لا بصمة تجريبيّة في أيّ ملفّ assets/*.js في حزمة الإنتاج.');
  log('    البصمات المفحوصة (كلّها غائبة):');
  for (const s of SENTINELS) log(`      • ${s}`);
  process.exit(0);
}

main();
