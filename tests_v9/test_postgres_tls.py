"""Postgres v9 يُلزِم TLS على الخادم، وكلُّ عميلٍ يتحقّق منه بـ``verify-full``.

**العطلُ مقيسٌ على main@0e5281614** — POSTGRES-V9-HAS-NO-TLS-SO-EVERY-CLIENT-IS-PLAINTEXT-01:
``sahool-postgres`` بلا ``command`` ولا شهادة، و``pg_hba`` الذي تكتبه صورةُ postgis يقبل
``host all all all scram-sha-256`` — أي TCP نصّيّاً من أيّ عنوان. و``prefer`` الافتراضيُّ في
asyncpg/libpq يسقط إليه صامتاً، فكلُّ عميلٍ كان يتّصل نصّاً؛ وتدقيقُ الأمن كان يُجيز ذلك ضمنيّاً
ويستثني التصريحَ الوحيد به (سطرَ المُصدِّر).

**وشرطُ الإغلاق بتحديد المالك ثلاثةُ أطرافٍ معاً** — أحدُها دون الآخر لا يُغلق:
  ① شهادةُ خادمٍ من مهمّةِ تهيئة (بلا مفتاحٍ مُلتزَم)؛
  ② ``hostssl`` وحده في ``pg_hba`` (TCP بلا TLS يُرفَض على الخادم، لا بحسن نيّة العميل)؛
  ③ ``sslmode=verify-full`` في كلّ عميل (لا يقبل خادماً منتحَلاً).

طبقتان: **عقدٌ ساكن** (``unit``) على compose و``pg_hba`` و``.env.example`` و``odoo-init.sh``؛
و**إثباتٌ حيّ** (``integration``) على خادم Postgres حقيقيّ محلّيّ يُشغَّل **بأعلام compose نفسِها**
و``pg_hba`` المُلتزَم ومادّةٍ يولّدها السكربتُ الحقيقيّ — يُتخطّى بلا ثنائيّات PG ويفشل بدل التخطّي
مع ``POSTGRES_TLS_LIVE_REQUIRED=1``. الثنائيّات: ``POSTGRES_TLS_PG_BIN`` أو ``/usr/lib/postgresql/<n>/bin``.
"""

from __future__ import annotations

import asyncio
import glob
import os
import pwd
import re
import shutil
import socket
import subprocess
import tempfile
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
COMPOSE = ROOT / "docker-compose.v9.yml"
HBA = ROOT / "postgres" / "pg_hba.conf"
ENV_EXAMPLE = ROOT / ".env.example"
ODOO_INIT = ROOT / "scripts" / "odoo-init.sh"
TLS_SCRIPT = ROOT / "scripts" / "tls" / "ensure_service_tls.sh"
SERVER = "sahool-postgres"
INIT = "sahool-postgres-tls-init"
CA_DIR = "/etc/sahool/postgres-ca"
CA = f"{CA_DIR}/ca.pem"
SERVER_TLS_DIR = "/etc/postgresql/tls"
HBA_PATH = "/etc/postgresql/pg_hba.conf"
DEV_VALUES = {"development", "dev", "local", "test"}

_DSN_KEYS = re.compile(r"(^|_)DATABASE_URL$|^PGHOST$|^DATA_SOURCE_URI$")


def _services() -> dict:
    return yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))["services"]


def postgres_clients(services: dict | None = None) -> dict[str, dict]:
    """كلُّ خدمةٍ تبلغ ``sahool-postgres``: عنوانُ اتّصالٍ أو ``PGHOST`` أو اعتمادٌ عليه في ``depends_on``.

    مُشتقٌّ من compose لا من قائمة — عميلٌ جديدٌ يدخل الشرطَ تلقائيّاً.
    """
    services = services if services is not None else _services()
    out = {}
    for name, svc in services.items():
        if name in {SERVER, INIT}:
            continue
        env = svc.get("environment") or {}
        if not isinstance(env, dict):
            continue
        reaches = any(_DSN_KEYS.search(str(k)) or SERVER in str(v) for k, v in env.items())
        if reaches or SERVER in (svc.get("depends_on") or {}):
            out[name] = svc
    return out


