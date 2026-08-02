# بوّابات CI وبروتوكول ما قبل الدفع

> **لمن؟** لأيّ وكيل أو مساهم يوشك أن يدفع إلى فرع في هذا المستودع.
> **لماذا؟** لأنّ الأصناف التي تُسقِط CI هنا **تتكرّر**، وكلّها تُقاس محلّيّاً في دقائق.
> كلّ صنف أدناه أسقط بناءً حقيقيّاً في هذا المستودع؛ لا شيء منه افتراضيّ.

المقيس عند كتابة هذه الوثيقة: **٥٥** ملفّ workflow · **٢٤٥** سكربت في `scripts/ci/` ·
**٦٠** اختبار معماريّ في `tests/architecture/` · **٦١٥** ملفّ اختبار في `tests_v9/` ·
**٤٣** مولّداً مُصرَّح علمه في `verify_all_generated._GENERATE_FLAG`.

---

## ١. الخريطة — أين يعمل ماذا

CI هنا ليس جناحاً واحداً بل سطح من الـworkflows المستقلّة. الحاجب منها ما يلي، ومن
المفيد معرفة أيّ ملفّ يُشغّل أيّ فحص لأنّ **رسالة الفشل تسمّي الوظيفة لا الملفّ**.

| الوظيفة (كما تظهر على الـPR) | الملفّ | ما تفرضه — والنطاق الحقيقيّ |
|---|---|---|
| `Lint & Format` | `.github/workflows/ci.yml:434` | `ruff check .` و`ruff format --check .` — **كامل الشجرة** بـ`ruff==0.15.8` مثبَّتاً · `conflict_marker_guard.sh` · `claim_base_guard.py` · `guard_mutation_guard.py` (الشطر الساكن) |
| `Unit Tests` | `ci.yml:523` | `test_marker_coverage_guard --check` · `guard_mutation_guard --run` · `pytest -v -m unit --cov=services` · أرضيّة `--cov-fail-under=43` · أربعة ملفّات غير مُعلَّمة بمساراتها الصريحة |
| `Security Scan` | `ci.yml:1112` | `bandit -r services/ bots/ agents/ --severity-level high` (يحجب) · `--severity-level medium` (إرشاديّ لا يحجب) · `pip-audit` على **١٩ ملفّ متطلّبات** |
| `Repository Structural Lint` | `ci.yml:6` | عقود واجهة/خدمة، سجلّ المؤشّرات، مصنوعات RIV المولَّدة، حوكمة الدماغ · `no_merge_conflict_markers_guard.py` (ci.yml:158) |
| `capability-registry` | `capability-governance.yml` | ~٢٠ بوّابة `--check` · **٥٨** اختباراً بالمسار · `arch_test_ci_coverage_guard` · `verify_all_generated` **أخيراً** |
| `no-report-only-change` | `no-report-only-change.yml` | `no_report_only_change_guard` · `brain_state_transition_guard` · `brain_deferral_registry_guard` · `brain_commit_claim_guard` |
| `platform-route-budget` | `platform-route-budget.yml` | ميزانية مسارات النطاق + `platform_route_placement_guard` (يعمل بلا pytest) |
| `p1-main-decomposition` / `p2-main-decomposition` | ملفّاهما | `main.py` خالٍ من مُزخرِفات المسار + سقف الأسطر |
| `report-index` | `report-index.yml` | `REPORT_INDEX.md` مطابق لقائمة الأقسام في `report_index_guard.SECTIONS` |

الباقي (~٤٥ workflow) عقود نطاق: raster · weather · edge · runtime-verification …
تُسقِطها تغييرات في نطاقها فقط.

---

## ٢. البروتوكول — أعِد إنتاج البوّابات الحاجبة محلّيّاً قبل الدفع

الترتيب مقصود: **الأرخص أوّلاً**. كلّ سطر يُعيد إنتاج بوّابة حاجبة بعينها.

