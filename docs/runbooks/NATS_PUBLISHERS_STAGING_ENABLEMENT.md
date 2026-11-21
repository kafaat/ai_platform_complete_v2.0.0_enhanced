# تفعيل `FEATURE_NATS_PUBLISHERS` في staging (W3-01)

**النطاق:** staging وحده، بقرار المالك في 2026-11-16. الإنتاج موافقةٌ منفصلة لم تُعطَ. هذا الدليل
لا يغيّر Railway ولا يقلب العلم في أيّ ملفّ: compose وHelm و`.env.example` تبقيه `false`،
ويحرس ذلك `test_compose_keeps_the_flag_off_for_both_platform_and_worker`
(`services/sahool-platform/tests/test_nats_staging_enablement.py`).

**الفجوات المرتبطة:** `events-1` و`events-11` و`x-7` في خطّة التدقيق ·
`JETSTREAM-STREAM-TOPOLOGY-OWNED-BY-A-CONSUMER-01` ·
`OUTBOX-RELAY-MARKS-SENT-WITHOUT-JETSTREAM-ACK-01` (الناشر صار مُقِرّاً) ·
`PLATFORM-STARTUP-HANGS-ON-FIRST-NATS-CONNECT-01` (أوّل اتّصالٍ محدود بمهلة منذ #1322؛ شاهدُه
`services/sahool-platform/tests/test_nats_relay_bounded_startup.py`، والصفُّ في
`sahool-brain/gaps/registry.md` ما زال `open` حتّى شاهدٍ تنفيذيّ على بيئةٍ حيّة، وهذا التفعيل
فرصةُ ذلك الشاهد).

## ما الذي يتغيّر حين يُقلَب العلم

| المكوّن | العلم مطفأ (الافتراض) | العلم مُفعَّل |
|---|---|---|
| المنصّة (`OutboxWorker`) | لا يتّصل بـNATS. كلُّ حدثٍ يبقى في `event_outbox` بحالة `pending` | يتّصل (أوّل اتّصالٍ محدود)، ثمّ يشغّل **preflight**، ولا يبدأ الـrelay قبل أن يمرّ |
| `/readyz` | `nats_preflight.status = disabled`، والرمز لا يتأثّر | 503 حتّى يمرّ الـpreflight ويبدأ الـrelay أوّلَ مرّة. بعدها يبقى 200، وفحصٌ لاحقٌ فاشل يُعلَن `degraded` (يُعاد الفحص كلَّ ≤30 ثانية عند النجاح و≤5 عند الفشل، وكلُّ تشغيلٍ محدودٌ كلّيّاً بـ`NATS_PREFLIGHT_TIMEOUT_SECONDS`، افتراضُه 5) |
| `/readyz.outbox` | `held` و`replay_on_enable` وتحذيرٌ صريح بأنّ التفعيل سيُعيد نشر المعلَّق | `held` يتناقص مع التصريف |
| عامل التعلّم (`--preflight`، فحصُ صحّة الحاوية) | **غير جاهز** (`publishers_disabled`): لا شيءَ يصله | جاهزٌ إن وُجدت الجداول وغطّى الدفقُ مواضيعَه |

**لماذا لا يبدأ الـrelay قبل الـpreflight:** بلا دفق يرفع `js.publish` لكلّ صفّ، و`OutboxWorker`
يعطي كلَّ صفٍّ خمسَ محاولاتٍ بتراجعٍ 2 ثم 4 ثم 8 ثم 16 ثم 32 ثانية. فكان التراكمُ كلُّه سيصير
رسائلَ ميتة خلال دقيقةٍ تقريباً من التفعيل. البوّابة (`NATS_PREFLIGHT.gate` في
`shared/nats_stream_contract.py`) تُبقي الصفوف `pending` بمحاولاتها كاملة حتّى توجد البنية.

## 1. قبل التفعيل

1. **اقرأ التراكم** والعلمُ ما زال مطفأً:
   `curl -s https://<staging-platform>/readyz | jq .outbox`
   - `held`: عدد الأحداث التي **ستُعاد كلُّها** إلى NATS لحظة التفعيل، و`oldest_held_age_seconds` عمرُ أقدمها.
   - `scope` يجب أن يكون `all_tenants`. القيمة `tenant_scoped_undercount` تعني أنّ المسبار يقرأ بدورٍ
     خاضعٍ لـRLS (v72) فيرى صفراً لغير مستأجِره. اضبط `JOBS_DATABASE_URL` على دور `sahool_jobs` قبل المتابعة.
   - `dead_letter` يجب أن يكون صفراً، أو مفهوماً ومُعالَجاً عبر `/api/v1/admin/events/dead-letter`.
   - قرِّر هل يُعاد نشرُ تراكمٍ قديم. المستهلكون يتحمّلون الإعادة بـ`event_id`
     (`processed_events` ونافذة تكرار JetStream)، لكنّ حدثاً عمرُه أسابيع قد يُطلق إشعاراً بائتاً.
     هذا قرار تشغيل، والدليل لا يتّخذه نيابةً عنك.
