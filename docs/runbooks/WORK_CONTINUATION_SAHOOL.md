# UWRP Portable v3.1 — طبقة SAHOOL (مكمّلة لا بديلة)

المهارة العامّة في `.claude/skills/work-continuation/` (UWRP Portable v3.1، محايدة للوكيل والمشروع) مورَّدة بايتاً ببايت ويُتحقَّق منها بـ`SHA256SUMS` داخلها، فلا تُحرَّر. هذه الوثيقة هي الطبقة الخاصّة بهذا المستودع، وكلّ بند فيها واقعة قيست في 2026-10-19. ومستوى العمل في هذا المستودع لأيّ دمج أو دفع أو نشر هو `COORDINATED`. ترتيب السلطة: تعليمات المالك الحاليّة، ثمّ `CLAUDE.md` وبروتوكول البوّابات، ثمّ هذه الطبقة، ثمّ المهارة العامّة.

## 1. الموافقة مربوطة برأس

موافقة المالك على دمجٍ تخصّ SHA بعينه. سجّل نصّها والرأس الذي تسري عليه. فإذا تغيّر الرأس (دفعٌ جديد أو مزامنة مع main)، فالموافقة **لاغية** حتى تُجدَّد، ولو كان الفرق ملفّات مولَّدة فقط. الدمج دائماً بـ`expectedHeadSha`.

## 2. حالة التشغيل ليست الدماغ

`state.json` حالة تشغيل مؤقّتة لعملٍ واحد، خارج الشجرة. أمّا `sahool-brain/` (hot/log/ledger/registry) فهو السجلّ المعرفيّ الدائم بقواعده (log/ledger إلحاق فقط، hot إضافة في الأعلى فقط، registry لا يتقلّص، أعداد U+200F ثابتة). لا يُنسخ أحدهما في الآخر. ما يستحقّ البقاء يُكتب في الدماغ بمصدره عند نهاية الجلسة.

## 3. قفل preflight لكلّ worktree

`scripts/ci/preflight.sh:78-80` يقفل `$(git rev-parse --git-dir)/preflight.lock`، فلا يمنع تشغيلتين في worktree مختلفين على الجهاز نفسه (قيس أكثر من 30 worktree في جلسة واحدة). للأعمال الثقيلة استعمل قفلاً في `$(git rev-parse --git-common-dir)`. يتّصل هذا بـ`LESSON-CONCURRENT-PREFLIGHT-CONTAMINATION-01`.

## 4. الأفعال الخارجيّة: قارن ثم بدّل

- الدمج بـ`expectedHeadSha`.
- الدفع إلى فرع مشترك تقدّم مباشر فقط، بعد التحقّق من أنّ الرأس البعيد ما زال الرأس المتوقَّع.
- الكتابة فوق فرعٍ خاصّ بالوكيل بـ`--force-with-lease=<ref>:<sha>`.

## 5. النسخ الاحتياطيّ

`secret-history-scan.yml` يجلب التاريخ كاملاً (`fetch-depth: 0`)، فالمفضَّل مستودع خاصّ منفصل (`references/STORAGE_AUTHORITY.md` في المهارة). إن تعذّر ذلك، فالفرع orphan بلا `.github/`، ويحمل `state.json` و`HANDOFF.md` منقّحين فقط، ويُرفع بـcommit-tree وفهرس مؤقّت دون checkout.

## 6. اختبر أداة الاستئناف قبل الثقة بها

`addopts` في هذا المستودع تغيّر معنى `pytest -q --collect-only`، فيصير الخرج شجرة لا معرّفات. قيس هذا الخطأ: جمع 149 «حالة» وهميّة بدل 10074. اجمع المعرّفات من `session.items` عبر plugin، وطابق العدد بعدد pytest قبل تشغيل الدفعات.

## 7. التوازي

`pytest -m unit -n auto` يفشل في الجمع («Different tests were collected between gw1 and gw0»). الدفعات بالملفّات تتجنّبه لكنّها `SHARDED_VERIFICATION` لا `CONTIGUOUS_PREFLIGHT`.

## 8. حجب الأذونات

في جلسات السحابة قد يحجب مُصنِّف الأذونات حذف فرع أو دمجاً رغم تفويضٍ عامّ. لا يُلتفّ على الحجب: سجّل `BLOCKED_BY_PERMISSION` مع ما يلزم للاستعادة (SHA، أو bundle محلّيّ)، وأعد القرار إلى المالك.

## 9. ruff والحزمة المورَّدة

`ruff.toml` يستثني `.claude/skills` لأنّ إعادة تنسيق الحزمة تكسر بصماتها. فحصها بأداتها: `python3 -I -B .claude/skills/work-continuation/scripts/validate_package.py`، واختباراتها 18 (`tests/test_contracts.py`)، ومطابقتها للمواصفة بـ`agentskills validate` (skills-ref 0.1.1).

