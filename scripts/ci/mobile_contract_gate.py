#!/usr/bin/env python3
"""Mobile/Flutter contract gate.

Static, deterministic checks for security and production-readiness contracts that
can be validated without Flutter SDK. This is intentionally conservative: it
blocks regressions that caused real mobile/session/offline drift.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MOBILE = ROOT / "mobile" / "sahool_app"
errors: list[str] = []
warnings: list[str] = []


def read(rel: str) -> str:
    p = ROOT / rel
    if not p.exists():
        errors.append(f"missing required file: {rel}")
        return ""
    return p.read_text(encoding="utf-8", errors="ignore")


api = read("mobile/sahool_app/lib/services/api_service.dart")
ws = read("mobile/sahool_app/lib/services/websocket_service.dart")
main = read("mobile/sahool_app/lib/main.dart")
auth_test = read("mobile/sahool_app/test/auth_service_test.dart")
offline_map = read("mobile/sahool_app/lib/widgets/offline_field_map.dart")
models = read("services/sahool-platform/api/api_models.py")
sync_router = read("services/sahool-platform/api/routers/sync.py")
smoke = read("scripts/mobile/mobile_sync_smoke.sh")

# Offline sync: tenant must be authoritative from JWT/server, not request JSON.
if re.search(r"syncOfflineOperations\s*\(\s*String\s+tenantId", api):
    errors.append("mobile syncOfflineOperations still accepts tenantId")
if re.search(r"['\"]tenant_id['\"]\s*:\s*tenantId", api):
    errors.append("mobile /api/v1/sync body still sends tenant_id from client")
if "tenant_id: str | None = None" not in models:
    errors.append("SyncBatchRequest.tenant_id must be optional legacy compatibility field")
if "tenant_id = user.tenant_id" not in sync_router:
    errors.append("sync router must derive authoritative tenant_id from authenticated user")
if "Tenant mismatch" not in sync_router:
    errors.append("sync router must reject mismatched legacy tenant_id when supplied")
if "TENANT_ID is required" in smoke:
    errors.append(
        "mobile_sync_smoke still requires TENANT_ID even though server derives tenant from JWT"
    )
if '"tenant_id"' in smoke or "'tenant_id'" in smoke:
    errors.append("mobile_sync_smoke still posts tenant_id in request body")

# WebSocket: no empty-token auth frame; fail closed before connect and before auth frame.
if "AuthService.instance.token ?? ''" in ws:
    errors.append("WebSocket auth frame can still send empty token")
if "if (!AuthService.instance.isAuthenticated)" not in ws:
    errors.append("WebSocketService.connect must skip missing/expired sessions")
if "policyViolation" not in ws or "missing-auth" not in ws:
    errors.append("WebSocketService must close fail-closed if token disappears after connect")
if "_messageQueue.clear()" not in ws:
    errors.append(
        "WebSocketService.dispose must clear queued mutating messages on logout/session teardown"
    )

# Logout/session teardown: close WS and clear memory cache before clearing auth.
logout_match = re.search(r"Future<void>\s+logout\([^)]*\)\s+async\s*{(?P<body>.*?)\n  }", api, re.S)
if not logout_match:
    errors.append("ApiService.logout not found")
else:
    body = logout_match.group("body")
    if "WebSocketService.instance.dispose()" not in body:
        errors.append("ApiService.logout must dispose WebSocketService")
    if "clearCache()" not in body:
        errors.append("ApiService.logout must clear ApiService memory cache")
    if "finally" not in body:
        errors.append("ApiService.logout teardown must run in finally")

# Error widget must not leak exception details in release builds.
if "details.exception.toString()" in main and "kDebugMode" not in main:
    errors.append("ErrorWidget leaks exception details without kDebugMode guard")
if "يرجى المحاولة مجدداً" not in main:
    errors.append("ErrorWidget should show production-safe generic message")
if "if (!AuthService.instance.isAuthenticated)" not in main:
    errors.append("AuthGate should use isAuthenticated, not raw token presence")

# JWT tests must import real implementation, not duplicate production logic.
if "package:sahool_app/utils/jwt.dart" not in auth_test:
    errors.append("auth_service_test must import real utils/jwt.dart")
if re.search(r"bool\s+isTokenExpired\s*\(", auth_test):
    errors.append("auth_service_test duplicates JWT expiration logic")

# Offline map path naming should clarify filesystem path, keeping old alias only as deprecated.
if "offlinePackFilePath" not in offline_map:
    errors.append("OfflineFieldMap must expose offlinePackFilePath filesystem path")
if (
    "File(path).exists" in offline_map
    and "offlinePackFilePath ?? widget.offlinePackPath" not in offline_map
):
    errors.append(
        "OfflineFieldMap must resolve offlinePackFilePath before deprecated offlinePackPath"
    )
if "assets/maps/aljawf.mbtiles" in offline_map:
    errors.append(
        "OfflineFieldMap docs still imply asset path works directly with File(path).exists"
    )

# Build artifacts: cannot be generated in static CI here, but make the gap explicit.
if not (MOBILE / "pubspec.lock").exists():
    warnings.append(
        "mobile/sahool_app/pubspec.lock is missing; generate with flutter pub get and commit it"
    )
if not (MOBILE / "android").exists():
    warnings.append(
        "mobile/sahool_app/android/ is missing; generate/restore with flutter create . --platforms=android"
    )
if not (MOBILE / "ios").exists():
    warnings.append(
        "mobile/sahool_app/ios/ is missing; generate/restore with flutter create . --platforms=ios"
    )

if errors:
    print("mobile contract gate: FAIL")
    for e in errors:
        print(f"ERROR: {e}")
    for w in warnings:
        print(f"WARN: {w}")
    sys.exit(1)

print("mobile contract gate: OK")
for w in warnings:
    print(f"WARN: {w}")
