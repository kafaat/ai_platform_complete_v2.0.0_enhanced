# جرد طوبولوجيا JetStream — قياس قبل نقل الملكيّة

> **الغرض:** لا تُنقَل ملكيّة الدفق قبل جرد ما هو قائم فعلاً. نقلٌ بلا جرد قد يُعيد إنشاء
> المستهلكين أو يُغيّر مواضعهم، فيفقد كلٌّ منهم موضع قراءته.
>
> **القياس:** 2026-08-04 · nats-server v2.10.22 محلّيّاً + مسح المستودع.
> **الحالة:** جرد فقط. لا يُقرّر هذا المستند نقل ملكيّة ولا يُنفّذه.

---

## ١. الدفق الوحيد — وما يُعلنه عن نفسه

الدفق ينشأ في مكان واحد: [`agents/notification/agent.py:449`](../../agents/notification/agent.py)

```python
await _js.add_stream(StreamConfig(name="sahool", subjects=["sahool.>"]))
```

كلّ حقل عدا `name` و`subjects` **افتراضيّ ضمنيّ**. المقيس على الخادم بعد الإنشاء:

| الحقل | القيمة | ملاحظة |
|---|---|---|
| `name` | `sahool` | دفق واحد لكلّ المنصّة |
| `subjects` | `sahool.>` | يبتلع كلّ موضوع في المنصّة |
| `retention` | `limits` | لا `workqueue` ولا `interest` |
| `discard` | `old` | **لا أثر له**: يعمل عند بلوغ حدود غير مضبوطة |
| `storage` | `file` | على `nats-js:/data/jetstream` |
| `num_replicas` | `1` | لا تكرار |
| `max_age` | `0` | **لا انتهاء صلاحيّة أبداً** |
| `max_msgs` | `-1` | بلا حدّ |
| `max_bytes` | `-1` | بلا حدّ |
| `duplicate_window` | `120s` | نافذة كشف التكرار |

**الحدّ الوحيد القائم ليس على الدفق بل على الخادم** — [`nats/nats.conf`](../../nats/nats.conf):

```
jetstream { store_dir: "/data/jetstream"  max_memory_store: 256MB  max_file_store: 2GB }
```

**وهذا يعني أنّ الدفق ينمو حتّى يستنفد 2GB ثمّ يبدأ النشر بالفشل** — حدّ الحساب يُنفَّذ
برفض الكتابة لا بإسقاط القديم، لأنّ حدود الدفق نفسه غير مضبوطة فلا شيء يُسقَط. ومع
`sahool.>` الذي يلتقط كلّ حدث نطاق، هذه مسألة **وقت لا احتمال**.

**والفشل صامت:** [`shared/helpers.py:318-325`](../../shared/helpers.py) يلتقط استثناء النشر،
يسجّل `warning`، ويُرجِع `False`. من لا يفحص القيمة المُرجَعة لا يرى شيئاً.

---

## ٢. المستهلكون — ١٣ مستهلكاً دائماً على دفق واحد، من ثلاثة مالكين

| المالك | الموضوع | الاسم الدائم |
|---|---|---|
| وكيل الإشعارات | `sahool.tenant.*.satellite.*.computed` | `notif_satellite` |
| وكيل الإشعارات | `sahool.alerts.weather` | `notif_weather` |
| وكيل الإشعارات | `sahool.pest.alert` | `notif_pest` |
| وكيل الإشعارات | `sahool.irrigation.recommendation` | `notif_irrigation` |
| وكيل الإشعارات | `sahool.fertilizer.recommendation` | `notif_fertilizer` |
| وكيل الإشعارات | `sahool.inventory.low_stock` | `notif_stock` |
| وكيل الإشعارات | `sahool.task.assigned` | `notif_task` |
| وكيل الإشعارات | `sahool.economic.analysis` | `notif_economic` |
| وكيل الإشعارات | `sahool.events.>` | `notif_domain_events` |
| عامل تراكب الطقس | `sahool.weather.forecast.updated` | `polygon-worker` |
| عامل التعلّم القانونيّ | `sahool.events.irrigation.execution.completed` | `canonical-execution-learning-v1-irrigation-execution-completed` |
| عامل التعلّم القانونيّ | `sahool.events.season.closed` | `canonical-execution-learning-v1-season-closed` |
| عامل التعلّم القانونيّ | `sahool.events.agronomy.projection.requested` | `canonical-execution-learning-v1-agronomy-projection-requested` |

