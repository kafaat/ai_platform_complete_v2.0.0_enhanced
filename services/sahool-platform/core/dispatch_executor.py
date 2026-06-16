"""core/dispatch_executor.py — تنفيذ قرار التوزيع المحروس (تنسيق نقيّ، منافذ مُحقَنة).

الحلقة المغلقة، المرحلة الأخيرة على المنصّة: يأخذ `DispatchDecision` (من
`core.decision_dispatch`) وينسّق إدامته + إدراجه في طابور المُشغِّل — **بحاجز أمان
مُنفَّذ بنيويّاً**: يُدرَج للتنفيذ **قرار READY فقط**؛ BLOCKED/PENDING يُسجَّل تدقيقاً
ولا يُنفَّذ أبداً.

نقيّ: منفذ `persist` واحد مُحقَن (يكتب صفّ `dispatch_decisions`) — فيُختبَر بمنفذ
وهميّ بلا قاعدة. **لا يُطلِق MQTT مباشرةً**: الإدراج (`exec_status='queued'`) هو
حدّ المنصّة الآمن؛ المُشغِّل (actuator-service) يستهلك الطابور وينشر الأمر الموقَّع —
يبقى التنفيذ الفيزيائيّ في مكانه المُحصَّن، لا يُطلَق أعمى من هنا.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any


class ExecutionStatus(str, Enum):
    """مآل التنفيذ — مخرَج المنسّق."""

    QUEUED = "queued"  # READY ⇒ أُدرج لطابور المُشغِّل
    NOT_EXECUTED = "not_executed"  # BLOCKED/PENDING ⇒ سُجِّل فقط، لم يُنفَّذ


@dataclass
class ExecutionResult:
    status: ExecutionStatus
    dispatch_state: str
    command: dict | None
    reason_ar: str

    def to_dict(self) -> dict:
        d = asdict(self)
        d["status"] = self.status.value
        return d


async def execute_dispatch(
    decision: Any,
    *,
    persist: Any,
    command: Any = None,
) -> ExecutionResult:
    """ينسّق تنفيذ قرار: يُدِيم دائماً (تدقيق)، ويُدرِج READY فقط.

    `persist(decision, command_dict_or_None, exec_status)` — منفذ الإدامة (idempotent).
    `command`: `ActuatorCommand` (أو None) — مطلوب لقرار READY، مُتجاهَل لغيره.

    fail-closed: قرار غير قابل للتنفيذ ⇒ يُسجَّل بـ`not_executed` بلا أمر. قرار READY
    بلا أمر ⇒ ValueError (لا تنفيذ بلا أمر مبنيّ). الذرّيّة (إدامة+إدراج) مسؤوليّة
    `persist` (معاملة واحدة لدى المُنادي).
    """
    if not getattr(decision, "executable", False):
        await persist(decision, None, ExecutionStatus.NOT_EXECUTED.value)
        return ExecutionResult(
            status=ExecutionStatus.NOT_EXECUTED,
            dispatch_state=decision.state.value,
            command=None,
            reason_ar=f"لم يُنفَّذ — {decision.reason_ar}",
        )

    if command is None:
        raise ValueError("قرار READY يتطلّب أمر مُشغِّل مبنيّاً للإدراج")

    cmd_dict = command.to_dict() if hasattr(command, "to_dict") else dict(command)
    await persist(decision, cmd_dict, ExecutionStatus.QUEUED.value)
    return ExecutionResult(
        status=ExecutionStatus.QUEUED,
        dispatch_state=decision.state.value,
        command=cmd_dict,
        reason_ar="أُدرج لطابور المُشغِّل (محروس + موافَق) — التنفيذ الفيزيائيّ لدى actuator-service",
    )
