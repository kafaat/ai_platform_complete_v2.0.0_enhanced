"""`RESTART-POLICY-BYPASSES-DEPENDS-ON-HEALTH-01` — الإقلاعُ يتحمّل Postgres لم يجهز بعد.

``depends_on: condition: service_healthy`` يُقيَّم عند ``docker compose up`` وحده؛ حاوٍ
أعادته سياسةُ ``restart:`` بعد إعادة تشغيل الخادم لا ينتظر Postgres. فالشاهدُ هنا
**سلوكيّ**: كلُّ خدمةٍ مُصلَحة تُقلِع في عمليّةٍ مستقلّة، من شجرةٍ مُجمَّعة بأسطر
``COPY`` في Dockerfile صورتها (لا من المستودع — فإصلاحٌ لا يصل الصورة يحمرّ هنا)،
أمام ``asyncpg`` مزيّف يرفض الاتّصال مرّتين ثمّ يقبل. على ``origin/main`` تموت كلٌّ
منها على الرفض الأوّل، والمنصّة تبتلعه فتبقى بلا قاعدة.

ثمّ اختباراتُ الوحدة المشتركة ``shared/startup_retry.py`` بساعةٍ ونومٍ محقونين، ثمّ
الحارس ``scripts/ci/startup_db_connect_retry_guard.py`` وجرده.
"""

from __future__ import annotations

import asyncio
import copy
import importlib.util
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest
import yaml

from shared import startup_retry

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
INVENTORY = ROOT / "docs" / "architecture" / "startup_db_connect_inventory.json"
COMPOSE = ROOT / "docker-compose.v9.yml"


def _load_guard():
    path = ROOT / "scripts" / "ci" / "startup_db_connect_retry_guard.py"
    spec = importlib.util.spec_from_file_location("_a_startup_db_connect_retry_guard", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


guard = _load_guard()


# ─── (١) كلُّ خدمةٍ مُصلَحة تنجو من رفضين عند الإقلاع ─────────────────────────

#: الخدمة → (Dockerfile، نوع المدخل، الهدف). ``lifespan`` يُشغّل دورة حياة FastAPI؛
#: ``coro`` يستدعي دالّة الإقلاع؛ ``file`` يحمّل ملفّاً بمساره ثمّ يستدعي دالّته.
SERVICES = {
    "sahool-auth": ("services/auth/Dockerfile", "lifespan", "main:app"),
    "sahool-platform": ("services/sahool-platform/Dockerfile", "coro", "api.main:_init_db_pool"),
    "sahool-soil-service": ("services/soil-service/Dockerfile", "lifespan", "main:app"),
    "sahool-market-mcp": ("services/mcp_servers/Dockerfile", "lifespan", "market_server:app"),
    "sahool-erp-bridge": ("services/odoo-bridge/Dockerfile", "lifespan", "main:app"),
    "sahool-weather-signal-engine": (
        "services/weather-signal-engine/Dockerfile",
        "coro",
        "main:run",
    ),
    "sahool-scout-ingest-projection": (
        "services/scout-ingest-service/Dockerfile",
        "coro",
        "projection_worker:loop",
    ),
    "sahool-irrigation-reservation-lifecycle-worker": (
        "services/sahool-platform/Dockerfile",
        "coro",
        "api.irrigation_reservation_lifecycle_worker:run",
    ),
    "sahool-canonical-execution-learning-worker": (
        "services/sahool-platform/Dockerfile",
        "file",
        "workers/canonical_execution_learning_worker.py:run",
    ),
}

_RUNNER = textwrap.dedent(
    """
    import asyncio, importlib, importlib.util, json, sys

    app_dir, kind, target = sys.argv[1], sys.argv[2], sys.argv[3]
    sys.path.insert(0, app_dir)

    import asyncpg

    attempts = 0


    class Reached(BaseException):
        "Third attempt: the service came back after two refusals."


    async def fake_connect(*args, **kwargs):
        global attempts
        attempts += 1
        if attempts <= 2:
            raise ConnectionRefusedError(111, "Connect call failed ('127.0.0.1', 1)")
        raise Reached()


    asyncpg.create_pool = fake_connect
    asyncpg.connect = fake_connect


    async def start():
        mod_name, _, attr = target.rpartition(":")
        if kind == "file":
            spec = importlib.util.spec_from_file_location("_svc", f"{app_dir}/{mod_name}")
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        else:
            module = importlib.import_module(mod_name)
        obj = getattr(module, attr)
        if kind == "lifespan":
            async with obj.router.lifespan_context(obj):
                pass
        else:
            await obj()


    try:
        asyncio.run(asyncio.wait_for(start(), 60))
        outcome = "returned"
    except Reached:
        outcome = "reached"
    except BaseException as exc:  # noqa: BLE001
        outcome = "died:" + type(exc).__name__
    print("RESULT " + json.dumps({"outcome": outcome, "attempts": attempts}), flush=True)
    """
)

_IMAGE_CACHE: dict[str, tuple[Path, list[str]]] = {}


def _assemble_image(dockerfile: str, base: Path) -> tuple[Path, list[str]]:
    """يجمع ``/app`` كما تبنيه أسطر ``COPY`` في Dockerfile — لا أكثر."""
    if dockerfile in _IMAGE_CACHE:
        return _IMAGE_CACHE[dockerfile]
    app = base / re.sub(r"\W", "_", dockerfile) / "app"
    app.mkdir(parents=True)
    pythonpath: list[str] = []
    ignore = shutil.ignore_patterns("__pycache__", "tests", "*.pyc", "node_modules")
    for raw in (ROOT / dockerfile).read_text(encoding="utf-8").splitlines():
        parts = raw.split()
        if len(parts) >= 2 and parts[0] == "ENV" and parts[1].startswith("PYTHONPATH="):
            value = parts[1].split("=", 1)[1]
            pythonpath = [p.replace("/app", str(app), 1) for p in value.split(":") if p]
        if len(parts) < 3 or parts[0] != "COPY" or any(p.startswith("--") for p in parts):
            continue
        *srcs, dst = parts[1:]
        if not dst.startswith("/app"):
            continue  # requirements → /tmp أو مسارٌ نسبيّ: ليس من شجرة التطبيق
        target = app / dst[len("/app") :].lstrip("/")
        for src in srcs:
            source = ROOT / src
            if source.is_dir():
                shutil.copytree(source, target, dirs_exist_ok=True, ignore=ignore)
            else:
                dest = target / source.name if dst.endswith("/") else target
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, dest)
    _IMAGE_CACHE[dockerfile] = (app, pythonpath)
    return app, pythonpath


