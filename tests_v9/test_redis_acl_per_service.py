"""مستخدمُ ACL لكلّ خدمة في Redis — ``REDIS-SHARED-PASSWORD-NO-ACL-01``.

**العطلُ مقيسٌ على main@ec3927ce:** خادما Redis في ``docker-compose.v9.yml`` (``sahool-redis`` الكاش
و``sahool-redis-state`` الحالةُ الأمنيّة) يُقلِعان بـ``--requirepass "${REDIS_PASSWORD}"`` وحدَه،
وثلاثةَ عشرَ عميلاً يحملون الكلمةَ نفسَها (``redis://:${REDIS_PASSWORD}@…``). فكلُّ عميلٍ هو
المستخدمُ ``default`` بـ``+@all ~* &*``: خدمةُ TTS تستطيع ``FLUSHALL`` على الكاش، وأيُّ عميلٍ على
redis-state يقرأ رموزَ التحديث ويمسح قفلَ الحسابات. لا ACL في أيّ ملفّ compose.

**قرارُ المالك (2026-09-30): مستخدمو ACL لكلّ خدمة.** المصدرُ الواحد
``docs/architecture/redis_acl_matrix.json``: لكلّ خدمةٍ أوامرُها ومفاتيحُها وقنواتُها مشتقّةً من
شيفرتها بـpath:line، وسطرُ أمر الخادم يُطابقه حرفيّاً. وما يحرسه هذا الملفّ طبقتان:

① **عقدٌ ساكن** (``unit``): ``default`` معطَّل · ``--user`` كلٌّ منها يُصيَّر من المصفوفة بلا زيادة
   ولا نقص · كلُّ خدمةٍ في v9 تتّصل بـRedis لها مستخدمٌ باسمها لا يشاركها فيه أحد · لا مستخدمَ
   خدمةٍ يملك أمراً من الصنف الإداريّ/الخطِر ولا ``~*``/``&*`` · كلُّ رابطِ عميلٍ يحمل اسمَه
   ومتغيّرَ كلمةِ سرّه هو · شواهدُ المصفوفة موجودةٌ في الشيفرة · و``&`` في سطر الأمر مُنصَّصة
   (compose يقطع السطرَ عند ``&`` العارية بصمت — مقيسٌ بـ``docker compose config``: 17 وسيطاً
   من 175، فيسقط كلُّ مستخدمٍ بعد المشغِّل).

② **إثباتٌ حيّ على redis-server حقيقيّ** (``integration``، يُتخطّى بلا الملفّ التنفيذيّ ويفشل بدله
   مع ``REDIS_ACL_LIVE_REQUIRED=1``): سطرُ الأمر من compose نفسُه بكلمات سرٍّ مختلفة لكلّ مستخدم.
   الكلمةُ المشتركة وحدَها تُرَدّ؛ كلُّ مستخدمٍ يتّصل برابطه عبر redis-py ويُنفِّذ ما له؛ و``FLUSHALL``
   و``CONFIG`` و``KEYS`` ومفتاحٌ خارج أنماطه وقناةٌ خارج قنواته كلُّها ``NOPERM``.
"""

from __future__ import annotations

import contextlib
import fnmatch
import functools
import hashlib
import json
import os
import re
import shlex
import shutil
import socket
import subprocess
import time
from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
COMPOSE = ROOT / "docker-compose.v9.yml"
MATRIX = ROOT / "docs" / "architecture" / "redis_acl_matrix.json"
ENV_EXAMPLE = ROOT / ".env.example"
SERVERS = ("sahool-redis", "sahool-redis-state")
_VAR = re.compile(r"\$\{([A-Z][A-Z0-9_]*)(?::([?-])([^}]*))?\}")
_REDIS_PW_VAR = re.compile(r"\$\{(REDIS_(?:[A-Z_]+_)?PASSWORD)(?:[:?-][^}]*)?\}")


@functools.cache
def _matrix() -> dict:
    return json.loads(MATRIX.read_text(encoding="utf-8"))


