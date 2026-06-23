# حالة Bundle C (مسار R&D) — إغلاق صادق بالحالة لا بالكود

> **الحالة:** `accepted` (2026-06-23). يُغلق عنصر «Bundle C» في إطار إغلاق الفجوات
> «implemented-but-off-by-default» **بإعلان الحقيقة لا باختلاق كود**. يربط:
> [`strategy.md`](strategy.md) (الحزمة C) · [`../gaps/registry.md`](../gaps/registry.md).

## المبدأ
Bundle C **مسار R&D** (رهانات، خارج المسار الحرج). على عكس الإغلاقات الأربعة السابقة
(ETc-dual #471 · C5 #472 · H2 #473 · C4/M1 #474) التي كان فيها **كود فعليّ يُحرَس بعلم**،
عناصر Bundle C **إمّا غير منفَّذة (فكرة)، أو محروسة أصلاً، أو موقوفة بقرار**. **الصدق يمنع**
اختلاق feature-flags لما لا وجود له، أو إعادة حراسة ما هو محروس. لذا إغلاق Bundle C =
**توثيق الحالة الحقيقيّة لكلّ عنصر** فيخرج من «غموض مفتوح» إلى «حالة معلَنة».

## الحالة الفعليّة لكلّ عنصر (مُتحقَّقة + تصنيف المستخدم النهائيّ 2026-06-23)

| # | العنصر | الحالة الفعليّة | التصنيف النهائيّ |
|---|---|---|---|
| 1 | **Field Embeddings / RAG** | خدمات RAG/استرجاع **اختياريّة موجودة تُفعَّل بالنشر**: `services/qdrant-seed/` · `services/local-ai-rag/` · `knowledge/conservative_rag.py`. **مُتحقَّق:** RAG **لا يدخل أيّ مسار قرار إنتاجيّ بلا حراسة** — `conservative_rag` وحدة قائمة لا تُستدعى في مسار قرار؛ `local-ai-rag` يُستعمَل في **إثراء الشرح** فقط (`api/decision_explainer.py:38`)، opt-in بالنشر، يتدهور برشاقة عند غيابه. (field embeddings المتخصّصة بعد لا كود لها.) | **closed (implemented-as-optional-services, deployment opt-in)** |
| 2 | **نماذج أساس (Prithvi/DINOv3)** | **لا كود** — لا استيراد مكتبات ولا أوزان ولا خطّ استدلال. ذِكرها في القرارات فقط. | **not started** |
| 3 | **SAM2 production** | **منفَّذ ومحروس** — خادم `services/sam2-inference/main.py` كامل؛ محروس بـ`profile=gpu` (`docker-compose.v9.yml:1351`)؛ بدون GPU ⇒ 503 صادق (`/readyz` model_loaded=false). | **closed (gated, env-unverified)** |
| 4 | **Multi-engine Ensemble** | **المفهوم غير منفَّذ** — لا تصويت/إجماع لمحرّكات قرار/حدود متعدّدة. (`core/engines/fusion.py` أداة **fusion للمؤشّرات الطيفيّة** صادقة موجودة — optical/SAR/thermal بانتشار خطأ + ثقة فئويّة — لكنّها **شيء مختلف** عن ensemble المحرّكات، ليست تنفيذاً له.) | **open (concept-only / not implemented)** |
| 5 | **Machine Integration (ISOXML)** | **موقوف بقرار معماريّ صريح** — [`strategy.md`](strategy.md): «أُوقِف ISOXML بصدق؛ Shapefile كافٍ #456». البديل: `api/prescription_shapefile.py`. مُلاءمة اليمن: لا John Deere/Trimble. | **deferred by design (#456)** |

## الخلاصة
- **لا PR كود لـBundle C** (بقرار المستخدم 2026-06-23): لا تُختلَق أعلام ولا إغلاقات مصطنعة لما لا وجود له،
  ولا يُعاد حراسة المحروس. إغلاق Bundle C = **توثيقيّ لا برمجيّ**.
- **لا حاجة لـ`FEATURE_CONSERVATIVE_RAG`:** الاستكشاف أثبت أنّ RAG/embeddings **لا تدخل مسار قرار إنتاجيّ
  مباشرةً بلا حراسة** — فلا فجوة «RAG production gating» مستقلّة. لو ظهر لاحقاً مسار قرار يعتمد RAG بلا
  حراسة، **حينها فقط** يُفتح علم صغير (`FEATURE_CONSERVATIVE_RAG=false` / `decision_path=deterministic_only`).
- **التفعيل المستقبليّ** (إن قُرِّر): نماذج الأساس/Ensemble تبدأ كرهان R&D صريح + feature-flag **عند وجود
  كود فعليّ** — لا قبله.

## أثر هذا الإغلاق على سحب الإطار
يكتمل بذلك سحب «implemented-but-off-by-default»: **4 إغلاقات كود** (ETc-dual #471 · C5 #472 · H2 #473 ·
C4/M1 #474، جميعها default off + إعلان سبب + اختبار off/opt-in) + **إغلاق حالة واحد** (Bundle C، توثيق
الحقيقة). **SAM2/MAP-QA تبقيان `implemented-gated-but-env-unverified`** (لا «production-ready») كما صنّف المستخدم.
