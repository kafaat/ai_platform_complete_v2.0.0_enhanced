// تهيئة ESLint المسطّحة (flat config) — الصيغة الوحيدة التي تقرؤها ESLint 9+.
//
// السياق الذي أوجب هذا الملفّ: كان `npm run lint` سكربتاً **زخرفيّاً** — لا `eslint`
// في التبعيّات، ولا ملفّ تهيئة في الشجرة كلّها، ولا وظيفة CI تستدعيه. سكربتٌ يبدو
// بوّابةً وليس بوّابة أسوأ من غيابه: قارئُ `package.json` يفترض أنّ الواجهة ملنوتة.
//
// النطاق مقصود ضيّق: قواعد **الأخطاء المنطقيّة** التي لا يلتقطها `tsc --noEmit`، لا
// قواعد الأسلوب. المشروع يملك بالفعل ٣ طبقات: `tsc` للأنواع، و١٩٦ ملفّ اختبار
// (منها حرّاس ساكنة تقرأ المصدر)، وPlaywright للسلوك الحيّ. اللِّنت يضيف ما تعجز
// هذه الثلاثة عنه: تبعيّات hooks الناقصة، ونداء hook مشروط، وanti-patterns.

import js from '@eslint/js';
import reactHooks from 'eslint-plugin-react-hooks';
import tseslint from 'typescript-eslint';

export default tseslint.config(
  {
    ignores: [
      'dist/**',
      'coverage/**',
      'node_modules/**',
      'playwright-report/**',
      'test-results/**',
      // مصنوعة مولَّدة: يحكمها مولّدها لا اللِّنت.
      'src/lib/platformCatalog.generated.ts',
    ],
  },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  {
    files: ['**/*.{ts,tsx}'],
    plugins: { 'react-hooks': reactHooks },
    rules: {
      // ── ما يُحجَب: أخطاء لا يراها المُصرِّف ──
      // تبعيّة hook ناقصة = إغلاق على قيمة بائتة. الصنف الذي يُنتِج «الشاشة لا
      // تتحدّث» بلا أيّ خطأ في وحدة التحكّم.
      'react-hooks/exhaustive-deps': 'error',
      'react-hooks/rules-of-hooks': 'error',
      // `catch {}` صامت يبتلع الفشل — نفس صنف `display:none` في المصغّرة.
      'no-empty': ['error', { allowEmptyCatch: false }],
      'no-fallthrough': 'error',
      'no-self-compare': 'error',
      'no-unsafe-optional-chaining': 'error',
      'require-atomic-updates': 'error',

      // ── ما لا يُحجَب اليوم: دَين موروث يُقلَّص ولا يُوسَّع ──
      // القاعدة الافتراضيّة تُطلِق على مئات المواضع القائمة. حجبها الآن يوقف كلّ
      // تغيير على دَين لم يُحدِثه — وهو ما يرفضه هذا المستودع صراحةً. تبقى تحذيراً
      // مرئيّاً حتّى تُقلَّص، ثمّ تُرفَع إلى error.
      '@typescript-eslint/no-explicit-any': 'warn',
      '@typescript-eslint/no-unused-vars': [
        'warn',
        { argsIgnorePattern: '^_', varsIgnorePattern: '^_', caughtErrors: 'none' },
      ],
      '@typescript-eslint/no-empty-object-type': 'warn',
    },
  },
  {
    // الاختبارات: الحرّاس الساكنة تقرأ المصدر نصّاً وتستعمل any عن قصد.
    files: ['**/*.test.{ts,tsx}', '**/*.spec.{ts,tsx}', 'e2e/**'],
    rules: {
      '@typescript-eslint/no-explicit-any': 'off',
    },
  },
);