@pytest.fixture(scope="module")
def image_root(tmp_path_factory):
    return tmp_path_factory.mktemp("images")


def _start(service: str, base: Path) -> dict:
    dockerfile, kind, target = SERVICES[service]
    app, pythonpath = _assemble_image(dockerfile, base)
    runner = base / "runner" / "start_service.py"
    runner.parent.mkdir(exist_ok=True)
    runner.write_text(_RUNNER, encoding="utf-8")
    dsn = "postgresql://sahool_app:unused@127.0.0.1:1/sahool"
    env = {
        k: v
        for k, v in os.environ.items()
        if k not in {"PYTHONPATH", "DATABASE_URL", "JOBS_DATABASE_URL"}
    }
    env.update(
        {
            "PYTHONPATH": os.pathsep.join(pythonpath),
            "DATABASE_URL": dsn,
            "JOBS_DATABASE_URL": dsn,
            "SAHOOL_ENV": "development",
            "JWT_SECRET": "test_secret_min_32_chars_for_sahool_v9",
            "SCOUT_INGEST_PROJECTION_ENABLED": "1",
            "WORKER_HEARTBEAT_DIR": str(base / "heartbeat"),
            "OTEL_SDK_DISABLED": "true",
            startup_retry.DEADLINE_ENV: "30",
            startup_retry.INITIAL_BACKOFF_ENV: "0.01",
            startup_retry.MAX_BACKOFF_ENV: "0.02",
        }
    )
    (base / "heartbeat").mkdir(exist_ok=True)
    proc = subprocess.run(
        [sys.executable, str(runner), str(app), kind, target],
        cwd=app,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=120,
    )
    lines = [ln for ln in proc.stdout.splitlines() if ln.startswith("RESULT ")]
    assert lines, f"{service}: the startup runner produced no result\n{proc.stderr[-3000:]}"
    return json.loads(lines[-1][len("RESULT ") :]) | {"stderr": proc.stderr}


@pytest.mark.parametrize("service", sorted(SERVICES))
def test_service_startup_survives_two_refused_connects(service, image_root):
    result = _start(service, image_root)
    if result["outcome"] == "returned" and result["attempts"] == 1:
        pytest.fail(
            f"{service}: the swallowed refusal left the platform DB-less — startup returned "
            "after one refused connect and never tried again"
        )
    assert result["attempts"] > 0, (
        f"{service} never reached its first connect: outcome={result['outcome']} — the image "
        f"as its Dockerfile assembles it cannot start\n{result['stderr'][-2000:]}"
    )
    assert result["attempts"] >= 3 and result["outcome"] == "reached", (
        f"{service} died on a refused connect: outcome={result['outcome']} "
        f"attempts={result['attempts']} — a restart-policy restart before Postgres is "
        f"ready kills it\n{result['stderr'][-2000:]}"
    )