2. **أنشئ الدفق من العقد التصريحيّ** (إنشاءٌ فقط، لا تعديل ولا حذف)، بهويّة مالك الدفق
   `sahool-notification-agent` (وحدها تملك `$JS.API.STREAM.CREATE.sahool`):
   ```bash
   NATS_URL='tls://sahool-notification-agent:<from-secret-store>@sahool-nats:4222' \
     python -m shared.nats_stream_contract plan    # قراءة فقط: would_create أو drift
   NATS_URL='…نفسه…' python -m shared.nats_stream_contract apply   # ينشئ إن غاب
   ```
   دفقٌ قائمٌ يخالف `STREAM_SPEC` يُبلَّغ `drift` بالحقل ورمزِ خروج 1، ولا يُعاد كتابتُه.
   تغييرُ الاحتفاظ قرارُ مالك. وفي وضع `NOTIFICATION_CONSUMER_MODE=legacy` ينشئ الوكيلُ الدفقَ نفسَه
   عند إقلاعه من `stream_config()` ذاتها، فالمساران يُنتجان الإعداد نفسَه.
3. **تأكّد من المستهلكين المطلوبين** (`required_consumer_groups()` في `shared/nats_stream_contract.py`):
   - `notif_domain_events` أو `notif_domain_events_queue_v1`: مطلوبٌ دائماً (وكيل الإشعارات، أو
     `shared.notification_consumers --apply` في `queue_v1`).
   - الثلاثة لعامل التعلّم (`canonical-execution-learning-v1-*`). **`apply` لا ينشئها؛ ينشئها العامل
     نفسُه حين يعمل.** فتحقّق أوّلاً أنّ خدمة `sahool-canonical-execution-learning-worker` **منشورةٌ فعلاً**
     في staging. اللقطة المحفوظة في المستودع (`docs/architecture/railway_watch_patterns.json`، 2026-10-26)
     لا تذكر خدمةً للعامل، وHelm لا يعرّفها. فإمّا:
     - **(أ) انشر العامل أوّلاً** (والعلمُ مطفأ ما زال، فـ`--preflight` الخاصّ به يقول `publishers_disabled`،
       وهذا متوقَّع)، ثمّ تحقّق من وجود الثلاثة بالخطوة 4. هذا هو المسار الافتراضيّ
       (`NATS_PREFLIGHT_LEARNING_WORKER=required`)؛
     - **(ب) أو صرِّح على المنصّة بأنّه غير منشور:** `NATS_PREFLIGHT_LEARNING_WORKER=not_deployed`. حينها
       لا يطلب الـpreflight مستهلكي العامل، ويُعلَن الاختيار في كلّ نتيجة (`learning_worker.mode`) وفي
       `/readyz` (`learning_worker_mode`). الأحداث تُنشَر وتُحفظ في الدفق (احتفاظٌ بلا حدّ عمر)، وحين يُنشَر
       العامل لاحقاً تبدأ مستهلكاته من أوّل رسالة مخزّنة (`DeliverPolicy.ALL`، افتراضُ nats-py عند الإنشاء)،
       فلا يفوته شيء. أزِل المتغيّر بعد نشر العامل. أيُّ قيمةٍ أخرى تُفشل الـpreflight مغلقاً.
   - **اسمٌ أساسيّ غير الافتراضيّ** (`CANONICAL_LEARNING_DURABLE` على العامل): اضبطه بالقيمة نفسها على
     المنصّة، فالـpreflight يقرأ المتغيّر نفسَه. لكنّ `nats/nats.conf` يمنح المنصّة `CONSUMER.INFO`
     على الأسماء الافتراضيّة وحدها، فاسمٌ جديد يحتاج تعديل الـACL أوّلاً، وإلّا رفض الوسيطُ الفحص وقرأه
     الـpreflight «مستهلكاً غائباً» (ونتيجته تحمل `learning_worker.acl_note` تشرح ذلك).
   - **لا تقلب العلم والـpreflight يفشل في staging على Railway:** فحصُ صحّة نشر `sahool-platform` هو `/readyz`
     (`certification/evidence/railway_reconciliation_readonly_20261014.json`)، و`/readyz` يعيد 503 ما دام
     الـpreflight لا يمرّ، فلا يصير النشرُ حيّاً. الخطوة 4 تمنع ذلك.
