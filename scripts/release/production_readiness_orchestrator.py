#!/usr/bin/env python3
"""SAHOOL v9 — منسّق جاهزيّة الإنتاج (أداة مشغّل، ليست بوّابة CI).

يجمع البوّابات السبع القانونيّة الساكنة + جناح الوحدات (اختياريّاً، ومرّةً ثانية تحت
لغة C) + مسابير HTTP حيّة + فحوص PostgreSQL، ويُخرِج حكماً واحداً بسند.

**حدّ الصدق، وهو أهمّ ما فيه:** قد يُقرّر `release_candidate` أو `live_ready` أو
`production_certified_candidate`. ولا يمسّ `production_certified` المحكوم أبداً —
تلك قيمة يفرضها CI صفراً حرفيّاً (`grep -F "production_certified: 0"` في
`capability-governance.yml`)، ورفعها بلا دليل **يُفشِل البناء**. الحمولة تُصدّرها
`False` مثبَّتة.

**ليس بوّابة CI عمداً:** لا workflow يستدعيه. البوّابات التي يُشغّلها محجوبة أصلاً في
CI كلٌّ في وظيفتها؛ قيمته أنّه يجمعها في تقرير واحد قابل للأرشفة عند نشرٍ حيّ، حيث
لا CI. جعلُه بوّابةً يعني تشغيل الجناح مرّتين ومسابير حيّة في بيئة بلا خدمات.

**الأصل والتعديل:** بُنِيَ على منسّق v2.2 الذي راجعتُه؛ بنيته وحدّه الصدقيّ وتركيب
`runtime_sha_bound` كما هي. المُصلَح خمسة عيوب مقيسة، كلٌّ موصوف عند موضعه:
توسيع متغيّرات البيئة · افتراضيّ `argparse` تراكميّ · عدّ المتخطّى الحَرِج ·
والعنونة داخل الشبكة (في ملفّ التهيئة المرافق).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

HEX40_RE = re.compile(r"^[0-9a-f]{40}$")
ALLOWED_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}
_PLACEHOLDER_RE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")

CANONICAL_STATIC_GATES: tuple[tuple[str, tuple[str, ...], bool], ...] = (
    ("verify_all_generated", ("scripts/ci/verify_all_generated.py",), True),
    ("no_merge_conflict_markers", ("scripts/ci/no_merge_conflict_markers_guard.py",), True),
    (
        "unified_production_readiness",
        ("scripts/ci/unified_production_readiness_gate.py", "--check"),
        True,
    ),
    ("production_honesty", ("scripts/ci/production_honesty_guard.py",), True),
    ("runtime_readiness_contract", ("scripts/ci/runtime_readiness_contract_gate.py",), True),
    ("production_evidence_pack", ("scripts/ci/production_evidence_pack_guard.py", "--check"), True),
    ("release_package", ("scripts/release/validate_release_package.py", "--root", "."), True),
)

DEFAULT_REQUIRED_RLS_TABLES = ("fields", "seasons", "users")


class ConfigError(ValueError):
    """خطأ في ملفّ التهيئة — يُبلَّغ ولا يُبتلَع."""


def expand_env(value: str, *, where: str) -> str:
    """يُوسّع `${VAR}` من البيئة، **ويفشل إن كان المتغيّر غائباً**.

    **العيب المُصلَح، مقيس لا مفترَض.** الصياغة السابقة مرّرت قيَم الترويسات عبر
    `str()` وحدها، فأُرسِلت `Authorization: Bearer ${SAHOOL_AGENT_TOKEN}` **حرفيّاً**
    ومتغيّر البيئة مضبوط. والأثر ليس فشلاً نظيفاً: مسبار «رمز صالح ⇒ 422» يحمل رمزاً
    غير صالح فيُعيد 401 دائماً، ولو صادف أن مرّ يوماً لمرّ **للسبب الخطأ** — وهو أسوأ
    من الأحمر، لأنّ الأخضر الكاذب يُقرأ شهادةً.

    والفشل عند الغياب مقصود: `os.path.expandvars` يُبقي النصّ كما هو حين لا يجد
    المتغيّر — أي يُعيد إنتاج العطل نفسه بصمت. **الصمت أسوأ من الرفض.**
    """
    missing: list[str] = []

    def _sub(match: re.Match[str]) -> str:
        name = match.group(1)
        got = os.environ.get(name)
        if got is None:
            missing.append(name)
            return ""
        return got

    out = _PLACEHOLDER_RE.sub(_sub, value)
    if missing:
        raise ConfigError(f"{where}: متغيّرات بيئة غير مضبوطة: {', '.join(sorted(set(missing)))}")
    return out


@dataclass
class Result:
    name: str
    category: str
    status: str  # passed | failed | skipped
    critical: bool
    exit_code: int | None = None
    duration_ms: int = 0
    detail: str = ""
    output_tail: str = ""
    output_sha256: str = ""


def _set_failed(result: Result, reason: str) -> None:
    result.status = "failed"
    result.detail = f"{result.detail}; {reason}" if result.detail else reason


def _decode_stream(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def _last_nonempty_line(text: str) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return lines[-1] if lines else ""


def _strict_bool(mapping: dict[str, Any], key: str, default: bool) -> bool:
    value = mapping.get(key, default)
    if not isinstance(value, bool):
        raise ConfigError(f"{key} must be boolean")
    return value


class Runner:
    def __init__(self, root: Path, verbose: bool = False) -> None:
        self.root = root.resolve()
        self.verbose = verbose
        self.results: list[Result] = []
        self.started = time.monotonic()
        self.commit_sha = self._git_value("rev-parse", "HEAD")
        self.tree_sha = self._git_value("rev-parse", "HEAD^{tree}")

        self._tests_attempted = False
        self._locale_tests_attempted = False
        self._http_probes_attempted = False
        self._database_probes_attempted = False
        self._runtime_identity_verified = False
        self._required_probe_names: set[str] = set()
        self._passed_probe_names: set[str] = set()

    # ── Git ────────────────────────────────────────────────────────────────
    def _git_value(self, *args: str) -> str:
        try:
            proc = subprocess.run(
                ["git", *args],
                cwd=self.root,
                text=True,
                encoding="utf-8",
                capture_output=True,
                timeout=15,
                check=False,
            )
            return proc.stdout.strip() if proc.returncode == 0 else ""
        except (OSError, subprocess.TimeoutExpired):
            return ""

    def _git_bool(self, *args: str) -> bool:
        return self._git_value(*args) == "true"

    # ── Results ────────────────────────────────────────────────────────────
    def add(self, result: Result) -> Result:
        self.results.append(result)
        mark = {"passed": "✓", "failed": "✗", "skipped": "○"}[result.status]
        print(f"{mark} {result.name}: {result.status}")
        if self.verbose:
            if result.detail:
                print(f"  {result.detail}")
            if result.output_tail:
                print(result.output_tail)
        return result

    def command(
        self,
        name: str,
        command: list[str],
        *,
        category: str,
        critical: bool,
        timeout: int = 900,
        env: dict[str, str] | None = None,
        semantic_validator: Callable[[Result], None] | None = None,
    ) -> Result:
        started = time.monotonic()
        merged_env = os.environ.copy()
        if env:
            merged_env.update(env)

        try:
            proc = subprocess.run(
                command,
                cwd=self.root,
                env=merged_env,
                text=True,
                encoding="utf-8",
                capture_output=True,
                timeout=timeout,
                check=False,
            )
            output = (proc.stdout + proc.stderr).strip()
            result = Result(
                name=name,
                category=category,
                status="passed" if proc.returncode == 0 else "failed",
                critical=critical,
                exit_code=proc.returncode,
                duration_ms=int((time.monotonic() - started) * 1000),
                detail=shlex.join(command),
                output_tail=output[-3000:],
                output_sha256=hashlib.sha256(output.encode("utf-8")).hexdigest(),
            )
        except subprocess.TimeoutExpired as exc:
            text = _decode_stream(exc.stdout) + _decode_stream(exc.stderr)
            result = Result(
                name=name,
                category=category,
                status="failed",
                critical=critical,
                exit_code=124,
                duration_ms=int((time.monotonic() - started) * 1000),
                detail=f"timeout after {timeout}s: {shlex.join(command)}",
                output_tail=text[-3000:],
                output_sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
            )
        except FileNotFoundError as exc:
            result = Result(
                name=name,
                category=category,
                status="failed" if critical else "skipped",
                critical=critical,
                exit_code=127,
                duration_ms=int((time.monotonic() - started) * 1000),
                detail=str(exc),
            )

        if semantic_validator and result.status == "passed":
            try:
                semantic_validator(result)
            except Exception as exc:  # noqa: BLE001 — أيّ خطأ تحقّق دلاليّ يُدين لا يمرّ
                _set_failed(result, f"semantic validation error: {exc}")

        return self.add(result)

    # ── Source preflight ───────────────────────────────────────────────────
    def static_preflight(self, expected_sha: str) -> None:
        inside = self._git_bool("rev-parse", "--is-inside-work-tree")
        self.add(
            Result(
                "git_repository",
                "source",
                "passed" if inside else "failed",
                True,
                detail="" if inside else "not inside a Git work tree",
            )
        )

        status = self._git_value("status", "--porcelain")
        self.add(
            Result(
                "working_tree_clean",
                "source",
                "passed" if not status else "failed",
                True,
                detail=status[:2000],
            )
        )

        self.add(
            Result(
                "commit_sha",
                "source",
                "passed" if HEX40_RE.fullmatch(self.commit_sha) else "failed",
                True,
                detail=self.commit_sha,
            )
        )
        self.add(
            Result(
                "tree_sha",
                "source",
                "passed" if HEX40_RE.fullmatch(self.tree_sha) else "failed",
                True,
                detail=self.tree_sha,
            )
        )

        if not expected_sha:
            self.add(
                Result(
                    "expected_sha_matches_checkout",
                    "source",
                    "skipped",
                    False,
                    detail="--expected-sha not supplied",
                )
            )
        elif not HEX40_RE.fullmatch(expected_sha):
            self.add(
                Result(
                    "expected_sha_matches_checkout",
                    "source",
                    "failed",
                    True,
                    detail=f"invalid expected SHA: {expected_sha!r}",
                )
            )
        elif expected_sha != self.commit_sha:
            self.add(
                Result(
                    "expected_sha_matches_checkout",
                    "source",
                    "failed",
                    True,
                    detail=f"expected={expected_sha}, checkout={self.commit_sha}",
                )
            )
        else:
            self.add(
                Result(
                    "expected_sha_matches_checkout",
                    "source",
                    "passed",
                    True,
                    detail=f"expected={expected_sha[:12]}, checkout={self.commit_sha[:12]}",
                )
            )

    # ── Canonical gates ────────────────────────────────────────────────────
    def canonical_static_gates(self) -> None:
        for name, argv, critical in CANONICAL_STATIC_GATES:
            script = self.root / argv[0]
            if not script.is_file():
                self.add(Result(name, "static", "failed", critical, detail=f"missing: {argv[0]}"))
                continue
            self.command(
                name,
                [sys.executable, *argv],
                category="static",
                critical=critical,
                timeout=1200,
            )

    # ── Tests ──────────────────────────────────────────────────────────────
    def test_suites(self, full_unit: bool, locale_unit: bool) -> None:
        if locale_unit and not full_unit:
            self.add(
                Result(
                    "unit_suite_c_locale",
                    "tests",
                    "failed",
                    True,
                    detail="--locale-unit requires --full-unit",
                )
            )
            return

        if not full_unit:
            self.add(Result("unit_suite", "tests", "skipped", False, detail="not requested"))
            return

        self._tests_attempted = True
        command = [sys.executable, "-m", "pytest", "-m", "unit", "-q", "-p", "no:cacheprovider"]
        self.command("unit_suite", command, category="tests", critical=True, timeout=1800)

        if locale_unit:
            self._locale_tests_attempted = True
            self.command(
                "unit_suite_c_locale",
                command,
                category="tests",
                critical=True,
                timeout=1800,
                env={
                    "LC_ALL": "C",
                    "LANG": "C",
                    "PYTHONCOERCECLOCALE": "0",
                    "PYTHONUTF8": "0",
                },
            )

    # ── HTTP ───────────────────────────────────────────────────────────────
    @staticmethod
    def _http(
        url: str,
        *,
        method: str = "GET",
        timeout: float = 8.0,
        headers: dict[str, str] | None = None,
        body: bytes | None = None,
    ) -> tuple[int, bytes, dict[str, str], str]:
        request = urllib.request.Request(url, data=body, method=method)  # noqa: S310
        request.add_header("User-Agent", "SAHOOL-Production-Readiness/1.0")
        for key, value in (headers or {}).items():
            request.add_header(key, value)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
                return response.status, response.read(16384), dict(response.headers), ""
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read(16384), dict(exc.headers), str(exc)
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            return -1, b"", {}, str(exc)

    def live_http_probes(self, config_path: Path | None, expected_sha: str) -> None:
        if config_path is None:
            self.add(
                Result(
                    "live_http_probes",
                    "live-http",
                    "skipped",
                    True,
                    detail="--probe-config not supplied",
                )
            )
            return

        path = config_path if config_path.is_absolute() else self.root / config_path
        try:
            config = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            self.add(Result("live_http_probes", "live-http", "failed", True, detail=str(exc)))
            return

        probes = config.get("probes")
        if not isinstance(probes, list) or not probes:
            self.add(
                Result(
                    "live_http_probes",
                    "live-http",
                    "failed",
                    True,
                    detail="config.probes must be a non-empty list",
                )
            )
            return

        for index, probe in enumerate(probes):
            if not isinstance(probe, dict):
                self.add(
                    Result(
                        f"probe_{index}", "live-http", "failed", True, detail="probe must be object"
                    )
                )
                return

        names = [str(probe.get("name", "")) for probe in probes]
        if any(not name for name in names):
            self.add(
                Result(
                    "live_http_probes",
                    "live-http",
                    "failed",
                    True,
                    detail="every probe requires a non-empty name",
                )
            )
            return
        duplicates = sorted({name for name in names if names.count(name) > 1})
        if duplicates:
            self.add(
                Result(
                    "live_http_probes",
                    "live-http",
                    "failed",
                    True,
                    detail=f"duplicate probe names: {duplicates}",
                )
            )
            return

        # لا افتراضيّ ضمنيّ لقائمة المسابير الواجبة: قائمةٌ يُخمّنها الكود تجعل
        # `live_ready` يعني شيئاً مختلفاً بين ملفّ تهيئة وآخر بلا أن يقول أحد ذلك.
        configured_required = config.get("required_probe_names", names)
        if not isinstance(configured_required, list) or not all(
            isinstance(x, str) and x for x in configured_required
        ):
            self.add(
                Result(
                    "live_http_probes",
                    "live-http",
                    "failed",
                    True,
                    detail="required_probe_names must be a list of non-empty strings",
                )
            )
            return

        self._required_probe_names = set(configured_required)
        missing = sorted(self._required_probe_names - set(names))
        if missing:
            self.add(
                Result(
                    "live_http_probe_contract",
                    "live-http",
                    "failed",
                    True,
                    detail=f"missing required probes: {missing}",
                )
            )
            return

        self._http_probes_attempted = True

        for index, probe in enumerate(probes):
            name = str(probe["name"])
            try:
                url = expand_env(str(probe["url"]), where=f"probe {name}: url")
                method = str(probe.get("method", "GET")).upper()
                if method not in ALLOWED_METHODS:
                    raise ConfigError(f"unsupported method: {method}")
                timeout = float(probe.get("timeout", 8))
                if timeout <= 0:
                    raise ConfigError("timeout must be positive")

                critical = _strict_bool(probe, "critical", True)
                runtime_identity = _strict_bool(probe, "runtime_identity", False)
                record_body = _strict_bool(probe, "record_body", False)

                headers_raw = probe.get("headers", {})
                if not isinstance(headers_raw, dict):
                    raise ConfigError("headers must be an object")
                headers = {
                    str(k): expand_env(str(v), where=f"probe {name}: header {k}")
                    for k, v in headers_raw.items()
                }

                body_bytes: bytes | None = None
                if "json" in probe and "body" in probe:
                    raise ConfigError("probe cannot specify both json and body")
                if "json" in probe:
                    body_bytes = json.dumps(probe["json"]).encode("utf-8")
                    headers.setdefault("Content-Type", "application/json")
                elif "body" in probe:
                    raw_body = probe["body"]
                    if not isinstance(raw_body, str):
                        raise ConfigError("body must be a string for raw-body probes")
                    body_bytes = raw_body.encode("utf-8")

                expected_values = probe.get("expect_status", [200])
                if not isinstance(expected_values, list) or not expected_values:
                    raise ConfigError("expect_status must be a non-empty list")
                expected = {int(value) for value in expected_values}

                started = time.monotonic()
                status, response_body, _, error = self._http(
                    url, method=method, timeout=timeout, headers=headers, body=body_bytes
                )
                duration_ms = int((time.monotonic() - started) * 1000)

                passed = status in expected
                details = [f"status={status}, expected={sorted(expected)}"]
                if error:
                    details.append(error)

                if passed and runtime_identity:
                    try:
                        payload = json.loads(response_body.decode("utf-8"))
                        observed = (
                            payload.get("sha")
                            or payload.get("commit_sha")
                            or payload.get("git_sha")
                        )
                        valid = isinstance(observed, str) and bool(HEX40_RE.fullmatch(observed))
                        passed = valid and observed == expected_sha
                        details.append(f"runtime_sha={observed}, expected_sha={expected_sha}")
                        if passed:
                            self._runtime_identity_verified = True
                    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                        passed = False
                        details.append(f"invalid identity JSON: {exc}")

                if passed:
                    self._passed_probe_names.add(name)

                self.add(
                    Result(
                        name=name,
                        category="live-http",
                        status="passed" if passed else "failed",
                        critical=critical,
                        duration_ms=duration_ms,
                        detail="; ".join(details),
                        output_tail=(
                            response_body.decode("utf-8", errors="replace")[-1200:]
                            if record_body
                            else ""
                        ),
                        output_sha256=hashlib.sha256(response_body).hexdigest(),
                    )
                )
            except Exception as exc:  # noqa: BLE001 — تهيئة معطوبة تُدين ولا تُسقِط الجولة
                self.add(
                    Result(
                        name or f"probe_{index}",
                        "live-http",
                        "failed",
                        True,
                        detail=f"probe validation error: {exc}",
                    )
                )

    # ── Database ───────────────────────────────────────────────────────────
    def database_probes(
        self,
        database_url: str | None,
        required_rls_tables: tuple[str, ...],
        migration_table: str | None,
    ) -> None:
        if not database_url:
            self.add(
                Result(
                    "database_live_contract",
                    "live-db",
                    "skipped",
                    True,
                    detail="DATABASE_URL not supplied",
                )
            )
            return

        self._database_probes_attempted = True
        db_env = {"PGDATABASE": database_url}
        base = ["psql", "-X", "-A", "-t", "-v", "ON_ERROR_STOP=1"]

        def nonempty(result: Result) -> None:
            if not _last_nonempty_line(result.output_tail):
                _set_failed(result, "expected non-empty output")

        def equals_zero(result: Result) -> None:
            value = _last_nonempty_line(result.output_tail)
            if value != "0":
                _set_failed(result, f"expected 0, observed {value!r}")

        self.command(
            "postgres_version",
            [*base, "-c", "SHOW server_version;"],
            category="live-db",
            critical=True,
            timeout=30,
            env=db_env,
            semantic_validator=nonempty,
        )
        self.command(
            "postgis_version",
            [*base, "-c", "SELECT PostGIS_Version();"],
            category="live-db",
            critical=True,
            timeout=30,
            env=db_env,
            semantic_validator=nonempty,
        )
        self.command(
            "connected_role_is_restricted",
            [
                *base,
                "-c",
                "SELECT count(*) FROM pg_roles WHERE rolname=current_user "
                "AND (rolsuper OR rolbypassrls);",
            ],
            category="live-db",
            critical=True,
            timeout=30,
            env=db_env,
            semantic_validator=equals_zero,
        )

        def validate_app_role(result: Result) -> None:
            value = _last_nonempty_line(result.output_tail)
            parts = value.split("|")
            if len(parts) != 2:
                _set_failed(result, f"expected role_count|privileged_count, observed {value!r}")
                return
            try:
                role_count, privileged_count = map(int, parts)
            except ValueError:
                _set_failed(result, f"non-integer role result: {value!r}")
                return
            if role_count != 1 or privileged_count != 0:
                _set_failed(
                    result,
                    f"expected role_count=1 and privileged_count=0, "
                    f"observed {role_count}|{privileged_count}",
                )

        self.command(
            "application_role_contract",
            [
                *base,
                "-c",
                "SELECT count(*), count(*) FILTER (WHERE rolsuper OR rolbypassrls) "
                "FROM pg_roles WHERE rolname='sahool_app';",
            ],
            category="live-db",
            critical=True,
            timeout=30,
            env=db_env,
            semantic_validator=validate_app_role,
        )

        quoted_tables = ", ".join(f"('{table}')" for table in required_rls_tables)
        rls_sql = (
            f"WITH required(tablename) AS (VALUES {quoted_tables}) "
            "SELECT coalesce(string_agg(r.tablename, ',' ORDER BY r.tablename), '') "
            "FROM required r "
            "LEFT JOIN pg_class c ON c.relname=r.tablename AND c.relkind='r' "
            "LEFT JOIN pg_namespace n ON n.oid=c.relnamespace "
            "WHERE c.oid IS NULL OR n.nspname <> 'public' "
            "OR NOT c.relrowsecurity OR NOT c.relforcerowsecurity;"
        )

        def validate_required_rls(result: Result) -> None:
            missing = _last_nonempty_line(result.output_tail)
            if missing:
                _set_failed(result, f"missing/non-forced RLS tables: {missing}")

        self.command(
            "required_force_rls_tables",
            [*base, "-c", rls_sql],
            category="live-db",
            critical=True,
            timeout=30,
            env=db_env,
            semantic_validator=validate_required_rls,
        )

        if migration_table:
            if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", migration_table):
                self.add(
                    Result(
                        "migration_tracking",
                        "live-db",
                        "failed",
                        True,
                        detail="invalid migration table identifier",
                    )
                )
            else:

                def validate_migrations(result: Result) -> None:
                    value = _last_nonempty_line(result.output_tail)
                    try:
                        count = int(value)
                    except ValueError:
                        _set_failed(result, f"non-integer migration count: {value!r}")
                        return
                    if count < 1:
                        _set_failed(
                            result, f"expected at least one migration row, observed {count}"
                        )

                self.command(
                    "migration_tracking",
                    [*base, "-c", f"SELECT count(*) FROM {migration_table};"],
                    category="live-db",
                    critical=True,
                    timeout=30,
                    env=db_env,
                    semantic_validator=validate_migrations,
                )
        else:
            # `migrations/MANIFEST.txt` هو المصدر القانونيّ في هذا المستودع، فغياب
            # جدول تتبّع ليس عيباً — ادّعاءٌ صحّحه تقرير خارجيّ سابقاً بالخطأ.
            self.add(
                Result(
                    "migration_tracking",
                    "live-db",
                    "skipped",
                    False,
                    detail="no migration table configured; MANIFEST.txt is canonical",
                )
            )

    # ── Verdict ────────────────────────────────────────────────────────────
    def finalize(
        self,
        output: Path,
        *,
        require_live: bool,
        require_tests: bool,
        require_certified: bool,
        require_locale_tests: bool,
    ) -> int:
        if require_certified:
            require_live = True
            require_tests = True
            require_locale_tests = True

        static_ready = not any(
            r.critical and r.status != "passed" and r.category in {"source", "static"}
            for r in self.results
        )

        tests_ready = self._tests_attempted and not any(
            r.critical and r.status != "passed" for r in self.results if r.category == "tests"
        )
        locale_tests_ready = self._locale_tests_attempted and any(
            r.name == "unit_suite_c_locale" and r.status == "passed" for r in self.results
        )

        live_results = [r for r in self.results if r.category in {"live-http", "live-db"}]
        live_complete = self._http_probes_attempted and self._database_probes_attempted
        required_probes_passed = self._required_probe_names.issubset(self._passed_probe_names)
        live_ready = (
            live_complete
            and bool(live_results)
            and required_probes_passed
            and not any(r.critical and r.status != "passed" for r in live_results)
        )

        checkout_sha_bound = any(
            r.name == "expected_sha_matches_checkout" and r.status == "passed" for r in self.results
        )
        runtime_sha_bound = checkout_sha_bound and self._runtime_identity_verified

        certified_candidate_ready = (
            static_ready and tests_ready and locale_tests_ready and live_ready and runtime_sha_bound
        )

        critical_failures = [r for r in self.results if r.critical and r.status == "failed"]
        # **العيب المُصلَح:** ملخّصٌ يقول `critical_failures: 0` بينما فحصان حَرِجان
        # تُخُطِّيا يُقرأ «لا شيء معلّق» وهو يعني «لم يُسأل». وهو تمييز «لم يجد» عن
        # «لم ينظر» نفسه الذي بُني عليه `ran_at_all` في حارس الطفرات.
        critical_skipped = [r for r in self.results if r.critical and r.status == "skipped"]

        blocked = bool(critical_failures)
        if require_tests and not tests_ready:
            blocked = True
        if require_locale_tests and not locale_tests_ready:
            blocked = True
        if require_live and not live_ready:
            blocked = True
        if require_certified and not certified_candidate_ready:
            blocked = True

        if blocked:
            verdict = "blocked"
            code = 1
        elif require_certified:
            verdict = "production_certified_candidate"
            code = 0
        elif live_ready:
            verdict = "live_ready"
            code = 0
        elif static_ready and (tests_ready or not require_tests):
            verdict = "release_candidate"
            code = 0
        else:
            verdict = "blocked"
            code = 1

        target = output if output.is_absolute() else self.root / output
        payload: dict[str, Any] = {
            "schema_version": 5,
            "generated_at_utc": datetime.now(UTC).isoformat(),
            "root": str(self.root),
            "commit_sha": self.commit_sha,
            "tree_sha": self.tree_sha,
            "verdict": verdict,
            "static_ready": static_ready,
            "tests_ready": tests_ready,
            "locale_tests_ready": locale_tests_ready,
            "live_complete": live_complete,
            "required_probes_passed": required_probes_passed,
            "live_ready": live_ready,
            "checkout_sha_bound": checkout_sha_bound,
            "runtime_identity_verified": self._runtime_identity_verified,
            "runtime_sha_bound": runtime_sha_bound,
            "production_certified": False,
            "truth_boundary": (
                "This orchestrator may establish release-candidate, live-ready, "
                "or production-certified-candidate status. It never mutates the "
                "repository's governed production_certified state."
            ),
            "duration_ms": int((time.monotonic() - self.started) * 1000),
            "summary": {
                "passed": sum(r.status == "passed" for r in self.results),
                "failed": sum(r.status == "failed" for r in self.results),
                "skipped": sum(r.status == "skipped" for r in self.results),
                "critical_failures": len(critical_failures),
                "critical_skipped": len(critical_skipped),
                "critical_skipped_names": sorted(r.name for r in critical_skipped),
            },
            "results": [asdict(r) for r in self.results],
        }
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(json.dumps(payload["summary"], ensure_ascii=False))
        print(f"verdict={verdict} report={target}")
        return code


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--project-dir", type=Path, default=Path("."))
    parser.add_argument(
        "--output", type=Path, default=Path("artifacts/production-readiness/report.json")
    )
    parser.add_argument("--probe-config", type=Path)
    parser.add_argument("--database-url", default=os.getenv("DATABASE_URL", ""))
    parser.add_argument("--expected-sha", default="")
    parser.add_argument("--full-unit", action="store_true")
    parser.add_argument("--locale-unit", action="store_true")
    parser.add_argument("--require-live", action="store_true")
    parser.add_argument("--require-tests", action="store_true")
    parser.add_argument("--require-locale-tests", action="store_true")
    parser.add_argument("--require-certified", action="store_true")
    # **العيب المُصلَح:** `action="append"` مع افتراضيّ غير `None` **يُوسّع** الافتراضيّ
    # ولا يستبدله — مقيس: `--required-rls-table audit` يُعطي
    # `['fields','seasons','users','audit']`، فلا سبيل إلى التضييق أصلاً.
    parser.add_argument(
        "--required-rls-table",
        action="append",
        default=None,
        help=(
            "كرّرها لكلّ جدول يجب أن يحمل ENABLE+FORCE RLS. "
            f"بلا الراية: {', '.join(DEFAULT_REQUIRED_RLS_TABLES)}"
        ),
    )
    parser.add_argument("--migration-table", default="")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    if args.locale_unit and not args.full_unit:
        parser.error("--locale-unit requires --full-unit")
    if args.require_locale_tests and not args.full_unit:
        parser.error("--require-locale-tests requires --full-unit")
    if args.require_certified and not args.expected_sha:
        parser.error("--require-certified requires --expected-sha")
    if args.require_certified and not args.probe_config:
        parser.error("--require-certified requires --probe-config")
    if args.require_certified and not (args.database_url or os.getenv("DATABASE_URL")):
        parser.error("--require-certified requires --database-url or DATABASE_URL")

    rls_tables = tuple(dict.fromkeys(args.required_rls_table or DEFAULT_REQUIRED_RLS_TABLES))

    runner = Runner(args.project_dir, verbose=args.verbose)
    runner.static_preflight(args.expected_sha)
    runner.canonical_static_gates()
    runner.test_suites(args.full_unit, args.locale_unit)
    expected_sha = args.expected_sha or runner.commit_sha
    runner.live_http_probes(args.probe_config, expected_sha)
    runner.database_probes(args.database_url or None, rls_tables, args.migration_table or None)
    return runner.finalize(
        args.output,
        require_live=args.require_live,
        require_tests=args.require_tests,
        require_certified=args.require_certified,
        require_locale_tests=args.require_locale_tests,
    )


if __name__ == "__main__":
    raise SystemExit(main())