def _hba_rules() -> list[list[str]]:
    rules = []
    for raw in HBA.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if line:
            rules.append(line.split())
    return rules


def _command_settings() -> dict[str, str]:
    cmd = [str(x) for x in _services()[SERVER]["command"]]
    assert cmd[0] == "postgres", cmd
    settings = {}
    for flag, value in zip(cmd[1::2], cmd[2::2], strict=True):
        assert flag == "-c", cmd
        key, _, val = value.partition("=")
        settings[key] = val
    return settings


# ══ ① العقدُ الساكن ══════════════════════════════════════════════════════════


@pytest.mark.unit
def test_the_server_requires_tls_from_the_init_volume_and_the_committed_hba():
    settings = _command_settings()
    assert settings.get("ssl") == "on", "sahool-postgres بلا ssl=on — كلُّ عميلٍ يتّصل نصّاً"
    assert settings["ssl_cert_file"] == f"{SERVER_TLS_DIR}/server.pem"
    assert settings["ssl_key_file"] == f"{SERVER_TLS_DIR}/server-key.pem"
    assert settings.get("ssl_min_protocol_version") == "TLSv1.2"
    assert settings.get("hba_file") == HBA_PATH, "pg_hba المُلتزَم غيرُ مُفعَّل — يبقى ملفُّ الصورة"
    svc = _services()[SERVER]
    mounts = [str(v) for v in svc["volumes"]]
    assert f"postgres-tls:{SERVER_TLS_DIR}:ro" in mounts
    assert f"./postgres/pg_hba.conf:{HBA_PATH}:ro" in mounts
    assert not any(m.startswith("./postgres/tls") for m in mounts), (
        "الخادمُ يقرأ مادّةَ المضيف مباشرةً — مفتاحٌ بمالكٍ وأذوناتٍ لا يقبلها Postgres"
    )
    deps = svc.get("depends_on") or {}
    assert deps.get(INIT, {}).get("condition") == "service_completed_successfully"


@pytest.mark.unit
def test_the_tls_init_uses_the_shared_fail_closed_script_and_installs_an_owned_key():
    init = _services()[INIT]
    env = init["environment"]
    assert (env["TLS_CODE"], env["TLS_SERVICE_HOST"]) == ("POSTGRES", SERVER)
    raw = str(env["SAHOOL_ENV"])
    match = re.fullmatch(r"\$\{SAHOOL_ENV(?::?-(?P<default>[^}]*)|:\?[^}]*)?\}", raw)
    assert match and (match.group("default") or "").strip().lower() not in DEV_VALUES, (
        f"{INIT} يفترض بيئةَ تطوير ({raw}) — نشرٌ بلا SAHOOL_ENV يولّد CA ذاتيّاً ويعمل به"
    )
    mounts = [str(v) for v in init["volumes"]]
    assert "./postgres/tls:/etc/service-tls" in mounts
    assert f"postgres-tls:{env['TLS_INSTALL_DIR']}" in mounts, "المهمّةُ لا تكتب حيث يقرأ الخادم"
    assert env["TLS_INSTALL_OWNER"] == "999:999", "مالكُ المفتاح ليس مستخدمَ postgres في الصورة"
    assert "./scripts/tls/ensure_service_tls.sh:/ensure_service_tls.sh:ro" in mounts
    assert "/ensure_service_tls.sh" in [str(x) for x in init["entrypoint"]]
    assert str(init.get("restart")) == "no" and init.get("network_mode") == "none"
    assert "postgres-tls" in yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))["volumes"]


@pytest.mark.unit
def test_pg_hba_accepts_tcp_only_over_tls_with_a_password():
    """Postgres يأخذ أوّلَ سطرٍ يطابق: لا ``host`` قطّ، و``hostnossl … reject`` قبل أيّ قبول."""
    rules = _hba_rules()
    types = [r[0] for r in rules]
    assert "host" not in types, "سطرُ `host` يقبل TCP نصّيّاً — الخادمُ عاد يعتمد على حسن نيّة العميل"
    assert set(types) <= {"local", "hostssl", "hostnossl"}, types
    tcp = [r for r in rules if r[0] != "local"]
    assert tcp and tcp[0] == ["hostnossl", "all", "all", "all", "reject"], tcp
    for rule in tcp[1:]:
        assert rule[0] == "hostssl" and rule[-1] == "scram-sha-256", (
            f"قبولٌ عبر TCP بغير TLS+scram: {rule}"
        )
    assert all(r[-1] == "trust" for r in rules if r[0] == "local")