```bash
cd "$(git rev-parse --show-toplevel)"
BASE="${BASE:-origin/main}"
failures=0
run() {
  echo "── $1"; shift
  local rc=0
  "$@" || rc=$?                       # `|| rc=$?` يلتقط الحالة الحقيقيّة ويحمي من set -e
  if [ "$rc" -ne 0 ]; then
    failures=$((failures+1)); echo "   ✗ فشل ($rc)"
  fi
  return 0                            # الدالّة لا تُسقِط السكربت؛ العدّاد هو الحكم
}
```

> **ثلاثة أخطاء مقيسة في هذه الأسطر الثمانية وحدها**، وكلّها وقعت فعلاً في سكربتات
> تحقّق كُتِبت في هذا المستودع:
>
> - `[ $rc -ne 0 ] && echo …` كآخر تعليمة تُعيد **١ عند النجاح** (الشرط كاذب)، فتصير
>   قيمةَ إرجاع الدالّة. `if/fi` + `return 0` الصريح لا يقع في هذا.
> - `"$@"; rc=$?` بلا `||` **يقتل السكربت** تحت `set -e` عند أوّل فشل، فلا ترى بقيّة
>   البوّابات — وهو عكس المقصود من عدّاد الإخفاقات.
> - `if "$@"; then …; fi; rc=$?` يقرأ حالة **جملة `if`** لا حالة الأمر، فيطبع `0`
>   لفحص فاشل. مُثبَت: `bash -c 'exit 4'` يُبلَّغ `fail (0)` بهذه الصيغة و`fail (4)`
>   بالصيغة أعلاه.

```bash
# ٠) الشجرة نظيفة — كلّ قياس على شجرة متّسخة يقيس شيئاً لن يُدفَع
git status --porcelain | head

# ١) التنسيق واللِّنت — كامل الشجرة، بالإصدار المثبَّت نفسه
pip install -q ruff==0.15.8
run "ruff check"          ruff check .
run "ruff format --check" ruff format --check .

# ٢) حرّاس تعارض الدمج (اثنان، ولا يغني أحدهما عن الآخر)
run "conflict_marker_guard" bash scripts/ci/conflict_marker_guard.sh
run "no_merge_conflict_markers" python scripts/ci/no_merge_conflict_markers_guard.py

# ٣) أساس الادّعاءات + حارس الطفرات (الشطران)
run "claim_base_guard"      python scripts/ci/claim_base_guard.py
run "guard_mutation static" python scripts/ci/guard_mutation_guard.py
run "guard_mutation --run"  python scripts/ci/guard_mutation_guard.py --run

# ٤) انحراف المصنوعات المولَّدة — راجع §٣.١ قبل تشغيله
run "verify_all_generated" python scripts/ci/verify_all_generated.py

# ٥) حرّاس الدماغ — على مدى الـPR لا على الشجرة
run "brain_state_transition" python scripts/ci/brain_state_transition_guard.py --base "$BASE" --head HEAD
run "brain_commit_claim"     python scripts/ci/brain_commit_claim_guard.py --base "$BASE" --head HEAD
run "brain_deferral"         python scripts/ci/brain_deferral_registry_guard.py

# ٦) تسجيل الاختبارات المعماريّة + علامات الاختبارات
run "arch_test_ci_coverage" python scripts/ci/arch_test_ci_coverage_guard.py
run "marker_coverage"       python scripts/ci/test_marker_coverage_guard.py --check

# ٧) الجناح — الأغلى، وآخره عمداً
run "pytest -m unit" python -m pytest -q -m unit

# ٨) المتّجه الذي يخفيه Linux: ترميز لغة الآلة (§٣.١٠)
run "pytest -m unit تحت لغة C" env LC_ALL=C PYTHONUTF8=0 python -m pytest -q -m unit

echo "═══ إخفاقات: $failures ═══"; [ "$failures" -eq 0 ]
```