def test_every_retrying_service_in_the_inventory_has_a_startup_witness():
    services = json.loads(INVENTORY.read_text(encoding="utf-8"))["services"]
    retrying = {n for n, e in services.items() if e["class"] == "retries_with_backoff"}
    assert retrying == set(SERVICES)


# ─── (٢) الوحدة المشتركة ─────────────────────────────────────────────────────


class _Clock:
    def __init__(self):
        self.now = 0.0
        self.sleeps: list[float] = []

    def __call__(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


class _PgError(Exception):
    def __init__(self, sqlstate: str, message: str = "boom"):
        super().__init__(message)
        self.sqlstate = sqlstate


def _flaky(failures: list[BaseException], result: object = "pool"):
    calls = {"n": 0}

    async def connect(*args, **kwargs):
        calls["n"] += 1
        if failures:
            raise failures.pop(0)
        return result, args, kwargs

    return connect, calls


def _run(connect, clock: _Clock, **kw):
    return asyncio.run(
        startup_retry.retry_startup_connect(
            connect,
            "dsn",
            min_size=1,
            startup_sleep=clock.sleep,
            startup_clock=clock,
            **kw,
        )
    )


def test_transient_refusals_are_retried_with_exponential_backoff():
    clock = _Clock()
    connect, calls = _flaky([ConnectionRefusedError(111, "refused")] * 2)
    result = _run(
        connect, clock, startup_deadline=90, startup_initial_backoff=0.5, startup_max_backoff=10
    )
    assert result == ("pool", ("dsn",), {"min_size": 1}), "arguments must reach connect unchanged"
    assert calls["n"] == 3
    assert clock.sleeps == [0.5, 1.0]


def test_backoff_is_capped_and_the_last_sleep_is_bounded_by_the_deadline():
    clock = _Clock()
    connect, calls = _flaky([OSError("down")] * 50)
    with pytest.raises(startup_retry.StartupConnectDeadlineExceeded) as info:
        _run(connect, clock, startup_deadline=10, startup_initial_backoff=1, startup_max_backoff=4)
    assert clock.sleeps[:4] == [1, 2, 4, 3], "capped at 4s, then only the 3s left before 10s"
    assert sum(clock.sleeps) == pytest.approx(10)
    assert isinstance(info.value, RuntimeError)
    assert isinstance(info.value.__cause__, OSError)
    assert calls["n"] == len(clock.sleeps) + 1


@pytest.mark.parametrize("sqlstate", ["08001", "08006", "57P03", "57P01", "53300"])
def test_connection_class_sqlstates_are_transient(sqlstate):
    assert startup_retry.is_transient_connect_error(_PgError(sqlstate))


@pytest.mark.parametrize(
    "exc",
    [_PgError("28P01"), _PgError("3D000"), _PgError("42501"), ValueError("bad dsn")],
    ids=["invalid-password", "no-database", "insufficient-privilege", "bad-dsn"],
)
def test_configuration_errors_propagate_on_the_first_attempt(exc):
    clock = _Clock()
    connect, calls = _flaky([exc])
    with pytest.raises(type(exc)):
        _run(connect, clock, startup_deadline=90)
    assert calls["n"] == 1 and clock.sleeps == []


def test_a_zero_deadline_means_one_attempt():
    clock = _Clock()
    connect, calls = _flaky([ConnectionRefusedError(111, "refused")])
    with pytest.raises(startup_retry.StartupConnectDeadlineExceeded):
        _run(connect, clock, startup_deadline=0)
    assert calls["n"] == 1


def test_logs_name_the_exception_class_never_its_text(caplog):
    secret = "postgresql://sahool_app:hunter2-secret@db/sahool"
    clock = _Clock()
    connect, _ = _flaky([OSError(secret)] * 3)
    with caplog.at_level(logging.INFO, logger="sahool.startup_retry"):
        with pytest.raises(startup_retry.StartupConnectDeadlineExceeded) as info:
            _run(connect, clock, startup_deadline=1, startup_initial_backoff=0.5)
    text = caplog.text + str(info.value)
    assert "OSError" in text
    assert "hunter2" not in text, "driver messages can echo the DSN; only class names are logged"


def test_environment_configures_the_defaults(monkeypatch):
    monkeypatch.setenv(startup_retry.DEADLINE_ENV, "2")
    monkeypatch.setenv(startup_retry.INITIAL_BACKOFF_ENV, "1")
    monkeypatch.setenv(startup_retry.MAX_BACKOFF_ENV, "1")
    clock = _Clock()
    connect, _ = _flaky([OSError("down")] * 10)
    with pytest.raises(startup_retry.StartupConnectDeadlineExceeded):
        _run(connect, clock)
    assert clock.sleeps == [1, 1]
    monkeypatch.setenv(startup_retry.DEADLINE_ENV, "not-a-number")
    assert startup_retry._env_seconds(startup_retry.DEADLINE_ENV, 90.0) == 90.0


def test_the_module_is_stdlib_only():
    """weather-signal-engine copies only this file and shared/__init__.py into its image."""
    src = (ROOT / "shared" / "startup_retry.py").read_text(encoding="utf-8")
    imported = set(re.findall(r"^(?:from|import)\s+([A-Za-z_][\w]*)", src, re.M))
    assert imported <= {"__future__", "asyncio", "logging", "os", "time", "collections", "typing"}


# ─── (٣) الحارس وجرده ───────────────────────────────────────────────────────


def _inputs():
    inventory = json.loads(INVENTORY.read_text(encoding="utf-8"))
    compose = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))
    return inventory, compose, guard.load_frozen()