def _password_for(var: str) -> str:
    """كلمةُ سرٍّ ستّ‑عشريّة مختلفة لكلّ متغيّر — تُبنى ولا تُكتَب (gitleaks)."""
    return hashlib.sha256(f"redis-acl::{var}".encode()).hexdigest()[:32]


@functools.cache
def _compose_raw() -> dict:
    return yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))


@functools.cache
def _compose() -> dict:
    """compose مُستوفى كما يستوفيه هو والمتغيّراتُ غيرُ مضبوطة: ``${REDIS_*PASSWORD}`` بكلمته،
    و``${VAR:-default}`` بافتراضه (رابطُ ai-agronomist متداخلٌ فيه)، والباقي بقيمةٍ محايدة."""
    text = _REDIS_PW_VAR.sub(
        lambda m: _password_for(m.group(1)), COMPOSE.read_text(encoding="utf-8")
    )
    return yaml.safe_load(_VAR.sub(lambda m: m.group(3) if m.group(2) == "-" else "x", text))


def _argv(server: str) -> list[str]:
    cmd = _compose()["services"][server]["command"]
    return [str(a) for a in cmd] if isinstance(cmd, list) else shlex.split(str(cmd))


def _user_rules(argv: list[str]) -> dict[str, list[str]]:
    """``--user <name> <rules…>`` ⇒ {الاسم: القواعد} بترتيبها."""
    users: dict[str, list[str]] = {}
    i = 0
    while i < len(argv):
        if argv[i] == "--user":
            name, j = argv[i + 1], i + 2
            rules: list[str] = []
            while j < len(argv) and not argv[j].startswith("--"):
                rules.append(argv[j])
                j += 1
            assert name not in users, f"المستخدم {name} مُعرَّف مرّتين"
            users[name] = rules
            i = j
            continue
        i += 1
    return users


def _expected_rules(server: str) -> dict[str, list[str]]:
    """القواعدُ كما تُصيَّر من المصفوفة — الصيغةُ الوحيدة المقبولة في compose."""
    s = _matrix()["servers"][server]
    out = {"default": list(_matrix()["default_user_rule"])}
    admin = s["admin"]
    out[admin["user"]] = ["on", ">" + _password_for(admin["password_env"]), "~*", "&*", "+@all"]
    for name, u in s["users"].items():
        out[name] = (
            ["on", ">" + _password_for(u["password_env"]), "resetkeys", "resetchannels", "-@all"]
            + [f"+{c}" for c in u["commands"]]
            + [f"~{k}" for k in u["keys"]]
            + [f"&{c}" for c in u["channels"]]
        )
    return out


def _service_users() -> list[tuple[str, str, dict]]:
    return [
        (server, name, u)
        for server in SERVERS
        for name, u in _matrix()["servers"][server]["users"].items()
    ]


def _env(svc: dict) -> dict[str, str]:
    env = svc.get("environment") or {}
    if isinstance(env, list):
        env = dict(str(e).partition("=")[::2] for e in env)
    return {str(k): str(v) for k, v in env.items()}


# ── ① العقدُ الساكن ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize("server", SERVERS)
def test_redis_server_disables_the_default_user_and_drops_the_shared_password(server):
    argv = _argv(server)
    users = _user_rules(argv)
    assert users.get("default") == _matrix()["default_user_rule"], (
        f"{server}: المستخدمُ default ليس `off resetpass resetkeys resetchannels -@all` "
        f"({users.get('default')!r}) ⇒ كلمةُ سرٍّ واحدة بلا اسم مستخدم تفتح Redis كلَّه."
    )
    assert "--requirepass" not in argv, (
        f"{server}: `--requirepass` يُعيد كلمةَ default المشتركة — ACL هو المصادقة وحدَه."
    )