> **فخّ مقيس:** `python … | tail -2; echo $?` يطبع حالة `tail` لا حالة بايثون. وكذلك
> `echo "$(cmd)"` يمسح `$?` قبل قراءته. إن أردت أنبوباً فاستعمل
> `set -o pipefail` أو `PIPESTATUS[0]` — وانتبه أنّ `grep -q` مع `pipefail` يُنتج
> SIGPIPE فيُبلَّغ فشلاً كاذباً.

---

## ٣. أصناف الفشل — كلٌّ منها أسقط بناءً هنا

### ٣.١ انحراف المصنوعات المولَّدة: `git ls-files` لا يرى ما لم يُضَف

**العَرَض:** `verify_all_generated` أخضر محلّيّاً ثمّ أحمر في CI بعد الالتزام مباشرة.

**السبب:** المولّدات تُعدّد **الملفّات المتعقَّبة** (`git ls-files`). ملفّ جديد لم
يُضَف بعدُ غير مرئيّ لها، فالمصنوعة المولَّدة تخلو منه — حتّى تلتزم، فيصير متعقَّباً،
فيظهر الانحراف في أوّل تشغيل بعد الالتزام.

**العلاج:** `git add` **قبل** إعادة التوليد، لا بعدها:

```bash
git add -A
python scripts/ci/verify_all_generated.py --fix
git add -A
```

**وقاعدة ترتيب ثانية، أسقطت أربع وظائف دفعةً واحدة:** `release/FILE_CHECKSUMS.sha256`
يُجزّئ **كلّ** المصنوعات الأخرى، فبناء حزمة الإصدار ثمّ إعادة توليد مصنوعة أخرى بعده
يترك جزءاً بائتاً. الرسالة تقول `checksum mismatch: <ملفّ>` وتظهر في `release-package`
و`pytest-contracts` و`Lint & Format` معاً — أربع رسائل لعطل واحد.

```bash
# ١) كلّ المولّدات الأخرى أوّلاً
python scripts/ci/verify_all_generated.py --fix
git add -A
# ٢) حزمة الإصدار **أخيراً** — لأنّها تُجزّئ ما سبق
SOURCE_DATE_EPOCH=$(git log -1 --pretty=%ct) python scripts/release/build_release_bundle.py
git add -A
python scripts/release/validate_release_package.py     # يجب أن يقول: checksums verified
```

> **ولا تُوقِف المكنسة لبطئها.** أوقفتُها مرّةً فمرّ انحراف
> `integration_runtime_governance_closure` إلى CI. المكنسة تُشغَّل كاملةً أو **لا
> يُدَّعى أنّها شُغِّلت** — نتيجة جزئيّة ليست نتيجة.

### ٣.٢ ضريبة التسجيل: أداة غير موصولة لا تحرس شيئاً

قاعدتان منفصلتان، وكلتاهما تحجب:

- **سكربت جديد يعلن `--check`** ولا يذكره أيّ workflow ⇒ يُسقِط
  `verify_all_generated.classify_uncovered`. الحلّ: صِله بـworkflow، أو صنّفه صراحةً
  في أساس الانحراف المعروف. والأساس **يتقلّص ولا ينمو**: مدخل بائت يُسقِط أيضاً.
- **ملفّ جديد في `tests/architecture/`** لا تذكره القائمة اليدويّة في
  `capability-governance.yml` ⇒ يُسقِط `arch_test_ci_coverage_guard`. **لا إعفاء** —
  الحارس وُلد لأنّ ١٧ من ٥٤ اختباراً كانت خارج القائمة تبيت بصمت، منها حرّاس بُنيت
  في اليوم نفسه.

> والقائمة يدويّة بالتصميم؛ الحارس هو ما يجعل نسيانها مستحيلاً لا استحضارها تلقائيّاً.

### ٣.٣ النطاق الحقيقيّ للِّنت والأمن — لا تُخمّنه

