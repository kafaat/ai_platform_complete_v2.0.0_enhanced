# صلاحية النتائج والاختبارات الطويلة

## النموذج

اعتبر كل نتيجة اختبار `Claim` بحدود صريحة، وليست شهادة مطلقة. يُثبت الإيصال: أي ملفات أو نطاق، على أي commit/base، بإصدار أي أداة، مع أي أمر وأي إعدادات، وماذا نجح وما لم يُشغَّل.

### مفتاح الصلاحية (Validity Key)

مثال حقول منطقية (لا تجمع النصوص الخام غير المُهيكلة):

```json
{
  "scope": "unit-shard-04",
  "source_head": "<sha>",
  "source_tree": "<tree-sha>",
  "base_ref": "main",
  "base_head": "<sha>",
  "merge_base": "<sha>",
  "input_digest": "sha256:<digest>",
  "dependency_digest": "sha256:<digest>",
  "environment_digest": "sha256:<digest>",
  "command_digest": "sha256:<digest>",
  "policy_digest": "sha256:<digest>"
}
```

يجب تحديد **اعتماديات الفحص الفعلية**. فحص وحدات Python مستقل عن base قد يظل صالحاً عندما يتغير `main`، بينما فحص سياسة merge-base يُبطَل بتغيره. لا نعيد كل شيء آلياً إذا تغير حقل ليس من مدخلاته، ولا نتجاهل مدخلاً بسبب ثبات الشجرة. إذا لم توجد خريطة تبعيات موثوقة، اعتبر النتيجة `STALE_RECHECK_REQUIRED` للبوابة الحاجبة.

**لا يخزن ملف الحالة أسرار متغيرات البيئة:** ابصم وصف بيئة منزوع القيم الحساسة أو مخارج `--version` وملفات lock؛ لا تُدرج token أو DSN في `environment_digest` بمعنى raw bytes مخفية قابلة لهجوم التخمين. رمز البصمة يثبت تطابق بايتات فقط، لا يثبت صحة الشاهد أو هوية منشئه.

### حُكم الصلاحية

| المجال | الموجب لإعادة القراءة/الاختبار |
|---|---|
| اختبار وحدة نقي | شيفرة/مدخلات/اعتماديات/أمر/بيئة تغيّرت |
| اختبار تكامل | أعلاه، وإصدارات الخدمات وبيئة البيانات والعقود المستهلكة |
| guard مرتبط بـ merge-base | تغير `base_head` أو `merge_base` أو السياسة المحتسبة |
| GitHub PR، CI، mergeability | يُقرأ مباشرةً قبل قرار الدفع/الدمج؛ snapshots لا تكفي |
| Railway أو خدمة خارجية | اقرأ deployment/service revision والبيئة الحية عند اتخاذ الإجراء |
| تحليل/مستند | نسخة الملفات والمراجع/المصادر التي بُني عليها الاستنتاج |

## تخطيط الاختبارات المتقطعة

1. **قبل التشغيل:** خزّن `shard-plan.json` بترتيب ثابت لوحدات الاختبار ومعرفاتها، وتخطيط مراحل preflight وتبعية كل مرحلة (المسارات، policy, base), والحدود الزمنية والتخزينية. احفظ بصمة الخطة. الأفضل تقسيم ملفات الاختبارات كاملة عند الإمكان، ولا تفصل fixture تشارك حالة بلا عزل.
2. **عند الإطلاق:** اكتب `RUN_STARTED` مع `work_id`, `shard_id`, `attempt_id`, `command_digest`, `run_id` حال إرجاعه، وخريطة `result_uri`. `run_id` مؤشر للبحث وليس دليلاً أن العملية ما زالت حية.
3. **عند النهاية:** خزّن إيصالاً منفصلاً `shard-receipt.json` يشمل: `exit_code`, PASS/FAIL/SKIP/XFAIL/XPASS/errors, collection hash، `start/end`, ولأدلة النجاح رابطاً وبصمة. تجنّب أخذ رموز Python subprocess exit codes من سطر stderr وحده.
4. **بعد الانقطاع:** تحقق من إنهاء العملية، وعدم التداخل، ومفتاح الصلاحية لكل إيصال. تابع `INTERRUPTED` أو `NOT_RUN` أو `STALE` فقط. لا تعِد `PASSED` صالحاً إلا إذا اشترطت بوابة المشروع تشغيلاً متصلاً لا يمكن تفكيكه.
5. **الحكم:** `SHARDED_VERIFICATION` من مجموعة إيصالات؛ لا يساوي `CONTIGUOUS_PREFLIGHT`. حتى مع نجاح جميع الوحدات، اجعل الامتياز متناسباً مع الشاهد وبوابة المشروع.

### preflight بمراحل 0–7

لا تُعِد المراحل 0–7 عندما تكون نتائجها `VERIFIED_CURRENT` ومدخلاتها ذات العلاقة لم تتغير. إذا تغير `main` وكان فحص gate01 يعتمد على merge-base، أعد *هذا الفحص* ولو لم تتغير الشجرة. إذا أصر عقد preflight على تشغيل كامل متصل، لا تُغيّر العقد عبر التقسيم: احتفظ بالشواهد المجزأة لكن الحالة `PREFLIGHT_CONTIGUOUS_NOT_PROVEN`.

## تزامن موارد الحاسب

- حدد ميزانية مفيدة للمساحة وزمن التنفيذ وعدد العمليات لكل مورد؛ راقب مساحة القرص قبل تشغيل PGlite/Postgres أو اختبارات تولّد عدداً كبيراً من الملفات.
- امنع كتابة ملفات المصدر بالتزامن مع بناء أو اختبار حساس لتغير الشجرة؛ العزل باستخدام Git worktrees مفيد، لكن worktrees **لا تمثل قفلاً موزعاً**.
- داخل GitHub Actions، استخدم `concurrency` لمجموعات صحيحة في نفس المستودع. لا تضع `cancel-in-progress: true` لعمل لا يمكن قطعه بأمان؛ أسماء المجموعة يجب أن تراعي اسم workflow/mode كي لا تلغي تشغيلًا غير متعلق.
- راقب `skipped`, `xfail`, `xpass` كما هي؛ لا تُضاف إلى passed.

## مصادر أصلية

- Bazel remote caching: https://bazel.build/remote/caching — أو https://github.com/bazel-contrib/bazel-docs/blob/main/remote/caching.mdx (content-addressable action cache).
- Prefect caching: https://github.com/PrefectHQ/prefect/blob/main/docs/v3/concepts/caching.mdx — cache keys + persistent results.
- GitHub required checks: https://docs.github.com/en/pull-requests/how-tos/merge-and-close-pull-requests/troubleshooting-required-status-checks
- GitHub concurrency: https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-workflow-concurrency
- Git worktrees: https://git-scm.com/docs/git-worktree.html