@pytest.mark.unit
def test_every_v9_client_verifies_the_server_with_its_ca_and_never_sees_the_key():
    offenders = []
    clients = postgres_clients()
    for name, svc in clients.items():
        env = svc["environment"]
        mounts = [str(v) for v in svc.get("volumes") or []]
        if env.get("PGSSLMODE") != "verify-full":
            offenders.append(f"{name}: PGSSLMODE={env.get('PGSSLMODE')!r}")
        if env.get("PGSSLROOTCERT") != CA:
            offenders.append(f"{name}: PGSSLROOTCERT={env.get('PGSSLROOTCERT')!r}")
        if f"./postgres/tls/ca:{CA_DIR}:ro" not in mounts:
            offenders.append(f"{name}: لا يُركِّب CA الخادم")
        if any(
            m.startswith(("./postgres/tls/server", "./postgres/tls:", "postgres-tls:"))
            for m in mounts
        ):
            offenders.append(f"{name}: يُركِّب مفتاحَ الخادم")
        for key, value in env.items():
            text = str(value)
            if f"@{SERVER}:5432/" in text or text.startswith(f"{SERVER}:5432/"):
                if f"sslmode=verify-full&sslrootcert={CA}" not in text:
                    offenders.append(f"{name}.{key}: عنوانٌ بلا verify-full — {text[:60]}…")
    assert len(clients) >= 30, f"انهار الاستخراج ({len(clients)}) — شرطٌ على لا عملاء يمرّ دائماً"
    assert not offenders, "\n  ".join(["عملاءُ Postgres لا يتحقّقون من الخادم:", *offenders])


@pytest.mark.unit
def test_env_example_dsns_verify_the_server():
    lines = [
        line
        for line in ENV_EXAMPLE.read_text(encoding="utf-8").splitlines()
        if not line.lstrip().startswith("#") and f"@{SERVER}:5432/" in line
    ]
    assert len(lines) >= 3, lines
    for line in lines:
        assert line.endswith(f"?sslmode=verify-full&sslrootcert={CA}"), line


@pytest.mark.unit
def test_odoo_passes_the_stack_sslmode_explicitly():
    """Odoo يُمرّر ``sslmode`` من إعداده (افتراضُه prefer) فيطغى على ``PGSSLMODE`` — فيُمرَّر صراحةً."""
    text = ODOO_INIT.read_text(encoding="utf-8")
    assert 'DB_SSLMODE="${PGSSLMODE:-prefer}"' in text
    runs = [line for line in text.splitlines() if re.match(r"\s*(exec\s+)?odoo\s", line)]
    assert len(runs) == 2, runs
    for line in runs:
        assert '--db_sslmode="${DB_SSLMODE}"' in line, f"Odoo يتّصل بلا db_sslmode: {line.strip()}"
    odoo = _services()["sahool-odoo"]
    assert odoo["environment"]["PGSSLMODE"] == "verify-full"


@pytest.mark.unit
def test_no_postgres_tls_material_can_be_committed():
    for name in ("server/server-key.pem", "server/server.pem", "ca/ca.pem", "ca/94bd4194.0"):
        rc = subprocess.run(
            ["git", "check-ignore", "--no-index", "-q", f"postgres/tls/{name}"],
            cwd=ROOT,
            check=False,
        ).returncode
        assert rc == 0, f"postgres/tls/{name} غير مُتجاهَل — مادّةُ الخادم قد تُلتزَم"
    rc = subprocess.run(
        ["git", "check-ignore", "--no-index", "-q", "postgres/pg_hba.conf"], cwd=ROOT, check=False
    ).returncode
    assert rc == 1, "pg_hba.conf نفسُه مُتجاهَل — السياسةُ يجب أن تُلتزَم"


