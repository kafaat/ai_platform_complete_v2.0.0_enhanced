"""هويّةٌ لكلّ خدمة ومواضيعُها وحدَها — ``NATS-AUTHORIZATION-NOT-ENFORCED``.

**العطلُ مقيسٌ على main@1cb6cd6c:** اعتمادٌ **واحد** (``$NATS_USER``/``$NATS_PASSWORD``) تحمله
ثلاثَ عشرةَ خدمة في ``NATS_URL``، و``nats/nats.conf`` بلا ``permissions``. فكلُّ خدمةٍ معتمَدة
تنشر على **أيّ** موضوع (عاملُ النبات ينشر ``sahool.events.*`` باسم المنصّة)، وتشترك في
``_INBOX.>`` فتقرأ ما يُسلِّمه JetStream لوكيل الإشعارات، وتحذف الدفقَ ``sahool`` كلَّه. وثلاثٌ
منها (soil · weather-service · telegram-bot) لا عميلَ NATS فيها أصلاً.

**وما يحرسه هذا الملفّ طبقتان:**

① **عقدٌ ساكنٌ مُشتقٌّ من الشيفرة لا من تخمين** (``unit``): كلُّ عميلٍ في compose هويّةٌ في
   nats.conf باسمه بكلمة مرورٍ ``:?`` لا يشاركها أحد · لا هويّةَ تنشر أو تشترك ``>`` · صندوقُ
   الردّ باسم صاحبه (والعميلُ يمرّره) · ومواضيعُ كلِّ هويّةٍ **تُطابِق** ما تنشره شيفرتُها أو
   تشترك فيه — ولا سيّما عمّالُ phase-runtime المجمَّدون، إذ رفضُ الإذن عندهم **صامت**.

② **إثباتٌ حيّ على nats-server حقيقيّ** (``integration``، يُتخطّى بلا الملفّ التنفيذيّ ويفشل
   بدله مع ``NATS_LEAST_PRIVILEGE_LIVE_REQUIRED=1``): nats.conf نفسُه بمادّة TLS يولّدها
   ``scripts/nats/ensure_nats_tls.sh`` الحقيقيّ — المجهولُ وكلمةُ المرور الخاطئة والنصُّ الصريح
   والعميلُ الذي لا يثق بـCA الوسيط كلُّها تُرفَض؛ وكلُّ هويّةٍ تفعل ما لها ويُرفَض ما لغيرها؛
   ومسارُ JetStream الحقيقيّ (الدفق · المستهلكون · PubAck · الإقرار) يعمل بدوال الشيفرة نفسِها.
   الملفُّ التنفيذيّ: ``NATS_SERVER_BIN`` أو ``NOTIFICATION_TEST_NATS_SERVER`` أو ``nats-server``.
"""

from __future__ import annotations

import ast
import asyncio
import contextlib
import importlib
import json
import os
import re
import secrets
import shutil
import socket
import ssl
import subprocess
import sys
import urllib.request
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
CONF = ROOT / "nats" / "nats.conf"
COMPOSE = ROOT / "docker-compose.v9.yml"
PLATFORM = ROOT / "services" / "sahool-platform"
TLS_SCRIPT = ROOT / "scripts" / "nats" / "ensure_nats_tls.sh"
BROKER = "sahool-nats"
NOTIFICATION = "sahool-notification-agent"
STREAM = "sahool"

#: خدماتٌ كانت تحمل كلمةَ مرور الوسيط ولا عميلَ NATS فيها — مقيسٌ بـgrep لا مظنون.
NON_CLIENTS = {
    "sahool-soil-service": ROOT / "services" / "soil-service",
    "sahool-weather-service": ROOT / "services" / "weather-service",
    "sahool-telegram-bot": ROOT / "bots" / "telegram",
}

#: أين يتّصل كلُّ عميلِ JetStream (يحتاج صندوقَ ردّ) — المسارُ الذي يجب أن يمرّر ``inbox_prefix``.
INBOX_CLIENTS = {
    "sahool-platform": PLATFORM / "api" / "main.py",
    "sahool-canonical-execution-learning-worker": PLATFORM
    / "workers"
    / "canonical_execution_learning_worker.py",
    "sahool-vegetation-analysis": ROOT
    / "services"
    / "vegetation-analysis-service"
    / "vegetation_runtime.py",
    "sahool-weather-polygon-worker": ROOT
    / "services"
    / "weather-polygon-worker"
    / "src"
    / "main.py",
}

#: عمّالُ phase-runtime: وضعُ الأمر في compose ⇒ الدالّةُ التي تنشر.
PHASE_WORKERS = {
    "sahool-phase-runtime-outbox-worker": "run_outbox_once",
    "sahool-plugin-runtime-worker": "run_plugin_once",
    "sahool-model-registry-worker": "run_model_registry_once",
    "sahool-actuator-dispatch-worker": "run_actuator_once",
}

JS_ADMIN = re.compile(
    r"^\$JS\.(>|API\.>|API\.STREAM\.(DELETE|PURGE|UPDATE|MSG\.DELETE)\b|API\.CONSUMER\.DELETE\b)"
)


# ══ قارئُ nats.conf ══════════════════════════════════════════════════════════
#
# صيغةُ الوسيط (شبيهة HOCON): خرائطُ ``{}`` · مصفوفاتٌ ``[]`` · ``key: value`` أو ``key = value``
# أو ``key {…}`` · نصوصٌ مقتبسة أو عارية · تعليقاتٌ ``#``. قارئٌ صغيرٌ لهذا الجزء وحدَه — يُقرأ
# به الملفُّ **كما يقرؤه الوسيط** بدل تعابيرَ نمطيّةٍ تُخطئ حدودَ الكتل.

_TOKEN = re.compile(r'\s+|#[^\n]*|//[^\n]*|"(?:[^"\\]|\\.)*"|[{}\[\]]|[,:=]|[^\s{}\[\],:=#"]+')


def _tokens(text: str) -> list[str]:
    out = []
    for match in _TOKEN.finditer(text):
        tok = match.group(0)
        if tok.isspace() or tok.startswith(("#", "//")) or tok in {",", ":", "="}:
            continue
        out.append(tok)
    return out


def _parse(tokens: list[str], pos: int = 0, *, until: str | None = None):
    result: dict = {}
    while pos < len(tokens) and tokens[pos] != until:
        key = tokens[pos].strip('"')
        value, pos = _value(tokens, pos + 1)
        assert key not in result, f"مفتاحٌ مكرّر في nats.conf: {key}"
        result[key] = value
    return result, pos + 1