@pytest.mark.parametrize("server", SERVERS)
def test_compose_acl_is_rendered_exactly_from_the_matrix(server):
    """لا مستخدمَ ولا قاعدةَ في compose بلا شاهدٍ في المصفوفة، ولا العكس."""
    actual = _user_rules(_argv(server))
    expected = _expected_rules(server)
    assert sorted(actual) == sorted(expected), (server, sorted(actual), sorted(expected))
    for name, rules in expected.items():
        assert actual[name] == rules, (
            f"{server}: قواعدُ {name} في compose {actual[name]} ≠ المصفوفة {rules}"
        )


@pytest.mark.parametrize("server", SERVERS)
def test_redis_command_has_no_unquoted_shell_metacharacter(server):
    """compose يُقسِّم ``command`` النصّيّ بمحلِّل صدفة، و``&`` العارية تُنهي السطر بصمت.

    مقيسٌ بـ``docker compose config``: ``~* &* +@all`` غيرُ مُنصَّصة ⇒ ``['…', '>pw', '~*']`` ثمّ لا
    شيء — 17 وسيطاً من 175، فكلُّ مستخدمٍ بعد المشغِّل لا يُعرَّف ويُرَدّ كلُّ عميل ``WRONGPASS``.
    """
    raw = _compose_raw()["services"][server]["command"]
    if isinstance(raw, list):
        return
    lexer = shlex.shlex(str(raw), posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    with_punct = list(lexer)
    assert with_punct == shlex.split(str(raw)), (
        f'{server}: محرفُ صدفةٍ عارٍ (& ; | < >) في command — نصِّصه (`"&chan"`) وإلّا قطع compose السطر.'
    )


def test_every_redis_consuming_v9_service_has_its_own_user():
    """كلُّ خدمةٍ في v9 يحمل بيئتُها رابطاً إلى أحد خادمَي Redis لها مستخدمٌ باسمها عليه."""
    users = {(server, name) for server, name, _ in _service_users()}
    seen: dict[tuple[str, str], str] = {}
    for svc_name, svc in _compose_raw()["services"].items():
        if svc_name in SERVERS or not isinstance(svc, dict):
            continue
        for key, value in _env(svc).items():
            m = re.search(r"redis://([^:@/]*):[^@]*@(sahool-redis(?:-state)?):", value)
            if not m:
                continue
            username, server = m.groups()
            assert username == svc_name, (
                f"{svc_name}.{key} يتّصل بـ{server} بالمستخدم {username!r} — "
                "لكلّ خدمةٍ مستخدمُها باسمها (لا كلمةَ سرٍّ مشتركة ولا مستخدمَ مُعار)."
            )
            assert (server, username) in users, (
                f"{svc_name}.{key}: لا مستخدمَ {username} على {server}"
            )
            seen[(server, username)] = key
    wired = {k for k in users if _matrix()["servers"][k[0]]["users"][k[1]]["client_env"]}
    assert set(seen) == wired, (sorted(set(seen) ^ wired), "مستخدمٌ بلا عميل أو عميلٌ بلا مستخدم")
    for server, name, u in _service_users():
        if u["client_env"]:
            assert seen[(server, name)] == u["client_env"], (name, seen[(server, name)])
    assert len(seen) >= 13, len(seen)


def test_no_two_services_share_a_user_or_a_password_variable():
    names = [name for _, name, _ in _service_users()]
    variables = [u["password_env"] for _, _, u in _service_users()]
    admins = {_matrix()["servers"][s]["admin"]["password_env"] for s in SERVERS}
    assert len(names) == len(set(names)), names
    assert len(variables) == len(set(variables)), variables
    assert not admins & set(variables), "كلمةُ المشغِّل لا تكون كلمةَ خدمة"


@pytest.mark.parametrize(
    "server,name,user", _service_users(), ids=[f"{s}::{n}" for s, n, _ in _service_users()]
)
def test_no_service_user_can_flush_reconfigure_or_reach_everything(server, name, user):
    forbidden = set(_matrix()["forbidden_for_service_users"])
    granted = set(user["commands"])
    assert not granted & forbidden, f"{name}: {sorted(granted & forbidden)}"
    assert not any(c.startswith("@") or "|" in c for c in granted), (
        f"{name}: صنفٌ أو أمرٌ فرعيّ ({sorted(granted)}) يتجاوز ما اشتُقّ من الشيفرة"
    )
    assert "*" not in user["keys"] and "*" not in user["channels"], f"{name}: ~* أو &*"
    for key in user["keys"]:
        assert re.fullmatch(r"[a-z][a-z0-9:_-]*(?::\*)?", key) and ":" in key, (
            f"{name}: نمطُ مفتاح بلا بادئةٍ مُسمّاة ({key!r})"
        )


def test_each_client_url_uses_its_own_password_variable_and_never_the_admin_one():
    text = COMPOSE.read_text(encoding="utf-8")
    owners = {
        u["password_env"]: (server, name) for server, name, u in _service_users() if u["client_env"]
    }
    found = re.findall(
        r"redis://([a-z0-9-]*):\$\{([A-Z_]+)(?::\?[^}]*)?\}@(sahool-redis(?:-state)?):", text
    )
    assert len(found) >= 13, found
    for username, var, server in found:
        assert var != "REDIS_PASSWORD", f"{username}: كلمةُ المشغِّل في رابط عميل"
        assert owners.get(var) == (server, username), (
            f"رابطُ {username}@{server} يحمل ${{{var}}} وهي كلمةُ {owners.get(var)}"
        )
    for svc_name, svc in _compose_raw()["services"].items():
        if svc_name in SERVERS or not isinstance(svc, dict):
            continue
        for key, value in _env(svc).items():
            assert "${REDIS_PASSWORD" not in value, (
                f"{svc_name}.{key} يحمل REDIS_PASSWORD — صارت كلمةَ المشغِّل وحدَه"
            )


def test_decision_service_replay_url_stays_operator_supplied():
    """``DECISION_WORKER_ASSERTION_REDIS_URL`` يضبطه المشغِّل؛ مستخدمُه معرَّفٌ لينجح حين يُضبَط."""
    env = _env(_compose_raw()["services"]["sahool-decision-service"])
    assert env["DECISION_WORKER_ASSERTION_REDIS_URL"] == "${DECISION_WORKER_ASSERTION_REDIS_URL:-}"
    user = _matrix()["servers"]["sahool-redis"]["users"]["sahool-decision-service"]
    assert user["client_env"] is None and "sahool-decision-service" in user["client_env_note"]


def _evidence():
    for _server, name, u in _service_users():
        for ev in u["evidence"]:
            yield pytest.param(name, ev, id=f"{name}::{ev['path']}:{ev['line']}")


@pytest.mark.parametrize("name,ev", list(_evidence()))
def test_matrix_evidence_still_exists_in_the_code(name, ev):
    """الشاهدُ يبقى في الملفّ (السطرُ إعلاميٌّ عند ``measured_on``؛ النصُّ هو المُلزِم)."""
    lines = (ROOT / ev["path"]).read_text(encoding="utf-8").splitlines()
    assert any(ev["needle"] in line for line in lines), (
        f"{name}: الشاهد {ev['needle']!r} غاب من {ev['path']} — أعِد اشتقاق صلاحيّاته"
    )
    assert 1 <= ev["line"] <= len(lines), ev


_REDIS_CLIENT = re.compile(r"^\s*(?:import redis|from redis\b)|\bfrom_url\(|aioredis", re.M)


@pytest.mark.parametrize(
    "name,user",
    [(n, u) for _, n, u in _service_users() if u["basis"] == "connection-only"],
    ids=[n for _, n, u in _service_users() if u["basis"] == "connection-only"],
)
def test_connection_only_users_belong_to_services_without_a_redis_client(name, user):
    """مستخدمٌ بلا مفاتيح ولا قنوات صادقٌ ما دامت الخدمةُ لا تبني عميلاً — فإن بنته، اشتُقّ له."""
    assert not user["keys"] and not user["channels"], name
    assert set(user["commands"]) <= {"ping", "select"}, name
    for rel in user["code_paths"]:
        path = ROOT / rel
        files = [path] if path.is_file() else sorted(path.rglob("*.py"))
        assert files, rel
        for f in files:
            if "tests" in f.parts or f.name.startswith("test_"):
                continue
            hit = _REDIS_CLIENT.search(f.read_text(encoding="utf-8"))
            assert not hit, (
                f"{name}: {f.relative_to(ROOT)} يبني عميلَ Redis ({hit.group(0)!r}) — "
                "اشتقّ أوامرَه ومفاتيحَه في redis_acl_matrix.json بدل connection-only"
            )


def test_env_example_declares_every_redis_password_empty():
    declared = {}
    for line in ENV_EXAMPLE.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^(REDIS_[A-Z_]*PASSWORD)=(.*)$", line)
        if m:
            declared[m.group(1)] = m.group(2)
    wanted = {u["password_env"] for _, _, u in _service_users()} | {"REDIS_PASSWORD"}
    assert wanted <= set(declared), sorted(wanted - set(declared))
    assert all(declared[v] == "" for v in wanted), {v: declared[v] for v in wanted if declared[v]}


# ── ② الإثباتُ الحيّ ────────────────────────────────────────────────────────────


def _redis_server_bin() -> str | None:
    return os.environ.get("REDIS_SERVER_BIN") or shutil.which("redis-server")


def _live_required() -> bool:
    return os.environ.get("REDIS_ACL_LIVE_REQUIRED") == "1"


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module", params=SERVERS)
def live_server(request, tmp_path_factory):
    redis = pytest.importorskip("redis")
    binary = _redis_server_bin()
    if not binary:
        if _live_required():
            pytest.fail("REDIS_ACL_LIVE_REQUIRED=1 ولا redis-server (REDIS_SERVER_BIN أو PATH)")
        pytest.skip("لا redis-server — الإثباتُ الحيّ غير مقيس في هذه البيئة")
    server = request.param
    port = _free_port()
    workdir = tmp_path_factory.mktemp(server)
    argv = [binary, *_argv(server)[1:]]
    argv += ["--port", str(port), "--bind", "127.0.0.1", "--dir", str(workdir), "--save", ""]
    log = workdir / "redis.log"
    argv += ["--logfile", str(log)]
    proc = subprocess.Popen(argv, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)  # noqa: S603
    admin = _matrix()["servers"][server]["admin"]
    admin_client = _login(port, admin["user"], _password_for(admin["password_env"]))
    try:
        deadline = time.monotonic() + 10
        while True:
            try:
                admin_client.ping()
                break
            except redis.exceptions.AuthenticationError as exc:
                pytest.fail(f"{server}: المشغِّل {admin['user']} لا يدخل بسطر compose ({exc})")
            except redis.exceptions.ConnectionError:
                if proc.poll() is not None or time.monotonic() > deadline:
                    out = log.read_text(encoding="utf-8", errors="replace") if log.exists() else ""
                    pytest.fail(f"{server}: redis-server لم يُقلِع بسطر compose:\n{out[-2000:]}")
                time.sleep(0.05)
        yield server, port, admin_client
    finally:
        admin_client.close()
        proc.terminate()
        with contextlib.suppress(subprocess.TimeoutExpired):
            proc.wait(timeout=10)
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=10)


