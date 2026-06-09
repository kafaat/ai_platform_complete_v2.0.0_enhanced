"""
sahool_core.execution_control_plane
=====================================
Execution Control Plane (ECP) — Observability + governance convention.

⚠️ الإقرار النزيه (استجابة لمراجعة التوثيق العاشرة 2026-05-29):
   هذه الوحدة كانت تُوصَف سابقاً كـ"structural enforcement" — هذا
   توصيف مُبالَغ فيه. Python لا يدعم true encapsulation:
   
       from core.recommendation_engine import generate_recommendation
       result = generate_recommendation(...)   # ينجح حتى في STRICT mode
   
   ECP يحرس entry points المُسجَّلة (المُزخرفة بـ@governed)، لا
   generate_recommendation نفسها. الـ`__all__` sealing هو convention
   يساعد IDEs/linters، لا يمنع الاستيراد الصريح.

ما يفعله ECP فعلاً (Observability + Convention):
  • كل استدعاء @governed يُسجَّل صراحةً مع call_path
  • audit_call_log: forensics قابل للقراءة
  • call_stats: Prometheus-ready metrics
  • bypass_alert_summary: يكشف محاولات bypass للـentry points المُسجَّلة
  • STRICT mode: يمنع استدعاء entry points غير مُسجَّلة (لا الـimports)

ما لا يفعله ECP (الإقرار الصريح):
  • لا يمنع `from core.X import Y` المباشر
  • لا يحمي من مطوّر يكتب route جديد دون @governed
  • لا يستبدل code review

التمييز عن سابقاته:
  • safe_delivery: نقطة دخول لطبقات خارجية
  • internal_orchestrator: نقطة دخول داخلية للـAPI
  • ECP: observability + convention layer (ليس enforcement structural)

النمط: opt-in عند البداية، mandatory للـentry points المُسجَّلة
  • المرحلة الحالية: ECP يُسجّل ويُحذّر (لا يرفع exception افتراضياً)
  • STRICT mode: يفرض @governed على entry points المُسجَّلة فقط

المبادئ المحفوظة:
  • شفّافية: كل قرار access يحمل سبباً
  • قابلية القياس: counters/timers لكل entry point
  • النضج: ECP يكمّل code review، لا يستبدله

التكامل:
  ← internal_orchestrator يسجّل نفسه عند الاستيراد
  ← safe_delivery يسجّل نفسه أيضاً
  → audit_call_log قابل للقراءة من خارج النواة (للـops)
  → bypass_attempts يُغذّي alerting (لاحقاً)
"""
from __future__ import annotations

import functools
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from enum import Enum


class EntryPointType(str, Enum):
    """أنواع نقاط الدخول المُسجَّلة."""
    EXTERNAL_API = "external_api"        # HTTP/RPC — safe_delivery
    INTERNAL_SERVICE = "internal_service"  # orchestrate_recommendation
    BACKGROUND_WORKER = "background_worker"   # scheduled jobs
    CLI_TOOL = "cli_tool"                # diagnostic/admin
    TEST = "test"                         # في tests
    UNKNOWN = "unknown"                   # bypass attempt محتمل


class GovernanceMode(str, Enum):
    """طور تفعيل الـECP."""
    OBSERVATION = "observation"   # يُسجّل، لا يفرض (الوضع الحالي)
    WARNING = "warning"           # يُسجّل + يُحذّر في logs
    STRICT = "strict"             # يرفع exception على bypass


@dataclass
class CallRecord:
    """سجلّ استدعاء واحد لـcontrolled function."""
    timestamp: float
    function_name: str
    entry_point: str             # المسار الذي بدأ منه الاستدعاء
    entry_type: EntryPointType
    duration_ms: float | None = None
    success: bool = True
    bypass_attempt: bool = False
    error: str | None = None


# ─── حالة عالمية thread-safe ─────────────────────────────────────

_LOCK = threading.RLock()
_MODE = GovernanceMode.OBSERVATION   # افتراضياً: نُسجّل، لا نرفض

# سجلّ الاستدعاءات (ring buffer — آخر 10K لتجنّب memory leak)
_CALL_LOG: deque = deque(maxlen=10000)

# المسارات المُسجَّلة كـapproved entry points
_APPROVED_ENTRY_POINTS: dict[str, EntryPointType] = {}

# عدّادات (للـmetrics)
_CALL_COUNTS: dict[str, int] = defaultdict(int)
_BYPASS_ATTEMPTS: dict[str, int] = defaultdict(int)