def _value(tokens: list[str], pos: int):
    tok = tokens[pos]
    if tok == "{":
        return _parse(tokens, pos + 1, until="}")
    if tok == "[":
        items, pos = [], pos + 1
        while tokens[pos] != "]":
            item, pos = _value(tokens, pos)
            items.append(item)
        return items, pos + 1
    return (tok[1:-1] if tok.startswith('"') else tok), pos + 1


def _conf() -> dict:
    return _parse(_tokens(CONF.read_text(encoding="utf-8")))[0]


def _users() -> dict[str, dict]:
    users = _conf()["authorization"]["users"]
    names = [u["user"] for u in users]
    assert len(names) == len(set(names)), f"هويّةٌ مكرّرة: {names}"
    return {u["user"]: u for u in users}


def _allow(user: dict, direction: str) -> list[str]:
    return list((user.get("permissions") or {}).get(direction, {}).get("allow", []))


def _matches(pattern: str, subject: str) -> bool:
    """مطابقةُ مواضيع NATS رمزاً رمزاً: ``*`` رمزٌ واحد، و``>`` رمزٌ فأكثر في الذيل."""
    pat, sub = pattern.split("."), subject.split(".")
    for i, token in enumerate(pat):
        if token == ">":
            return len(sub) > i
        if i >= len(sub) or (token != "*" and token != sub[i]):
            return False
    return len(pat) == len(sub)


def _services() -> dict:
    return yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))["services"]


def _clients() -> dict[str, str]:
    return {
        name: str(svc["environment"]["NATS_URL"])
        for name, svc in _services().items()
        if isinstance(svc.get("environment"), dict) and "NATS_URL" in svc["environment"]
    }


_URL = re.compile(
    r"^tls://(?P<user>[a-z0-9-]+):\$\{(?P<var>[A-Z0-9_]+):\?[^}]+\}@sahool-nats:4222$"
)


def _platform_import(module: str):
    for path in (str(PLATFORM), str(PLATFORM / "api"), str(ROOT)):
        if path not in sys.path:
            sys.path.insert(0, path)
    return importlib.import_module(module)


def _canonical_worker():
    return _platform_import("workers.canonical_execution_learning_worker")


def _canonical_base() -> str:
    """قاعدةُ أسماء المستهلكين كما تُسلِّمها compose — الأسماءُ المأذونةُ مشتقّةٌ منها."""
    env = _services()["sahool-canonical-execution-learning-worker"]["environment"]
    base = re.fullmatch(
        r"\$\{CANONICAL_LEARNING_DURABLE:-([^}]+)\}", str(env["CANONICAL_LEARNING_DURABLE"])
    )
    assert base, env["CANONICAL_LEARNING_DURABLE"]
    return base[1]


def _canonical_durables() -> list[str]:
    worker = _canonical_worker()
    return [worker.durable_for_subject(_canonical_base(), s) for s in worker.SUBJECTS]


def _notification_durables() -> list[str]:
    from shared import notification_consumers

    legacy = [name for _, name in notification_consumers.SUBSCRIPTIONS]
    return legacy + [notification_consumers.queue_name(n) for n in legacy]


# ══ ① العقدُ الساكن ══════════════════════════════════════════════════════════


@pytest.mark.unit
def test_every_connecting_service_has_its_own_identity_and_nothing_else_does():
    users = _users()
    clients = _clients()
    assert sorted(users) == sorted(clients), (
        "هويّاتُ nats.conf لا تطابق عملاءَ compose:\n"
        f"  بلا عميل: {sorted(set(users) - set(clients))}\n  بلا هويّة: {sorted(set(clients) - set(users))}"
    )
    assert len(users) == 10, "تغيّر عددُ الهويّات — راجِع أنّ الجديدةَ مشتقّةٌ من شيفرتها ثمّ حدّثه"
    broker_env = _services()[BROKER]["environment"]
    seen: dict[str, str] = {}
    for name, url in clients.items():
        m = _URL.fullmatch(url)
        assert m, f"{name}: NATS_URL ليس tls://<هويّة>:${{VAR:?…}}@sahool-nats:4222 — {url}"
        assert m["user"] == name, f"{name} يتّصل بهويّة {m['user']} — كلُّ خدمةٍ بهويّتها وحدَها"
        var = m["var"]
        assert users[name]["password"] == f"${var}", (
            f"{name}: كلمةُ المرور في العنوان ({var}) ليست التي يقرؤها الوسيط لهذه الهويّة"
        )
        assert var not in seen, f"{name} و{seen.get(var)} يتشاركان {var} — هويّتان باعتمادٍ واحد"
        seen[var] = name
        assert f"${{{var}:?" in str(broker_env.get(var, "")), (
            f"sahool-nats لا يرث {var} بـ`:?` — سرٌّ افتراضيّ أو إقلاعٌ بلا اعتماد"
        )
    assert sorted(broker_env) == sorted(seen), "الوسيطُ يرث متغيّراتٍ لا هويّةَ لها (أو ينقصه بعضُها)"


@pytest.mark.unit
def test_no_credential_is_committed_and_no_shared_one_remains():
    text = " ".join(_tokens(CONF.read_text(encoding="utf-8")))  # بلا التعليقات
    for user in _users().values():
        assert str(user["password"]).startswith("$NATS_"), f"سرٌّ حرفيٌّ في nats.conf: {user['user']}"
    compose = COMPOSE.read_text(encoding="utf-8")
    for legacy in ("${NATS_USER", "${NATS_PASSWORD", "${NATS_URL"):
        assert legacy not in compose, f"{legacy}… عاد إلى compose — اعتمادٌ مشترك يُبطِل الهويّات"
    assert "$NATS_USER" not in text and "$NATS_PASSWORD" not in text


@pytest.mark.unit
def test_services_without_a_nats_client_carry_no_broker_credential():
    """كلمةُ مرورٍ في حاويةٍ لا تستعملها امتيازٌ بلا وظيفة — يُسرَق ولا يُفتقَد."""
    for name, source in NON_CLIENTS.items():
        env = _services()[name].get("environment") or {}
        assert not any(
            "NATS" in str(k) or "nats://" in str(v) or "tls://" in str(v) for k, v in env.items()
        ), f"{name} يحمل اعتمادَ الوسيط"
        code = "\n".join(
            p.read_text(encoding="utf-8") for p in source.rglob("*.py") if "test" not in p.name
        )
        assert not re.search(r"^\s*(import nats|from nats)\b|nats\.connect\(", code, re.M), (
            f"{name} صار عميلَ NATS — يحتاج هويّةً في nats.conf لا اعتماداً مشتركاً"
        )


@pytest.mark.unit
def test_anonymous_is_refused_and_an_identity_without_permissions_inherits_nothing():
    conf = _conf()
    assert "no_auth_user" not in conf and "no_auth_user" not in conf["authorization"]
    assert "accounts" not in conf, "حساباتٌ تُغيّر نموذجَ العزل — لم تُصمَّم هنا"
    default = conf["authorization"]["default_permissions"]
    assert default == {"publish": {"deny": [">"]}, "subscribe": {"deny": [">"]}}, default
    for name, user in _users().items():
        assert user.get("permissions"), f"{name} بلا permissions"