- `ruff` يعمل على `.` — **كامل المستودع** بما فيه `scripts/` و`tests/` و`alembic/`
  و`sdk/`. «ملفّي خارج `services/` فلن يُفحَص» خطأ أسقط بناءً في هذه الجلسة.
- `ruff` **مثبَّت على `0.15.8`**. `pip install ruff` الطليق يجلب أحدث إصدار، وقواعد
  التنسيق تتغيّر بين الإصدارات ⇒ ملفّ «مُنسَّق» محلّيّاً يصير «would reformat» في CI.
  **والاتّجاه المعاكس أكلف، ومقيس في هذه الجلسة:** تشغيل `ruff` **غير المثبَّت** من
  البيئة (0.16.0) أعطى **٢٦ ملفّاً «would be reformatted»** لا يمسّ أيٌّ منها تغييري،
  لأنّ 0.16 تُنسّق كتل الكود **داخل Markdown** (3716 ملفّاً مفحوصاً مقابل 2915). أحمرُ
  محلّيّ لن يُنتِجه CI أبداً — يدعوك إلى «إصلاح» ستّة وعشرين ملفّاً لم يُطالَب بها، أو
  إلى الشكّ في خطّ أنابيب أخضر. **العلاج: كتلة §٢ تُثبِّت الإصدار؛ شغّلها هي، لا
  `ruff` الذي في مسارك.**
- `bandit` الحاجب يعمل على `services/ bots/ agents/` فقط وعلى `--severity-level high`
  فقط. MEDIUM إرشاديّ لا يحجب. لا تُصلح MEDIUM ظنّاً أنّه أسقطك.

### ٣.٤ ما يمنع التعارض قبل وقوعه — وما لا يمنعه

قبل قراءة قواعد الحلّ أدناه: أربع طبقات هبطت تحت
`DETERMINISTIC-GENERATION-AND-MERGE-SAFETY-01`، ولكلٍّ حدّ يجب أن يُعرَف.

| الطبقة | ماذا تفعل | ماذا **لا** تفعل |
|---|---|---|
| **حتميّة المصنوعات** (`scripts/ci/deterministic_time.py`) | إعادة توليد بلا تغيّر حمولة ⇒ **صفر فرق** | لا تمنع تعارض تغيّر حقيقيّ |
| **`merge=union`** على أربعة مسارات دماغ | يضمّ الجانبين محلّيّاً بدل ترك العلامات | **لا يُزيل لافتة GitHub** — GitHub يتجاهل `.gitattributes` |
| **`brain_duplicate_gap_identity_guard`** | يكشف فجوة بحالتين متناقضتين بعد union | **يكشف** ولا يمنع |
| **`scripts/dev/enable_rerere.sh`** | يحفظ الحلّ ويُعيده على الفروع طويلة العمر | محلّيّ لكلّ نسخة، **وليس بوّابة CI** |

**قاعدتان عمليّتان:**

```bash
# قبل أيّ إعادة توليد يدويّة — وإلّا فشل صريح داخل أرشيف بلا .git
export SOURCE_DATE_EPOCH=$(git log -1 --pretty=%ct)

# مرّة واحدة لكلّ نسخة عمل
bash scripts/dev/enable_rerere.sh
```

> **ولا تكتب `git log -1` بلا نطاق داخل مولّد.** أوّل تنفيذ فعل ذلك، فصار الختم
> تابعاً لـ`HEAD` — و`HEAD` يختلف بين فرعين بالضرورة، فبقي التعارض الذي جاء الإصلاح
> لإزالته، ومرّ الادّعاء إلى `main` لأنّ اختبار القبول يُثبّت `SOURCE_DATE_EPOCH`
> صراحةً فلا يعبر حدّ الالتزام أبداً. القاعدة الصحيحة نطاق **الحمولة**
> (`git log -1 --pretty=%ct -- <payload>`)، ويُشتقّ النطاق من ثوابت المولّد لا
> يُكتَب بيدٍ ثانية تنحرف. مسجَّل `DETERMINISTIC-STAMP-SCOPED-TO-HEAD-NOT-PAYLOAD-01`.