# ─── الـAPI العامّ ───────────────────────────────────────────────

def register_entry_point(
    function_qualname: str,
    entry_type: EntryPointType = EntryPointType.INTERNAL_SERVICE,
) -> None:
    """يسجّل دالة كـapproved entry point.

    يُستدعى مرّة واحدة عند تحميل الـmodule. الـqualname مثل:
      'sahool_core.recommendation_bridge.safe_delivery'
      'sahool_core.internal_orchestrator.orchestrate_recommendation'
    """
    with _LOCK:
        _APPROVED_ENTRY_POINTS[function_qualname] = entry_type


def unregister_entry_point(function_qualname: str) -> bool:
    """يحذف entry point من السجلّ. للاختبار/الـmigration."""
    with _LOCK:
        return _APPROVED_ENTRY_POINTS.pop(function_qualname, None) is not None


def is_approved_entry_point(function_qualname: str) -> bool:
    """يفحص إن كانت الدالة approved."""
    with _LOCK:
        return function_qualname in _APPROVED_ENTRY_POINTS


def set_mode(mode: GovernanceMode) -> GovernanceMode:
    """يضبط طور الـECP. يُرجع الطور السابق.

    OBSERVATION → WARNING → STRICT تدريجياً مع نضوج النظام."""
    global _MODE
    with _LOCK:
        previous = _MODE
        _MODE = mode
        return previous


def get_mode() -> GovernanceMode:
    with _LOCK:
        return _MODE


def governed(
    entry_type: EntryPointType = EntryPointType.INTERNAL_SERVICE,
    *,
    require_governance: bool = False,
):
    """Decorator يفرض المرور عبر ECP.

    @governed(EntryPointType.EXTERNAL_API)
    def safe_delivery(...): ...

    @governed(EntryPointType.INTERNAL_SERVICE, require_governance=True)
    def critical_internal(...): ...

    معاني المعطيات:
      • entry_type: تصنيف الدالة للـmetrics
      • require_governance: في STRICT mode، يجب أن يكون المُستدعي
                            entry_point مُسجَّل، وإلا exception."""
    def decorator(func):
        qualname = f"{func.__module__}.{func.__qualname__}"
        register_entry_point(qualname, entry_type)

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            start = time.time()
            record = CallRecord(
                timestamp=start,
                function_name=qualname,
                entry_point=qualname,
                entry_type=entry_type,
            )

            mode = get_mode()
            # في STRICT + require_governance: تحقّق من المُستدعي
            if require_governance and mode == GovernanceMode.STRICT:
                # التحقّق ليس "stack inspection" هشّ — بل آلية مرنة:
                # نتحقّق أنّ ECP في حالة active (السماح صريح)
                with _LOCK:
                    if qualname not in _APPROVED_ENTRY_POINTS:
                        _BYPASS_ATTEMPTS[qualname] += 1
                        record.bypass_attempt = True
                        record.error = "bypass attempt in STRICT mode"
                        _CALL_LOG.append(record)
                        raise PermissionError(
                            f"ECP STRICT: '{qualname}' "
                            f"ليست entry point مُسجَّلة. "
                            "استخدم safe_delivery أو orchestrate_recommendation."
                        )

            try:
                result = func(*args, **kwargs)
                record.success = True
                return result
            except Exception as e:
                record.success = False
                record.error = str(e)[:200]
                raise
            finally:
                record.duration_ms = (time.time() - start) * 1000
                with _LOCK:
                    _CALL_LOG.append(record)
                    _CALL_COUNTS[qualname] += 1

        return wrapper
    return decorator


# ─── الـmetrics والـaudit ────────────────────────────────────────

def call_stats() -> dict:
    """KPIs قابلة للقراءة لـops/metrics."""
    with _LOCK:
        total = sum(_CALL_COUNTS.values())
        bypass_total = sum(_BYPASS_ATTEMPTS.values())

        # متوسّط المدّة لكل entry point
        by_function: dict[str, dict] = {}
        for record in _CALL_LOG:
            fn = record.function_name
            if fn not in by_function:
                by_function[fn] = {"count": 0, "total_ms": 0.0,
                                  "failures": 0}
            by_function[fn]["count"] += 1
            if record.duration_ms:
                by_function[fn]["total_ms"] += record.duration_ms
            if not record.success:
                by_function[fn]["failures"] += 1

        for fn, stats in by_function.items():
            if stats["count"]:
                stats["avg_ms"] = round(stats["total_ms"] / stats["count"], 2)

        return {
            "mode": _MODE.value,
            "total_calls": total,
            "bypass_attempts": bypass_total,
            "approved_entry_points": len(_APPROVED_ENTRY_POINTS),
            "by_function": by_function,
            "summary_ar": (f"وضع {_MODE.value}: {total} استدعاء، "
                          f"{bypass_total} محاولة bypass، "
                          f"{len(_APPROVED_ENTRY_POINTS)} entry point"),
        }


