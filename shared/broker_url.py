"""عنوانُ الوسيط يُطبَع مُنقَّى من الاعتماد — `NATS-BROKER-HAS-NO-AUTHENTICATION-…-01`.

**لمَ وُجِد هذا الملفّ:** إغلاقُ فتحةِ الوسيط المفتوح وضع الاعتمادَ **داخل**
`NATS_URL` — وهي القناةُ الوحيدة التي تبلغ كلَّ عميلٍ في هذه الشجرة بلا تعديل
`phase_runtime_workers.py` (ينادي ``nats.connect(nats_url)`` بلا وسائطِ اعتماد،
وتعديلُه ممنوعٌ بقرار المالك). فالعلاجُ فتح عطلاً ثانياً بيده: سطران يطبعان العنوان
في السجلّ (`main.py` عند بدء OutboxWorker · `irrigation_dispatch_relay_worker.py`
عند الاتّصال)، فكانا سيُسرِّبان كلمةَ المرور إلى سجلّاتٍ تُجمَع وتُشحَن.

**وهذا صنفٌ مقيسٌ لا متخيَّل:** «العلاجُ الظاهر يفتح عطلاً في مكانٍ آخر» — نفسُ
الصنف الذي أوجب إعلانَ المُنتِجين في حزمة الاعتماد. فالتنقيةُ تُكتَب **مرّةً واحدة**
هنا: نسختان في ملفَّين تتّفقان اليوم وتنحرفان غداً، وهو ما يقيسه هذا المستودع مراراً.

**حدُّ صدقٍ مُعلَن:** هذا يُنقّي ما **نطبعه نحن**. ولا يمنع مكتبةً أخرى أو أثرَ
استثناءٍ من طباعة العنوان الخام، ولا يُغني عن عدم تسجيل الأسرار أصلاً.
"""

from __future__ import annotations

from urllib.parse import urlsplit, urlunsplit

#: ما يحلّ محلّ الاعتماد في المخرَج. صريحٌ لا نجومٌ مبهمة: القارئُ يجب أن يعرف أنّ
#: هناك اعتماداً حُذِف، لا أن يظنّ العنوانَ بلا اعتماد فيطارد عطلاً غير موجود.
PLACEHOLDER = "***:***"


def redact_broker_url(url: str | None) -> str:
    """يُعيد العنوانَ بلا اسمِ مستخدمٍ ولا كلمةِ مرور — صالحاً للطباعة.

    ``nats://u:p@host:4222`` ⇒ ``nats://***:***@host:4222``.
    والعنوانُ بلا اعتماد يعود كما هو، فلا يُقلِق قارئَه بتنقيةٍ لم تقع.
    """
    if not url:
        return ""
    try:
        parts = urlsplit(url)
    except ValueError:  # عنوانٌ مشوَّه — لا يُطبَع خاماً على كلّ حال
        return "<عنوانٌ غيرُ صالح>"
    if not parts.netloc or "@" not in parts.netloc:
        return url
    host = parts.netloc.rsplit("@", 1)[-1]
    return urlunsplit(
        (parts.scheme, f"{PLACEHOLDER}@{host}", parts.path, parts.query, parts.fragment)
    )


def make_jetstream_publisher(nats_conn):
    """ناشرٌ **مُقِرّ** للصندوق الصادر — `OUTBOX-RELAY-MARKS-SENT-WITHOUT-JETSTREAM-ACK-01`.

    **العطلُ مقيسٌ على stack معزول:** حدثٌ نُشِر إلى موضعٍ لا يغطّيه أيُّ دفق صار صفُّه
    `sent` بـ`last_error=NULL` ومحاولةً `published` — **ولم تُخزَّن الرسالة**. والسببُ
    أنّ الناشرَ المحقون كان `nats_conn.publish`: **Core NATS**، إطلاقٌ بلا إقرار ينجح
    ما دام الاتّصالُ قائماً، وُجِد دفقٌ أم لا. فـ`sent` كانت تعني «سُلِّمت إلى المقبس»
    لا «صارت دائمة». وأُعيد الـcounterexample حيّاً على JetStream:
    `docs/evidence/outbox_jetstream_ack_live_certification.json`.

    **والعلاجُ ليس في `OutboxWorker`:** بنيتُه سليمة — ينشر ثمّ يَسِم داخل معاملة، وأيُّ
    استثناءٍ يُعيد الصفَّ `pending/failed` بـ`last_error` ومحاولةً فاشلة. فالمسارُ الصحيح
    كان **موجوداً ومعطَّلاً** لأنّ الناشرَ لا يفشل أبداً. و`js.publish` ينتظر `PubAck`
    ويرفع `NoStreamResponseError` حين لا يغطّي الموضعَ دفقٌ، فيسلك المسارَ القائم —
    **الإصلاح يُفعِّل حارساً موجوداً بدل أن يضيف ثانياً.**

    **وموضعُها هنا اختارته بوّابتان لا الراحة:** `main.py` محدودٌ بميزانيّة أسطرٍ حاجبة
    (٢٥٥٣، بلا هامش)، و`api/event_bus.py` **مسارٌ مجمَّد خلف GATE-01** — وتفويضُه
    قرارُ مالكٍ لمرّةٍ واحدة، لا يُنتزَع لأجل نقلِ دالّة. وهذا الملفُّ هو الموضعُ
    القانونيُّ لشؤون الوسيط بنصّه أعلاه: «تُكتَب مرّةً واحدة هنا». فالبوّابتان دلّتا
    على الموضع الصحيح بدل أن تُعطَّلا.
    """
    jetstream = nats_conn.jetstream()

    async def publish(subject: str, payload: bytes) -> None:
        ack = await jetstream.publish(subject, payload)
        # حزامٌ ثانٍ: عميلٌ يُرجِع `None` أو إقراراً بلا تسلسلٍ لا يُثبِت دواماً — وبلا
        # هذا الشرط يعود `sent` يعني «لم يُرفَع استثناء» لا «خُزِّنت».
        if ack is None or getattr(ack, "seq", None) in (None, 0):
            raise RuntimeError(
                f"JETSTREAM_PUBACK_MISSING: {subject} — نُشِر بلا إقرارِ تخزين، فلا يُوسَم الحدثُ `sent`."
            )

    return publish