> **والحدّ الذي يُنسى فيُعاد اكتشافه:** `merge=union` **لا** يُنهي لافتة
> «This branch has conflicts». الحلّ الجذريّ لها بنيويّ — ملفّ لكلّ مدخل بدل أربعة
> ملفّات مشتركة — مسجَّل `BRAIN-FRAGMENTED-SOURCE-OF-TRUTH-01` ومؤجَّل بقرار المالك.

### ٣.٥ حلّ التعارض له **صنفان**، وخلطهما يفسد الشجرة

| صنف الملفّ | القاعدة الصحيحة | الخطأ الشائع |
|---|---|---|
| مصنوعة مولَّدة (`*.generated.json`, `*.csv`) | خُذ جانب `main` ثمّ **أعِد التوليد** | اختيار جانب — ينتج مصنوعة لا تطابق أيّ شجرة |
| دماغ إلحاقيّ (`log.md` · `hot.md` · `gaps/registry.md` · `decisions/ledger.md`) | **أبقِ الجانبين** | اختيار جانب — يحذف عمل جلسة أخرى |
| شيفرة | حلّ يدويّ حقيقيّ | — |

**وبعد «أبقِ الجانبين» افحص التكرار.** «الإبقاء الميكانيكيّ» على `hot.md` أنتج ختماً
مكرّراً وثلاث علامات «(الأحدث)» وسطراً بادئته `>>`. أعِد بناء الملفّ من `main` ثمّ
ألحِق ختمك، لا تدمج نصّياً.

**و`*.md` داخل نطاق حارس علامات التعارض** منذ حادثة `=======` شاردة في `log.md` مرّت
من الحارسين معاً: الشِّلّيّ لم يكن ينظر إلى Markdown، والبايثونيّ يتجاهل `=======`
المنفردة عمداً (تحتها معنى شرعيّ: تسطير عنوان setext). والضرر صامت لا صاخب — السطر
**فوقها** يصير عنوان H1.

### ٣.٦ `Capability-Impact` يُحسَب **بعد** الدفع

- الرمز `ALL` صالح **فقط** حين يكون التغيير `governance_wide`؛ وإن ورد فلا رمز غيره.
- الوظيفة تعمل على `pull_request` بلا `edited` ⇒ **تعديل جسم الـPR وحده لا يُعيد
  تشغيلها**. صحّح الجسم ثمّ ادفع التزاماً، أو أعِد تشغيل الوظيفة يدويّاً.
- احسب الرموز على مدى `base…head` **الفعليّ بعد الدفع**، لا على ما تظنّ أنّك غيّرت.

### ٣.٧ `brain_commit_claim_guard`: ذكر معرّف فجوة = ادّعاء وجودها

كلّ معرّف على نمط `AAA-BBB-CCC` في **رسالة التزام** داخل نطاق الـPR يجب أن يوجد
عنوان `## <المعرّف>` يحمله في `sahool-brain/gaps/registry.md`. سجّل أوّلاً ثمّ اذكر.

### ٣.٨ `brain_state_transition_guard`: مفردات الإغلاق تحتاج شيفرة خارج الدماغ

يرفض تغييراً **يمسّ `sahool-brain/`** ويُدخل سطراً يحمل
`CLOSED|VERIFIED|RUNTIME_VERIFIED|PRODUCTION_CERTIFIED` (مع ذيل `_UPPER` اختياريّ)
**ما لم** يحمل التغيير ملفّاً في `services/` · `scripts/ci/` · `tests/` · `tests_v9/` ·
`.github/workflows/` · `migrations/` · `runtime-verification/` · `certification/evidence/`.

لاحظ ما **لا** يُعدّ جوهريّاً هنا: `docs/`. وثيقة وحدها + تحديث دماغ بمفردات إغلاق
= رفض صحيح. أعِد الصياغة، **لا** تُرخِ الحارس.

