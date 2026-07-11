"""Process supervisor entrypoint for WX-12 lifecycle runtime."""

from __future__ import annotations

import json
import logging
import os
import signal
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from adapter import validate_runtime
from runtime import Backoff, LifecycleRuntime, RuntimeContractError
from worker import execute_activation, execute_rollback

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(name)s %(message)s"
)
LOG = logging.getLogger("model-lifecycle-service")
STOP = False
STATE = {"ready": False, "last_success_at": None, "last_error": None, "iterations": 0}


def _signal(*_: object) -> None:
    global STOP
    STOP = True


class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path not in {"/healthz", "/readyz"}:
            self.send_response(404)
            self.end_headers()
            return
        status = 200 if self.path == "/healthz" or STATE["ready"] else 503
        body = json.dumps(STATE, sort_keys=True).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_: object) -> None:
        return


def serve_health() -> None:
    import threading

    server = ThreadingHTTPServer(("0.0.0.0", int(os.getenv("PORT", "8099"))), HealthHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()


def run_once(runtime: LifecycleRuntime) -> int:
    """Consume one batch from decision-service runtime work feed.

    The feed is intentionally authoritative and lease-based. Unknown work types fail closed.
    """
    tenant = os.getenv("RUNTIME_TENANT_ID", "").strip()
    if not tenant:
        raise RuntimeContractError("RUNTIME_TENANT_ID is required")
    batch = runtime.decision.get(
        "/v1/learning/runtime-work", tenant, {"worker_id": runtime.adapter_id, "limit": 20}
    )
    processed = 0
    for item in batch.get("items", []):
        kind = item.get("work_type")
        payload = item.get("payload") or {}
        if kind == "post_activation_verification":
            runtime.verify_activation(tenant, payload)
        elif kind == "rollout_apply":
            runtime.apply_rollout(tenant, payload)
        elif kind == "monitoring_window":
            runtime.record_monitoring(
                tenant, payload["active_state"], payload["window_start"], payload["window_end"]
            )
        elif kind == "retraining_dispatch":
            runtime.dispatch_retraining(tenant, payload)
        elif kind == "activation_command":
            execute_activation(payload, tenant)
        elif kind == "rollback_command":
            execute_rollback(payload, tenant)
        elif kind == "active_state_reconcile":
            # Read/evidence path owned by runtime.reconcile_active_state; not fed as pending work.
            continue
        else:
            raise RuntimeContractError(f"unsupported work_type={kind!r}")
        processed += 1
    return processed


def main() -> None:
    signal.signal(signal.SIGTERM, _signal)
    signal.signal(signal.SIGINT, _signal)
    validate_runtime()
    runtime = LifecycleRuntime()
    serve_health()
    STATE["ready"] = True
    backoff = Backoff(minimum=1, maximum=60)
    interval = float(os.getenv("RUNTIME_POLL_INTERVAL_SECONDS", "5"))
    while not STOP:
        try:
            count = run_once(runtime)
            STATE["iterations"] += 1
            STATE["last_error"] = None
            STATE["last_success_at"] = time.time()
            backoff.reset()
            time.sleep(0 if count else interval)
        except Exception as exc:
            STATE["last_error"] = str(exc)[:500]
            LOG.exception("runtime iteration failed")
            time.sleep(backoff.next())


if __name__ == "__main__":
    main()
