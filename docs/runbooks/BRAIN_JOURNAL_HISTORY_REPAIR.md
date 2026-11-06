# إصلاح تاريخ سجل تقلّص ثم استُعيد

تُنشئ [`repair_brain_journal_history.py`](../../scripts/ci/repair_brain_journal_history.py)
فرعاً محلياً جديداً يدمج نافذة التقلّص والاستعادة في التزام واحد، مع حفظ **شجرة
الرأس الأصلية كاملةً**. تستعمل قواعد
[`brain_append_only_guard.py`](../../scripts/ci/brain_append_only_guard.py) نفسها؛
لا تغيّر الحارس أو ميزانية `hot.md`، ولا تعالج فقدان نص لم يُستعد بعد.

هذه أداة صيانة يطلبها المساهم صراحةً، وليست بوابة CI أو مولّداً للمصنوعات.
اختباراتها في
[`test_repair_brain_journal_history.py`](../../tests_v9/test_repair_brain_journal_history.py).

## لماذا لا يصلح التزام لاحق الخطأ؟

يفحص الحارس كل علاقة بين التزام ووالده داخل المدى `base..head`. لذلك يبقى
`JOURNAL_SHRANK` حاجباً إذا قلّص التزام وسيط السجل، حتى لو أعاد الرأس النهائي النص
كاملاً. الإصلاح هو إعادة تشكيل تلك النافذة؛ إضافة بايتات إلى الرأس لا تغيّر
العلاقة التاريخية التي فشلت.