def _login(port: int, user: str | None, password: str):
    """اتّصالٌ بهويّةٍ بلا إعادة محاولة: الرفضُ يُرَدّ فوراً لا بعد تراجعٍ أُسّيّ."""
    import redis
    from redis.backoff import NoBackoff
    from redis.retry import Retry

    return redis.Redis(
        host="127.0.0.1",
        port=port,
        username=user,
        password=password,
        decode_responses=True,
        retry=Retry(NoBackoff(), 0),
    )


def _sample(pattern: str) -> str:
    return pattern.replace("*", "acl-probe")


def _dryrun(admin, user: str, *cmd: str) -> str:
    return str(admin.execute_command("ACL", "DRYRUN", user, *cmd))


#: كيف يُستدعى كلُّ أمرٍ ممنوح على مفتاحٍ/قناة — لـ``ACL DRYRUN`` (لا يُنفَّذ شيء).
_KEYED = {
    "get": ["{k}"],
    "set": ["{k}", "v"],
    "setex": ["{k}", "10", "v"],
    "del": ["{k}"],
    "exists": ["{k}"],
    "expire": ["{k}", "10"],
    "ttl": ["{k}"],
    "incr": ["{k}"],
    "getdel": ["{k}"],
    "sadd": ["{k}", "m"],
    "srem": ["{k}", "m"],
    "smembers": ["{k}"],
    "rpush": ["{k}", "v"],
    "lrange": ["{k}", "0", "-1"],
    "eval": ["return 1", "1", "{k}"],
}
_UNKEYED = {"ping": [], "select": ["0"], "scan": ["0"]}
_CHANNEL = {"subscribe": ["{c}"], "unsubscribe": ["{c}"]}


