"""حارس صحّة Redis في ملفّات compose — يمنع تكرار عطل «redis unhealthy».

الجذر الذي ظهر تشغيليّاً: docker-compose.fixed.yml كتب redis.conf إلى
/usr/local/etc/redis/ — وهو مجلّد **لا تُنشئه** صورة redis:7-alpine، فتفشل الكتابة
("No such file or directory")، فينكسر سلسلة `&&` فلا يبدأ redis ⇒ unhealthy ⇒ تتالي
فشل المعتمدين (postgres/nats/الخدمات). unified/light كانا سليمَين (--requirepass).

هذا الحارس (بوّابة CI) يفحص **كلّ** ملفّ compose يُعرّف Redis:
  1. لا يكتب إعداداً إلى /usr/local/etc/redis/ (المجلّد المفقود).
  2. يستعمل requirepass (سطر أمر أو إعداد بمسار موجود) أو ACL (``--user``) بمستخدمٍ ``default``
     معطَّل وكلُّ مستخدمٍ مفعَّل بكلمة سرّ — لا redis مكشوف.
  3. فحص الصحّة يُصادِق (redis-cli -a) — لا NOAUTH.
"""

from __future__ import annotations

import glob
import os
import shlex

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.security]

yaml = pytest.importorskip("yaml")

ROOT = os.path.join(os.path.dirname(__file__), "..")
_BROKEN_DIR = "/usr/local/etc/redis/"


def _compose_files():
    return sorted(glob.glob(os.path.join(ROOT, "docker-compose*.yml")))


def _redis_services(doc):
    """يُرجِع (اسم, تعريف) لكلّ خدمة صورتها redis."""
    for name, svc in (doc.get("services") or {}).items():
        if isinstance(svc, dict) and "redis" in str(svc.get("image", "")).lower():
            yield name, svc


def _cmd_text(svc) -> str:
    c = svc.get("command", "")
    return " ".join(c) if isinstance(c, list) else str(c)


def _healthcheck_text(svc) -> str:
    hc = svc.get("healthcheck", {}) or {}
    t = hc.get("test", "")
    return " ".join(t) if isinstance(t, list) else str(t)


def _cases():
    out = []
    for f in _compose_files():
        with open(f, encoding="utf-8") as fh:
            doc = yaml.safe_load(fh)
        if not isinstance(doc, dict):
            continue
        for name, svc in _redis_services(doc):
            out.append((os.path.basename(f), name, svc))
    return out


def test_redis_services_found():
    cases = _cases()
    assert cases, "لم يُكتشَف أيّ خدمة Redis في ملفّات compose — التحليل مكسور"


@pytest.mark.parametrize("fname,svc_name,svc", _cases())
def test_redis_not_writing_to_missing_dir(fname, svc_name, svc):
    """لا كتابة إعداد إلى /usr/local/etc/redis/ (مجلّد لا تُنشئه الصورة ⇒ فشل البدء)."""
    cmd = _cmd_text(svc)
    assert _BROKEN_DIR not in cmd, (
        f"{fname}:{svc_name} يكتب إعداد redis إلى {_BROKEN_DIR} (مجلّد مفقود في redis:alpine) "
        "⇒ يفشل البدء فيصير unhealthy. استعمل redis-server --requirepass، أو مساراً موجوداً (/tmp)."
    )


# Redis مُجمَّع داخليّ تابع لـERPNext (cache/queue): بلا كلمة مرور بحكم عُرف ERPNext
# (شبكة داخليّة فقط، غير مكشوف؛ فرض كلمة مرور يتطلّب إعادة ضبط روابط redis في ERPNext —
# خارج نطاق إصلاح بدء redis). يبقى فحص المجلّد المفقود مُطبَّقاً عليه (الجذر الفعليّ).
_INTERNAL_NOAUTH_OK = {"erpnext-redis-cache", "erpnext-redis-queue"}


def _acl_users(svc) -> dict[str, list[str]]:
    """``--user <name> <rules…>`` في سطر الأمر ⇒ {الاسم: القواعد} (REDIS-SHARED-PASSWORD-NO-ACL-01)."""
    c = svc.get("command", "")
    argv = [str(a) for a in c] if isinstance(c, list) else shlex.split(str(c))
    users: dict[str, list[str]] = {}
    current: list[str] | None = None
    for arg in argv:
        if arg.startswith("--"):
            current = None
            if arg == "--user":
                current = []
            continue
        if current is not None:
            if not current:
                users[arg] = current
            current.append(arg)
    return {name: rules[1:] for name, rules in users.items()}


def _acl_enforces_authentication(svc) -> bool:
    """ACL بديلٌ عن requirepass **بشرطين معاً**: ``default`` معطَّل صراحةً (``off``)، وكلُّ مستخدمٍ
    مفعَّل (``on``) يحمل كلمةَ سرّ (``>…``) ولا ``nopass``. أيُّهما ناقصٌ ⇒ Redis مكشوف."""
    users = _acl_users(svc)
    if "off" not in users.get("default", []):
        return False
    enabled = [rules for rules in users.values() if "on" in rules]
    return bool(enabled) and all(
        "nopass" not in rules and any(r.startswith(">") and len(r) > 1 for r in rules)
        for rules in enabled
    )


@pytest.mark.parametrize("fname,svc_name,svc", _cases())
def test_redis_requires_password(fname, svc_name, svc):
    """Redis لا يعمل مكشوفاً: requirepass عبر سطر الأمر أو إعداد بمسار موجود، أو ACL بلا ``default``."""
    if svc_name in _INTERNAL_NOAUTH_OK:
        pytest.skip(f"{svc_name}: redis داخليّ لـERPNext (بلا مصادقة بحكم العُرف)")
    cmd = _cmd_text(svc)
    writes_conf_to_valid_path = "requirepass" in cmd and _BROKEN_DIR not in cmd
    assert (
        "--requirepass" in cmd or writes_conf_to_valid_path or _acl_enforces_authentication(svc)
    ), f"{fname}:{svc_name} لا يفرض كلمة مرور Redis (requirepass/ACL) — Redis مكشوف."


def test_acl_branch_rejects_an_enabled_default_or_a_passwordless_user():
    """الفرعُ الجديد لا يفتح ثغرة: ``default on`` أو مستخدمٌ ``nopass`` ⇒ مكشوف."""
    ok = {"command": "redis-server --user default off --user a on >pw ~k:* +get"}
    assert _acl_enforces_authentication(ok)
    for bad in (
        "redis-server --user default on >pw --user a on >pw ~k:* +get",
        "redis-server --user a on >pw ~k:* +get",
        "redis-server --user default off --user a on nopass ~k:* +get",
        "redis-server --user default off --user a on ~k:* +get",
    ):
        assert not _acl_enforces_authentication({"command": bad}), bad


@pytest.mark.parametrize("fname,svc_name,svc", _cases())
def test_redis_healthcheck_authenticates(fname, svc_name, svc):
    """فحص الصحّة يُصادِق (-a/--requirepass) وإلّا NOAUTH ⇒ unhealthy دائماً."""
    hc = _healthcheck_text(svc)
    if not hc:
        return  # لا فحص صحّة ⇒ خارج النطاق
    assert "-a" in hc or "requirepass" in hc, (
        f"{fname}:{svc_name} فحص صحّة Redis بلا مصادقة (-a) ⇒ NOAUTH ⇒ unhealthy."
    )
