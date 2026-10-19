# دراسة مقارنة للممارسات التقنية — 2026-10-19

هذه مراجعة لمصادر أصلية وتقنيات منشورة، **وليست ادعاء** بأن الحزمة الصغيرة تعيد تنفيذ محركات Temporal أو LangGraph أو تحقق ضماناتها.

## مصفوفة الاستخلاص

| المصدر | السلوك المُثبت في المصدر | الفكرة المتبناة في UWRP v3 | القيد |
|---|---|---|---|
| Temporal event history [T1] | تاريح أحداث durable واستعادة workflow بتشغيل replay بعد crash | حدث صغير لكل انتقال + snapshot قابل لإعادة البناء | ملفات JSONL محلية لا تحقق متانة Temporal Server |
| Temporal Activities [T2] | activity lifecycle/retries وقد يعاد العمل بعد timeout | نتيجة خارجية UNKNOWN قبل المصالحة؛ لا retry أعمى | لا يضمن exactly-once في نظام ثالث |
| LangGraph persistence [L1] | Checkpointer لكل thread وStore عابر للـthreads | فصل حالة جلسة العمل عن مخزن حالة دائم عبر الجلسات | InMemorySaver لا يصمد أمام إعادة تشغيل العملية |
| Prefect caching [P1] | key يُحسب من مدخلات/كود/سياق؛ يتطلب persisted result | حقول صلاحية متغيرة بحسب التبعيات + expiry للنتائج المتقادمة | digest صالح فقط للمدخلات المُعلنة |
| Bazel remote caching [B1] | action keys من الأمر/المدخلات/المخرجات/البيئة | عدم إعادة اختبار على input signature متطابق | مخرجات غير deterministic أو متغيرة خارجياً غير قابلة للتخزين الموثوق |
| GitHub Actions concurrency [G1] | يمنع متوازيات same group في المستودع نفسه مع سياسة pending/cancel | طبقات أقفال بحسب النطاق، و`cancel-in-progress` مدروس | لا يمنع جلسات cloud خارج Actions |
| GitHub Create refs [G2] | إنشاء ref جديد يعطي `201`، أخطاء مثل `409`, `422` | حجز اسم ذري استرشادي بدلاً من push fast-forward | لا يمنع العمال المنفصلين بعد القفل ولا يوفر fencing |
| Kubernetes leases [K1] | Lease لتنسيق leader election وrenewal | اعتبار lock هوية/جيل/نبض لا وقتاً بسيطاً | مدة TTL أو عمر PID لا يثبت غياب writer القديم |
| Microsoft Idempotent Consumer [M1] | dedupe stable key، atomic unique record، side-effect reconciliation | `operation_id` + readback + `EFFECT_UNKNOWN_RECONCILE` | مفتاح العميل وحده لا يضمن exactly-once |
| Microsoft Transactional Outbox [M2] | event مسجّل مع تغير business state في transaction واحدة | تشجيع transactional writes للأحداث الحرجة | JSON state + journal ليسا معاملة قاعدة بيانات |
| Agent Skills standard [A1] | `SKILL.md` minimal مع `references/`, `assets/`, `scripts/` تُفتح عند الحاجة | Skill رئيسي قصير + ملفات متخصصة | agent-specific discovery/setup تختلف حسب البيئة |
| GitHub branch protection/merge queue [G3] | Status checks على head/merge queue وstrict base handling | Fresh gate lookup وbase_head + merge_base | CI subset لا يعني accept/deploy |
| SLSA provenance [S1], GitHub attestations [G4] | إثبات مصدر بناء artifacts بهوية ومنصة | تمييز SHA256 عن صحة مصدر/بناء ورفع مستوى الثقة بالـattestation | hash بلا توقيع ليس مصادقة على منشئ الملف |
| NIST SSDF [N1], GitHub untrusted contexts [G5] | ضوابط سلاسل التوريد والإجراءات الأمنية والمُدخلات غير الموثوقة | state/handoff مصدر بيانات لا تعليمات؛ موافقات خارجية | scanner لا يكشف كل تسريب بيانات |
| GitHub retention settings [G6] | للـartifacts/logs مدد احتفاظ قابلة للضبط | سياسة حجم ومدة لكل مشروع وحماية أدلة القبول | سياسات المستودع قد تحد الحد الأعلى |
| Git worktrees [W1] | worktrees متعددة لكل مشروع مع HEAD مستقل | عزل الملفات أثناء العمل المتزامن | مراجع Git مشتركة ولا يحل محل قفل العمليات |

