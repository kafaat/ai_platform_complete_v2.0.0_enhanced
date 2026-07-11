"""WX-12 runtime workers for the governed model lifecycle.

The service deliberately separates authoritative state (decision-service) from external side
 effects (registry, traffic router, inference endpoint, trainer). Every adapter is HTTP/CAS based,
 idempotent at the decision boundary, observable, and fail-closed in production.
"""

from __future__ import annotations

import json
import logging
import os
import random
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

LOG = logging.getLogger("model-lifecycle-runtime")


class RuntimeContractError(RuntimeError):
    pass


def _env(name: str, default: str = "", *, required_prod: bool = False) -> str:
    value = os.getenv(name, default).strip()
    if required_prod and os.getenv("SAHOOL_ENV", "").lower() == "production" and not value:
        raise RuntimeContractError(f"{name} is required in production")
    return value


def _json_request(
    method: str,
    url: str,
    *,
    token: str = "",
    body: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = 15.0,
) -> dict[str, Any]:
    payload = (
        None if body is None else json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
    )
    request_headers = {"Accept": "application/json", **(headers or {})}
    if payload is not None:
        request_headers["Content-Type"] = "application/json"
    if token:
        request_headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=payload, headers=request_headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            raw = response.read().decode()
            return json.loads(raw or "{}")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:1000]
        raise RuntimeContractError(f"HTTP {exc.code} from {url}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeContractError(f"request failed for {url}: {exc.reason}") from exc


class DecisionClient:
    def __init__(self) -> None:
        self.base = _env("DECISION_SERVICE_URL", "http://decision-service:8090").rstrip("/")
        self.token = _env("DECISION_SERVICE_TOKEN", required_prod=True)
        self.timeout = float(_env("DECISION_SERVICE_TIMEOUT_SECONDS", "15"))

    def get(
        self, path: str, tenant_id: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        query = "" if not params else "?" + urllib.parse.urlencode(params)
        return _json_request(
            "GET",
            self.base + path + query,
            token=self.token,
            headers={"X-Tenant-Id": tenant_id},
            timeout=self.timeout,
        )

    def post(
        self,
        path: str,
        tenant_id: str,
        body: dict[str, Any],
        actor_headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        return _json_request(
            "POST",
            self.base + path,
            token=self.token,
            body=body,
            headers={"X-Tenant-Id": tenant_id, **(actor_headers or {})},
            timeout=self.timeout,
        )


class HttpTrafficController:
    """Traffic routing adapter. The controller endpoint must implement compare-and-swap."""

    def __init__(self) -> None:
        self.base = _env("MODEL_TRAFFIC_CONTROLLER_URL", required_prod=True).rstrip("/")
        self.token = _env("MODEL_TRAFFIC_CONTROLLER_TOKEN", required_prod=True)

    def apply(self, plan: dict[str, Any]) -> dict[str, Any]:
        if not self.base:
            raise RuntimeContractError("MODEL_TRAFFIC_CONTROLLER_URL is required")
        payload = {
            "model_id": plan["model_id"],
            "feature_set_id": plan["feature_set_id"],
            "environment": plan["target_environment"],
            "mode": plan["rollout_mode"],
            "traffic_percent": plan["traffic_percent"],
            "candidate_artifact_digest": plan["candidate_artifact_digest"],
            "expected_active_artifact_digest": plan["expected_active_artifact_digest"],
            "idempotency_key": plan["rollout_plan_id"],
        }
        result = _json_request(
            "POST", self.base + "/v1/model-routing:cas", token=self.token, body=payload
        )
        observed = result.get("candidate_artifact_digest")
        if observed != payload["candidate_artifact_digest"]:
            raise RuntimeContractError("traffic controller returned a different candidate digest")
        return result


class HttpInferenceVerifier:
    def __init__(self) -> None:
        self.base = _env("MODEL_INFERENCE_VERIFY_URL", required_prod=True).rstrip("/")
        self.token = _env("MODEL_INFERENCE_VERIFY_TOKEN", required_prod=True)

    def verify(self, receipt: dict[str, Any]) -> dict[str, Any]:
        if not self.base:
            raise RuntimeContractError("MODEL_INFERENCE_VERIFY_URL is required")
        started = time.monotonic()
        result = _json_request(
            "POST",
            self.base + "/v1/models:verify",
            token=self.token,
            body={
                "model_id": receipt["model_id"],
                "feature_set_id": receipt["feature_set_id"],
                "environment": receipt["target_environment"],
                "artifact_uri": receipt["active_artifact_uri"],
                "artifact_digest": receipt["active_artifact_digest"],
                "checks": ["artifact_digest", "schema", "feature_set", "smoke_inference"],
            },
        )
        elapsed_ms = (time.monotonic() - started) * 1000
        if result.get("artifact_digest") != receipt["active_artifact_digest"]:
            raise RuntimeContractError("verification target digest mismatch")
        checks = result.get("checks") or {}
        failures = [name for name, ok in checks.items() if not bool(ok)]
        max_latency = float(_env("MODEL_VERIFY_MAX_LATENCY_MS", "1500"))
        state = "verified_healthy"
        if failures:
            state = "verification_failed"
        elif elapsed_ms > max_latency:
            state = "verified_degraded"
        return {
            "verification_state": state,
            "latency_ms": elapsed_ms,
            "checks": checks,
            "failure_reason": ",".join(failures) if failures else None,
        }


class HttpMetricsSource:
    def __init__(self) -> None:
        self.base = _env("MODEL_METRICS_SOURCE_URL", required_prod=True).rstrip("/")
        self.token = _env("MODEL_METRICS_SOURCE_TOKEN", required_prod=True)

    def window(
        self, *, model_id: str, feature_set_id: str, environment: str, start: str, end: str
    ) -> dict[str, Any]:
        if not self.base:
            raise RuntimeContractError("MODEL_METRICS_SOURCE_URL is required")
        query = urllib.parse.urlencode(
            {
                "model_id": model_id,
                "feature_set_id": feature_set_id,
                "environment": environment,
                "window_start": start,
                "window_end": end,
            }
        )
        return _json_request("GET", self.base + "/v1/model-metrics?" + query, token=self.token)


class HttpTrainingBackend:
    def __init__(self) -> None:
        self.base = _env("MODEL_TRAINING_BACKEND_URL", required_prod=True).rstrip("/")
        self.token = _env("MODEL_TRAINING_BACKEND_TOKEN", required_prod=True)

    def submit(self, request: dict[str, Any]) -> dict[str, Any]:
        if not self.base:
            raise RuntimeContractError("MODEL_TRAINING_BACKEND_URL is required")
        result = _json_request(
            "POST",
            self.base + "/v1/training-jobs",
            token=self.token,
            body={
                "request_id": request["retraining_request_id"],
                "model_id": request["model_id"],
                "feature_set_id": request["feature_set_id"],
                "dataset_fingerprint": request["dataset_fingerprint"],
                "training_manifest": request["training_manifest"],
                "code_version": request["code_version"],
                "hyperparameters": request["hyperparameters"],
                "idempotency_key": request["retraining_request_id"],
            },
        )
        if result.get("request_id") != request["retraining_request_id"]:
            raise RuntimeContractError("training backend request correlation mismatch")
        return result


def classify_drift(metrics: dict[str, Any]) -> str:
    thresholds = {
        "feature_drift": float(_env("MODEL_DRIFT_FEATURE_WARNING", "0.15")),
        "prediction_drift": float(_env("MODEL_DRIFT_PREDICTION_WARNING", "0.15")),
        "calibration_error": float(_env("MODEL_DRIFT_CALIBRATION_WARNING", "0.10")),
        "error_rate": float(_env("MODEL_DRIFT_ERROR_WARNING", "0.05")),
    }
    critical_multiplier = float(_env("MODEL_DRIFT_CRITICAL_MULTIPLIER", "2"))
    values = {k: float(metrics.get(k, 0) or 0) for k in thresholds}
    if any(values[k] >= thresholds[k] * critical_multiplier for k in thresholds):
        return "critical"
    if any(values[k] >= thresholds[k] for k in thresholds):
        return "warning"
    return "stable"


@dataclass
class Backoff:
    minimum: float = 1.0
    maximum: float = 60.0
    factor: float = 2.0
    jitter: float = 0.2
    current: float = 1.0

    def reset(self) -> None:
        self.current = self.minimum

    def next(self) -> float:
        base = min(self.current, self.maximum)
        self.current = min(self.maximum, max(self.minimum, self.current * self.factor))
        return max(0.0, base * (1 + random.uniform(-self.jitter, self.jitter)))


class LifecycleRuntime:
    def __init__(self, decision: DecisionClient | None = None) -> None:
        self.decision = decision or DecisionClient()
        self.adapter_id = _env("REGISTRY_ADAPTER_ID", required_prod=True)

    def reconcile_active_state(
        self,
        tenant_id: str,
        model_id: str,
        feature_set_id: str,
        environment: str,
        registry_get: Callable[..., Any],
    ) -> dict[str, Any]:
        projection = self.decision.get(
            f"/v1/learning/models/{model_id}/active-state",
            tenant_id,
            {"feature_set_id": feature_set_id, "target_environment": environment},
        )
        actual = registry_get(model_id, environment, projection["registry_alias"])
        drift = actual.artifact_digest != projection["active_artifact_digest"]
        evidence = {
            "model_id": model_id,
            "feature_set_id": feature_set_id,
            "environment": environment,
            "expected_digest": projection["active_artifact_digest"],
            "observed_digest": actual.artifact_digest,
            "registry_version": actual.version,
            "drift_detected": drift,
        }
        if drift:
            LOG.error("registry alias drift detected", extra=evidence)
        return evidence

    def verify_activation(self, tenant_id: str, receipt: dict[str, Any]) -> dict[str, Any]:
        result = HttpInferenceVerifier().verify(receipt)
        receipt_id = receipt["activation_receipt_id"]
        return self.decision.post(
            f"/v1/learning/activation-receipts/{receipt_id}/verification",
            tenant_id,
            {
                "verification_state": result["verification_state"],
                "artifact_digest": receipt["active_artifact_digest"],
                "checks": result["checks"],
                "latency_ms": result["latency_ms"],
                "failure_reason": result["failure_reason"],
                # deterministic per receipt: safe to retry without duplicating evidence.
                "idempotency_key": f"verify:{receipt_id}",
            },
            actor_headers={"X-Verified-By": self.adapter_id},
        )

    def apply_rollout(self, tenant_id: str, plan: dict[str, Any]) -> dict[str, Any]:
        result = HttpTrafficController().apply(plan)
        plan_id = plan["rollout_plan_id"]
        return self.decision.post(
            f"/v1/learning/rollout-plans/{plan_id}/receipt",
            tenant_id,
            {
                "receipt_state": "applied",
                "controller_id": self.adapter_id,
                "observed_traffic_percent": result.get("traffic_percent"),
                "candidate_artifact_digest": result.get("candidate_artifact_digest"),
                "routing_version": result.get("version"),
                "idempotency_key": f"rollout:{plan_id}",
            },
            actor_headers={"X-Recorded-By": self.adapter_id},
        )

    def record_monitoring(
        self, tenant_id: str, active: dict[str, Any], start: str, end: str
    ) -> dict[str, Any]:
        metrics = HttpMetricsSource().window(
            model_id=active["model_id"],
            feature_set_id=active["feature_set_id"],
            environment=active["target_environment"],
            start=start,
            end=end,
        )
        sample_count = int(metrics.get("sample_count", 0))
        minimum = int(_env("MODEL_MONITORING_MIN_SAMPLES", "100"))
        state = "warning" if sample_count < minimum else classify_drift(metrics)
        return self.decision.post(
            "/v1/learning/monitoring-snapshots",
            tenant_id,
            {
                "model_id": active["model_id"],
                "feature_set_id": active["feature_set_id"],
                "target_environment": active["target_environment"],
                "window_start": start,
                "window_end": end,
                "sample_count": sample_count,
                "metrics": metrics,
                "drift_state": state,
                # deterministic per (model, environment, window): retry-safe.
                "idempotency_key": (
                    f"monitor:{active['model_id']}:{active['target_environment']}:{start}:{end}"
                ),
            },
            actor_headers={"X-Captured-By": self.adapter_id},
        )

    def dispatch_retraining(self, tenant_id: str, request: dict[str, Any]) -> dict[str, Any]:
        result = HttpTrainingBackend().submit(request)
        request_id = request["retraining_request_id"]
        return self.decision.post(
            f"/v1/learning/retraining-requests/{request_id}/dispatch-receipt",
            tenant_id,
            {
                "dispatch_state": "dispatched",
                "dispatcher_id": self.adapter_id,
                "job_id": result.get("job_id"),
                "backend": result.get("backend_version"),
                "receipt_payload": {"job_state": result.get("state", "submitted")},
                "idempotency_key": f"dispatch:{request_id}",
            },
            actor_headers={"X-Recorded-By": self.adapter_id},
        )