4. **شغّل الـpreflight يدويّاً بهويّة المنصّة** (صلاحيّاتها في `nats/nats.conf` قراءةٌ فقط لهذه الأسماء):
   ```bash
   NATS_URL='tls://sahool-platform:<from-secret-store>@sahool-nats:4222' \
   NATS_INBOX_PREFIX=_INBOX_sahool-platform \
     python -m shared.nats_stream_contract preflight
   ```
   المطلوب `"status": "passed"`. الخرجُ يذكر وجودَ الاعتماد قيماً منطقيّة (`user_present` و`password_present` و`tls`) ولا يطبع قيمتَه.

## 2. التفعيل

**شرطٌ مسبق:** الخطوة 4 أعطت `"status": "passed"` بالبيئة نفسها التي ستعمل بها المنصّة
(بما فيها `NATS_PREFLIGHT_LEARNING_WORKER` إن ضُبط).

اضبط `FEATURE_NATS_PUBLISHERS=true` لـ`sahool-platform` و`sahool-canonical-execution-learning-worker`
معاً في staging (أو للمنصّة وحدها في المسار (ب) أعلاه)، ثمّ أعِد تشغيلهما. العامل يقرأ العلمَ نفسَه،
فتفعيلُ أحدهما دون الآخر يُبقي العامل غير جاهز أو يُبقي المنصّة صامتة.

المتوقَّع في الدقائق الأولى:
- سجلّ المنصّة: `NATS preflight passed` ثمّ `OutboxWorker بدأ`. وإن ظهر
  `NATS preflight failed (…) — relay held` فالـrelay لم يبدأ والصفوف سليمة. أصلِح السبب المذكور
  (`stream_info:*` أو `consumer_missing:*` أو `stream_drift`) وسيبدأ وحده خلال ≤30 ثانية بلا إعادة تشغيل.
- `/readyz`: يصير 200 و`nats_preflight.status = passed`. و`failed` مع `preflight_timeout` تعني أنّ الفحص كلّه
  تجاوز `NATS_PREFLIGHT_TIMEOUT_SECONDS` (غالباً وسيطٌ يُسقط طلب `CONSUMER.INFO` بصمت لأنّ `nats.conf` قديم)؛
  الـrelay محجوز والإقلاع لا ينتظر أكثر من هذه المهلة. القيمة `pending` مع `relay_not_started_yet` تعني
  أنّ البنية موجودة والـrelay يبدأ الآن؛ و`failed` مع `relay_start` تعني أنّ بدء العامل نفسه فشل (التفصيل
  في السجلّ، ويُعاد المحاولة). `/readyz` غير مُصادَق، فيعرض الحكم ورموز الأخطاء وأعداد المستهلكين فقط؛
  الأسماء والانحراف والاعتماد في سجلّ المنصّة وفي `python -m shared.nats_stream_contract preflight`.
- **إعادة التراكم:** `outbox.held` يتناقص نحو الصفر بدُفعاتٍ من 50 صفّاً متتالية بلا انتظار ما دام في الصندوق معلَّق.

## 3. نافذة المراقبة (48 ساعة على الأقلّ)

المقاييس على `/metrics` (Prometheus):

| المقياس | المتوقَّع |
|---|---|
| `sahool_platform_nats_publishers_enabled` | 1 |
| `sahool_platform_nats_preflight_passed` | 1، إلّا لحظاتِ إعادة تشغيل الوسيط (انظر تحت الجدول) |
| `sahool_platform_outbox_held` | ينزل إلى ما يقارب الصفر ويبقى قريباً منه |
| `sahool_platform_outbox_oldest_held_age_seconds` | ثوانٍ لا دقائق بعد التصريف |
| `sahool_platform_outbox_dead_letter` | 0. أيُّ زيادة تستوجب الفحص |
| `sahool_platform_outbox_backlog_all_tenants` | 1 |
| `sahool_platform_outbox_backlog_probe_ok` | 1 |

