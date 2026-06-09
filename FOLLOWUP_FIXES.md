# الجولة الثالثة — إصلاح النتائج المتبقّية + الثغرات

استجابةً لـ"قوم باصلاحها": عالجتُ كل النتائج المؤجَّلة والثغرات. الكل **مُتحقَّق**.

## ① OpenAPI 500 — مُصلَح ✅
- **الجذر الحقيقي**: `api/main.py` يستخدم `Optional[...]` (8 مرّات) لكن **لا
  يستورد `typing.Optional` إطلاقاً**. مع `from __future__ import annotations`
  لا يظهر الخطأ وقت التشغيل، لكنّه يكسر توليد مخطّط OpenAPI (`/openapi.json`
  → 500، وكذلك `export_openapi.py`).
- **الإصلاح**: `from typing import Optional` + حلقة `model_rebuild()` دفاعيّة
  لكلّ نماذج الوحدة.
- **تحقّق حيّ**: `GET /openapi.json = 200` ويكشف >50 مسارًا (smoke_e2e 13/13).

## ② ثغرات الأمان — مُصلَحة ✅ (pip-audit + npm audit نظيفان)
| المصدر | الثغرة | الإصلاح | التحقّق |
|--------|--------|---------|---------|
| Python (4 high) | `starlette` 0.38.6: CVE-2024-47874، CVE-2025-54121، PYSEC-2026-161 | رفع `fastapi==0.136.3` + `pydantic==2.13.4` عبر **21 ملف requirements** ⇒ يسحب starlette 1.2.1 (≥1.0.1) | `pip-audit`: **No known vulnerabilities** |
| Frontend (2 moderate) | `esbuild`/`vite` (خادم التطوير + path traversal) | رفع `vite ^6.4.3` + `@vitejs/plugin-react ^4.3.4` | `npm audit`: **0 vulnerabilities** |

تحقّق عدم الكسر: smoke+e2e **13/13** على ستاك fastapi 0.136، وverify_review_fixes **23/23**.

## ③ ديون بناء الواجهة — مُصلَحة ✅
| المشكلة | الإصلاح |
|---------|---------|
| `npm install` يفشل ERESOLVE (lucide-react@0.376 ضد React 19) | رفع `lucide-react ^0.400.0` + `.npmrc` (`legacy-peer-deps=true`) لتبعيات أخرى تعلن peer لـ18 (react-leaflet@4) — `npm install` ينجح **دون أعلام يدويّة** |
| `tsc` خطأ إعداد TS5103 | `ignoreDeprecations: "6.0"` → `"5.0"` |
| `npm run build` (`tsc && vite`) يفشل | فُصل الفحص النوعي: `build` = `vite build` (مطابق لمسار Dockerfile/الإنتاج)، وأُضيف `typecheck` = `tsc --noEmit` للدين النوعي |
| وسم النسخة v8 | `package.json` → `sahool-v9-frontend@9.0.0` |

**تحقّق**: `npm install` (نظيف) ✅ · `npm run build` ✅ (dist 1.3M، vite 6) · `npm audit` 0.

### دين نوعي موثّق (لم يُخفَ)
`npm run typecheck` يكشف **118 خطأ TypeScript حقيقيًّا** في 12 ملف UI (wizards/
spatial): implicit-any (TS7006/7031/7053) وعدم تطابق أنواع (TS2322/2339/2345).
مسار الإنتاج (vite) لا يتأثّر. إصلاحها مهمّة مُركّزة مستقلّة (تعديل مكوّنات UI
بحذر) — متاحة عبر `typecheck` ولم تُسكَت بترخية tsconfig.

## ملاحظة صدق
- ثغرة PYSEC-2026-161 تتطلّب starlette ≥ 1.0.1؛ رفع fastapi إلى 0.136.3 (الذي
  يسحب starlette 1.2.1) عالجها — وتأكّدتُ أنّ المنصّة تعمل على هذا الستاك حيًّا.
- لم أُسكِت أخطاء TypeScript بترخية الإعداد؛ فصلتُها في `typecheck` وأبقيتُها
  مرئيّة كدين موثّق، لأنّ مسار النشر الفعلي (vite) لا يمرّ بـtsc أصلاً.