وفحص البصمات داخل المجلّد صارم: `sha256sum -c SHA256SUMS`، بلا `--ignore-missing`. فذلك العلَم يتخطّى الملفّ المُدرَج الغائب ويخرج بـ0 ما دام ملفٌّ واحد مطابقاً. قيس في 2026-10-20 على main@`c9e8c15e`: الملفّات المُدرَجة 21، وكلّها حاضرة، والفحص الصارم خرج بـ0. وفي نسخة حُذف منها أيّ ملفّ من الـ21، فشل الصارم ونجح `--ignore-missing`. يحرس ذلك `tests_v9/test_work_continuation_checksum_strict.py`، ويشغّل الأمر كما يكتبه `CLAUDE.md`. أمّا الملفّ الزائد غير المُدرَج فلا يكشفه `sha256sum` أصلاً، ويكشفه `validate_package.py` («manifest coverage differs»).

## 10. مسرّع الاختبارات (`.claude/skills/adaptive-test-accelerator`، v1.1)

حزمة مورَّدة بايتاً ببايت، كحزمة الاستئناف. تجربة 2026-10-19 على main@`bf0356f01` (الشجرة `de2c2ab2`):

- جرد `pytest -m unit`: 10074 حالة في 890 ملفّاً، مطابق لعدّ pytest.
- خطّة بوحدتين، قيست بـ`checkpoint_runner.py run` بعد اعتماد بصمة الخطّة `4ba1684f`:
  - `unit-00`: 282 من 282، في 39.4 ث.
  - `unit-01`: 284 من 284، في 114.3 ث.
- إعادة التشغيل نفسه تخطّت الوحدتين في 0.19 ث، و`status` أعطى `PASS_VERIFIED`، والشجرة بقيت نظيفة.

حدود الاستعمال هنا:

- **التشغيل تسلسليّ:** يمنح الاستئناف لا السرعة. أمّا التوازي فيعطّله فشل جمع xdist (§7).
- **التخطّيات:** JUnit في pytest يعدّ xfail «skipped». لذلك يُشتقّ `max_skipped` لكلّ وحدة من خطّ أساس مقيس، لا يُرفع اعتباطاً.
- **`--resume-interrupted`:** لا يفحص حياة العمليّة إذا كان مضيف علامة `inflight` مختلفاً. لا يُستعمل بين الحاويات.
- **نطاق الإيصالات:** `SHARDED_VERIFICATION` لما شُغِّل فقط، لا preflight ولا CI.

## 11. منظومة UWRP Professional v4.2 (ثماني مهارات بجوار المجمَّدتين)

مصدرها حزمة المالك v4.1 (`2e178008…`)، وحُسِّنت إلى v4.2. وأُدخلت مهارات التعلّم الثلاث من أرشيف المالك v4.3 (`2f5d0994…`) في #1242 ثمّ أُزيلت: سكربت السجلّ يقبل بيانات اعتماد (6 من 7 صيغ مقيسة)، و`draft_proposals --out` يكتب فوق أيّ ملفّ بما فيه `SKILL.md` (`UWRP-V43-LEARNING-SCRIPTS-UNSAFE-01`). المهارات هنا مطابقة لـv4.2 كما في `9a897635d`. كلّ مهارة مستقلّة في `.claude/skills/<الاسم>/`، ومركزها `work-router` (جدول التوجيه `references/routing.json`، والتحقّق `scripts/verify_pack.py`، والأبحاث). ما قيس وما لم يُقَس: `.claude/skills/work-router/references/EVALUATION_RESULTS.md`.

كلّ مهارة تقابلها آليّة هنا، ولا تحلّ محلّها:

| المهارة | الآليّة الحاكمة في هذا المستودع |
|---|---|
| `intent-to-proof` | الفجوة بمصدر وحالة في `sahool-brain/gaps/registry.md`؛ و`check_contract.py` لعقد العمل الطويل خارج الشجرة |
| `change-review` | `scripts/ci/preflight.sh` وCI على **رأس** الـPR نفسه؛ والمراجعة لا تغني عن البوّابات (§1) |
| `safe-delivery` | الدمج مثبَّت بـ`expectedHeadSha`، وتجميد الحوادث وقيود Railway في هذا الملف وCLAUDE.md |
| `collaboration-coordination` | قفل preflight لكلّ worktree لا للمستودع (§3)؛ لا تشغيلان ثقيلان معاً |
| `failure-investigation` | `docs/runbooks/GUARD_CATALOGUE.md` نقطة البدء عند فشل حارس |
| `skill-evaluator` | `trigger_eval.py` قبل تعديل أيّ وصف مهارة هنا |

والفحص: `python3 -I .claude/skills/work-router/scripts/verify_pack.py .claude/skills --require-baselines`. يتحقّق أيضاً من أنّ المهارتين المجمَّدتين مطابقتان لإصدارهما بايتاً ببايت.

**مرشّح v4.4 (`reliable-agent-execution`) لم يُثبَّت.** في الاختبار الأعمى (44 حالة، منها 9 سالبة، على نموذجين) لم يختره أيّ نموذج في أيّ حالة. والسبب أنّ `safe-delivery` و`work-continuation` يغطّيان محفّزاته. الجديد فيه صار مقترحاً على `safe-delivery` ينتظر مراجعة المالك ومقارنة قبل وبعد: مستويات إثبات القراءة الراجعة، وفئتا الأدوات `EGRESS` و`UNKNOWN`، وتسجيل نيّة الإرسال قبل الاستدعاء.