**انقطاع الوسيط بعد بدء الـrelay لا يُسقط الجاهزيّة.** المنصّة تفشل مغلقةً حتّى يبدأ الـrelay أوّلَ مرّة فقط.
بعدها، إن أُعيد تشغيل NATS أو انقطع الاتّصال، يقرأ الفحصُ التالي `not_connected` فيصير
`/readyz.nats_preflight.status = degraded` مع `relay: started` ورموز الأخطاء، ويبقى رمزُ `/readyz` 200، وينزل
`sahool_platform_nats_preflight_passed` إلى 0 ريثما يعود الاتّصال. الأحداث في هذه المدّة تبقى في `event_outbox`
ويصرّفها الـrelay حين يعود الوسيط. لو أسقطت الجاهزيّةُ كلَّ انقطاع لخرجت كلُّ نُسخ المنصّة من الخدمة مع كلِّ إعادة
تشغيلٍ للوسيط، وهي لا تحتاجه لخدمة الطلبات. `degraded` يدوم أكثر من دقائق يستوجب الفحص (`nats` في `/readyz`
يقول `reconnecting`). ومسبارُ التراكم في `/readyz` و`/metrics` يُخبَّأ 5 ثوانٍ، فقيمُه قد تتأخّر حتّى 5 ثوانٍ.

**`degraded` لا يعني دائماً انقطاع الوسيط.** حين يقول `nats` في `/readyz` `up` لا `reconnecting`، فشيءٌ في
الطوبولوجيا تغيّر بعد البدء، والـrelay لا يُعاد احتجازه داخل العمليّة نفسها. وقد يتأخّر ظهور `degraded` حتّى ~30
ثانية لأنّ نتيجة الفحص الناجح تُخبَّأ. `/readyz` يقطع الرمز عند `:`، فاقرأ نوع الاستثناء الكامل في سجلّ المنصّة، أو
شغّل `python -m shared.nats_stream_contract plan` (و`preflight`) قبل أيّ إجراء:

- `stream_info`: يجمع ثلاث حالات: دفقٌ مفقود، أو رفضُ صلاحيّة، أو مهلةُ 3 ثوانٍ لاستدعاءٍ بطيء. **فقط إن ثبت أنّ
  الدفق مفقود** يفشل كلّ نشر، فتنتقل الصفوف المحتجزة إلى الرسائل الميتة خلال دقيقة تقريباً (5 محاولات بتراجعٍ
  أُسّيّ) ويبقى `/readyz` 200. افحص `sahool_platform_outbox_dead_letter` فوراً، ثمّ أعِد `FEATURE_NATS_PUBLISHERS`
  إلى false أو أنشئ الدفق بالخطوة 2 (`apply`). أمّا المهلة فوسيطٌ بطيء، والرفض صلاحيّاتٌ تغيّرت: لا تُعِد التجهيز لهما.
- `stream_does_not_cover_platform_events`: مواضيع الدفق لم تعد تغطّي `sahool.events.*`، فالنشر لا يجد مستجيباً
  ويفشل، وتنتقل الصفوف إلى الرسائل الميتة كما في الدفق المفقود. صحّح المواضيع بقرار مالك (`apply` لا يعدّل دفقاً قائماً).
- `consumer_missing`: مستهلكٌ دائمٌ مطلوبٌ مفقود، **أو** رُفض الاستعلام عنه، أو تجاوز مهلة 3 ثوانٍ (الفحص لا يميّز بينها):
  أحد مستهلكي عامل التعلّم، أو مستهلك الإشعارات (`notif_domain_events` / `notif_domain_events_queue_v1`). شغّل
  `preflight` بهويّة المنصّة (الخطوة 4) واقرأ السجلّ الكامل قبل إعادة تشغيل أيّ شيء. إن ثبت أنّه مفقود: النشر ينجح
  والأحداث تتراكم في الدفق بلا قارئ.
  **`apply` لا ينشئ المستهلكين.** مستهلكو التعلّم ينشئهم العامل حين يشترك: أعِد تشغيل
  `sahool-canonical-execution-learning-worker` أو أعِد نشره؛ ويُعاد إنشاء المستهلك بسياسة التسليم الافتراضيّة
  (من أوّل رسالة مخزّنة)، فتوقّع إعادة تشغيل كلّ ما في الدفق على العامل. ومستهلك الإشعارات: أعِد تشغيل وكيل
  الإشعارات في `legacy`، أو في `queue_v1` أعِد بناء الخطّة بـ`shared.notification_consumers` ثمّ `--apply`. هذا المسار يحتاج أن تكون مستهلكات
  `notif_*` القديمة التسعة ما زالت موجودة، ويبدأ بعد حدّ إقرارها، فتوقّع إعادة كلّ ما خُزّن منذ الترحيل.
