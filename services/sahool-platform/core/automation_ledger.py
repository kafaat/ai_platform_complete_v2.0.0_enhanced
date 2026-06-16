"""core/automation_ledger.py — سجلّ تشغيل الأتمتة (مراقبة، منطق نقيّ)
====================================================================
الفجوة المسدودة:
  ``api/scheduler.py`` يتتبّع آخر تشغيل/نجاح/فشل + عدّاد التشغيل لكلّ مهمّة،
  لكنّه لا يحفظ **ماذا فعلت** كلّ دورة فعليّاً: كم حقلاً قُيّم/تُخطّى/تعثّر،
  كم تنبيهاً أُنشئ، وكم استغرقت. حلقة تقييم التنبيهات الدوريّة تُسجّل
  ``total_created`` نصّاً فقط — لا سجلّ منظّم قابل للاستعلام.

التصميم (صدق + نقاء):
  • وحدة نقيّة بلا I/O ولا قاعدة — حلقة حلقيّة (ring buffer) محدودة في الذاكرة.
  • ``RunLedger`` يحمل ``deque(maxlen)`` من ``RunRecord`` (الأقدم يسقط تلقائيّاً).
  • ``RunRecordBuilder`` يُراكِم نتائج كلّ حقل أثناء الدورة ثمّ ``finish()`` يحسب
    المدّة + الحالة من العدّادات الحقيقيّة (لا اختلاق): ok/partial/error.
  • مفردة وحيدة ``LEDGER`` تتشاركها حلقة الجدولة ونقطة القراءة.

ملاحظة تزامن: مصمَّمة لحلقة asyncio واحدة (لا تعدّد خيوط فعليّ)؛ العمليّات
ذرّيّة بما يكفي لهذا الاستخدام (append على deque + كتابات حقول بسيطة).
"""

from __future__ import annotations

from collections import deque
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime

# الحالات الممكنة لتشغيل واحد
Status = str  # "ok" | "partial" | "error"

DEFAULT_MAXLEN = 50


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


@dataclass
class RunRecord:
    """سجلّ تشغيل دوريّ واحد — لقطة صادقة لِما فعلته الدورة."""

    task_name: str
    started_at: str
    finished_at: str | None = None
    fields_total: int = 0
    evaluated: int = 0
    skipped: int = 0
    errored: int = 0
    alerts_created: int = 0
    duration_ms: int = 0
    status: Status = "ok"
    note_ar: str | None = None
    # أخطاء كلّ حقل (field_id → رسالة) — للتشخيص، يبقى مختصراً
    errors: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


class RunRecordBuilder:
    """مُراكِم نتائج دورة واحدة. يُنشأ عبر ``RunLedger.start_run`` ويُختم بـ``finish``.

    استخدام مقصود من حلقة الجدولة:
        rec = LEDGER.start_run("alerts_evaluation", n_fields)
        for f in fields:
            try:
                ...
                rec.mark_evaluated(); rec.add_alerts(k)
            except SkipError:
                rec.mark_skipped()
            except Exception as e:
                rec.mark_errored(field_id, e)
        rec.finish()
    """

    def __init__(self, ledger: RunLedger, record: RunRecord) -> None:
        self._ledger = ledger
        self._record = record
        self._start_monotonic = datetime.now(UTC)
        self._finished = False

    # ─── مُراكِمات كلّ حقل ──────────────────────────────────────────
    def mark_evaluated(self, n: int = 1) -> None:
        """حقل قُيّم بنجاح."""
        self._record.evaluated += int(n)

    def mark_skipped(self, n: int = 1) -> None:
        """حقل تُخطّي عمداً (لا بيانات/خارج النطاق) — ليس خطأ."""
        self._record.skipped += int(n)

    def mark_errored(self, field_id: str, err: object) -> None:
        """حقل تعثّر — يُسجَّل خطؤه ولا يُسقط الدورة."""
        self._record.errored += 1
        self._record.errors.append({"field_id": str(field_id), "error": str(err)})

    def add_alerts(self, n: int) -> None:
        """يضيف عدد التنبيهات المُنشأة في هذا الحقل."""
        self._record.alerts_created += int(n)

    # ─── الختم ─────────────────────────────────────────────────────
    def finish(self, note_ar: str | None = None) -> RunRecord:
        """يحسب المدّة + الحالة من العدّادات الحقيقيّة ويُلحق السجلّ بالحلقة.

        الحالة (صدق، من العدّادات لا اختلاق):
          • errored == 0 ⇒ "ok"
          • errored > 0 وevaluated > 0 ⇒ "partial"
          • errored > 0 وevaluated == 0 (الكلّ تعثّر) ⇒ "error"
        دورة بصفر حقول ⇒ "ok" مع ملاحظة (لا عمل لِيُنجَز).
        """
        if self._finished:
            return self._record
        rec = self._record
        rec.finished_at = _now_iso()
        delta = datetime.now(UTC) - self._start_monotonic
        rec.duration_ms = max(0, int(delta.total_seconds() * 1000))

        if rec.errored == 0:
            rec.status = "ok"
        elif rec.evaluated > 0:
            rec.status = "partial"
        else:
            rec.status = "error"

        if note_ar is not None:
            rec.note_ar = note_ar
        elif rec.fields_total == 0:
            rec.note_ar = "لا حقول للتقييم في هذه الدورة."

        self._ledger._append(rec)
        self._finished = True
        return rec


class RunLedger:
    """حلقة حلقيّة محدودة من سجلّات التشغيل — مراقبة في الذاكرة (لا قاعدة)."""

    def __init__(self, maxlen: int = DEFAULT_MAXLEN) -> None:
        self._runs: deque[RunRecord] = deque(maxlen=maxlen)

    def start_run(self, task_name: str, fields_total: int) -> RunRecordBuilder:
        """يبدأ تتبّع دورة جديدة ويُرجع مُراكِماً تُغذّيه حلقة الجدولة."""
        rec = RunRecord(
            task_name=str(task_name),
            started_at=_now_iso(),
            fields_total=int(fields_total),
        )
        return RunRecordBuilder(self, rec)

    def _append(self, rec: RunRecord) -> None:
        """إلحاق داخليّ (يُستدعى من ``RunRecordBuilder.finish``)."""
        self._runs.append(rec)

    def recent(self, limit: int | None = None) -> list[dict]:
        """يُرجع السجلّات (الأحدث أوّلاً) كقواميس. ``limit`` يقصّ العدد."""
        records = list(reversed(self._runs))
        if limit is not None:
            records = records[: max(0, int(limit))]
        return [r.to_dict() for r in records]

    def summary(self) -> dict:
        """ملخّص: آخر دورة + إجماليّات عبر كامل الحلقة (للمراقبة السريعة)."""
        total_runs = len(self._runs)
        last = self._runs[-1].to_dict() if self._runs else None
        totals = {
            "evaluated": sum(r.evaluated for r in self._runs),
            "skipped": sum(r.skipped for r in self._runs),
            "errored": sum(r.errored for r in self._runs),
            "alerts_created": sum(r.alerts_created for r in self._runs),
        }
        return {
            "total_runs": total_runs,
            "buffer_capacity": self._runs.maxlen,
            "last_run": last,
            "totals": totals,
        }

    def clear(self) -> None:
        """تفريغ الحلقة (للاختبارات/إعادة الضبط)."""
        self._runs.clear()


# مفردة وحيدة للتطبيق — تتشاركها حلقة الجدولة ونقطة القراءة
LEDGER = RunLedger()