@pytest.mark.integration
def test_live_the_shared_password_alone_is_refused(live_server):
    import redis

    server, port, _ = live_server
    admin_pw = _password_for(_matrix()["servers"][server]["admin"]["password_env"])
    for user, password in (("default", admin_pw), ("default", ""), (None, admin_pw)):
        with pytest.raises(redis.exceptions.AuthenticationError):
            _login(port, user, password).ping()


@pytest.mark.integration
def test_live_every_client_url_connects_as_its_user(live_server):
    """رابطُ العميل كما يكتبه compose (بمحلِّل redis-py) يتّصل ويُنفِّذ ``PING`` و``SELECT`` قاعدتِه."""
    import redis

    server, port, _ = live_server
    for svc_name, svc in _compose()["services"].items():
        for key, value in _env(svc).items() if isinstance(svc, dict) else ():
            m = re.search(rf"(redis://[^\s]*@){re.escape(server)}:6379(/\d+)?", value)
            if not m or svc_name in SERVERS:
                continue
            url = f"{m.group(1)}127.0.0.1:{port}{m.group(2) or ''}"
            client = redis.Redis.from_url(url, decode_responses=True)
            try:
                assert client.ping() is True, (svc_name, key)
            finally:
                client.close()


@pytest.mark.integration
def test_live_each_user_runs_its_commands_inside_its_patterns_only(live_server):
    server, port, admin = live_server
    every_pattern = {
        k for s in SERVERS for u in _matrix()["servers"][s]["users"].values() for k in u["keys"]
    } | {"sahool:acl-outsider:*", "unrelated"}
    for name, user in _matrix()["servers"][server]["users"].items():
        for cmd in user["commands"]:
            if cmd in _UNKEYED:
                assert _dryrun(admin, name, cmd, *_UNKEYED[cmd]) == "OK", (name, cmd)
                continue
            if cmd in _CHANNEL:
                for ch in user["channels"]:
                    args = [a.format(c=ch) for a in _CHANNEL[cmd]]
                    assert _dryrun(admin, name, cmd, *args) == "OK", (name, cmd, ch)
                continue
            for pattern in user["keys"]:
                args = [a.format(k=_sample(pattern)) for a in _KEYED[cmd]]
                assert _dryrun(admin, name, cmd, *args) == "OK", (name, cmd, pattern)
            for other in every_pattern:
                key = _sample(other)
                if any(fnmatch.fnmatchcase(key, own) for own in user["keys"]):
                    continue
                args = [a.format(k=key) for a in _KEYED[cmd]]
                verdict = _dryrun(admin, name, cmd, *args)
                assert verdict != "OK", f"{name}: {cmd} على {key!r} خارج أنماطه مسموح"