@pytest.mark.unit
def test_no_identity_publishes_or_subscribes_everything_or_administers_jetstream():
    offenders = []
    for name, user in _users().items():
        for direction in ("publish", "subscribe"):
            for subject in _allow(user, direction):
                if subject in {">", "*", "sahool.>", "$JS.>", "$JS.API.>"}:
                    offenders.append(f"{name} {direction} {subject}")
                if direction == "publish" and JS_ADMIN.match(subject):
                    offenders.append(f"{name} يدير JetStream: {subject}")
    assert not offenders, "\n  ".join(["امتيازٌ أوسعُ من الحاجة:", *offenders])


@pytest.mark.unit
def test_reply_inboxes_are_private_to_their_owner():
    """``_INBOX.>`` يحمل تسليمَ مستهلكي وكيل الإشعارات — فمن اشترك فيه قرأ الأحداثَ كلَّها.

    لكلّ هويّةٍ ``_INBOX_<الهويّة>.>``، والعميلُ يمرّر ``inbox_prefix`` المطابق — وإلّا لا يصل
    ردُّ JetStream فيفشل بمهلة. الاستثناءُ الوحيد وكيلُ الإشعارات (مستهلكوه القائمون تُسلِّم إلى
    ``_INBOX.<nuid>`` و``queue_v1`` إلى ``_INBOX.sahool.notification.*``).
    """
    offenders = []
    for name, user in _users().items():
        inboxes = [s for s in _allow(user, "subscribe") if s.startswith("_INBOX")]
        expected = ["_INBOX.>"] if name == NOTIFICATION else [f"_INBOX_{name}.>"]
        if inboxes and inboxes != expected:
            offenders.append(f"{name}: {inboxes} (المتوقَّع {expected})")
    assert not offenders, "\n  ".join(["صناديقُ ردٍّ غيرُ خاصّة:", *offenders])
    for name, path in INBOX_CLIENTS.items():
        assert f"_INBOX_{name}.>" in _allow(_users()[name], "subscribe")
        tree = ast.parse(path.read_text(encoding="utf-8"))
        literals = {
            n.value
            for n in ast.walk(tree)
            if isinstance(n, ast.Constant) and isinstance(n.value, str)
        }
        assert {s for s in literals if s.startswith("_INBOX")} == {f"_INBOX_{name}"}, (
            f"{path.relative_to(ROOT)} لا يحمل صندوقَ الردّ `_INBOX_{name}` وحدَه"
        )
        connects = [
            n
            for n in ast.walk(tree)
            if isinstance(n, ast.Call)
            and isinstance(n.func, ast.Attribute)
            and n.func.attr == "connect"
            and isinstance(n.func.value, ast.Name)
            and n.func.value.id == "nats"
        ]
        assert connects, f"{path.relative_to(ROOT)}: لا nats.connect — تغيّر موضعُ الاتّصال"
        for call in connects:
            assert "inbox_prefix" in {k.arg for k in call.keywords}, (
                f"{path.relative_to(ROOT)}:{call.lineno} يتّصل بلا inbox_prefix — ردودُه تُسقَط"
            )


def _phase_worker_literals() -> dict[str, set[str]]:
    tree = ast.parse((PLATFORM / "api" / "phase_runtime_workers.py").read_text(encoding="utf-8"))
    out: dict[str, set[str]] = {}
    for fn in tree.body:
        if isinstance(fn, ast.AsyncFunctionDef) and fn.name in PHASE_WORKERS.values():
            out[fn.name] = {
                call.args[0].value
                for call in ast.walk(fn)
                if isinstance(call, ast.Call)
                and isinstance(call.func, ast.Name)
                and call.func.id == "_publish_nats"
                and call.args
                and isinstance(call.args[0], ast.Constant)
            }
    return out


def _runtime_event_types() -> set[str]:
    """``persist_runtime_event(event_type="…")`` — ما يضعه أيُّ مسارٍ في ``runtime_event_outbox``."""
    found = set()
    for path in (PLATFORM / "api").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for call in ast.walk(tree):
            if (
                isinstance(call, ast.Call)
                and getattr(call.func, "id", getattr(call.func, "attr", None))
                == "persist_runtime_event"
            ):
                for kw in call.keywords:
                    if kw.arg == "event_type":
                        assert isinstance(kw.value, ast.Constant), (
                            f"{path.relative_to(ROOT)}:{call.lineno} نوعُ حدثٍ غيرُ حرفيّ — لا يُشتقّ موضوعُه"
                        )
                        found.add(kw.value.value)
    return found


@pytest.mark.unit
def test_frozen_phase_workers_may_publish_exactly_what_their_code_publishes():
    """رفضُ الإذن عند هؤلاء **صامت** (Core NATS بلا إقرار؛ مقيسٌ حيّاً أدناه): الصفُّ يُوسَم
    ``published`` والرسالةُ مرفوضة. فالقائمةُ تُطابِق الشيفرةَ **بالتمام** — لا نقصانَ يُضيّع
    الأحداثَ صامتاً، ولا زيادةَ امتياز."""
    from shared.marketplace_ecosystem_phase12 import KNOWN_HOOKS

    source = (PLATFORM / "api" / "phase_runtime_workers.py").read_text(encoding="utf-8")
    assert (
        'receipt"]["subject"]' in source
        and "f\"sahool.{str(row['event_type']).replace('_', '.')}\"" in source
    ), "تغيّر تحويلُ المواضيع الديناميكيّة في العامل — أعِد اشتقاقَها"
    literals = _phase_worker_literals()
    dotted = lambda t: f"sahool.{t.replace('_', '.')}"  # noqa: E731 — تحويلُ العامل نفسُه
    derived = {
        "run_outbox_once": {dotted(t) for t in _runtime_event_types()},
        "run_plugin_once": {dotted(h) for h in KNOWN_HOOKS},
        "run_model_registry_once": set(),
        "run_actuator_once": set(),
    }
    users = _users()
    for service, fn in PHASE_WORKERS.items():
        command = " ".join(str(x) for x in _services()[service]["command"])
        mode = {
            "run_outbox_once": "outbox",
            "run_plugin_once": "plugin",
            "run_model_registry_once": "model",
            "run_actuator_once": "actuator",
        }[fn]
        assert command.endswith(f"api.phase_runtime_workers {mode}"), (service, command)
        expected = literals[fn] | derived[fn]
        assert expected, f"{fn}: لا مواضيعَ مُشتقّة — انهار الاستخراج"
        assert set(_allow(users[service], "publish")) == expected, (
            f"{service}: إذنُ النشر ≠ ما تنشره {fn}\n"
            f"  ناقص (يُرفَض صامتاً): {sorted(expected - set(_allow(users[service], 'publish')))}\n"
            f"  زائد: {sorted(set(_allow(users[service], 'publish')) - expected)}"
        )
        assert users[service]["permissions"]["subscribe"] == {"deny": [">"]}


