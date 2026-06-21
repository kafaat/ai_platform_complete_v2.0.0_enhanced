"""حارس فصل قاعدة Odoo في ملفّات compose — يمنع تكرار عطل «Odoo على قاعدة المنصّة».

الجذر الذي ظهر تشغيليّاً (حاوية sahool-odoo): Odoo كان مُوجَّهاً إلى قاعدة المنصّة
`sahool` (DB_NAME/ODOO_DB يُطمَس إلى «sahool») وبلا أمر يُهيّئ قاعدته، فيبحث عن جداول
Odoo الأساسيّة في قاعدة لا تحويها ⇒ `relation "ir_module_module" does not exist` /
`KeyError: 'ir.http'`. كذلك خلط Odoo بقاعدة RLS للمنصّة خطر عزل.

الحلّ المعتمد (docker-compose.v9.yml ثمّ fixed.yml): قاعدة Odoo منفصلة (sahool_erp)
+ تهيئة base أوّل تشغيل (`-i base`) + `--db-filter` يحصر Odoo على قاعدته.

هذا الحارس (بوّابة CI) يفحص كلّ ملفّ compose:
  1. لا خدمة Odoo (image: odoo) تُوجَّه قاعدتها إلى المنصّة «sahool».
  2. لا متغيّر ODOO_DB (في أيّ خدمة، كالجسر) يُطمَس إلى «sahool».
  3. خدمة صورة Odoo تُهيّئ base (أمر فيه `-i base`) وإلّا تفشل بلا جداول.
"""

from __future__ import annotations

import glob
import os
import re

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.security]

yaml = pytest.importorskip("yaml")

ROOT = os.path.join(os.path.dirname(__file__), "..")
_PLATFORM_DB = "sahool"  # قاعدة المنصّة (RLS) — يجب ألّا تكون قاعدة Odoo.


def _compose_files():
    return sorted(glob.glob(os.path.join(ROOT, "docker-compose*.yml")))


def _docs():
    for f in _compose_files():
        with open(f, encoding="utf-8") as fh:
            doc = yaml.safe_load(fh)
        if isinstance(doc, dict):
            yield os.path.basename(f), doc


def _odoo_image_services():
    """(ملف, اسم, تعريف) لكلّ خدمة صورتها odoo (خادم ERP، لا الجسر المبنيّ محليّاً)."""
    out = []
    for fname, doc in _docs():
        for name, svc in (doc.get("services") or {}).items():
            if isinstance(svc, dict) and "odoo" in str(svc.get("image", "")).lower():
                out.append((fname, name, svc))
    return out


def _resolves_to_platform_db(value: str) -> bool:
    """هل قيمة متغيّر بيئة تُطمَس (default) إلى قاعدة المنصّة «sahool» بالضبط؟

    تمسك `sahool` و`${ODOO_DB:-sahool}` لكن **لا** تمسك `sahool_erp` أو
    `${ODOO_DB:-sahool_erp}` (قاعدة منفصلة مشروعة).
    """
    v = str(value).strip()
    # القيمة الحرفيّة المجرّدة «sahool».
    if v == _PLATFORM_DB:
        return True
    # افتراضي داخل ${VAR:-default} يساوي «sahool» بالضبط.
    m = re.search(r"\$\{[^:}]+:-([^}]*)\}", v)
    if m and m.group(1).strip() == _PLATFORM_DB:
        return True
    return False


def test_odoo_image_services_found():
    assert _odoo_image_services(), "لم تُكتشَف خدمة Odoo (image: odoo) — التحليل مكسور"


@pytest.mark.parametrize("fname,svc_name,svc", _odoo_image_services())
def test_odoo_db_not_platform_db(fname, svc_name, svc):
    """قاعدة Odoo (DB_NAME) منفصلة عن قاعدة المنصّة «sahool» (عزل + تهيئة صحيحة)."""
    env = svc.get("environment", {}) or {}
    # environment قد تكون قائمة "K=V" أو قاموساً.
    if isinstance(env, list):
        env = dict(e.split("=", 1) for e in env if isinstance(e, str) and "=" in e)
    for key in ("DB_NAME", "ODOO_DB"):
        if key in env:
            assert not _resolves_to_platform_db(env[key]), (
                f"{fname}:{svc_name} يُوجِّه {key} إلى قاعدة المنصّة «{_PLATFORM_DB}» "
                f"(={env[key]}) ⇒ ir_module_module مفقود / خلط بقاعدة RLS. استعمل قاعدة منفصلة."
            )


def _init_script_inits_base(cmd: str) -> bool:
    """هل الأمر يستدعي entrypoint تهيئة (odoo-init.sh) يُثبّت base داخله؟

    التهيئة الذاتيّة‑التعافي نقلت `-i base` من أمر compose إلى السكربت (يُنشئ/يُهيّئ
    القاعدة عند الحاجة فقط). نتبع المرجع إلى scripts/ ونتحقّق أنّ base يُثبَّت فيه.
    """
    m = re.search(r"([\w./-]*odoo-init\.sh)", cmd)
    if not m:
        return False
    script = os.path.join(ROOT, "scripts", os.path.basename(m.group(1)))
    if not os.path.exists(script):
        return False
    with open(script, encoding="utf-8") as fh:
        body = fh.read()
    return "-i base" in body or "--init base" in body


@pytest.mark.parametrize("fname,svc_name,svc", _odoo_image_services())
def test_odoo_initializes_base(fname, svc_name, svc):
    """خدمة Odoo تُهيّئ base أوّل تشغيل وإلّا فلا جداول ⇒ فشل دائم.

    يُقبَل أحد مسارين: `-i base` مباشرةً في أمر compose، أو استدعاء entrypoint
    ذاتيّ‑التعافي (odoo-init.sh) يُثبّت base داخله (المسار المعتمد حاليّاً)."""
    cmd = svc.get("command", "")
    cmd = " ".join(cmd) if isinstance(cmd, list) else str(cmd)
    assert "-i base" in cmd or "--init base" in cmd or _init_script_inits_base(cmd), (
        f"{fname}:{svc_name} بلا تهيئة Odoo (`-i base` مباشرةً ولا عبر odoo-init.sh) ⇒ "
        'entrypoint الافتراضي لا يُثبّت base ⇒ relation "ir_module_module" does not exist.'
    )


def test_no_service_odoo_db_env_points_to_platform():
    """أيّ خدمة (كالجسر) تُعرّف ODOO_DB يجب ألّا تطمسه إلى قاعدة المنصّة «sahool»."""
    offenders = []
    for fname, doc in _docs():
        for name, svc in (doc.get("services") or {}).items():
            if not isinstance(svc, dict):
                continue
            env = svc.get("environment", {}) or {}
            if isinstance(env, list):
                env = dict(e.split("=", 1) for e in env if isinstance(e, str) and "=" in e)
            val = env.get("ODOO_DB")
            if val is not None and _resolves_to_platform_db(val):
                offenders.append(f"{fname}:{name} (ODOO_DB={val})")
    assert not offenders, "خدمات تُوجِّه ODOO_DB إلى قاعدة المنصّة «sahool»: " + ", ".join(offenders)