@pytest.mark.integration
def test_live_no_service_user_holds_an_admin_or_dangerous_command(live_server):
    """الأصنافُ من الخادم نفسه (``ACL CAT``) لا من قائمةٍ نكتبها."""
    server, _, admin = live_server
    risky = set(admin.execute_command("ACL", "CAT", "dangerous")) | set(
        admin.execute_command("ACL", "CAT", "admin")
    )
    assert {"flushall", "flushdb", "keys", "shutdown"} <= risky, sorted(risky)
    for name, user in _matrix()["servers"][server]["users"].items():
        assert not set(user["commands"]) & risky, (name, sorted(set(user["commands"]) & risky))
        for cmd in ("flushall", "flushdb", "keys", "monitor", "debug", "shutdown", "save"):
            args = {"keys": ["*"], "debug": ["sleep", "0"]}.get(cmd, [])
            assert _dryrun(admin, name, cmd, *args) != "OK", (name, cmd)


@pytest.mark.integration
def test_live_denials_are_real_noperm_for_command_key_and_channel(live_server):
    """تنفيذٌ فعليّ بهويّة كلّ مستخدم (لا DRYRUN): الأمرُ والمفتاحُ والقناةُ خارجَ ما له ⇒ NOPERM."""
    import redis

    server, port, admin = live_server
    admin.set("sahool:acl-outsider:canary", "1")
    for name, user in _matrix()["servers"][server]["users"].items():
        client = _login(port, name, _password_for(user["password_env"]))
        try:
            for cmd in (("FLUSHALL",), ("CONFIG", "GET", "*"), ("KEYS", "*")):
                with pytest.raises(redis.exceptions.NoPermissionError):
                    client.execute_command(*cmd)
            reader = next((c for c in ("get", "set", "smembers") if c in user["commands"]), None)
            if reader:
                args = [a.format(k="sahool:acl-outsider:canary") for a in _KEYED[reader]]
                with pytest.raises(redis.exceptions.NoPermissionError, match="key"):
                    client.execute_command(reader.upper(), *args)
            with pytest.raises(redis.exceptions.NoPermissionError):
                client.execute_command("SUBSCRIBE", "sahool:acl-outsider")
            with pytest.raises(redis.exceptions.NoPermissionError):
                client.publish(
                    user["channels"][0] if user["channels"] else "raster:layer_evict", "x"
                )
        finally:
            client.close()
    assert admin.get("sahool:acl-outsider:canary") == "1", "مُسِح المفتاحُ الحارس — FLUSHALL مرّ"