def test_the_guard_is_green_on_the_tree():
    inventory, compose, frozen = _inputs()
    errs, _ = guard.check(inventory, compose, frozen)
    assert errs == []


def test_an_unclassified_dependant_is_blocked():
    inventory, compose, frozen = _inputs()
    compose = copy.deepcopy(compose)
    compose["services"]["sahool-new-worker"] = {
        "restart": "unless-stopped",
        "depends_on": {"sahool-postgres": {"condition": "service_healthy"}},
    }
    errs, _ = guard.check(inventory, compose, frozen)
    assert any("sahool-new-worker" in e and "retry_startup_connect" in e for e in errs), errs


def test_a_classified_service_that_left_compose_is_blocked():
    inventory, compose, frozen = _inputs()
    compose = copy.deepcopy(compose)
    del compose["services"]["sahool-soil-service"]
    errs, _ = guard.check(inventory, compose, frozen)
    assert any(e.startswith("sahool-soil-service:") for e in errs), errs


def test_pending_removal_is_green_before_and_after_the_service_disappears():
    inventory, compose, frozen = _inputs()
    pending = set(inventory["pending_removal"])
    present = copy.deepcopy(compose)
    for name in pending:
        present["services"].setdefault(
            name, {"depends_on": {"sahool-postgres": {"condition": "service_healthy"}}}
        )
    absent = copy.deepcopy(compose)
    for name in pending:
        absent["services"].pop(name, None)
    assert guard.check(inventory, present, frozen)[0] == []
    errs, notes = guard.check(inventory, absent, frozen)
    assert errs == [] and {n.split()[0] for n in notes} == pending


def test_frozen_class_is_accepted_only_for_a_gate01_frozen_path():
    inventory, compose, frozen = _inputs()
    entry = {
        "class": "gate01_frozen_fail_fast",
        "anchor": "services/soil-service/main.py::lifespan",
    }
    errs = guard.check_entry("x", entry, compose["services"]["sahool-soil-service"], frozen)
    assert any("غير مجمَّد" in e for e in errs), errs


def test_one_shot_requires_restart_no():
    errs = guard.check_entry("x", {"class": "one_shot"}, {"restart": "unless-stopped"}, set())
    assert errs and "restart" in errs[0]
    assert guard.check_entry("x", {"class": "one_shot"}, {"restart": "no"}, set()) == []


def test_a_direct_connect_classified_as_retrying_is_blocked(tmp_path):
    module = tmp_path / "svc.py"
    module.write_text(
        "import asyncpg\n\nasync def run():\n    return await asyncpg.create_pool('dsn')\n",
        encoding="utf-8",
    )
    entry = {"class": "retries_with_backoff", "anchor": f"{module}::run"}
    errs = guard.check_entry("x", entry, {}, set())
    assert any("مباشر" in e for e in errs), errs


def test_moved_lines_stay_green(tmp_path):
    """The anchor is path::function, so shifting the code does not break the inventory."""
    inventory, compose, frozen = _inputs()
    for name, entry in inventory["services"].items():
        assert not re.search(r":\d+$", entry.get("anchor", "")), f"{name}: line-number anchor"
    src = ROOT / "services" / "soil-service" / "main.py"
    moved = tmp_path / "main.py"
    moved.write_text("\n" * 40 + src.read_text(encoding="utf-8"), encoding="utf-8")
    entry = {"class": "retries_with_backoff", "anchor": f"{moved}::lifespan"}
    assert guard.check_entry("x", entry, compose["services"]["sahool-soil-service"], frozen) == []


def test_the_guard_runs_in_ci_after_the_compose_auth_sink_guard():
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    sink = ci.index("python scripts/ci/compose_auth_sink_guard.py")
    mine = ci.index("python scripts/ci/startup_db_connect_retry_guard.py")
    assert sink < mine