## لماذا ليس إطار orchestration جديداً؟

المطلوب Skill نُدخلها مع أي وكيل أو مهمة؛ لا يوجد ضمان transaction عبر جميع الأنظمة الخارجية، ولا يمكن فرض distributed lease على مزود لا يدعمه. لذلك:

- **L0** دون حالة دائمة إذا لم يوجد خطر إعادة عمل أو أثر خارجي.
- **L1** حالة صغيرة، evidence receipts، checkpoint، backup بإذن.
- **L2** حجز وحماية مورد وحساب identity/epoch وتأكيدات مستقلة، أو استخدام Temporal/Prefect/نظام موجود عند الحاجة. عند غياب الحماية لا ينفذ الكاتب عمليات متزامنة خطرة.

## تحسينات تصميم مهمة

1. **فصل الثقة عن النتيجة**: `RECORDED_UNVERIFIED` تعني وجود ادعاء فقط، و`VERIFIED_CURRENT` تعني إسنادًا حديثًا بمصدر أصلي، ولا يكفي ذلك لوحده لاستنتاج التفويض.
2. **فصل الأثر عن الاستجابة**: نتيجة HTTP 202 ليست اكتمالاً؛ وnetwork timeout ليس فشلاً مؤكداً.
3. **فصل النسخ عن الاعتماد**: النسخة المرفوعة backup فقط بعد مقارنة محتواها، ونتائج الاختبارات `scope-limited`, لا شهادة إنتاج.
4. **محفظة مخرجات صغيرة**: لا تحفظ 18 MB محادثات أو logs خام على فروع النسخ؛ ملفات handoff/snapshot المنقحة فقط ومراجع لا تسرّب tokens.
5. **عدم محو العقد السابقة**: احتُفظ بـv2.1 حرفياً تحت references؛ v3 طبقة تطبيق تتقدم في الوضوح والأمان.

## قائمة المصادر الرسمية

[T1] Temporal — Event History: https://docs.temporal.io/encyclopedia/event-history
[T2] Temporal — Activity Execution: https://docs.temporal.io/activity-execution
[L1] LangGraph — Persistence: https://docs.langchain.com/oss/python/langgraph/persistence
[P1] Prefect — Caching: https://github.com/PrefectHQ/prefect/blob/main/docs/v3/concepts/caching.mdx
[B1] Bazel — Remote Caching: https://github.com/bazel-contrib/bazel-docs/blob/main/remote/caching.mdx
[G1] GitHub Actions — Workflow concurrency: https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-workflow-concurrency
[G2] GitHub REST — Create a reference: https://docs.github.com/en/rest/git/refs
[K1] Kubernetes — Leases: https://kubernetes.io/docs/concepts/architecture/leases/
[M1] Microsoft — Idempotent Consumer: https://learn.microsoft.com/en-us/azure/architecture/patterns/idempotent-consumer
[M2] Microsoft — Transactional Outbox: https://learn.microsoft.com/en-us/power-platform/architecture/reference-architectures/transactional-outbox-pattern
[A1] Agent Skills specification: https://agentskills.io/specification
[G3] GitHub — Branch protection: https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches
[S1] SLSA — Build provenance: https://github.com/slsa-framework/slsa/blob/main/spec/build-provenance.md
[G4] GitHub — Artifact attestations: https://docs.github.com/en/actions/concepts/security/artifact-attestations
[N1] NIST — SSDF SP 800-218: https://csrc.nist.gov/pubs/sp/800/218/final
[G5] GitHub — Script injections: https://docs.github.com/en/actions/concepts/security/script-injections
[G6] GitHub — Managing Actions settings and retention: https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/enabling-features-for-your-repository/managing-github-actions-settings-for-a-repository
[W1] Git — git-worktree: https://git-scm.com/docs/git-worktree.html