- `stream_drift`: حقلٌ من `STREAM_SPEC` يخالف الدفق القائم (المواضيع، الاحتفاظ `retention`، التخزين، `discard`، النسخ، نافذة التكرار،
  حدود `max_*`). بعض الانحراف يغيّر سلوك النشر (حدٌّ محدود مع `discard: new` يفشل النشر عند بلوغه)، فاقرأ قائمة
  `drift` من `plan` قبل الحكم. تصحيحه قرار مالك.
- `preflight_timeout`: الفحص كلّه تجاوز مهلته؛ وسيطٌ بطيء أو رفضٌ صامت لطلبات `$JS.API`. النشر قد ينجح. راقب
  الرسائل الميتة وزمن الاستجابة قبل أيّ إجراء.

وفي الوسيط: رسائل `sahool.dlq.canonical_execution_learning` (رسائل عامل التعلّم الميتة) يجب أن تبقى صفراً،
وتأخّر المستهلكين (`num_pending`) يعود إلى الصفر. شاهدُ القبول الوظيفيّ: حدث `season.closed` حقيقيّ
يصل إلى العامل ويُنتج صفّ `decision_learning_runs`.

## 4. التراجع

1. اضبط `FEATURE_NATS_PUBLISHERS=false` للخدمتين وأعِد تشغيلهما. لا شيء يُفقَد: الأحداث الجديدة تبقى
   في `event_outbox` بحالة `pending`، و`/readyz.outbox` يعود يعلن ما سيُعاد عند التفعيل التالي.
2. **لا تحذف الدفق ولا تُفرِّغه.** لا هويّة تملك ذلك (`test_live_nobody_can_destroy_or_read_around_the_stream`)،
   والرسائل المخزّنة هي ما يستأنف منه المستهلكون.
3. الرسائل الميتة في `event_outbox` تُفحص وتُعاد جدولتها عبر
   `/api/v1/admin/events/dead-letter` و`…/{outbox_id}/requeue` بعد إصلاح السبب.

## ما يثبته هذا ولا يثبته

- **مُثبَت بمكوّنات حقيقيّة:** `tests_v9/test_nats_outbox_staging_enablement_live.py` على PostgreSQL 16
  مُرحَّلة وnats-server 2.15.0. يثبت أنّ الحدث يبقى معلّقاً والعلمُ مطفأ مع تحذيرٍ بالإعادة، وأنّ البوّابة لا تبدأ
  الـrelay بلا دفق، وأنّ النشر الفاشل يُعاد لا يُفقَد. وبعد إنشاء الدفق من العقد يصل الحدث مرّةً واحدة، وإعادتُه
  بعد تعطّلٍ بين PubAck والوسم تُسقطها نافذة التكرار فلا يُخزَّن ثانيةً ولا يصل المستهلكَ ثانيةً، **بشرط أن تقع
  الإعادة داخل `duplicate_window` (120 ثانية في `STREAM_SPEC`)**.
  وفي `tests_v9/test_nats_least_privilege.py`: preflight المنصّة بهويّتها وبـTLS يمرّ بلا خرق صلاحيّة،
  والمنصّة لا تستطيع إنشاء الدفق، وإعادةُ نشر حدثٍ بالـ`Nats-Msg-Id` نفسه على الدفق المُنشأ من العقد تُخزَّن
  مرّةً وتصل المستهلكَ مرّةً. هذا الملفّ يعمل على nats-server حقيقيّ في CI (`notification-rollout.yml`)،
  أمّا الاختبار الأوّل فيحتاج PostgreSQL مُرحَّلة ووسيطاً معاً، ولا وظيفة CI تجمعهما بعد، فيتخطّى هناك.
- **غير مُثبَت:** إعادةٌ بعد أكثر من 120 ثانية من النشر الأوّل (تعطّلٌ ثمّ إعادة تشغيلٍ وpreflight أطول من النافذة)
  يخزّنها الدفق ويسلّمها ثانيةً؛ عندها لا يمنع التكرارَ إلّا تحمّلُ المستهلك بـ`event_id` (`processed_events`).
- **غير مُثبَت:** سلوك staging نفسه. لم يُشغَّل هنا أيُّ شيء على Railway. وتدفّق الأحداث بأحجام حقيقيّة،
  وسلوك المستهلكين مع تراكمٍ قديم، يقيسهما هذا الدليل ولا يدّعيهما.
  والـpreflight يثبت وجود المستهلك الدائم ولا يثبت أنّ عمليّته حيّة.
