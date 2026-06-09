"""
services/supervisor-agent/tool_contracts.py — Formal Tool Contracts

مشكلة المراجعة:
    "لا يوجد Formal Tool Contracts ... يجب أن تكون كل أداة:
     { tool, input_schema, output_schema, side_effects, timeout_ms, deterministic }"

الحلّ:
    ١. كل tool يُسجَّل بـToolContract صريح
    ٢. الـsupervisor لا يستدعي أيّ tool بدون contract مسجّل
    ٣. validation للـinput قبل الإرسال
    ٤. validation للـoutput قبل الإرجاع
    ٥. timeout enforcement
    ٦. side-effects تُسجَّل في execution journal
    ٧. capability scoping (per-tenant + per-role)

المرجع:
    AI Orchestration review — "Execution Contract Engine"
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set
from enum import Enum
import asyncio
import hashlib
import json
import logging
import time
import uuid

logger = logging.getLogger(__name__)


# ─── Types ──────────────────────────────────────────────────────

class SideEffectClass(str, Enum):
    """تصنيف الـside-effects لكل tool."""
    PURE = "pure"                  # لا side effects (read-only، deterministic)
    READ_DB = "read_db"            # يقرأ من DB لكن لا يكتب
    WRITE_DB = "write_db"          # يكتب في DB
    EXTERNAL_API = "external_api"  # يستدعي API خارجي (weather, satellite)
    NOTIFICATION = "notification"  # يرسل SMS/email/push
    ACTUATOR = "actuator"          # يشغّل/يوقف مضخّة/أجهزة (CRITICAL)


@dataclass(frozen=True)
class ToolContract:
    """
    التوصيف الرسمي لـtool. كل tool يجب أن يملك واحداً.

    Fields:
        tool_id: معرّف فريد (e.g. "weather.forecast")
        version: SemVer (e.g. "1.0.0")
        input_schema: JSON Schema للـinput
        output_schema: JSON Schema للـoutput
        side_effects: تصنيف side-effects (للـjournaling)
        timeout_ms: حدّ أقصى للتنفيذ
        deterministic: هل نفس الـinput ينتج نفس الـoutput دائماً؟
        required_capabilities: قائمة بالـcapabilities المطلوبة
        cost_estimate: تقدير تكلفة الاستدعاء (للـtoken budgeting)
        retry_policy: إن فشل، هل نُعيد المحاولة؟
        idempotent: هل الاستدعاء مرّتَين = استدعاء مرّة واحدة؟
    """
    tool_id: str
    version: str
    description: str
    input_schema: Dict[str, Any]
    output_schema: Dict[str, Any]
    side_effects: SideEffectClass
    timeout_ms: int = 5000
    deterministic: bool = True
    required_capabilities: List[str] = field(default_factory=list)
    cost_estimate_tokens: int = 0
    retry_policy: str = "exponential_backoff"
    max_retries: int = 3
    idempotent: bool = True

    def __post_init__(self):
        # Validation
        assert "/" not in self.tool_id, "tool_id لا يجب أن يحتوي /"
        assert self.timeout_ms > 0, "timeout_ms يجب أن يكون موجباً"
        if self.side_effects in (SideEffectClass.WRITE_DB, SideEffectClass.ACTUATOR):
            assert self.idempotent or self.max_retries == 0, \
                f"{self.tool_id}: write/actuator يجب أن يكون idempotent أو max_retries=0"


@dataclass
class ToolExecutionResult:
    """نتيجة استدعاء tool."""
    tool_id: str
    invocation_id: str
    success: bool
    output: Optional[Any] = None
    error: Optional[str] = None
    duration_ms: int = 0
    timed_out: bool = False
    side_effects_recorded: bool = False


# ─── Registry ───────────────────────────────────────────────────

class ToolRegistry:
    """
    سجلّ الـtools الرسمي.
    Singleton-like — يُملأ عند bootstrap الـsupervisor-agent.
    """
    def __init__(self):
        self._contracts: Dict[str, ToolContract] = {}
        self._implementations: Dict[str, Callable] = {}

    def register(
        self,
        contract: ToolContract,
        implementation: Callable[..., Any],
    ) -> None:
        """يسجّل tool جديد + implementation."""
        if contract.tool_id in self._contracts:
            raise ValueError(f"tool {contract.tool_id} مسجّل مسبقاً")
        self._contracts[contract.tool_id] = contract
        self._implementations[contract.tool_id] = implementation
        logger.info(
            f"Tool registered: {contract.tool_id} v{contract.version} "
            f"({contract.side_effects.value})"
        )

    def get_contract(self, tool_id: str) -> Optional[ToolContract]:
        return self._contracts.get(tool_id)

    def list_tools(self) -> List[str]:
        return sorted(self._contracts.keys())

    def list_by_side_effect(self, sec: SideEffectClass) -> List[str]:
        return [tid for tid, c in self._contracts.items() if c.side_effects == sec]

    async def invoke(
        self,
        tool_id: str,
        input_data: Dict[str, Any],
        actor_capabilities: Set[str],
        tenant_id: Optional[str] = None,
        journal: Optional['ExecutionJournal'] = None,
    ) -> ToolExecutionResult:
        """
        يستدعي tool مع جميع الـenforcement:
          ١. تحقّق أنّ الـtool مسجّل
          ٢. تحقّق capabilities (least privilege)
          ٣. validate الـinput (basic shape check)
          ٤. enforce timeout
          ٥. record في الـjournal
          ٦. validate الـoutput
        """
        invocation_id = str(uuid.uuid4())
        contract = self._contracts.get(tool_id)

        # ١. tool exists?
        if not contract:
            return ToolExecutionResult(
                tool_id=tool_id, invocation_id=invocation_id,
                success=False, error=f"tool {tool_id} غير مسجّل",
            )

        # ٢. capabilities check
        missing = set(contract.required_capabilities) - actor_capabilities
        if missing:
            err = f"capability denied: {sorted(missing)}"
            if journal:
                await journal.record_denial(invocation_id, tool_id, err, tenant_id)
            return ToolExecutionResult(
                tool_id=tool_id, invocation_id=invocation_id,
                success=False, error=err,
            )

        # ٣. input validation (basic — full JSON Schema لاحقاً)
        if not self._validate_input(input_data, contract.input_schema):
            return ToolExecutionResult(
                tool_id=tool_id, invocation_id=invocation_id,
                success=False, error="input لا يطابق الـschema",
            )

        # ٤. journal — قبل التنفيذ (للـreplay)
        if journal:
            await journal.record_start(
                invocation_id=invocation_id,
                tool_id=tool_id,
                input_data=input_data,
                actor_capabilities=list(actor_capabilities),
                tenant_id=tenant_id,
                contract_version=contract.version,
            )

        # ٥. invoke with timeout
        impl = self._implementations[tool_id]
        start = time.time()
        try:
            output = await asyncio.wait_for(
                impl(**input_data),
                timeout=contract.timeout_ms / 1000.0,
            )
            duration_ms = int((time.time() - start) * 1000)

            # ٦. output validation
            if not self._validate_output(output, contract.output_schema):
                err = "output لا يطابق الـschema"
                if journal:
                    await journal.record_complete(
                        invocation_id, success=False, error=err,
                        duration_ms=duration_ms,
                    )
                return ToolExecutionResult(
                    tool_id=tool_id, invocation_id=invocation_id,
                    success=False, error=err, duration_ms=duration_ms,
                )

            # success
            if journal:
                await journal.record_complete(
                    invocation_id, success=True, output=output,
                    duration_ms=duration_ms,
                )
            return ToolExecutionResult(
                tool_id=tool_id, invocation_id=invocation_id,
                success=True, output=output, duration_ms=duration_ms,
                side_effects_recorded=journal is not None,
            )

        except asyncio.TimeoutError:
            duration_ms = contract.timeout_ms
            err = f"timeout after {contract.timeout_ms}ms"
            if journal:
                await journal.record_complete(
                    invocation_id, success=False, error=err,
                    duration_ms=duration_ms, timed_out=True,
                )
            return ToolExecutionResult(
                tool_id=tool_id, invocation_id=invocation_id,
                success=False, error=err, duration_ms=duration_ms,
                timed_out=True,
            )

        except Exception as e:
            duration_ms = int((time.time() - start) * 1000)
            err = f"{type(e).__name__}: {str(e)[:200]}"
            if journal:
                await journal.record_complete(
                    invocation_id, success=False, error=err,
                    duration_ms=duration_ms,
                )
            return ToolExecutionResult(
                tool_id=tool_id, invocation_id=invocation_id,
                success=False, error=err, duration_ms=duration_ms,
            )

    def _validate_input(self, data: Any, schema: Dict[str, Any]) -> bool:
        """تحقّق أساسي من الـinput shape (للـMVP — JSON Schema كامل لاحقاً)."""
        if schema.get("type") == "object":
            if not isinstance(data, dict):
                return False
            required = schema.get("required", [])
            for key in required:
                if key not in data:
                    return False
        return True

    def _validate_output(self, output: Any, schema: Dict[str, Any]) -> bool:
        """تحقّق أساسي من الـoutput."""
        if schema.get("type") == "object" and not isinstance(output, dict):
            return False
        return True


# ─── Execution Journal (append-only) ─────────────────────────────

@dataclass
class JournalEntry:
    invocation_id: str
    tool_id: str
    event: str                  # "start" | "complete" | "denial"
    timestamp: str
    tenant_id: Optional[str]
    payload: Dict[str, Any]


class ExecutionJournal:
    """
    سجل غير قابل للتغيير لكل invocation.
    Production: يُكتب في append-only Postgres table أو NATS JetStream.
    هنا in-memory للـMVP (يُستبدَل بـPersistentJournal لاحقاً).

    استخدامه:
       - debugging: ما الذي حدث في decision X؟
       - audit: من استدعى actuator متى؟
       - replay: أعد بناء الـstate من history
    """
    def __init__(self):
        self._entries: List[JournalEntry] = []
        self._lock = asyncio.Lock()

    async def record_start(
        self,
        invocation_id: str, tool_id: str,
        input_data: Dict[str, Any],
        actor_capabilities: List[str],
        tenant_id: Optional[str],
        contract_version: str,
    ):
        async with self._lock:
            self._entries.append(JournalEntry(
                invocation_id=invocation_id,
                tool_id=tool_id,
                event="start",
                timestamp=_now_iso(),
                tenant_id=tenant_id,
                payload={
                    "input_hash": _hash_payload(input_data),
                    "actor_capabilities": actor_capabilities,
                    "contract_version": contract_version,
                },
            ))

    async def record_complete(
        self,
        invocation_id: str,
        success: bool,
        output: Any = None,
        error: Optional[str] = None,
        duration_ms: int = 0,
        timed_out: bool = False,
    ):
        async with self._lock:
            # L4 FIX: استخرج tool_id (وtenant_id) من سجلّ "start" لنفس الـ
            # invocation. السابق كتب "" فلم يُملأ أبداً ⇒ get_entries(tool_id)
            # وتدقيق المُشغّلات لا يطابقان أحداث الإكمال (تُسقَط بصمت).
            _start = next(
                (e for e in reversed(self._entries)
                 if e.invocation_id == invocation_id and e.event == "start"),
                None,
            )
            self._entries.append(JournalEntry(
                invocation_id=invocation_id,
                tool_id=(_start.tool_id if _start else ""),
                event="complete",
                timestamp=_now_iso(),
                tenant_id=(_start.tenant_id if _start else None),
                payload={
                    "success": success,
                    "error": error,
                    "duration_ms": duration_ms,
                    "timed_out": timed_out,
                    "output_hash": _hash_payload(output) if output else None,
                },
            ))

    async def record_denial(
        self,
        invocation_id: str, tool_id: str,
        reason: str, tenant_id: Optional[str],
    ):
        async with self._lock:
            self._entries.append(JournalEntry(
                invocation_id=invocation_id,
                tool_id=tool_id,
                event="denial",
                timestamp=_now_iso(),
                tenant_id=tenant_id,
                payload={"reason": reason},
            ))

    async def get_entries(self, tool_id: Optional[str] = None) -> List[JournalEntry]:
        async with self._lock:
            if tool_id:
                return [e for e in self._entries if e.tool_id == tool_id]
            return list(self._entries)

    async def replay(self, invocation_id: str) -> List[JournalEntry]:
        """يستخرج كل الأحداث المتعلّقة بـinvocation معيّن."""
        async with self._lock:
            return [e for e in self._entries if e.invocation_id == invocation_id]


# ─── Helpers ────────────────────────────────────────────────────

def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


def _hash_payload(data: Any) -> str:
    """SHA-256 hash للـpayload (لا نخزّن البيانات الحسّاسة)."""
    if data is None:
        return ""
    try:
        s = json.dumps(data, sort_keys=True, default=str)
    except Exception:
        s = str(data)
    return hashlib.sha256(s.encode()).hexdigest()[:16]


# ─── Example: تسجيل tools حقيقيّة ────────────────────────────────

def bootstrap_default_tools(registry: ToolRegistry) -> None:
    """يسجّل أمثلة من الـtools الحقيقيّة في سهول."""

    # 1. Weather forecast (pure, read-only)
    registry.register(
        ToolContract(
            tool_id="weather.forecast",
            version="1.0.0",
            description="جلب توقّعات الطقس لـ٧ أيّام",
            input_schema={
                "type": "object",
                "required": ["lat", "lng"],
                "properties": {
                    "lat": {"type": "number"},
                    "lng": {"type": "number"},
                    "days": {"type": "integer", "minimum": 1, "maximum": 14},
                },
            },
            output_schema={
                "type": "object",
                "required": ["forecast"],
                "properties": {
                    "forecast": {"type": "array"},
                },
            },
            side_effects=SideEffectClass.EXTERNAL_API,
            timeout_ms=5000,
            deterministic=False,    # weather يتغيّر
            required_capabilities=["weather.read"],
            idempotent=True,
        ),
        implementation=_dummy_weather_impl,
    )

    # 2. Pump start (ACTUATOR — حسّاس جدّاً)
    registry.register(
        ToolContract(
            tool_id="actuator.pump.start",
            version="1.0.0",
            description="تشغيل مضخّة الري",
            input_schema={
                "type": "object",
                "required": ["well_id", "duration_min"],
                "properties": {
                    "well_id": {"type": "string"},
                    "duration_min": {"type": "integer", "minimum": 1, "maximum": 480},
                },
            },
            output_schema={
                "type": "object",
                "required": ["irrigation_event_id"],
            },
            side_effects=SideEffectClass.ACTUATOR,
            timeout_ms=10000,
            deterministic=False,
            required_capabilities=["actuator.pump.control"],
            cost_estimate_tokens=0,
            max_retries=0,    # ⚠ لا retry للـactuators
            idempotent=False,
        ),
        implementation=_dummy_pump_impl,
    )

    # 3. NDVI compute (read DB)
    registry.register(
        ToolContract(
            tool_id="ndvi.compute",
            version="1.0.0",
            description="حساب NDVI من Sentinel-2",
            input_schema={
                "type": "object",
                "required": ["field_id"],
            },
            output_schema={
                "type": "object",
                "required": ["ndvi_mean"],
            },
            side_effects=SideEffectClass.READ_DB,
            timeout_ms=30000,
            deterministic=True,
            required_capabilities=["ndvi.read"],
        ),
        implementation=_dummy_ndvi_impl,
    )


async def _dummy_weather_impl(lat: float, lng: float, days: int = 7):
    """مثال — يُستبدَل بالـimpl الحقيقي."""
    await asyncio.sleep(0.01)
    return {"forecast": [{"day": i, "temp_c": 25 + i} for i in range(days)]}


async def _dummy_pump_impl(well_id: str, duration_min: int):
    await asyncio.sleep(0.01)
    return {"irrigation_event_id": str(uuid.uuid4())}


async def _dummy_ndvi_impl(field_id: str):
    await asyncio.sleep(0.01)
    return {"ndvi_mean": 0.65}