@pytest.mark.unit
def test_the_actuator_subject_is_a_notice_not_a_command_and_nobody_may_consume_it():
    """الأثرُ الفيزيائيّ لا يمرّ بالوسيط — ولا تفتحه هذه الصلاحيّات."""
    subject = "sahool.actuator.dispatch.requested"
    assert _matches("sahool.>", subject) and not _matches(
        "sahool.events.>", subject
    )  # المطابِق نفسُه
    for name, user in _users().items():
        for pattern in _allow(user, "subscribe"):
            assert not _matches(pattern, subject), (
                f"{name} يستطيع الاشتراك في {subject} ({pattern})"
            )
    assert "nats" not in (ROOT / "services" / "actuator-service" / "actuator_runtime.py").read_text(
        encoding="utf-8"
    ).lower().replace("natsu", "")


@pytest.mark.unit
def test_the_relay_subscribes_exactly_to_the_reservation_dispatch_subjects():
    relay = _platform_import("irrigation_dispatch_relay")
    expected = {f"sahool.events.{e}" for e in relay.SUPPORTED_DISPATCH_EVENTS}
    user = _users()["sahool-reservation-dispatch-relay-worker"]
    assert set(_allow(user, "subscribe")) == expected
    assert user["permissions"]["publish"] == {"deny": [">"]}


@pytest.mark.unit
def test_the_learning_worker_may_bind_only_its_own_durables():
    durables = _canonical_durables()
    allowed = set(_allow(_users()["sahool-canonical-execution-learning-worker"], "publish"))
    expected = {"$JS.API.INFO", "$JS.API.STREAM.NAMES"}
    for d in durables:
        expected |= {
            f"$JS.API.CONSUMER.INFO.{STREAM}.{d}",
            f"$JS.API.CONSUMER.DURABLE.CREATE.{STREAM}.{d}",
            f"$JS.ACK.{STREAM}.{d}.>",
        }
    assert allowed == expected, (
        f"ناقص: {sorted(expected - allowed)}\n زائد: {sorted(allowed - expected)}"
    )


@pytest.mark.unit
def test_the_stream_owner_is_scoped_not_stripped():
    """JETSTREAM-STREAM-TOPOLOGY-OWNED-BY-A-CONSUMER-01: وكيلُ الإشعارات ما يزال يُنشئ الدفق —
    باسمه وحدَه، ومستهلكيه التسعة بصيغتيهم، ولا يحذف ولا يُفرِّغ ولا يُعدّل."""
    from shared import notification_consumers

    allowed = set(_allow(_users()[NOTIFICATION], "publish"))
    assert f"$JS.API.STREAM.CREATE.{notification_consumers.STREAM}" in allowed
    assert {s for s in allowed if s.startswith("$JS.API.STREAM.CREATE.")} == {
        f"$JS.API.STREAM.CREATE.{STREAM}"
    }
    legacy = [name for _, name in notification_consumers.SUBSCRIPTIONS]
    for name in legacy:
        assert f"$JS.API.CONSUMER.DURABLE.CREATE.{STREAM}.{name}" in allowed
        assert (
            f"$JS.API.CONSUMER.CREATE.{STREAM}.{notification_consumers.queue_name(name)}" in allowed
        )
    acks = {s for s in allowed if s.startswith("$JS.ACK.")}
    assert acks == {f"$JS.ACK.{STREAM}.{d}.>" for d in _notification_durables()}
    creates = {s for s in allowed if ".CREATE." in s and not s.startswith("$JS.API.STREAM")}
    assert len(creates) == 2 * len(legacy), f"إنشاءُ مستهلكين خارج التسعة: {sorted(creates)}"
    agent = (ROOT / "agents" / "notification" / "agent.py").read_text(encoding="utf-8")
    assert '"sahool.notification.dead_letter"' in agent
    assert "sahool.notification.dead_letter" in allowed
    for _, name in notification_consumers.SUBSCRIPTIONS:
        cfg = notification_consumers.queue_config("x", name, 1, "")
        assert cfg.deliver_subject.startswith("_INBOX.sahool.notification."), (
            "تسليمُ queue_v1 خرج من `_INBOX.` — راجِع صندوقَ الوكيل"
        )


@pytest.mark.unit
def test_publishers_may_publish_only_their_own_subjects():
    users = _users()
    vegetation = INBOX_CLIENTS["sahool-vegetation-analysis"].read_text(encoding="utf-8")
    assert 'f"sahool.tenant.{tenant_id}.satellite.{field_id}.computed"' in vegetation
    assert _allow(users["sahool-vegetation-analysis"], "publish") == [
        "sahool.tenant.*.satellite.*.computed"
    ]
    migration = (ROOT / "migrations" / "v18_entity_ids_text.sql").read_text(encoding="utf-8")
    assert "'sahool.events.' || p_event_type" in migration
    assert _allow(users["sahool-platform"], "publish") == ["sahool.events.>"]
    polygon = INBOX_CLIENTS["sahool-weather-polygon-worker"].read_text(encoding="utf-8")
    assert '"sahool.weather.field.overlay.completed"' in polygon
    assert '"sahool.weather.forecast.updated", durable="polygon-worker"' in polygon
    assert "sahool.weather.field.overlay.completed" in _allow(
        users["sahool-weather-polygon-worker"], "publish"
    )