> `fail-closed` و`open-closed` **لا** تُطلقانه (النظرة الخلفيّة ترفض الشرطة السابقة)،
> و`CLOSED_IN_CODE` **تُطلقه** (الذيل `_UPPER` مقصود). هذا مُثبَت في
> `tests_v9/test_brain_transition_guard_vocabulary.py` — **١٦ حالة** إيجابيّة وسلبيّة،
> مقيسة خضراء.

**وحدّ معروف في هذا الحارس، فلا تقرأ خُضرته شهادةً:** مفرداته إنجليزيّة وحدها، وسجلّ
الفجوات يكتب حالاته بالعربيّة في أكثر الأحيان. المقيس على `54a91d8e`: **١٦ من ١٠٠**
عنوان فجوة يحمل حالة إغلاق عربيّة، ويلتقط الحارس منها **صفراً**. مسجَّل
`BRAIN-TRANSITION-GUARD-BLIND-TO-ARABIC-STATUS-01` (مفتوحة) مع سبب عدم توسيع النمط
بالكلمة المجرّدة: ٤٠ سطراً تصف «يفشل مُغلَقاً» تصميماً لا حالة، فيُعاد إنتاج نفس
الإيجابيّ الكاذب الذي أُصلِح سابقاً.

### ٣.٩ `no_report_only_change_guard`: تغيير تقاريريّ صرف يُحجَب

مصنوعات `.md/.csv/.json` تحمل في اسمها `REPORT|INVENTORY|CHECKLIST|SUMMARY|MATRIX|REGISTRY`
لا تمرّ وحدها. المسارات المُعتبَرة جوهريّة تشمل `docs/runbooks/` — ولهذا موضع هذه
الوثيقة هنا وليس في `docs/` مباشرة.

### ٣.١٠ ترميز لغة الآلة — العطل الذي يخفيه Linux

Linux افتراضيّه UTF-8، فـ`pytest -m unit` أخضر لا يُثبِت أنّ الحرّاس تقرأ ما تدّعي
قراءته. تحت `LC_ALL=C PYTHONUTF8=0` انهار **١٢** اختباراً بـ`UnicodeDecodeError`.
والمتّجهات **أربعة** لا واحد:

1. قراءة مباشرة — `read_text()`/`open()` بلا `encoding`.
2. فكّ مخرَج عمليّة في الأب — `subprocess.run(..., text=True)`.
3. **مخرَج الابن نفسه** — `encoding` على الأب لا يُملي على الابن؛ يلزم
   `PYTHONIOENCODING=utf-8` في بيئته. وحده سبب أربعة من الاثني عشر.
4. `os.environ` — ترميز نظام الملفّات؛ حدّ نظام تشغيل لا عيب شيفرة.

`tests_v9/test_text_encoding_locale.py` يمنع النموّ بأساس **يتقلّص ولا ينمو** (١٨٤ ملفّاً).
ملفّ جديد بلا `encoding` يُسقِطه؛ **الإصلاح سطر واحد، لا مدخل جديد في الأساس**.

### ٣.١١ اختبار بلا علامة اختبارٌ ميت

ملفّ في `tests_v9/` بلا `pytestmark` يستبعده `-m` في **كلّ** وظيفة: حيّ محلّيّاً حين
تُشغّله بالمسار، ميت في البوّابة. `test_marker_coverage_guard --check` يمنع مولوداً
خامداً جديداً؛ أساسه المُجمَّد (`docs/testing/unmarked_tests_baseline.json` — **٩** ملفّات
بأسبابها المقيسة) يتقلّص ولا ينمو.

### ٣.١٢ أرضيّة التغطية راتشِت

`--cov-fail-under=43`، والمقيس ~٤٧٪. الأرضيّة تصعد ولا تنزل (20 → 40 → 42 → 43).
انظر `docs/testing/coverage_ratchet.md`. **لا تُخفِّضها** لتمرير شريحة.

### ٣.١٣ ميزانية المسارات وموضعها القانونيّ

