"""MCP-style tool registry for SAHOOL field-context tools.

This is a dependency-free internal adapter inspired by MCP, not a decision layer.
Tools registered here may only emit Observation/Signal/Annotation envelopes.
They must not emit recommendations, prescriptions, tasks, or farmer-facing advice.
The Canonical Field State remains the only gateway into Recommendation Engine.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Literal

ToolKind = Literal["weather", "lab", "satellite", "iot", "operations", "rag", "kg"]
ToolOutputType = Literal["observation", "signal", "annotation"]


class ToolDecisionLeakError(ValueError):
    """Raised when an MCP tool tries to bypass Field State."""


class ToolUnavailableError(RuntimeError):
    """Raised when circuit breaker is open for a tool."""


class CostLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class LatencyClass(str, Enum):
    FAST = "fast"
    NORMAL = "normal"
    SLOW = "slow"


FORBIDDEN_KEYS = {
    "recommendation",
    "prescription",
    "task",
    "farmer_advice",
    "decision",
    "dose",
    "fertilizer_rate",
    "pesticide_application",
    "seed_rate",
}


def _find_forbidden_keys(obj: Any, *, path: str = "") -> list[str]:
    """Recursively scan JSON-like keys, not string values.

    This avoids false positives where a harmless citation mentions the word
    'recommendation', while still blocking any structured decision payload.
    """
    found: list[str] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            key = str(k).lower()
            key_path = f"{path}.{key}" if path else key
            if key in FORBIDDEN_KEYS:
                found.append(key_path)
            found.extend(_find_forbidden_keys(v, path=key_path))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            found.extend(_find_forbidden_keys(v, path=f"{path}[{i}]"))
    return found


@dataclass(frozen=True)
class ToolSpec:
    name: str
    kind: ToolKind
    output_type: ToolOutputType
    required_permissions: tuple[str, ...] = ("FIELD_VIEW",)
    timeout_ms: int = 500
    sla_ms: int = 500
    cost_level: CostLevel = CostLevel.LOW
    latency_class: LatencyClass = LatencyClass.NORMAL
    max_failures: int = 3

    def __post_init__(self) -> None:
        if self.kind in {"rag", "kg"} and self.output_type != "annotation":
            raise ToolDecisionLeakError("RAG/KG tools must be annotation-only")


@dataclass(frozen=True)
class ToolEnvelope:
    tool: str
    kind: ToolKind
    output_type: ToolOutputType
    payload: dict[str, Any]
    verified: bool = False
    latency_ms: float = 0.0

    def __post_init__(self) -> None:
        leaked = _find_forbidden_keys(self.payload)
        if leaked:
            raise ToolDecisionLeakError(
                f"MCP tool '{self.tool}' emitted decision fields: {sorted(leaked)}"
            )
        if self.kind in {"rag", "kg"} and (self.verified or self.output_type != "annotation"):
            raise ToolDecisionLeakError("RAG/KG outputs must remain unverified annotations")

    def as_context_result(self) -> dict[str, Any]:
        return {
            "source": self.tool,
            "kind": self.kind,
            "payload": {**self.payload, "verified": self.verified},
        }


@dataclass
class ToolHealth:
    available: bool = True
    latency_ms: float = 0.0
    last_success: float | None = None
    error_count: int = 0
    circuit_open: bool = False
    last_error: str | None = None


@dataclass
class RegisteredTool:
    spec: ToolSpec
    handler: Callable[..., dict[str, Any]]
    health: ToolHealth = field(default_factory=ToolHealth)


class MCPToolRegistry:
    """Explicit dynamic registry for context tools.

    It gives the Coordinator MCP-like discovery without allowing tools to make
    agronomic decisions directly.  Includes health, basic circuit breaker, and
    cost/latency metadata without adding runtime dependencies.
    """

    def __init__(self) -> None:
        self._tools: dict[str, RegisteredTool] = {}

    def register(self, spec: ToolSpec, handler: Callable[..., dict[str, Any]]) -> None:
        self._tools[spec.name] = RegisteredTool(spec=spec, handler=handler)

    def discover(
        self, *, kind: ToolKind | None = None, max_cost: CostLevel | None = None
    ) -> list[ToolSpec]:
        specs = [registered.spec for registered in self._tools.values()]
        if kind is not None:
            specs = [spec for spec in specs if spec.kind == kind]
        if max_cost is not None:
            order = {CostLevel.LOW: 0, CostLevel.MEDIUM: 1, CostLevel.HIGH: 2}
            specs = [spec for spec in specs if order[spec.cost_level] <= order[max_cost]]
        return sorted(specs, key=lambda spec: (spec.cost_level.value, spec.name))

    def health(self) -> dict[str, ToolHealth]:
        return {name: registered.health for name, registered in self._tools.items()}

    def reset_circuit(self, tool_name: str) -> None:
        registered = self._tools[tool_name]
        registered.health.error_count = 0
        registered.health.circuit_open = False
        registered.health.available = True
        registered.health.last_error = None

    def call(self, tool_name: str, **kwargs: Any) -> ToolEnvelope:
        if tool_name not in self._tools:
            raise KeyError(f"Unknown MCP tool: {tool_name}")
        registered = self._tools[tool_name]
        health = registered.health
        if health.circuit_open:
            raise ToolUnavailableError(f"MCP tool circuit open: {tool_name}")

        started = time.perf_counter()
        try:
            payload = dict(registered.handler(**kwargs))
            verified = bool(payload.pop("verified", False))
            latency_ms = (time.perf_counter() - started) * 1000
            envelope = ToolEnvelope(
                tool=registered.spec.name,
                kind=registered.spec.kind,
                output_type=registered.spec.output_type,
                payload=payload,
                verified=verified,
                latency_ms=latency_ms,
            )
            health.available = True
            health.latency_ms = latency_ms
            health.last_success = time.time()
            health.error_count = 0
            health.circuit_open = False
            health.last_error = None
            return envelope
        except Exception as exc:
            health.available = False
            health.error_count += 1
            health.last_error = str(exc)
            health.latency_ms = (time.perf_counter() - started) * 1000
            if health.error_count >= registered.spec.max_failures:
                health.circuit_open = True
            raise

    def tool_metadata(self) -> list[dict[str, Any]]:
        return [
            {
                "name": spec.name,
                "kind": spec.kind,
                "output_type": spec.output_type,
                "cost_level": spec.cost_level.value,
                "latency_class": spec.latency_class.value,
                "sla_ms": spec.sla_ms,
                "available": self._tools[spec.name].health.available,
            }
            for spec in self.discover()
        ]


def default_context_registry() -> MCPToolRegistry:
    """Build a safe default registry with thin internal wrappers.

    Real service calls can replace handlers at runtime; the contract remains the
    same, so adding IoT or external connectors does not modify the coordinator.
    """
    reg = MCPToolRegistry()
    reg.register(
        ToolSpec(
            "weather.get_daily",
            "weather",
            "signal",
            sla_ms=500,
            cost_level=CostLevel.LOW,
            latency_class=LatencyClass.FAST,
        ),
        lambda **kw: {"name": "weather", "value": kw, "verified": bool(kw.get("verified", True))},
    )
    reg.register(
        ToolSpec(
            "lab.latest_results",
            "lab",
            "signal",
            sla_ms=500,
            cost_level=CostLevel.LOW,
            latency_class=LatencyClass.FAST,
        ),
        lambda **kw: {
            "name": kw.get("name", "lab"),
            "value": kw,
            "verified": bool(kw.get("verified", True)),
        },
    )
    reg.register(
        ToolSpec(
            "rag.search",
            "rag",
            "annotation",
            sla_ms=700,
            cost_level=CostLevel.MEDIUM,
            latency_class=LatencyClass.NORMAL,
        ),
        lambda **kw: {"text": kw.get("query", ""), "citations": kw.get("citations", [])},
    )
    reg.register(
        ToolSpec(
            "kg.query",
            "kg",
            "annotation",
            sla_ms=300,
            cost_level=CostLevel.LOW,
            latency_class=LatencyClass.FAST,
        ),
        lambda **kw: {"query": kw.get("query", ""), "edges": kw.get("edges", [])},
    )
    return reg