def _expected() -> dict[str, dict[str, set[str]]]:
    """ما **يحقّ** لكلّ هويّة خارج `$JS` — مُشتقٌّ من الشيفرة لا من nats.conf.

    المِسبارُ الحيّ يُقارِن الوسيطَ بهذا لا بالإعداد نفسِه: مِسبارٌ يشتقّ «الممنوع» من nats.conf
    يُثبِت أنّ الوسيطَ يطيع الملفّ — فإن وُسِّع الملفُّ اتّسع المِسبارُ معه وبقي أخضر (مقيس:
    توسيعُ النبات إلى `sahool.events.>` مرّ على النسخة الأولى من هذا الملفّ).
    """
    from shared.marketplace_ecosystem_phase12 import KNOWN_HOOKS

    literals = _phase_worker_literals()

    def dotted(t: str) -> str:
        return f"sahool.{t.replace('_', '.')}"

    relay = _platform_import("irrigation_dispatch_relay")

    def inbox(name: str) -> set[str]:
        return {f"_INBOX_{name}.>"}

    return {
        "sahool-platform": {"publish": {"sahool.events.>"}, "subscribe": inbox("sahool-platform")},
        "sahool-phase-runtime-outbox-worker": {
            "publish": literals["run_outbox_once"] | {dotted(t) for t in _runtime_event_types()},
            "subscribe": set(),
        },
        "sahool-plugin-runtime-worker": {
            "publish": literals["run_plugin_once"] | {dotted(h) for h in KNOWN_HOOKS},
            "subscribe": set(),
        },
        "sahool-model-registry-worker": {
            "publish": literals["run_model_registry_once"],
            "subscribe": set(),
        },
        "sahool-actuator-dispatch-worker": {
            "publish": literals["run_actuator_once"],
            "subscribe": set(),
        },
        "sahool-reservation-dispatch-relay-worker": {
            "publish": set(),
            "subscribe": {f"sahool.events.{e}" for e in relay.SUPPORTED_DISPATCH_EVENTS},
        },
        "sahool-canonical-execution-learning-worker": {
            "publish": set(),
            "subscribe": inbox("sahool-canonical-execution-learning-worker"),
        },
        NOTIFICATION: {"publish": {"sahool.notification.dead_letter"}, "subscribe": {"_INBOX.>"}},
        "sahool-weather-polygon-worker": {
            "publish": {"sahool.weather.field.overlay.completed"},
            "subscribe": inbox("sahool-weather-polygon-worker"),
        },
        "sahool-vegetation-analysis": {
            "publish": {"sahool.tenant.*.satellite.*.computed"},
            "subscribe": inbox("sahool-vegetation-analysis"),
        },
    }


@pytest.mark.unit
def test_every_non_jetstream_permission_is_what_the_code_needs():
    """خارج `$JS` لا زيادةَ ولا نقصان: كلُّ موضوعٍ في nats.conf مُشتقٌّ من شيفرة صاحبه."""
    expected = _expected()
    assert sorted(expected) == sorted(_users())
    for name, user in _users().items():
        for direction in ("publish", "subscribe"):
            actual = {s for s in _allow(user, direction) if not s.startswith("$")}
            assert actual == expected[name][direction], (
                f"{name} {direction}: زائد {sorted(actual - expected[name][direction])} · "
                f"ناقص {sorted(expected[name][direction] - actual)}"
            )


# ══ ② الإثباتُ الحيّ ═════════════════════════════════════════════════════════


def _server_binary() -> str | None:
    return (
        os.getenv("NATS_SERVER_BIN")
        or os.getenv("NOTIFICATION_TEST_NATS_SERVER")
        or shutil.which("nats-server")
    )


