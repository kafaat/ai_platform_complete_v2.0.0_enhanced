from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any


def _now_iso() -> str:
    """لحظةُ إنشاء الحدث — تُقيَّم عند كلّ حدث لا مرّةً عند الاستيراد."""
    return datetime.now(UTC).isoformat()


@dataclass
class GuardrailEvent:
    tenant_id: str
    field_id: str
    action: str
    reason: str
    confidence: float
    # كان `= datetime.utcnow().isoformat()` — قيمةٌ افتراضيّة تُقيَّم **مرّةً واحدة
    # عند تنفيذ جسد الصنف**، أي عند الاستيراد. فكلّ أحداث الحارس في عمليّةٍ واحدة
    # كانت تُنشَر بختمِ لحظةِ الإقلاع نفسه. مقيسٌ بالتشغيل: حدثان بفارق 1.1s حملا
    # الطابع ذاته حرفيّاً. وهو أسوأ من غياب الطابع، لأنّ حقلاً اسمه `timestamp`
    # يُقرأ لحظةَ وقوعٍ في مسارٍ تدقيقيّ. `default_factory` يُقيَّم لكلّ نسخة.
    timestamp: str = field(default_factory=_now_iso)

    def to_event(self) -> dict[str, Any]:
        return asdict(self)


NATS_SUBJECTS = {
    "guardrail": "SAHOOL.AI.GUARDRAIL",
    "human_review": "SAHOOL.AI.REVIEW",
    "feedback": "SAHOOL.AI.FEEDBACK",
}
