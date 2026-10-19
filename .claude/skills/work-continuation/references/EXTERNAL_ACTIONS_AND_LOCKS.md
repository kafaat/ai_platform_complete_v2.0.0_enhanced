# الأفعال الخارجية والحجوزات الموزّعة

## نموذج العملية الخارجية (Intent → Observe → Reconcile)

عمليات الدفع والدمج والنشر والإرسال والفوترة وإلغاء الموارد ليست مجرد subprocess. يجب أن تكون قابلة للمصالحة عند ضياع استجابة الشبكة.

**التسلسل الآمن:**

1. احصل على إذن خارجي فعلي وفق سياسة المشروع؛ لا تنشئه داخل ملف حالة.
2. عرّف `operation_id` ثابتاً للعمل المنطقي (لا تغيره في retry)، و`target`، و`expected_before`، و`request_digest`، و`allowed_effect`، و`verification_plan`.
3. اقرأ الحالة الخارجية للتحقق من عدم وقوع نفس الأثر من محاولة قديمة أو وكيل آخر. عند وجود خيار أصلي للمزوّد لاستخدام Idempotency-Key، استخدمه بالطريقة الموثقة للمزوّد؛ لا تخترع API غير مدعوم.
4. سجّل `INTENT_RECORDED` قبل التنفيذ في مساحة العمل؛ وإذا كانت الاستمرارية شرطاً قبل الأثر، تحقّق من حفظ هذا القيد على مخزن دائم أو نظام معاملات معتمد قبل إرسال الطلب.
5. نفّذ مرةً فقط بعد التأكد من السلطة وحصرية المورد والـpreconditions.
6. لا تعتبر `timeout` أو `connection reset` فشلاً مؤكداً: أنشئ `EFFECT_UNKNOWN_RECONCILE`، ثم اقرأ الحالة المستهدفة (commit/ref/PR/deployment/job idempotency receipt)، ولا تعِد العملية تلقائياً.
7. سجّل `EFFECT_VERIFIED` فقط عندما يثبت النظام الهدف وقوع الأثر عند المرجع المتوقع. نتيجة `202 Accepted` تعني قبول الطلب للنظر فيه، لا اكتمال التغيير بالضرورة.
8. للعمليات غير القابلة للإعادة والمزودات التي لا تدعم idempotency أو readback، توقف عند `REVIEW_REQUIRED` أو صمّم transaction/outbox مسبقاً؛ لا تدّع exactly-once من معرف محلي.

## الحجز المحلي والموزّع

| الآلية | تصلح لـ | لا تصلح لـ |
|---|---|---|
| `flock` أو mutex | عاملان في نفس المضيف/مساحة الأقفال | حاويتان منفصلتان أو انقطاع السلطة |
| GitHub Actions `concurrency` | سير العمل في **المستودع ذاته** | وكلاء خارجيون وأعمال عبر مستودعات متعددة |
| GitHub Create ref API | المطالبة الذرية باسم ref غير مستخدم داخل GitHub | ضمان توقف كاتب قديم أو حماية مورد خارجي بعد فقد القفل |
| Lock service/DB CAS + fencing | مُنتِج واحد بملكية قابلة للتحقق وقيمة token تتزايد | الأثر الخارجي إذا لم يتحقق الهدف من token نفسه |

### مثال GitHub reservation

```text
POST /repos/{owner}/{repo}/git/refs
{"ref":"refs/heads/lock/<resource-id>","sha":"<existing-commit-sha>"}
```

`201` يعني أن الإنشاء نجح. حالات `409`/`422` تُفحص ولا تُترجم آلياً إلى "القفل محجوز". هذا **حجز اسم**، وليس lease مع heartbeat أو تسلسلاً متزايداً ولا يتجنب وحده race عند تحرير lock. يجب استخدام GitHub API عبر عميل معتمد؛ لا يُحفظ token في الحالة. إنشاء refs غير متاح في repository فارغ تماماً حتى يوجد فرع أساسي.

### stale lock / recovery

- لا تحذف قفلاً بسبب مرور 24 ساعة أو رقم PID قديم فقط. تحقق من سجل حيازته ومن الموارد التي يحميها، ومن عدم وجود عمليات وجلسات وPRs أو jobs ذات صلة عند كل منصة تستطيع فحصها.
- **عدم العثور على عملية ليس دائماً إثبات انتهاء الحائز**، لا سيما على شبكات أو بيئات لا تملك صلاحية فحص جميع العمال. إذا لم تثبت ملكية/نهاية الحائز، احتفظ بالقفل واطلب تسوية موثقة.
- إذا كان الحجز يتجدد عبر lease، فاستعادة الجلسة القديمة بعد انقضائه خطرة؛ يجب أن يرفض المورد الهدف عملياتها عبر fencing token/نسخة CAS أقدم من الحائز الجديد.
- لا تعِد إنشاء lock مع اختلاف owner identity دون حساب حالة الطلب الأصلي؛ وحين يكون إجراء تحرير مشروط غير مدعوم، لا تخاطر بحذف حجز مملوك لآخر.

### Fencing tokens عملياً

- مصدر السلطة يولّد generation/epoch تصاعدياً لكل انتقال ملكية.
- كل أمر كتابة يحمل epoch.
- المورد الذي يطبق الأثر يرفض epoch أقل من آخر epoch معتمد لديه عبر قيد ذري (DB transaction/conditional update).
- إذا لم يتحكم النظام الهدف في التحقق من epoch، فالحجز advisory فقط؛ لا تسمّه fencing.

## مصادر

- GitHub Create ref API: https://docs.github.com/en/rest/git/refs
- Kubernetes Lease: https://kubernetes.io/docs/concepts/architecture/leases/
- Temporal activity retry: https://docs.temporal.io/activity-execution
- Microsoft idempotent consumer: https://learn.microsoft.com/en-us/azure/architecture/patterns/idempotent-consumer
- Microsoft transactional outbox: https://learn.microsoft.com/en-us/power-platform/architecture/reference-architectures/transactional-outbox-pattern
