"""
services/sahool-platform/api/failure_modes.py — Explicit Failure Taxonomy

المرجع: المراجعة (مستند ١١.١٠):
   "لا يظهر وجود Failure Taxonomy حقيقي مثل:
      - satellite unavailable
      - cloud contamination
      - stale weather
      - corrupted raster
      - AI hallucination
      - delayed synchronization

   والخطر: النظام يتصرّف وكأن كل البيانات صحيحة دائماً"

✅ الادّعاء صحيح. هذا الملف يحدّد بصراحة:
   ١. ما هي الحالات الفاشلة المعروفة
   ٢. كيف نكتشفها
   ٣. ما هو الـfallback لكل واحدة
   ٤. ماذا نعرض للمستخدم

هذا ليس "AI Failure Detection" — هو قاموس صريح للحالات الزراعيّة الواقعيّة.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import List, Dict, Optional, Any


# ─── Failure categories ─────────────────────────────────────────

class FailureCategory(str, Enum):
    DATA_UNAVAILABLE = "data_unavailable"
    DATA_DEGRADED = "data_degraded"          # موجود لكن ضعيف
    DATA_STALE = "data_stale"                # قديم جدّاً
    DATA_CORRUPTED = "data_corrupted"        # invalid syntax/range
    SOURCE_OFFLINE = "source_offline"        # API/sensor down
    INFERENCE_FAILURE = "inference_failure"  # model crashed/timeout
    POLICY_VIOLATION = "policy_violation"    # guardrails rejected
    USER_INPUT_INVALID = "user_input_invalid"
    UNKNOWN = "unknown"


class FailureSeverity(str, Enum):
    INFO = "info"          # log only
    WARNING = "warning"    # show to user, continue with reduced confidence
    DEGRADED = "degraded"  # show fallback, partial functionality
    CRITICAL = "critical"  # halt operation, require user attention


class FallbackStrategy(str, Enum):
    NONE = "none"                          # no fallback, fail loudly
    USE_CACHED = "use_cached"              # last-known-good value
    USE_HISTORICAL = "use_historical"      # 30-day average
    USE_NEARBY_FIELD = "use_nearby_field"  # spatial fallback
    USE_RULE_BASED = "use_rule_based"      # disable AI, use rules
    DEFER_DECISION = "defer_decision"      # don't decide, prompt user
    SAFE_DEFAULT = "safe_default"          # most-conservative action


class RetryPolicy(str, Enum):
    NO_RETRY = "no_retry"                  # corrupt data, banned chems
    IMMEDIATE = "immediate"                # transient (rare)
    EXP_BACKOFF = "exp_backoff"            # network/API timeouts
    WAIT_NEXT_CYCLE = "wait_next_cycle"    # wait for next Sentinel pass
    MANUAL_INTERVENTION = "manual"         # user/operator must act


@dataclass
class RetryHint:
    """retry guidance machine-readable للـclient/worker."""
    policy: RetryPolicy
    max_attempts: int = 3
    initial_delay_sec: int = 1
    max_delay_sec: int = 300
    backoff_factor: float = 2.0


# Default retry hints per category
DEFAULT_RETRY: Dict["FailureCategory", RetryHint] = {}   # populated after class def


# ─── Known failure modes (catalog) ──────────────────────────────

@dataclass
class FailureMode:
    code: str                        # machine-readable
    category: FailureCategory
    severity: FailureSeverity
    message_ar: str
    user_action_ar: str              # ماذا يفعل المزارع؟
    fallback: FallbackStrategy
    retry: Optional[RetryHint] = None  # ← retry-aware
    technical_details: Optional[str] = None


# المرجع: كل failure mode تمّت رؤيتها أو متوقّعتها في ميدان السياق اليمني
FAILURE_CATALOG: Dict[str, FailureMode] = {
    # ── Satellite / Remote Sensing ──
    "sentinel.cloud_high": FailureMode(
        code="sentinel.cloud_high",
        category=FailureCategory.DATA_DEGRADED,
        severity=FailureSeverity.WARNING,
        message_ar="تغطية سحب عالية في آخر صورة قمر صناعي",
        user_action_ar="انتظر صورة جديدة (٥ أيّام) أو خُذ مشاهدة ميدانيّة",
        fallback=FallbackStrategy.USE_CACHED,
        retry=RetryHint(policy=RetryPolicy.WAIT_NEXT_CYCLE, max_attempts=1),
    ),
    "sentinel.unavailable": FailureMode(
        code="sentinel.unavailable",
        category=FailureCategory.SOURCE_OFFLINE,
        severity=FailureSeverity.DEGRADED,
        message_ar="خدمة الأقمار الصناعيّة غير متاحة حالياً",
        user_action_ar="استمرّ في العمل — البيانات السابقة لا تزال قيد التحميل",
        fallback=FallbackStrategy.USE_CACHED,
        retry=RetryHint(policy=RetryPolicy.EXP_BACKOFF, max_attempts=5,
                        initial_delay_sec=60, max_delay_sec=3600),
    ),
    "sentinel.stale": FailureMode(
        code="sentinel.stale",
        category=FailureCategory.DATA_STALE,
        severity=FailureSeverity.WARNING,
        message_ar="آخر صورة قمر صناعي أقدم من ١٤ يوم",
        user_action_ar="القرارات حسّاسة لذلك خذ المشاهدات الميدانيّة بعين الاعتبار",
        fallback=FallbackStrategy.USE_HISTORICAL,
        retry=RetryHint(policy=RetryPolicy.WAIT_NEXT_CYCLE, max_attempts=1),
    ),

    # ── Weather ──
    "weather.api_offline": FailureMode(
        code="weather.api_offline",
        category=FailureCategory.SOURCE_OFFLINE,
        severity=FailureSeverity.WARNING,
        message_ar="خدمة الطقس مؤقّتاً غير متاحة",
        user_action_ar="القرارات اليوم بدون توقّعات الطقس",
        fallback=FallbackStrategy.USE_HISTORICAL,
        retry=RetryHint(policy=RetryPolicy.EXP_BACKOFF, max_attempts=4),
    ),
    "weather.stale": FailureMode(
        code="weather.stale",
        category=FailureCategory.DATA_STALE,
        severity=FailureSeverity.WARNING,
        message_ar="بيانات الطقس أقدم من ٤٨ ساعة",
        user_action_ar="لا تعتمد على توصيات الري المرتبطة بالـET0",
        fallback=FallbackStrategy.USE_HISTORICAL,
        retry=RetryHint(policy=RetryPolicy.IMMEDIATE, max_attempts=1),
    ),

    # ── Soil / Lab ──
    "soil.no_recent_lab": FailureMode(
        code="soil.no_recent_lab",
        category=FailureCategory.DATA_UNAVAILABLE,
        severity=FailureSeverity.WARNING,
        message_ar="لا توجد تحاليل تربة حديثة (أقدم من سنة)",
        user_action_ar="التوصيات قائمة على متوسّطات المنطقة. خذ عيّنة للحصول على دقّة أعلى",
        fallback=FallbackStrategy.USE_HISTORICAL,
        retry=RetryHint(policy=RetryPolicy.MANUAL_INTERVENTION, max_attempts=0),
    ),
    "soil.invalid_range": FailureMode(
        code="soil.invalid_range",
        category=FailureCategory.DATA_CORRUPTED,
        severity=FailureSeverity.CRITICAL,
        message_ar="قيمة تحليل تربة خارج النطاق الفيزيائي (مثل pH=15)",
        user_action_ar="تحقّق من إدخال البيانات — قد تكون وحدة خاطئة",
        fallback=FallbackStrategy.NONE,
        retry=RetryHint(policy=RetryPolicy.NO_RETRY, max_attempts=0),
    ),

    # ── AI / Inference ──
    "ai.confidence_too_low": FailureMode(
        code="ai.confidence_too_low",
        category=FailureCategory.DATA_DEGRADED,
        severity=FailureSeverity.WARNING,
        message_ar="ثقة الذكاء الاصطناعي في هذه التوصية منخفضة",
        user_action_ar="لا تتّخذ قرار صرف ري/سماد بناءً على هذه التوصية وحدها",
        fallback=FallbackStrategy.USE_RULE_BASED,
        retry=RetryHint(policy=RetryPolicy.NO_RETRY, max_attempts=0),
    ),
    "ai.timeout": FailureMode(
        code="ai.timeout",
        category=FailureCategory.INFERENCE_FAILURE,
        severity=FailureSeverity.DEGRADED,
        message_ar="انتهت مهلة معالجة الذكاء الاصطناعي",
        user_action_ar="تمّ استخدام القواعد المباشرة بدلاً من الـAI",
        fallback=FallbackStrategy.USE_RULE_BASED,
        retry=RetryHint(policy=RetryPolicy.EXP_BACKOFF, max_attempts=2,
                        initial_delay_sec=2),
    ),
    "ai.unknown_crop": FailureMode(
        code="ai.unknown_crop",
        category=FailureCategory.USER_INPUT_INVALID,
        severity=FailureSeverity.WARNING,
        message_ar="المحصول غير معروف في قاعدة المعرفة",
        user_action_ar="اختر محصول قريب أو اطلب من المهندس الزراعي المساعدة",
        fallback=FallbackStrategy.DEFER_DECISION,
        retry=RetryHint(policy=RetryPolicy.MANUAL_INTERVENTION, max_attempts=0),
    ),

    # ── Policy / Guardrails ──
    "policy.banned_chemical": FailureMode(
        code="policy.banned_chemical",
        category=FailureCategory.POLICY_VIOLATION,
        severity=FailureSeverity.CRITICAL,
        message_ar="المبيد المطلوب محظور في اليمن",
        user_action_ar="ابحث عن بدائل آمنة. لا توصية معه ممكنة",
        fallback=FallbackStrategy.NONE,
        retry=RetryHint(policy=RetryPolicy.NO_RETRY, max_attempts=0),
    ),
    "policy.dosage_exceeded": FailureMode(
        code="policy.dosage_exceeded",
        category=FailureCategory.POLICY_VIOLATION,
        severity=FailureSeverity.CRITICAL,
        message_ar="الجرعة المطلوبة تتجاوز الحدّ الآمن",
        user_action_ar="تطبيق هذه الجرعة خطر صحّي وبيئيّ — تمّ رفضها",
        fallback=FallbackStrategy.SAFE_DEFAULT,
        retry=RetryHint(policy=RetryPolicy.NO_RETRY, max_attempts=0),
    ),

    # ── User input ──
    "field.polygon_invalid": FailureMode(
        code="field.polygon_invalid",
        category=FailureCategory.USER_INPUT_INVALID,
        severity=FailureSeverity.CRITICAL,
        message_ar="حدود الحقل غير صالحة (تقاطع ذاتي أو نقاط ناقصة)",
        user_action_ar="ارسم الحدود من جديد بدون تقاطعات",
        fallback=FallbackStrategy.NONE,
        retry=RetryHint(policy=RetryPolicy.MANUAL_INTERVENTION, max_attempts=0),
    ),
    "field.outside_yemen": FailureMode(
        code="field.outside_yemen",
        category=FailureCategory.USER_INPUT_INVALID,
        severity=FailureSeverity.WARNING,
        message_ar="إحداثيّات الحقل تبدو خارج اليمن",
        user_action_ar="تأكّد من إعدادات الـGPS — قد يكون الترتيب (lat,lng) معكوس",
        fallback=FallbackStrategy.NONE,
        retry=RetryHint(policy=RetryPolicy.MANUAL_INTERVENTION, max_attempts=0),
    ),

    # ── Sync / Network ──
    "sync.queue_overflow": FailureMode(
        code="sync.queue_overflow",
        category=FailureCategory.DATA_DEGRADED,
        severity=FailureSeverity.WARNING,
        message_ar="عمليّات كثيرة في طابور المزامنة (>١٠٠)",
        user_action_ar="حاول الاتّصال بشبكة قويّة لمزامنة سريعة",
        fallback=FallbackStrategy.USE_CACHED,
        retry=RetryHint(policy=RetryPolicy.EXP_BACKOFF, max_attempts=10,
                        initial_delay_sec=10),
    ),
}


# ─── Result type ────────────────────────────────────────────────

@dataclass
class FailureReport:
    """ما يُرجَع لكل عمليّة تعرف بالـfailure modes."""
    failure_mode: FailureMode
    detected_at: str
    context: Dict[str, Any] = field(default_factory=dict)
    fallback_applied: bool = False
    fallback_value: Optional[Any] = None

    def to_dict(self) -> Dict[str, Any]:
        d = {
            "code": self.failure_mode.code,
            "category": self.failure_mode.category.value,
            "severity": self.failure_mode.severity.value,
            "message_ar": self.failure_mode.message_ar,
            "user_action_ar": self.failure_mode.user_action_ar,
            "fallback": self.failure_mode.fallback.value,
            "fallback_applied": self.fallback_applied,
            "detected_at": self.detected_at,
            "context": self.context,
        }
        if self.failure_mode.retry:
            d["retry"] = {
                "policy": self.failure_mode.retry.policy.value,
                "max_attempts": self.failure_mode.retry.max_attempts,
                "initial_delay_sec": self.failure_mode.retry.initial_delay_sec,
                "max_delay_sec": self.failure_mode.retry.max_delay_sec,
                "backoff_factor": self.failure_mode.retry.backoff_factor,
            }
        return d


# ─── Detector functions ─────────────────────────────────────────

def detect(code: str, **context) -> FailureReport:
    """يُرجع FailureReport بـcode معروف."""
    mode = FAILURE_CATALOG.get(code)
    if not mode:
        mode = FailureMode(
            code=f"unknown:{code}",
            category=FailureCategory.UNKNOWN,
            severity=FailureSeverity.WARNING,
            message_ar=f"حالة غير معروفة: {code}",
            user_action_ar="تواصل مع الدعم الفنّي",
            fallback=FallbackStrategy.NONE,
        )

    return FailureReport(
        failure_mode=mode,
        detected_at=datetime.now(timezone.utc).isoformat(),
        context=context,
    )


def detect_sentinel_issues(
    cloud_pct: float, days_since_observation: int,
) -> Optional[FailureReport]:
    """يفحص حالة قراءة Sentinel ويُرجع failure إن وجد."""
    if cloud_pct > 80:
        return detect("sentinel.cloud_high", cloud_pct=cloud_pct)
    if days_since_observation > 14:
        return detect("sentinel.stale", days=days_since_observation)
    return None


def detect_weather_issues(hours_since_update: int) -> Optional[FailureReport]:
    if hours_since_update > 48:
        return detect("weather.stale", hours=hours_since_update)
    return None


def detect_soil_issues(soil_data: Dict[str, Any]) -> List[FailureReport]:
    """يفحص قيم soil ويُرجع كل المشاكل."""
    failures = []

    ph = soil_data.get("soil_ph")
    if ph is not None and (ph < 3 or ph > 12):
        failures.append(detect("soil.invalid_range", field="soil_ph", value=ph))

    ec = soil_data.get("soil_ec")
    if ec is not None and (ec < 0 or ec > 50):
        failures.append(detect("soil.invalid_range", field="soil_ec", value=ec))

    last_sample = soil_data.get("last_sample_days_ago")
    if last_sample is None or last_sample > 365:
        failures.append(detect("soil.no_recent_lab", days=last_sample or "unknown"))

    return failures


def severity_rank(severity: FailureSeverity) -> int:
    return {
        FailureSeverity.INFO: 0,
        FailureSeverity.WARNING: 1,
        FailureSeverity.DEGRADED: 2,
        FailureSeverity.CRITICAL: 3,
    }[severity]


def highest_severity(failures: List[FailureReport]) -> Optional[FailureSeverity]:
    if not failures:
        return None
    return max(failures, key=lambda f: severity_rank(f.failure_mode.severity)).failure_mode.severity