# ══ ② الإثباتُ الحيّ ═════════════════════════════════════════════════════════


def _pg_bin() -> Path | None:
    explicit = os.getenv("POSTGRES_TLS_PG_BIN")
    if explicit:
        return Path(explicit)
    found = sorted(glob.glob("/usr/lib/postgresql/*/bin/initdb"))
    return Path(found[-1]).parent if found else None


def _runner() -> list[str] | None:
    """initdb وpostgres يرفضان root: يُشغَّلان بمستخدم postgres حين يكون المُشغِّلُ root."""
    if os.geteuid() != 0:
        return []
    try:
        pwd.getpwnam("postgres")
    except KeyError:
        return None
    runuser = shutil.which("runuser")
    return [runuser, "-u", "postgres", "--"] if runuser else None


def _require_live() -> tuple[Path, list[str]]:
    pg_bin, runner = _pg_bin(), _runner()
    if pg_bin is None or runner is None or not shutil.which("openssl"):
        reason = (
            f"LIVE PROOF SKIPPED: pg_bin={pg_bin} runner={runner} openssl={shutil.which('openssl')}"
        )
        if os.getenv("POSTGRES_TLS_LIVE_REQUIRED") == "1":
            pytest.fail(f"POSTGRES_TLS_LIVE_REQUIRED=1 — {reason}")
        pytest.skip(reason)
    return pg_bin, runner


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture(scope="module")
def live_server():
    pg_bin, runner = _require_live()
    owner = "postgres" if runner else None
    work = Path(tempfile.mkdtemp(prefix="sahool-pg-tls-"))
    work.chmod(0o755)
    uid, gid = (
        (pwd.getpwnam(owner).pw_uid, pwd.getpwnam(owner).pw_gid)
        if owner
        else (os.getuid(), os.getgid())
    )
    tls, install, data = work / "tls", work / "install", work / "data"
    for d in (tls, install):
        d.mkdir()
    install.chmod(0o755)
    gen = subprocess.run(
        ["sh", str(TLS_SCRIPT)],
        env={
            **os.environ,
            "TLS_DIR": str(tls),
            "TLS_CODE": "POSTGRES",
            "TLS_SERVICE_HOST": SERVER,
            "TLS_INSTALL_DIR": str(install),
            "TLS_INSTALL_OWNER": f"{uid}:{gid}",
            "SAHOOL_ENV": "development",
        },
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert gen.returncode == 0, gen.stderr
    shutil.copy(HBA, work / "pg_hba.conf")
    password = "pgtls-" + os.urandom(8).hex()
    (work / "pw").write_text(password, encoding="utf-8")
    for path in (work, work / "pg_hba.conf", work / "pw"):
        os.chown(path, uid, gid)
    init = subprocess.run(
        [
            *runner,
            str(pg_bin / "initdb"),
            "-D",
            str(data),
            "-U",
            "sahool_user",
            "--pwfile",
            str(work / "pw"),
            "-A",
            "trust",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert init.returncode == 0, init.stderr
    port = _free_port()
    settings = _command_settings()
    # أعلامُ compose **نفسُها**، والمساراتُ وحدها تُنقل إلى المجلّد المؤقّت.
    settings["ssl_cert_file"] = settings["ssl_cert_file"].replace(SERVER_TLS_DIR, str(install))
    settings["ssl_key_file"] = settings["ssl_key_file"].replace(SERVER_TLS_DIR, str(install))
    settings["hba_file"] = str(work / "pg_hba.conf")
    settings.update(
        {"listen_addresses": "127.0.0.1", "port": str(port), "unix_socket_directories": str(work)}
    )
    opts = " ".join(f"-c {k}={v}" for k, v in settings.items())
    start = subprocess.run(
        [
            *runner,
            str(pg_bin / "pg_ctl"),
            "-D",
            str(data),
            "-l",
            str(work / "log"),
            "-w",
            "-o",
            opts,
            "start",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    log = (
        (work / "log").read_text(encoding="utf-8", errors="replace")
        if (work / "log").exists()
        else ""
    )
    assert start.returncode == 0, start.stderr + log
    try:
        yield {
            "port": port,
            "password": password,
            "ca": str(tls / "ca" / "ca.pem"),
            "work": work,
            "pg_bin": pg_bin,
        }
    finally:
        subprocess.run(
            [*runner, str(pg_bin / "pg_ctl"), "-D", str(data), "-m", "fast", "stop"],
            capture_output=True,
            check=False,
        )
        shutil.rmtree(work, ignore_errors=True)


def _psql(live, conninfo: str, password: str | None = None) -> subprocess.CompletedProcess[str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith("PG")}
    env["PGPASSWORD"] = password if password is not None else live["password"]
    return subprocess.run(
        [
            str(live["pg_bin"] / "psql"),
            "-X",
            "-At",
            "-d",
            conninfo,
            "-c",
            "SELECT ssl FROM pg_stat_ssl WHERE pid = pg_backend_pid()",
        ],
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
    )


def _conninfo(live, **extra: str) -> str:
    params = {
        "host": "localhost",
        "port": str(live["port"]),
        "user": "sahool_user",
        "dbname": "postgres",
        "sslmode": "verify-full",
        "sslrootcert": live["ca"],
        **extra,
    }
    return " ".join(f"{k}={v}" for k, v in params.items())


@pytest.mark.integration
def test_live_plaintext_tcp_is_refused_by_the_server(live_server):
    out = _psql(live_server, _conninfo(live_server, sslmode="disable"))
    assert out.returncode != 0
    assert "no encryption" in out.stderr or "pg_hba.conf rejects" in out.stderr, out.stderr


@pytest.mark.integration
def test_live_verify_full_with_the_ca_connects_over_tls(live_server):
    out = _psql(live_server, _conninfo(live_server))
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() == "t", "الاتّصالُ قام بلا TLS"


@pytest.mark.integration
def test_live_a_client_that_does_not_trust_the_ca_refuses_the_server(live_server, tmp_path):
    foreign = tmp_path / "foreign.pem"
    subprocess.run(
        [
            "openssl",
            "req",
            "-x509",
            "-newkey",
            "ec",
            "-pkeyopt",
            "ec_paramgen_curve:prime256v1",
            "-nodes",
            "-keyout",
            str(tmp_path / "k.pem"),
            "-out",
            str(foreign),
            "-days",
            "1",
            "-subj",
            "/CN=impostor CA",
        ],
        check=True,
        capture_output=True,
    )
    foreign.chmod(0o644)
    tmp_path.chmod(0o755)
    out = _psql(live_server, _conninfo(live_server, sslrootcert=str(foreign)))
    assert out.returncode != 0
    assert "certificate verify failed" in out.stderr, out.stderr


@pytest.mark.integration
def test_live_a_server_name_outside_the_certificate_is_refused(live_server):
    out = _psql(live_server, _conninfo(live_server, host="impostor.internal", hostaddr="127.0.0.1"))
    assert out.returncode != 0
    assert "does not match host name" in out.stderr, out.stderr


@pytest.mark.integration
def test_live_asyncpg_honours_the_compose_dsn_and_a_wrong_password_is_refused(live_server):
    """الخدماتُ تتّصل بـasyncpg بعنوان compose نفسِه: ``?sslmode=verify-full&sslrootcert=…``."""
    asyncpg = pytest.importorskip("asyncpg")

    base = f"postgresql://sahool_user:{{pw}}@localhost:{live_server['port']}/postgres"
    query = f"?sslmode=verify-full&sslrootcert={live_server['ca']}"

    async def probe(pw: str):
        conn = await asyncpg.connect(base.format(pw=pw) + query, timeout=10)
        try:
            return await conn.fetchval("SELECT ssl FROM pg_stat_ssl WHERE pid = pg_backend_pid()")
        finally:
            await conn.close()

    assert asyncio.run(probe(live_server["password"])) is True
    with pytest.raises(asyncpg.InvalidPasswordError):
        asyncio.run(probe("wrong-" + live_server["password"]))
