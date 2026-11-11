"""core/engines/harvest_traceability.py — منطق تتبّع سلسلة الإمداد (نقيّ، بلا DB).

يكمّل input_traceability (تتبّع المدخلات على مستوى الحقل) بسلسلة الحيازة من الحصاد
إلى السوق. كلّ الدوالّ هنا نقيّة (لا I/O) فتُختبَر offline، والراوتر يلفّها بالقاعدة.

- compute_custody_event_hash: SHA-256 حتميّ على **كلّ** حقل عمل مُخزَّن، بعد تطبيعٍ يطابق
  ما تُعيده القاعدة (الزمن UTC · الكمّيّة NUMERIC(12,2)) فيُعاد حسابه عند القراءة.
- compute_event_hash: الصيغة القديمة (lot/type/at/details فقط) — تُبقى للتعرّف على صفوف
  قديمة فتُوسَم «legacy_hash» لا «متلاعَب بها».
- verify_event_hash: يعيد حساب البصمة لحدث مقروء ويصنّفه.
- custody_event_refusal: سبب رفض حدث يخالف الكتلة/الزمن (422 في الراوتر).
- status_for_event: الحالة الجديدة للدفعة المُشتقّة من نوع حدث الحيازة (وفحص راسب ⇒ rejected).
- transition_refusal: سبب رفض حدث غير مسموح (بيع المرفوض، الرجوع عن البيع) — 409 في الراوتر.
- assemble_traceability: يجمع الدفعة + السلسلة المرتّبة زمنيّاً + المنشأ + تقييم
  اكتمال السلسلة في أثر واحد جاهز للـJSON.
- ثوابت التحقّق (الأنواع/الأدوار) — مصدر حقيقة واحد يشاركه الراوتر والاختبار.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

# مجموعات القيم المسموحة — تطابق قيود CHECK في v65_harvest_traceability.sql.
CUSTODY_EVENT_TYPES: tuple[str, ...] = (
    "harvest",
    "storage",
    "quality_check",
    "transport",
    "sales",
)
HANDLER_ROLES: tuple[str, ...] = (
    "farmer",
    "storage",
    "transporter",
    "trader",
    "buyer",
    "inspector",
    "system",
)
LOT_STATUSES: tuple[str, ...] = (
    "harvested",
    "stored",
    "in_transit",
    "at_market",
    "sold",
    "rejected",
)

# انتقال حالة الدفعة المُشتقّ من نوع حدث الحيازة (تطبيقيّ). None ⇒ لا تغيّر الحالة
# (فحص الجودة لا يحرّك موضع الدفعة). يحرّكه الراوتر عند تسجيل حدث.
_EVENT_TO_STATUS: dict[str, str | None] = {
    "harvest": "harvested",
    "storage": "stored",
    "transport": "in_transit",
    "quality_check": None,
    "sales": "sold",
}


# اصطلاح نتيجة فحص الجودة في event_details (لا عمود مخصّص في v65): أيّ من
#   passed: false · result ∈ {fail, failed, reject, rejected} · grade/quality_grade = reject
# يعني فحصاً راسباً ⇒ الدفعة «rejected». غياب هذه المفاتيح ⇒ فحص لا يحرّك الحالة.
_FAILED_RESULTS = frozenset({"fail", "failed", "reject", "rejected"})
# حالات «ما قبل البيع» التي لا تعود إليها دفعة مُباعة (البيع لا يُنقَض بحدث حركة).
_PRE_SALE_STATUSES = frozenset({"harvested", "stored", "in_transit", "at_market"})


def quality_check_failed(event_details: dict[str, Any] | None) -> bool:
    """هل تفاصيل فحص الجودة تقول «راسب»؟ اصطلاح صريح ضيّق — لا استدلال من نصّ حرّ."""
    details = event_details or {}
    if details.get("passed") is False:
        return True
    result = details.get("result")
    if isinstance(result, str) and result.strip().lower() in _FAILED_RESULTS:
        return True
    for key in ("grade", "quality_grade"):
        grade = details.get(key)
        if isinstance(grade, str) and grade.strip().lower() == "reject":
            return True
    return False


def status_for_event(
    event_type: str, current_status: str, event_details: dict[str, Any] | None = None
) -> str:
    """الحالة الجديدة للدفعة بعد حدث حيازة. النوع المجهول أو غير المُحرِّك ⇒ تبقى الحالة.

    فحص جودة راسب ⇒ «rejected» (إلّا على دفعة مُباعة: البيع لا يُعاد كتابته، والفحص
    يبقى دليلاً في السلسلة). فحص ناجح لا يُلغي رفضاً سابقاً.
    """
    if event_type == "quality_check":
        if quality_check_failed(event_details) and current_status != "sold":
            return "rejected"
        return current_status
    nxt = _EVENT_TO_STATUS.get(event_type)
    return nxt if nxt is not None else current_status


def transition_refusal(
    event_type: str,
    current_status: str,
    *,
    quality_grade: str | None = None,
    event_details: dict[str, Any] | None = None,
) -> str | None:
    """سبب رفض الحدث (نصّ عربيّ) أو None إن كان مسموحاً — يُترجمه الراوتر إلى 409.

    - بيع دفعة مرفوضة (حالة rejected) أو مُصنَّفة reject عند الإنشاء ⇒ مرفوض.
    - إعادة دفعة مُباعة إلى حالة ما قبل البيع (حصاد/تخزين/نقل) ⇒ مرفوض.
    """
    if event_type == "sales":
        if current_status == "rejected":
            return "لا يمكن بيع دفعة مرفوضة في فحص الجودة"
        if isinstance(quality_grade, str) and quality_grade.strip().lower() == "reject":
            return "لا يمكن بيع دفعة مُصنَّفة reject"
    if current_status == "sold":
        nxt = status_for_event(event_type, current_status, event_details)
        if nxt in _PRE_SALE_STATUSES:
            return "الدفعة مُباعة — لا تعود إلى حالة ما قبل البيع"
    return None


def compute_event_hash(
    harvest_lot_id: str,
    event_type: str,
    occurred_at: str,
    event_details: dict[str, Any] | None,
) -> str:
    """الصيغة **القديمة** (lot/type/at/details فقط، والزمن نصّ الإدخال كما جاء).

    لا تُستخدَم للكتابة بعد اليوم (تُغفل المناوِل/الكمّيّة/الموقع، والزمن غير مُطبَّع
    فلا يتحقّق بعد الرحلة إلى القاعدة)؛ تُبقى ليتعرّف verify_event_hash على صفوفٍ
    كُتبت بها فيَسِمها «legacy_hash» بدل «mismatch»."""
    canonical = json.dumps(
        {
            "lot": harvest_lot_id,
            "type": event_type,
            "at": occurred_at,
            "details": event_details or {},
        },
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# ─── تطبيع الحقول قبل البصمة (يطابق ما تُعيده القاعدة) ─────────────────────────


def parse_occurred_at(value: str | datetime) -> datetime:
    """ISO/datetime → datetime واعٍ بالمنطقة. الساذج يُعامَل UTC (كما يكتبه asyncpg في
    حاوية UTC) فيتطابق المُخزَّن والمُبصَّم. يرفع ValueError على قيمة غير صالحة."""
    if isinstance(value, datetime):
        dt = value
    else:
        text = str(value).strip()
        if text.endswith(("Z", "z")):
            text = text[:-1] + "+00:00"
        dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt


def normalize_occurred_at(value: str | datetime) -> str:
    """الزمن القانونيّ للبصمة: UTC ISO (`…+00:00`) — هو ما تُعيده TIMESTAMPTZ عند القراءة،
    فإدخال `+03:00` يتحقّق بعد الرحلة إلى القاعدة."""
    return parse_occurred_at(value).astimezone(UTC).isoformat()


_KG_QUANTUM = Decimal("0.01")


def normalize_quantity_kg(value: Any) -> Decimal | None:
    """الكمّيّة كما تخزّنها NUMERIC(12,2) (تقريب نصف-بعيد-عن-الصفر كـPostgres)."""
    if value is None:
        return None
    try:
        return Decimal(str(value)).quantize(_KG_QUANTUM, rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError) as e:
        raise ValueError(f"quantity_kg غير صالحة: {value!r}") from e


def compute_custody_event_hash(
    harvest_lot_id: str,
    event_type: str,
    occurred_at: str | datetime,
    *,
    handler: str | None = None,
    handler_role: str | None = None,
    location_name: str | None = None,
    quantity_kg: Any = None,
    event_details: dict[str, Any] | None = None,
) -> str:
    """SHA-256 حتميّ على كلّ حقل عمل مُخزَّن لحدث الحيازة (الصيغة v2).

    يُطبَّع قبل البصمة: الزمن → UTC ISO، والكمّيّة → نصّ NUMERIC(12,2)، والتفاصيل
    بتمثيل قانونيّ (sort_keys + فواصل ثابتة). فيُعاد الحساب من الصفّ المقروء ويطابق
    ما حُسب عند الكتابة مهما كانت منطقة الإدخال أو ترتيب مفاتيحه."""
    qty = normalize_quantity_kg(quantity_kg)
    canonical = json.dumps(
        {
            "v": 2,
            "lot": harvest_lot_id,
            "type": event_type,
            "at": normalize_occurred_at(occurred_at),
            "handler": handler,
            "handler_role": handler_role,
            "location": location_name,
            "quantity_kg": None if qty is None else str(qty),
            "details": event_details or {},
        },
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def custody_event_hash_of(event: dict[str, Any], harvest_lot_id: str | None = None) -> str:
    """compute_custody_event_hash على dict حدث (مقروء أو مُقترَح)."""
    return compute_custody_event_hash(
        harvest_lot_id if harvest_lot_id is not None else event.get("harvest_lot_id"),
        event.get("event_type"),
        event.get("occurred_at"),
        handler=event.get("handler"),
        handler_role=event.get("handler_role"),
        location_name=event.get("location_name"),
        quantity_kg=event.get("quantity_kg"),
        event_details=event.get("event_details"),
    )


# إزاحات المنطقة الممكنة لنصّ إدخالٍ قديم (−12:00 … +14:00 بخطوة ربع ساعة): الصيغة القديمة
# بَصَمت نصّ الإدخال كما جاء، والقاعدة لا تحفظ إزاحته — فنجرّب كلّ تمثيلٍ محتمَل.
_LEGACY_OFFSETS_MIN = tuple(range(-12 * 60, 14 * 60 + 1, 15))

HASH_VERIFIED = "verified"
HASH_LEGACY = "legacy_hash"
HASH_MISMATCH = "mismatch"
HASH_MISSING = "missing"


def _legacy_time_candidates(occurred_at: Any) -> list[str]:
    try:
        utc = parse_occurred_at(occurred_at).astimezone(UTC)
    except (ValueError, TypeError):
        return [str(occurred_at)] if occurred_at is not None else []
    out = [utc.replace(tzinfo=None).isoformat()]  # إدخال ساذج (خُزِّن UTC)
    for minutes in _LEGACY_OFFSETS_MIN:
        out.append(utc.astimezone(timezone(timedelta(minutes=minutes))).isoformat())
    return out


def verify_event_hash(event: dict[str, Any], harvest_lot_id: str | None = None) -> str:
    """يعيد حساب بصمة حدث مقروء ويصنّفه:

    - ``verified``: تطابق الصيغة v2 (كلّ الحقول).
    - ``legacy_hash``: تطابق الصيغة القديمة فقط — صفّ سابق لهذا الإصلاح؛ يغطّي
      lot/type/at/details وحدها، فلا يُثبت المناوِل/الكمّيّة/الموقع لكنّه ليس تلاعباً.
    - ``mismatch``: لا تطابق أيّاً منهما ⇒ تغيّر المحتوى بعد التسجيل.
    - ``missing``: لا بصمة مُخزَّنة."""
    stored = event.get("content_hash")
    if not stored:
        return HASH_MISSING
    lot_id = harvest_lot_id if harvest_lot_id is not None else event.get("harvest_lot_id")
    try:
        if custody_event_hash_of(event, lot_id) == stored:
            return HASH_VERIFIED
    except (ValueError, TypeError):
        pass
    details = event.get("event_details")
    for at in _legacy_time_candidates(event.get("occurred_at")):
        if compute_event_hash(lot_id, event.get("event_type"), at, details) == stored:
            return HASH_LEGACY
    return HASH_MISMATCH


# ─── الكتلة والزمن ─────────────────────────────────────────────────────────────

# الأحداث التي تُخرِج كمّيّة من الدفعة (تُجمَع مقابل كمّيّتها). النقل/التخزين يحرّكان
# الدفعة نفسها فلا يُستهلكان منها، لكن لا حدث يتعامل مع أكثر من كمّيّة الدفعة.
OUTGOING_EVENT_TYPES: frozenset[str] = frozenset({"sales"})
# انحراف ساعة مسموح لزمن حدث «في المستقبل» (ساعة جهاز ميدانيّ).
FUTURE_SKEW = timedelta(minutes=10)
# harvest_date تاريخ محلّيّ بلا منطقة: لا نحكم بأنّ حدثاً «قبل الحصاد» إلّا إن سبق منتصف
# ليل يومه في أقصى منطقة شرقاً (UTC+14) — فلا يُرفَض حدث صحيح بسبب فرق المنطقة.
_HARVEST_DATE_SLACK = timedelta(hours=14)


def _to_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value).strip()[:10])
    except ValueError:
        return None


def _earliest_after_harvest(harvest_date: Any) -> datetime | None:
    d = _to_date(harvest_date)
    if d is None:
        return None
    return datetime(d.year, d.month, d.day, tzinfo=UTC) - _HARVEST_DATE_SLACK


def custody_event_refusal(
    *,
    event_type: str,
    occurred_at: datetime,
    quantity_kg: Any,
    lot_quantity_kg: Any,
    harvest_date: Any,
    last_occurred_at: datetime | None,
    outgoing_kg_so_far: Any,
    now: datetime | None = None,
) -> str | None:
    """سبب رفض حدث يخالف الكتلة أو الزمن (نصّ عربيّ ⇒ 422 في الراوتر) أو None.

    يُستدعى تحت قفل FOR UPDATE على الدفعة، بآخر زمن حدث ومجموع الكمّيّات الخارجة حتّى الآن:
    - زمن الحدث في المستقبل أبعد من FUTURE_SKEW.
    - زمن الحدث قبل تاريخ الحصاد (بهامش المنطقة).
    - زمن الحدث أسبق من آخر حدث مُسجَّل (السلسلة لا تُكتب بأثر رجعيّ).
    - كمّيّة حدث أكبر من كمّيّة الدفعة، أو كمّيّة خارجة تتجاوز المتبقّي."""
    at = parse_occurred_at(occurred_at)
    now = now or datetime.now(UTC)
    if at > now + FUTURE_SKEW:
        return "occurred_at في المستقبل — لا يُسجَّل حدث لم يقع بعد"
    floor = _earliest_after_harvest(harvest_date)
    if floor is not None and at < floor:
        return "occurred_at يسبق تاريخ حصاد الدفعة"
    if last_occurred_at is not None and at < parse_occurred_at(last_occurred_at):
        return "occurred_at أسبق من آخر حدث مُسجَّل على الدفعة — السلسلة لا تُكتب بأثر رجعيّ"
    qty = normalize_quantity_kg(quantity_kg)
    lot_qty = normalize_quantity_kg(lot_quantity_kg)
    if qty is not None and lot_qty is not None:
        if qty > lot_qty:
            return "كمّيّة الحدث تتجاوز كمّيّة الدفعة"
        if event_type in OUTGOING_EVENT_TYPES:
            remaining = lot_qty - (normalize_quantity_kg(outgoing_kg_so_far) or Decimal("0"))
            if qty > remaining:
                return f"الكمّيّة الخارجة تتجاوز المتبقّي من الدفعة ({remaining} كغ)"
    return None


# ─── الأثر ─────────────────────────────────────────────────────────────────────

_EPOCH = datetime.min.replace(tzinfo=UTC)


def _sort_time(event: dict[str, Any]) -> datetime:
    try:
        return parse_occurred_at(event.get("occurred_at"))
    except (ValueError, TypeError):
        return _EPOCH


def assemble_traceability(
    lot: dict[str, Any],
    custody_events: list[dict[str, Any]],
    origin: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """يبني الأثر الكامل لدفعة: الدفعة + سلسلة الحيازة مرتّبة زمنيّاً + المنشأ + تقييم
    الاكتمال + تحقّق البصمات. نقيّ: يقبل dicts مُطبّعة ويُرجِع dict للـJSON.

    ترتيب السلسلة بـ(occurred_at كزمن واعٍ, custody_event_id) حتميّ — يطابق فهرس
    الاستعلام، وكاسر التعادل (id تسلسليّ) يمنع اختلاف الترتيب عند تساوي occurred_at.

    «كامل» لا يعني «فيها حصاد وبيع في مكانٍ ما»؛ يعني كلّ ما يلي، وإلّا تُذكر الأسباب
    في ``incomplete_reasons``:
    - أوّل حدث حصاد (``first_event_not_harvest``) وفيها بيع (``no_sales_event``).
    - لا حدث قبل تاريخ الحصاد (``occurred_before_harvest_date``).
    - ترتيب التسجيل يطابق ترتيب الوقوع — لا حدث مُسجَّل لاحقاً بزمن أسبق
      (``non_monotonic_occurred_at``).
    - لا كمّيّة حدث فوق كمّيّة الدفعة ومجموع الخارج لا يتجاوزها
      (``outgoing_quantity_exceeds_lot``).
    - لا بصمة لا تطابق محتواها (``hash_mismatch``)."""
    lot_id = lot.get("harvest_lot_id")
    chain = sorted(
        (dict(e) for e in custody_events),
        key=lambda e: (_sort_time(e), e.get("custody_event_id") or 0),
    )
    statuses: list[str] = []
    for e in chain:
        st = verify_event_hash(e, lot_id)
        e["hash_status"] = st
        e["hash_verified"] = {HASH_VERIFIED: True, HASH_MISMATCH: False}.get(st)
        statuses.append(st)

    started_at_harvest = bool(chain) and chain[0].get("event_type") == "harvest"
    reached_market = any(e.get("event_type") == "sales" for e in chain)
    reasons: list[str] = []
    if not chain:
        reasons.append("no_events")
    elif not started_at_harvest:
        reasons.append("first_event_not_harvest")
    if not reached_market:
        reasons.append("no_sales_event")

    floor = _earliest_after_harvest(lot.get("harvest_date"))
    if floor is not None and any(_sort_time(e) < floor for e in chain if e.get("occurred_at")):
        reasons.append("occurred_before_harvest_date")

    by_record = sorted(
        (e for e in chain if e.get("custody_event_id") is not None and e.get("occurred_at")),
        key=lambda e: e["custody_event_id"],
    )
    if any(_sort_time(b) < _sort_time(a) for a, b in zip(by_record, by_record[1:], strict=False)):
        reasons.append("non_monotonic_occurred_at")

    try:
        lot_qty = normalize_quantity_kg(lot.get("quantity_kg"))
        qtys = [(e.get("event_type"), normalize_quantity_kg(e.get("quantity_kg"))) for e in chain]
    except ValueError:
        lot_qty, qtys = None, []
    if lot_qty is not None:
        outgoing = sum(
            (q for t, q in qtys if q is not None and t in OUTGOING_EVENT_TYPES), Decimal("0")
        )
        if outgoing > lot_qty or any(q is not None and q > lot_qty for _, q in qtys):
            reasons.append("outgoing_quantity_exceeds_lot")

    if HASH_MISMATCH in statuses:
        reasons.append("hash_mismatch")
        overall_hash: bool | None = False
    elif chain and all(st == HASH_VERIFIED for st in statuses):
        overall_hash = True
    else:
        # لا تلاعب مكشوف، لكن صفوف قديمة/بلا بصمة لا تُثبَت كاملةً.
        overall_hash = None

    return {
        "harvest_lot": lot,
        "custody_chain": chain,
        "origin": origin or {},
        "chain": {
            "event_count": len(chain),
            "started_at_harvest": started_at_harvest,
            "reached_market": reached_market,
            "complete": not reasons,
            "incomplete_reasons": reasons,
            "hash_verified": overall_hash,
            "hash_status_counts": {st: statuses.count(st) for st in sorted(set(statuses))},
        },
    }