def _require_live():
    if not _server_binary() or not shutil.which("openssl"):
        if os.getenv("NATS_LEAST_PRIVILEGE_LIVE_REQUIRED") == "1":
            pytest.fail(
                "NATS_LEAST_PRIVILEGE_LIVE_REQUIRED=1 ولا nats-server/openssl — الإثباتُ الحيّ لم يقع"
            )
        pytest.skip(
            "LIVE PROOF SKIPPED: لا nats-server (NATS_SERVER_BIN/NOTIFICATION_TEST_NATS_SERVER) — "
            "العقدُ الساكن وحدَه قِيس في هذا التشغيل"
        )


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class _Broker:
    def __init__(self, tmp: Path, override: dict[str, str] | None = None):
        self.tmp = tmp
        # حرفٌ ثمّ hex — الصيغةُ التي يوصي بها .env.example: قيمةٌ تبدأ برقمٍ قد يُعرِبها الوسيطُ
        # عدداً (`3e0f…`) فيرفض الإقلاع. المقيسُ في test_a_password_that_looks_like_a_number….
        self.passwords = {
            str(u["password"])[1:]: "n" + secrets.token_hex(16) for u in _users().values()
        }
        self.passwords.update(override or {})
        self.by_user = {
            name: self.passwords[str(u["password"])[1:]] for name, u in _users().items()
        }
        tls = tmp / "tls"
        tls.mkdir()
        gen = subprocess.run(
            [shutil.which("sh") or "/bin/sh", str(TLS_SCRIPT)],
            env={**os.environ, "NATS_TLS_DIR": str(tls), "SAHOOL_ENV": "development"},
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        assert gen.returncode == 0, gen.stderr
        self.ca_dir = tls / "ca"
        conf = (
            CONF.read_text(encoding="utf-8")
            .replace('"/etc/nats/tls/', f'"{tls}/server/')
            .replace('"/data/jetstream"', f'"{tmp / "js"}"')
        )
        # بلا كتلة tls يُقلِع الوسيطُ نصّاً — فلا يُحجَب الإقلاع هنا: الشواهدُ أدناه هي التي تحمرّ.
        assert conf.count(str(tls)) == (2 if "\ntls {" in conf else 0), (
            "مسارا الشهادة في nats.conf تغيّرا — حدِّث البديلَ هنا"
        )
        (tmp / "nats.conf").write_text(conf, encoding="utf-8")
        self.port, self.monitor = _free_port(), _free_port()
        self.log = tmp / "nats.log"
        self.proc = subprocess.Popen(
            [
                _server_binary(),
                "-c",
                str(tmp / "nats.conf"),
                "-a",
                "127.0.0.1",
                "-p",
                str(self.port),
                "-m",
                str(self.monitor),
            ],
            env={**os.environ, **self.passwords},
            stdout=self.log.open("w", encoding="utf-8"),
            stderr=subprocess.STDOUT,
        )

    def url(self, user: str, password: str | None = None) -> str:
        return f"tls://{user}:{password or self.by_user[user]}@localhost:{self.port}"

    def log_text(self) -> str:
        return self.log.read_text(encoding="utf-8", errors="replace")


@pytest.fixture
async def broker(tmp_path, monkeypatch):
    _require_live()
    b = _Broker(tmp_path)
    # الآليّةُ نفسُها التي تُسلِّمها compose للعملاء: CA الوسيط مُضافاً إلى مخزن النظام.
    monkeypatch.setenv("SSL_CERT_DIR", f"{b.ca_dir}:/etc/ssl/certs")
    try:
        for _ in range(200):
            if b.proc.poll() is not None:
                pytest.fail(b.log_text())
            if "Server is ready" in b.log_text():
                break
            await asyncio.sleep(0.02)
        else:
            pytest.fail(b.log_text())
        yield b
    finally:
        b.proc.terminate()
        await asyncio.to_thread(b.proc.wait, 5)


class _Client:
    """اتّصالٌ يجمع رفضَ الصلاحيّات الذي يُرسله الوسيطُ (`-ERR Permissions Violation`)."""

    def __init__(self):
        self.violations: list[str] = []

    async def err(self, e):
        text = str(e).lower()
        if "permissions violation" in text:
            self.violations.append(text)

    def denied(self, subject: str) -> bool:
        return any(f'"{subject.lower()}"' in v for v in self.violations)


async def _connect(broker: _Broker, user: str, **kw):
    import nats

    client = _Client()
    nc = await nats.connect(
        broker.url(user), error_cb=client.err, max_reconnect_attempts=0, connect_timeout=3, **kw
    )
    return nc, client


def _inbox(user: str) -> dict:
    return {} if user == NOTIFICATION else {"inbox_prefix": f"_INBOX_{user}"}


def _concrete(subject: str) -> str:
    return subject.replace("*", "t1").replace(">", "probe")


@pytest.mark.integration
async def test_live_unauthenticated_and_wrong_password_are_refused(broker):
    import nats

    for url in (f"tls://localhost:{broker.port}", broker.url("sahool-platform", "wrong")):
        with pytest.raises(Exception, match="(?i)authorization violation"):
            await nats.connect(
                url, max_reconnect_attempts=0, allow_reconnect=False, connect_timeout=3
            )
    nc, _ = await _connect(broker, "sahool-platform", **_inbox("sahool-platform"))
    await nc.close()
    # هويّةٌ صحيحة بكلمة مرورِ هويّةٍ أخرى: الاعتمادُ لا يُنقَل بين الخدمات.
    with pytest.raises(Exception, match="(?i)authorization violation"):
        await nats.connect(
            broker.url("sahool-platform", broker.by_user["sahool-vegetation-analysis"]),
            max_reconnect_attempts=0,
            allow_reconnect=False,
            connect_timeout=3,
        )


@pytest.mark.integration
async def test_live_plaintext_is_refused_before_any_credential_is_accepted(broker):
    reader, writer = await asyncio.open_connection("127.0.0.1", broker.port)
    info = json.loads((await reader.readline()).decode().split(" ", 1)[1])
    assert info.get("tls_required") is True, info
    creds = {"user": "sahool-platform", "pass": broker.by_user["sahool-platform"]}
    # `verbose: true` ⇒ اتّصالٌ مقبولٌ يُجيب `+OK` ثمّ `PONG`. المقيسُ (2.14.6 و2.15.0): الوسيطُ
    # يُغلِق المقبسَ فوراً بلا ردٍّ — ينتظر مصافحةَ TLS فيقرأ `CONNECT` بايتاتٍ غيرَ صالحة.
    writer.write(f"CONNECT {json.dumps({**creds, 'verbose': True})}\r\nPING\r\n".encode())
    await writer.drain()
    reply = await asyncio.wait_for(reader.read(512), 5)
    writer.close()
    assert reply == b"", f"الوسيطُ ردّ على اتّصالٍ نصّيّ: {reply!r}"
    assert '"$G/user:sahool-platform"' not in broker.log_text(), "الاعتمادُ النصّيّ قُبِل هويّةً"


@pytest.mark.integration
async def test_live_a_client_that_does_not_trust_the_broker_ca_refuses_to_connect(
    broker, monkeypatch, tmp_path
):
    """التحقّقُ **غيرُ مُتخطّى**: بلا CA الوسيط في الثقة يرفض العميلُ الشهادةَ نفسَها."""
    import nats

    empty = tmp_path / "empty-trust"
    empty.mkdir()
    monkeypatch.setenv("SSL_CERT_DIR", str(empty))
    with pytest.raises(ssl.SSLCertVerificationError):
        await nats.connect(
            broker.url("sahool-platform"),
            max_reconnect_attempts=0,
            allow_reconnect=False,
            connect_timeout=3,
        )
    monkeypatch.setenv("SSL_CERT_DIR", f"{empty}:{broker.ca_dir}")  # قائمةٌ مضافة: الثاني يكفي
    nc, _ = await _connect(broker, "sahool-platform", **_inbox("sahool-platform"))
    await nc.close()
    with pytest.raises(ssl.SSLCertVerificationError):  # والاسمُ مفحوص لا الشهادةُ وحدها
        await nats.connect(
            broker.url("sahool-platform"),
            tls_hostname="impostor.example",
            max_reconnect_attempts=0,
            allow_reconnect=False,
            connect_timeout=3,
        )


def _pub_probes() -> tuple[dict[str, set[str]], dict[str, set[str]]]:
    """الموجبُ: ما يحقّ لكلّ هويّة (من الشيفرة). السالبُ: ما يحقّ لغيرها وما ليس لأحد."""
    expected = _expected()
    own = {n: {_concrete(s) for s in e["publish"]} for n, e in expected.items()}
    everyone = set().union(*own.values()) | {
        "sahool.events.forged",
        "sahool.anything",
        "other.subject",
    }
    return {n: everyone - own[n] for n in expected}, own


@pytest.mark.integration
async def test_live_each_identity_publishes_its_own_subjects_and_is_refused_everyone_elses(broker):
    forbidden, own = _pub_probes()
    expected = _expected()

    def rightful(user: str, subject: str) -> bool:
        return any(_matches(p, subject) for p in expected[user]["publish"])

    for user in _users():
        nc, client = await _connect(broker, user, **_inbox(user))
        try:
            for subject in sorted(own[user]):
                await nc.publish(subject, b"{}")
            probes = sorted(s for s in forbidden[user] if not rightful(user, s))
            for subject in probes:
                await nc.publish(subject, b"forged")
            await nc.flush(timeout=3)
            await asyncio.sleep(0.2)
            leaked = [s for s in own[user] if client.denied(s)]
            assert not leaked, f"{user}: رُفِض ما هو له: {leaked}"
            accepted = [s for s in probes if not client.denied(s)]
            assert not accepted, f"{user}: نُشِر ما ليس له: {accepted}"
        finally:
            await nc.close()


@pytest.mark.integration
async def test_live_subscriptions_are_confined_and_inboxes_are_private(broker):
    users = _users()
    expected = _expected()
    for user in users:
        nc, client = await _connect(broker, user, **_inbox(user))
        try:
            mine = sorted(expected[user]["subscribe"])
            others_inboxes = [f"_INBOX_{o}.>" for o in users if o != user]
            probes = [">", "sahool.>", "sahool.events.>", *others_inboxes]
            if user != NOTIFICATION:
                probes.append("_INBOX.>")
            probes = [p for p in probes if p not in mine]
            for subject in [*mine, *probes]:
                await nc.subscribe(subject)
            await nc.flush(timeout=3)
            await asyncio.sleep(0.2)
            assert not [s for s in mine if client.denied(s)], f"{user}: رُفِض اشتراكٌ هو له"
            assert all(client.denied(p) for p in probes), (
                f"{user}: قُبِل اشتراكٌ ليس له: {[p for p in probes if not client.denied(p)]}"
            )
        finally:
            await nc.close()


@pytest.mark.integration
async def test_live_jetstream_path_works_end_to_end_with_the_real_client_code(broker):
    """الدفقُ يُنشئه مالكُه، والناشرُ المُقِرّ يأخذ PubAck، والمستهلكون الحقيقيّون يستلمون ويُقِرّون."""
    from nats.js.api import ConsumerConfig, StreamConfig

    from shared import notification_consumers
    from shared.broker_url import make_jetstream_publisher

    agent, agent_client = await _connect(broker, NOTIFICATION)
    platform, platform_client = await _connect(
        broker, "sahool-platform", **_inbox("sahool-platform")
    )
    worker_nc, worker_client = await _connect(
        broker,
        "sahool-canonical-execution-learning-worker",
        **_inbox("sahool-canonical-execution-learning-worker"),
    )
    try:
        js = agent.jetstream()
        # كما يفعل `_ensure_subscriptions` في وضع legacy: الدفقُ ثمّ المستهلكون التسعة.
        await js.add_stream(StreamConfig(name=STREAM, subjects=["sahool.>"]))
        subs = {}
        for subject, durable in notification_consumers.SUBSCRIPTIONS:
            subs[durable] = await js.subscribe(
                subject,
                durable=durable,
                manual_ack=True,
                config=ConsumerConfig(ack_wait=120, max_deliver=-1),
            )
        # عاملُ التعلّم بدالّته الحقيقيّة.
        worker = _canonical_worker()
        received: asyncio.Queue = asyncio.Queue()

        async def on_message(msg):
            await msg.ack()
            await received.put(msg.subject)

        bound = await worker.subscribe_subjects(
            worker_nc.jetstream(), durable_base=_canonical_base(), callback=on_message
        )
        assert sorted(bound.values()) == sorted(_canonical_durables())
        # الناشرُ المُقِرّ للمنصّة بعينه (make_jetstream_publisher) ⇒ PubAck وإلّا يرفع.
        publish = make_jetstream_publisher(platform)
        await publish("sahool.events.irrigation.execution.completed", b'{"tenant_id": "t1"}')
        assert (
            await asyncio.wait_for(received.get(), 5)
            == "sahool.events.irrigation.execution.completed"
        )
        msg = await subs["notif_domain_events"].next_msg(timeout=5)
        await msg.ack_sync()
        await js.publish("sahool.notification.dead_letter", b"{}")  # الرسالةُ الميتة
        info = await js.consumer_info(STREAM, "notif_domain_events")
        assert info.ack_floor.stream_seq >= 1, "الإقرارُ لم يبلغ الوسيط"
        for client in (agent_client, platform_client, worker_client):
            assert not client.violations, client.violations
        # النبات: PubAck على موضوعه.
        veg, veg_client = await _connect(
            broker, "sahool-vegetation-analysis", **_inbox("sahool-vegetation-analysis")
        )
        ack = await veg.jetstream().publish("sahool.tenant.t1.satellite.f1.computed", b"{}")
        assert ack.seq > 0 and not veg_client.violations
        await veg.close()
    finally:
        for nc in (agent, platform, worker_nc):
            await nc.close()


@pytest.mark.integration
async def test_live_learning_worker_takes_over_durables_created_before_identities(broker):
    """الترقيةُ على مخزنٍ محفوظ: مستهلكو العامل أُنشئوا بتسليمٍ إلى ``_INBOX.<nuid>``.

    **مقيس:** بلا النقل يعود ``js.subscribe`` بلا استثناء، والوسيطُ يسجّل Subscription Violation،
    والعاملُ خاملٌ وفحصُ صحّته أخضر. ``retarget_foreign_deliveries`` ينقل التسليمَ إلى صندوقه
    **ويحفظ أرضيّةَ الإقرار** — ثمّ يستلم العاملُ الجديد."""
    from nats.js.api import ConsumerConfig, StreamConfig

    worker = _canonical_worker()
    user = "sahool-canonical-execution-learning-worker"
    agent, _ = await _connect(broker, NOTIFICATION)
    await agent.jetstream().add_stream(StreamConfig(name=STREAM, subjects=["sahool.>"]))
    platform, _ = await _connect(broker, "sahool-platform", **_inbox("sahool-platform"))
    nc, client = await _connect(broker, user, **_inbox(user))
    try:
        js = nc.jetstream()
        for subject in worker.SUBJECTS:  # كما أنشأها مكدّسُ ما قبل الهويّات
            await js.add_consumer(
                STREAM,
                config=ConsumerConfig(
                    durable_name=worker.durable_for_subject(_canonical_base(), subject),
                    deliver_subject=f"_INBOX.legacy{abs(hash(subject)) % 10_000}",
                    filter_subject=subject,
                    ack_policy="explicit",
                ),
            )
        subject = worker.SUBJECTS[1]
        durable = worker.durable_for_subject(_canonical_base(), subject)
        await platform.jetstream().publish(subject, b"{}")
        moved = await worker.retarget_foreign_deliveries(nc, js, durable_base=_canonical_base())
        assert sorted(moved) == sorted(_canonical_durables())
        info = await js.consumer_info(STREAM, durable)
        assert info.config.deliver_subject.startswith(f"_INBOX_{user}.")
        assert (
            await worker.retarget_foreign_deliveries(nc, js, durable_base=_canonical_base()) == []
        )
        got: asyncio.Queue = asyncio.Queue()

        async def on_message(msg):
            await msg.ack()
            await got.put(msg.subject)

        await worker.subscribe_subjects(js, durable_base=_canonical_base(), callback=on_message)
        assert await asyncio.wait_for(got.get(), 5) == subject, "لم يُسلَّم ما نُشِر قبل النقل"
        await nc.flush()
        await asyncio.sleep(0.2)
        assert not client.violations, client.violations
    finally:
        for c in (agent, platform, nc):
            await c.close()


@pytest.mark.integration
async def test_live_nobody_can_destroy_or_read_around_the_stream(broker):
    """المالكُ لا يحذف ولا يُفرِّغ، وغيرُ المالك لا يُنشئ مستهلكاً يقرأ الدفقَ من حوله."""
    from nats.js.api import StreamConfig

    agent, agent_client = await _connect(broker, NOTIFICATION)
    js = agent.jetstream()
    await js.add_stream(StreamConfig(name=STREAM, subjects=["sahool.>"]))
    try:
        for attempt in (
            js.delete_stream(STREAM),
            js.purge_stream(STREAM),
            js.update_stream(StreamConfig(name=STREAM, subjects=[">"])),
        ):
            with pytest.raises(Exception):  # noqa: B017 — طلبٌ مرفوضٌ يعود مهلةً لا ردّاً
                await asyncio.wait_for(attempt, 3)
        assert agent_client.denied(f"$JS.API.STREAM.DELETE.{STREAM}")
        assert agent_client.denied(f"$JS.API.STREAM.PURGE.{STREAM}")
        assert (await js.stream_info(STREAM)).config.subjects == ["sahool.>"]
        for user in ("sahool-vegetation-analysis", "sahool-canonical-execution-learning-worker"):
            nc, client = await _connect(broker, user, **_inbox(user))
            try:
                with pytest.raises(Exception):  # noqa: B017
                    await nc.jetstream().add_consumer(
                        STREAM,
                        durable_name="eavesdrop",
                        deliver_subject=f"_INBOX_{user}.x",
                        timeout=2,
                    )
                assert client.denied(f"$JS.API.CONSUMER.DURABLE.CREATE.{STREAM}.eavesdrop")
            finally:
                await nc.close()
    finally:
        await agent.close()


@pytest.mark.integration
async def test_live_frozen_phase_worker_publishes_its_subject_and_a_refusal_is_silent(
    broker, monkeypatch
):
    """``_publish_nats`` الحقيقيّ (مجمَّدٌ خلف GATE-01): موضوعُه يُخزَّن، وموضوعُ غيره يُرفَض
    **دون استثناء** — حدٌّ مُعلَنٌ يجعل مطابقةَ القائمة للشيفرة (العقدُ الساكن) شرطاً لا زينة."""
    from nats.js.api import StreamConfig

    workers = _platform_import("api.phase_runtime_workers")
    agent, _ = await _connect(broker, NOTIFICATION)
    js = agent.jetstream()
    await js.add_stream(StreamConfig(name=STREAM, subjects=["sahool.>"]))
    try:
        monkeypatch.setenv("NATS_URL", broker.url("sahool-actuator-dispatch-worker"))
        await workers._publish_nats("sahool.actuator.dispatch.requested", {"command_id": "c1"})
        assert (await js.stream_info(STREAM)).state.messages == 1
        await workers._publish_nats("sahool.events.forged", {"event_id": "x"})  # لا يرفع
        assert (await js.stream_info(STREAM)).state.messages == 1, "الموضوعُ الممنوع خُزِّن"
        assert 'Publish Violation - Subject "sahool.events.forged"' in broker.log_text()
    finally:
        await agent.close()


@pytest.mark.integration
async def test_live_queue_v1_provisioning_and_binding_work_under_the_scoped_identity(broker):
    """مسارُ ``queue_v1``: خطوةُ المشغِّل (``build_plan``/``apply_plan``) بهويّة الوكيل، ثمّ الربط."""
    from nats.js.api import ConsumerConfig, StreamConfig

    from shared import notification_consumers as consumers

    agent, client = await _connect(broker, NOTIFICATION)
    try:
        v = agent.connected_server_version
        if (v.major, v.minor) < (2, 15):
            pytest.skip(
                f"apply_plan يشترط nats-server ≥ 2.15 (هذا {v.major}.{v.minor}) — قِس بـ2.15"
            )
        if "allow_msg_ttl" not in getattr(StreamConfig, "__dataclass_fields__", {}):
            pytest.skip("validate_stream يشترط nats-py ≥ 2.16 (تثبيتُ الوكيل) — هذا العميلُ أقدم")
        js = agent.jetstream()
        await js.add_stream(StreamConfig(name=STREAM, subjects=["sahool.>"]))
        for subject, durable in consumers.SUBSCRIPTIONS:
            await js.subscribe(
                subject,
                durable=durable,
                manual_ack=True,
                config=ConsumerConfig(ack_wait=120, max_deliver=-1),
            )
        plan = await consumers.build_plan(js)
        names = await consumers.apply_plan(agent, plan)
        subject, legacy = (
            dict((d, s) for s, d in consumers.SUBSCRIPTIONS)["notif_domain_events"],
            "notif_domain_events",
        )
        info = await js.consumer_info(STREAM, consumers.queue_name(legacy))
        consumers.validate_queue(info.config, subject, legacy)
        sub = await js.subscribe_bind(
            stream=STREAM,
            consumer=consumers.queue_name(legacy),
            config=info.config,
            manual_ack=True,
        )
        # الناشرُ هو صاحبُ الموضوع (المنصّة) — الوكيلُ لا ينشر أحداثَ النطاق، ورفضُه مقيسٌ أعلاه.
        platform, _ = await _connect(broker, "sahool-platform", **_inbox("sahool-platform"))
        await platform.jetstream().publish("sahool.events.task.assigned", b'{"x": 1}')
        await platform.close()
        msg = await sub.next_msg(timeout=5)
        await msg.ack_sync()
        assert len(names) == len(consumers.SUBSCRIPTIONS) and not client.violations, (
            client.violations
        )
    finally:
        with contextlib.suppress(Exception):
            await agent.close()


@pytest.mark.integration
async def test_live_a_password_that_looks_like_a_number_stops_the_broker_loudly(tmp_path):
    """عطلٌ **سابقٌ لهذا التغيير** قِيس عرضاً: الوسيطُ يُعرِب قيمةَ متغيّر البيئة بمُعرِب الإعداد.

    فكلمةُ مرورٍ hex تبدأ بـ``3e0`` تُقرأ عدداً عشريّاً ويرفض الإقلاع — كان ذلك قائماً مع
    ``$NATS_PASSWORD`` الواحد أيضاً. الفشلُ **صاخبٌ ومُسمّى** (لا قبولٌ صامت)، وعلاجُه في
    ``.env.example``: حرفٌ ثمّ hex. وهذا الشاهدُ يُثبِت أنّه ما يزال صاخباً."""
    _require_live()
    b = _Broker(tmp_path, override={"NATS_VEGETATION_PASSWORD": "3e0f9c2b7a"})
    rc = await asyncio.to_thread(b.proc.wait, 10)
    assert rc != 0, "الوسيطُ أقلع بكلمة مرورٍ أعربها عدداً"
    assert "NATS_VEGETATION_PASSWORD" in b.log_text() and "could not be parsed" in b.log_text()


@pytest.mark.integration
async def test_live_monitoring_shows_tls_and_the_authenticated_identity(broker):
    nc, _ = await _connect(broker, "sahool-platform", **_inbox("sahool-platform"))
    try:
        body = await asyncio.to_thread(
            lambda: urllib.request.urlopen(
                f"http://127.0.0.1:{broker.monitor}/connz?auth=1", timeout=3
            ).read()
        )
        conns = json.loads(body)["connections"]
        assert conns and all(c.get("tls_version") for c in conns), conns
        assert {c.get("authorized_user") for c in conns} == {"sahool-platform"}
    finally:
        await nc.close()