**تداخل مقصود ومسجَّل:** `notif_domain_events` يشترك في `sahool.events.>`، وهو يشمل مواضيع
عامل التعلّم الثلاثة. مستهلكان مختلفان على الرسالة نفسها ⇒ نسختان مستقلّتان، وهذا سليم
لأنّ لكلٍّ اسمه الدائم. **لكنّه يعني أنّ نقل الملكيّة يمسّ مساراً يقرؤه الإشعارُ والتعلّمُ معاً.**

المقيس حيّاً على مستهلكي عامل التعلّم (الافتراضيّات الضمنيّة نفسها في كلّ الحالات):

| الحقل | القيمة |
|---|---|
| `ack_policy` | `explicit` |
| `deliver_policy` | `all` |
| `replay_policy` | `instant` |
| `max_deliver` | `-1` — **بلا حدّ إعادة تسليم** |
| `ack_wait` | `30s` |

**لا DLQ ولا حدّ تسليم على أيّ مستهلك.** العامل يُنهي (`term()`) عند الخطأ الدائم فلا حلقة
هناك، لكنّه يُعيد (`nak(delay=5)`) عند الخطأ العابر — ورسالةٌ تفشل عبوريّاً دائماً تُعاد
**إلى الأبد**. لا `dead_letter` مُعرَّف في أيّ إعداد JetStream في المستودع (المطابقات
الموجودة كلّها في مسارات outbox داخل القاعدة، لا على الناقل).

---

## ٣. الناشرون

| الناشر | الموضوع |
|---|---|
| `shared/helpers.py::dispatch` | `sahool.tenant.{tenant_id}.{event_type}` |
| `shared/helpers.py::publish_event` | أيّ موضوع يُمرَّر |
| outbox المنصّة | `sahool.events.<event_type>` |
| `irrigation_dispatch_relay_worker.py:44` | `sahool.events.<dispatch_event>` |
| `vegetation_runtime.py:545` | موضوع مؤشّرات النبات |
| عامل تراكب الطقس | `sahool.weather.field.overlay.completed` (بلا مستهلك — طريق مسدود مُعلَن) |

---

## ٤. ما يكشفه الجرد ولم يكن معروفاً

1. **التهيئة مفتوحة عند الفشل.** `add_stream` يبتلع كلّ استثناء عدا «already exists»
   ويُكمِل الإقلاع. فلو فشلت التهيئة فعلاً، تفشل الاشتراكات التسعة كلٌّ بتحذير، ثمّ
   يُعلن الوكيل `✅ Notification Agent ready`. **جاهزيّة تُعلَن بلا ناقل.**
2. **الدفق بلا سياسة احتفاظ.** `max_age=0` و`max_msgs=-1` و`max_bytes=-1`، والحدّ الوحيد
   على الخادم كلّه. النموّ غير محدود حتّى الرفض، والرفض صامت.
3. **`num_replicas=1`** — لا تكرار، وفقد المجلّد يفقد الدفق ومواضع كلّ المستهلكين.
4. **لا حدّ إعادة تسليم ولا DLQ** على أيّ من الثلاثة عشر.
5. **المالك القانونيّ للأسماء الدائمة موزّع على ثلاثة مستودعات فرعيّة** — `agents/`
   و`services/weather-polygon-worker/` و`scripts/workers/` — بلا سجلّ واحد يجمعها. هذا
   المستند هو أوّل سجلّ من نوعه.

---

## ٥. ما يلزم قبل نقل الملكيّة (لا يُنفَّذ الآن)

نقل التهيئة إلى طبقة بنية تحتيّة مستقلّة (`scripts/bootstrap/nats_streams.py` أو خدمة
قصيرة العمر `sahool-nats-bootstrap`) يتطلّب حسماً في:

- **سياسة الاحتفاظ الصريحة** لكلّ موضوع أو لكلّ فئة — قرار منتَج لا قرار تنفيذ.
- **حدّ إعادة التسليم وDLQ** — يغيّر سلوك كلّ مستهلك قائم.
- **ملكيّة الأسماء الدائمة**: هل تُعلَن مركزيّاً أم يبقى كلّ مستهلك يُعلن اسمه؟ الأوّل
  يمنع التصادم (وقد وقع فعلاً — `WORKER-REGISTERED-BUT-CANNOT-START-01`)، والثاني يحفظ
  استقلال الخدمات.
- **`num_replicas`** — يتبع طوبولوجيا النشر لا الكود.

والمستهلكون بعدها يعملون بصلاحيّات **استهلاك ونشر فقط**، بلا إدارة دفق.

**حدّ صدق:** كلّ ما في هذا المستند مقيس على nats-server محلّيّ وبمسح المستودع. لم يُقَس
دفق إنتاجيّ، ولا حجم مُتراكم حقيقيّ، ولا زمن بلوغ حدّ الـ2GB.