@pytest.mark.integration
def test_live_scripts_are_held_to_the_callers_acl(live_server):
    """``EVAL`` الممنوح لـraster لا يتجاوز ACL: سكربتُ القفل يعمل على نمطه، و``flushall`` فيه يُرفَض."""
    import redis

    server, port, admin = live_server
    users = _matrix()["servers"][server]["users"]
    if "sahool-raster-service" not in users:
        pytest.skip("لا مستخدمَ يملك EVAL على هذا الخادم")
    u = users["sahool-raster-service"]
    client = _login(port, "sahool-raster-service", _password_for(u["password_env"]))
    release = (
        "if redis.call('get', KEYS[1]) == ARGV[1] then return redis.call('del', KEYS[1]) "
        "else return 0 end"
    )
    try:
        key = "sahool:raster:indicator-batch:acl-probe"
        assert client.set(key, "job-1", nx=True, ex=30)
        assert client.eval(release, 1, key, "job-1") == 1
        with pytest.raises(
            redis.exceptions.ResponseError, match="(?i)can.t run|can.t access|permission|NOPERM"
        ):
            client.eval("return redis.call('flushall')", 0)
        with pytest.raises(
            redis.exceptions.ResponseError, match="(?i)can.t run|can.t access|permission|NOPERM"
        ):
            client.eval("return redis.call('get', KEYS[1])", 1, "sahool:refresh:acl-probe")
    finally:
        client.close()