- `main.py` خالٍ من مُزخرِفات المسار **بالعقد**؛ كلّ مسار جديد إلى `api/routers/`.
- مسارات البنية (`/healthz` · `/readyz` · `/metrics` · `/runtime-identity`) موضعها
  `api/routers/platform_health.py`، مُعلَنة كبيانات ومفروضة بحارس مستقلّ.
- الميزانية تحدّ **مسارات النطاق فقط** (`domain ≤ 629`) والجرد الخام يبقى ظاهراً.
- الاستثناء من الميزانية **لا** يرخّص الإعلان في `main.py`.

### ٣.١٤ `%G?` لا يقيس وجود التوقيع — يقيس قدرتك على التحقّق منه

**لا تستعمل `git log --pretty=%G?` للحكم على أنّ التزاماً موقَّع.** في هذه البيئة
`gpg.ssh.allowedSignersFile` غير مضبوط، فيطبع git `N` **على التزام يحمل توقيعاً
كاملاً**. المميّز الصحيح هو الترويسة نفسها:

```bash
git cat-file commit HEAD | grep -q '^gpgsig' && echo "موقَّع" || echo "بلا توقيع"
```

المقيس: `%G?` = `N` على التزام محلّيّ ترويسته `gpgsig -----BEGIN SSH SIGNATURE-----`
حاضرة · و`%G?` = `E` على التزامات `main` (وهي دمجات squash يُوقّعها GitHub). أي أنّ
**الحرفين معاً يعنيان «لم أستطع التحقّق»**، لا «غير موقَّع».

وحدٌّ منفصل حقيقيّ: ملفّ المفتاح العموميّ `commit_signing_key.pub` بحجم **صفر بايت**،
فلا سبيل محلّيّاً لبناء `allowedSigners`. **لا تُولّد مفتاحاً عشوائيّاً وتعتبره هويّة
المستودع** لتجعل الحرف أخضر — التحقّق موضعه GitHub، وهناك يظهر صادقاً.

---

## ٤. ما لا ينبغي فعله

هذه ليست أسلوباً بل سياسة أُقرّت في قرارات دمج سابقة:

- **لا ترفع سقف ميزانية** ولا تحذف نقطة provenance لحلّ تعارض ميزانية — صنّف بصدق
  أو انقل المسار إلى خدمته.
- **لا تُحدِّث أساساً لاستيعاب انحراف متوقَّع** — أعِد التوليد.
- **لا تفصل `ruff` أو المصنوعات المولَّدة إلى «إصلاح لاحق»** — الشريحة التي لا تقيس
  نظيفةً وحدها ليست شريحة.
- **لا تحذف حارساً لأنّه أزعجك** — انقله إلى موضعه الصحيح. حارس يحجب الخطوة التي
  ينتمي إليها يُدرِّب المُشغّل على حذف الحرّاس.
- **لا تصف 422 بأنّه خطأ تحقّق عاديّ** حين يصل مستدعياً غير مُصادَق — العيب ترتيبيّ
  لا عدديّ.
- **لا تُقِس على شجرة متّسخة.** كلّ رقم في جسم PR يجب أن يكون مقيساً على SHA مُثبَّت.

---

## ٥. حدود هذه الوثيقة

- تصف السطح الحاجب **الشائع**، لا كلّ الـ٥٥ workflow. عقود النطاق (raster · weather ·
  edge) تُسقِطها تغييرات نطاقها، وقراءة ملفّها أسرع من أيّ تلخيص هنا.
- الأرقام (٥٥ · ٢٤٥ · ٦٠ · ٦١٥ · ٤٣ · ١٨٤ · ٩ · ٤٣٪) مقيسة على شجرة كتابة الوثيقة
  وتَبيت بالنموّ. تحقّق منها قبل الاستشهاد بها في ادّعاء.
- الوثيقة **لا تُغني عن تشغيل §٢**. توثيق البوّابة ليس اجتيازها.