مثال مقيس في [PR #1335](https://github.com/kafaat/ai_platform_complete_v2.0.0_enhanced/pull/1335)،
عند الرأس `ea12a230814f4d341e4aa2d106a9bd767b30b567`:

| العلاقة | ما حدث في `sahool-brain/gaps/registry.md` | الحجم بالبايت |
|---|---|---:|
| `ebb838e6 → e26a7153` | استُبدلت فقرة تاريخية بأخرى أقصر | 2,549,116 → 2,548,631؛ نقص 485 |
| `e26a7153 → ea12a230` | استُعيدت الفقرة الأصلية وأُضيف توضيح الإغلاق | 2,548,631 → 2,549,917 |
| `ebb838e6 → ea12a230` | الصافي يحفظ الفقرة الأصلية ويضيف التوضيح | زيادة 801 |

مصادر المقارنة:
[التقلّص](https://github.com/kafaat/ai_platform_complete_v2.0.0_enhanced/commit/e26a71537ce642cf22fde8630f4b8a89910d2af0)،
[الاستعادة](https://github.com/kafaat/ai_platform_complete_v2.0.0_enhanced/commit/ea12a230814f4d341e4aa2d106a9bd767b30b567)،
[صافي النافذة](https://github.com/kafaat/ai_platform_complete_v2.0.0_enhanced/compare/ebb838e6af2d9c87c82273a651225cb61377402e...ea12a230814f4d341e4aa2d106a9bd767b30b567).
كانت ميزانية `hot.md` في التشغيل 171,196 / 526,815 بايت، فهي ضمن السقف وليست
سبب هذا الفشل. أما `PREFIX_NOT_PRESERVED` فإشعار إرشادي في هذا العقد.

## اختيار النافذة

- `--base`: أساس فحص CI الحالي، مثل `origin/main`؛ يبقى مدى التحقق كاملاً.
- `--parent`: آخر التزام سليم قبل التقلّص؛ سيصبح والد الالتزام الجديد.
- `--head`: الرأس الذي استعاد المحتوى، ويُؤخذ منه كائن الشجرة كما هو؛ الافتراضي `HEAD`.
- `--branch`: اسم فرع محلي **جديد**؛ ترفض الأداة الكتابة فوق فرع موجود.
- `--apply`: أنشئ الفرع بعد التحقق. بدونه تُعرض خطة فقط، ولا يُنشأ فرع.

يلزم تاريخ Git كامل ومراجع قابلة للقراءة، وأن يشترك `base` و`parent` في أساس دمج
واحد. يجوز أن يكون `origin/main` قد تقدّم مستقلاً بعد تفرّع المصدر، بما في ذلك
دمج PR هذه الأداة؛ لا يلزم تعديل الفرع القديم أو دمج `main` فيه لتخطيط الإصلاح.
لا يُستبدل أساس CI بأساس الدمج: يبقى الفحص على `base..head` ثم `base..candidate`،
وتبقى مقارنة الميزانية مع `base` الحالي. تُرفض التواريخ غير المرتبطة أو التي
لها أكثر من أساس دمج مشترك، وتحتاج مراجعة يدوية.
تقبل الأداة نافذة خطية متصلة من التزامين فأكثر، فيها تقلّص تاريخي استُعيد محتواه.
يجب أن تكون حواجز المدى الأصلي كلها من نوع `JOURNAL_SHRANK` داخل النافذة وقبل
الرأس، مع سلامة الميزانية. تُثبت الأداة بقاء أسطر والد التقلّص في الرأس بايتاً
ببايت، بترتيبها وتكرارها؛ تعادل الحجم وحده ليس برهان استعادة النص. ترفض النوافذ
التي تحتوي دمجاً، والمحتوى غير المستعاد، والتاريخ الضحل، وأخطاء الحارس التي لا
تُصلحها هذه النافذة.

## خطة ثم فرع محلي جديد

نفّذ من جذر المستودع الذي يحتوي الأداة. اجلب المراجع المطلوبة أولاً إن لم تكن
محلية، وتحقق من أن `origin/main` يمثل الأساس المراد اختباره. المثال التالي
مثبّت على لقطة #1335 أعلاه؛ عند تغيّر الرأس أعد تحديد نافذة الإصلاح من التاريخ.

```bash
python scripts/ci/repair_brain_journal_history.py \
  --base origin/main \
  --parent ebb838e6af2d9c87c82273a651225cb61377402e \
  --head ea12a230814f4d341e4aa2d106a9bd767b30b567 \
  --branch repair/pr1335-journal-history
```

تعرض الخطة JSON بحالة `planned` بعد نجاح التحقق. راجع `base` و`parent` و`head`
و`tree` و`commits_squashed`. قيمة `candidate` تخص كائن التزام مؤقتاً يُزال بعد
التخطيط، وليست مرجعاً محلياً صالحاً للاستعمال لاحقاً. لإنشاء الفرع المحلي الجديد،
أعد الطلب نفسه مع `--apply`:

```bash
python scripts/ci/repair_brain_journal_history.py \
  --base origin/main \
  --parent ebb838e6af2d9c87c82273a651225cb61377402e \
  --head ea12a230814f4d341e4aa2d106a9bd767b30b567 \
  --branch repair/pr1335-journal-history \
  --apply
```

تعني حالة `created` أن المرجع الجديد أُنشئ بعد اجتياز الفحص. لا تنفّذ الأداة
`checkout` أو `push`، ولا تعدّل الفرع الأصلي أو `HEAD` أو الفهرس أو ملفات العمل.
إذا كان اسم الوجهة موجوداً تتوقف؛ افحص الموجود ثم اختر اسماً جديداً بدلاً من حذف
فرع تلقائياً.

## التحقق من النتيجة

يجب أن يعيد الأمر الأول رمز خروج صفراً بلا فرق، وأن يتطابق معرّفا الشجرة، وأن
يجتاز الفرع الجديد الحارس الأصلي على مدى الفرع `base..candidate`:

```bash
git diff --exit-code \
  ea12a230814f4d341e4aa2d106a9bd767b30b567 repair/pr1335-journal-history
git rev-parse 'ea12a230814f4d341e4aa2d106a9bd767b30b567^{tree}'
git rev-parse 'repair/pr1335-journal-history^{tree}'
python scripts/ci/brain_append_only_guard.py \
  --base origin/main --head repair/pr1335-journal-history
```

هذا البرهان يخص محتوى الشجرة وقاعدة السجل على الفرع. يعيد CI فحص حارس السجل
على مرجع دمج طلب السحب، بما فيه المقارنة مع كلا والدَيه؛ نجاح الفحص المحلي لا
يغني عن ذلك. تبقى بوابات المستودع خاضعة
لـ[بروتوكول ما قبل الدفع](CI_GATES_AND_PRE_PUSH_PROTOCOL.md) وCI على الرأس الجديد.

## حدود الطلب المستقل

إضافة الأداة واختباراتها في PR مستقل لا تغيّر تاريخ #1335 ولا تجعل فحوصه ناجحة.
الفرع الذي تنتجه الأداة من مثال #1335 يحمل **جميع ملفات رأس #1335**، بما فيها
تغييرات Windows وGPU الموجودة أصلاً؛ الذي يتغير هو التاريخ فقط. لذلك فإن فتح
ذلك الفرع نفسه مقابل `main` يعرض نطاق تغييرات #1335 الكامل، وليس تصحيح سجل وحده.

تحديث الفرع القديم أو استبدال طلبه إجراء لاحق يحتاج تفويضاً صريحاً، ولا تنفذه هذه
الأداة. عند تفويض تحديث التاريخ، يلزم التحقق من الرأس البعيد مجدداً واستعمال
`--force-with-lease` المربوط بذلك الرأس، وفق
[طبقة استمرارية العمل](WORK_CONTINUATION_SAHOOL.md). لا يُعد نجاح خطة محلية إذناً
بالدفع أو الدمج.

## English reference

The utility consolidates a linear shrink-and-restore window into one commit whose
tree is identical to the selected head and whose parent is the last good commit.
The current CI base may have advanced independently after the source fork; it must
share exactly one merge base with the selected parent. Unrelated or ambiguous
histories are rejected. No update of the original branch is needed, and guard and
budget checks still use the current CI base rather than substituting the merge base.
It validates the candidate with the existing journal guard and budget rules before
creating a new local branch. The default is a plan; `--apply` creates only the new
branch. The original branch, checkout, index and working files are preserved.

A tool-only pull request does not repair the history of an existing pull request.
In the #1335 example, the generated branch retains the entire original source tree,
so a replacement PR against `main` would retain that PR's full file scope. Publication
and any update of the old branch are separate, explicitly authorized operations.