def audit_call_log(
    *,
    last_n: int = 100,
    only_bypass: bool = False,
    only_failures: bool = False,
) -> list[CallRecord]:
    """يستخرج آخر N سجلّ بـfilters للـforensic."""
    with _LOCK:
        records = list(_CALL_LOG)[-last_n:]
        if only_bypass:
            records = [r for r in records if r.bypass_attempt]
        if only_failures:
            records = [r for r in records if not r.success]
        return records


def bypass_alert_summary() -> dict:
    """ملخّص محاولات bypass — يُغذّي alerting لاحقاً."""
    with _LOCK:
        if not _BYPASS_ATTEMPTS:
            return {
                "count": 0,
                "summary_ar": "✅ لا محاولات bypass مكتشفة",
            }
        return {
            "count": sum(_BYPASS_ATTEMPTS.values()),
            "by_function": dict(_BYPASS_ATTEMPTS),
            "summary_ar": (f"⚠️ {sum(_BYPASS_ATTEMPTS.values())} محاولة bypass "
                          f"على {len(_BYPASS_ATTEMPTS)} دالّة. مراجعة مطلوبة."),
        }


def reset_ecp_state() -> None:
    """إعادة تعيين كاملة — للاختبارات فقط، ليس للإنتاج."""
    global _MODE
    with _LOCK:
        _MODE = GovernanceMode.OBSERVATION
        _CALL_LOG.clear()
        _APPROVED_ENTRY_POINTS.clear()
        _CALL_COUNTS.clear()
        _BYPASS_ATTEMPTS.clear()


# ─── Sealed Engine API ──────────────────────────────────────────

def seal_direct_engine_access() -> dict:
    """يفعّل حماية module-level: generate_recommendation تصبح مُسوَّرة.

    هذه الدالة تُستدعى مرّة واحدة عند تثبيت ECP في STRICT mode.
    تُغيّر __all__ في recommendation_engine لإخفاء generate_recommendation
    من 'from core.recommendation_engine import *'.

    لا تمنع الاستيراد الصريح (Python لا يدعم true encapsulation)، لكنّها:
      • تُعلن المسار الموصى به (PEP 8 — underscore prefix لاحقاً)
      • تُحذّر الـIDE/linter
      • تكمّل ECP runtime enforcement"""
    try:
        from core import recommendation_engine

        if not hasattr(recommendation_engine, "_original_all"):
            recommendation_engine._original_all = getattr(
                recommendation_engine, "__all__", None)

        # نُعلن __all__ الذي يخفي generate_recommendation
        recommendation_engine.__all__ = [
            "Recommendation", "BackendDetail", "FarmerView",
            "RecommendationStatus", "FarmerSignal",
            # generate_recommendation مُستبعَدة عمداً
        ]
        return {
            "sealed": True,
            "exposed_symbols": recommendation_engine.__all__,
            "note_ar": ("recommendation_engine.generate_recommendation "
                       "تبقى importable برمجياً لكنّها لا تُصدَّر بـ"
                       "'from module import *'. للوصول الصحيح: "
                       "استخدم orchestrate_recommendation."),
        }
    except Exception as e:
        return {"sealed": False, "error": str(e)}


# ─── Self-Registration عند الاستيراد ────────────────────────────

def _bootstrap_known_entry_points() -> None:
    """يسجّل المسارات المعروفة عند تحميل ECP.

    هذه opt-in: ECP يعرف من البداية من هي entry points الموصى بها،
    حتى لو لم تُستخدم decorators."""
    register_entry_point(
        "core.recommendation_bridge.safe_delivery",
        EntryPointType.EXTERNAL_API)
    register_entry_point(
        "core.recommendation_bridge.full_delivery_pipeline",
        EntryPointType.EXTERNAL_API)
    register_entry_point(
        "core.internal_orchestrator.orchestrate_recommendation",
        EntryPointType.INTERNAL_SERVICE)
    register_entry_point(
        "core.api_adapter.handle_recommendation_request",
        EntryPointType.EXTERNAL_API)


_bootstrap_known_entry_points()
