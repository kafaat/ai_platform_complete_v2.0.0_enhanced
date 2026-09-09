"""وسيطُ NATS يشترط اعتماداً — `NATS-BROKER-HAS-NO-AUTHENTICATION-…-01`.

**العطلُ مقيسٌ لا مظنون:** `nats/nats.conf` حمل `http` و`jetstream` فقط — لا
`authorization` ولا `accounts` ولا `users`. فالوسيطُ مفتوحٌ لكلّ من بلغ شبكةَ
`sahool-internal`: أيُّ حاويةٍ مخترَقة في المكدّس تنشر وتشترك على أيّ موضوع بلا
اعتماد. وتعليقُ رأس الملفّ كان يقول «منفذ العميل 4222 افتراضيّ ولا يحتاج تصريحاً
هنا» — **صادقٌ عن المنفذ، صامتٌ عن المصادقة**، فيُقرأ إقراراً بأنّ لا شيءَ ناقص.

**وما يحرسه هذا الملفّ ثلاثةُ أطراف، وسقوطُ أيّها يُعيد العطل:**

  ① الوسيطُ يشترط اعتماداً (`authorization` في `nats.conf`).
  ② والاعتمادُ يبلغه فعلاً (`sahool-nats` يرث `NATS_USER`/`NATS_PASSWORD` بـ`:?`)،
     **وكلُّ** عميلٍ يحمله في `NATS_URL` — وإلّا صار الإغلاقُ كسراً للمكدّس:
     وسيطٌ يرفض وعملاءُ لا يعرفون، وهو أسوأ من الفتحة لأنّه يُقرأ عطلَ شبكة.
  ③ ولا يُطبَع الاعتمادُ في سجلّ — فالعلاجُ وضع كلمةَ المرور في عنوانٍ **كان
     يُطبَع في موضعين**، فيُسرَّب إلى سجلّاتٍ تُجمَع وتُشحَن.

**ولمَ في `tests_v9/` لا في `scripts/ci/`:** يحجب في *Unit Tests* كما يحجب حارسُ
`scripts/ci` في *Structural Lint*، بلا أن يضيف ثلاثيّةً إلى كتالوج الحرّاس ولا أن
يطلب إقراراً في `blocking_surface_additions`. حجبٌ بالكلفة الأدنى.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
CONF = ROOT / "nats" / "nats.conf"
COMPOSE = ROOT / "docker-compose.v9.yml"

#: المكدّسُ الوحيد الذي يُركِّب `nats/nats.conf` — مقيسٌ لا مفترَض، ويُثبَّت أدناه.
STACK = "docker-compose.v9.yml"


def _services() -> dict:
    return yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))["services"]


# ── ① الوسيطُ يشترط اعتماداً ──────────────────────────────────────────────────


def test_the_broker_config_demands_credentials():
    text = CONF.read_text(encoding="utf-8")
    body = "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))
    assert re.search(r"^\s*authorization\s*\{", body, re.M), (
        "لا كتلةَ `authorization` في nats.conf — الوسيطُ مفتوحٌ لكلّ من بلغ الشبكة الداخليّة"
    )
    assert "$NATS_USER" in body and "$NATS_PASSWORD" in body, (
        "الاعتمادُ يجب أن يُورَث من البيئة (`$NATS_USER`/`$NATS_PASSWORD`) لا يُكتَب في الملفّ"
    )


def test_no_credential_is_written_into_the_committed_config():
    """سرٌّ حرفيٌّ في ملفٍّ مُلتزَم سرٌّ منشور — نفسُ قاعدة `compose_no_default_secrets`."""
    body = "\n".join(
        line
        for line in CONF.read_text(encoding="utf-8").splitlines()
        if not line.lstrip().startswith("#")
    )
    for field in ("user", "password"):
        for match in re.finditer(rf"^\s*{field}\s*:\s*(\S+)", body, re.M):
            assert match.group(1).startswith("$"), (
                f"`{field}` بقيمةٍ حرفيّة في nats.conf: {match.group(1)!r} — سرٌّ منشور"
            )


# ── ② والاعتمادُ يبلغ الوسيطَ وكلَّ عميل ────────────────────────────────────────


def test_the_broker_service_inherits_the_credentials_and_refuses_a_published_default():
    nats = _services()["sahool-nats"]
    env = nats.get("environment") or {}
    for var in ("NATS_USER", "NATS_PASSWORD"):
        value = str(env.get(var) or "")
        assert value, f"`sahool-nats` لا يرث {var} — الوسيطُ يقرأ `$" + var + "` من بيئته"
        assert ":?" in value, (
            f"{var} بلا `:?` — سرٌّ افتراضيّ منشور، أو إقلاعٌ بصمتٍ بلا اعتماد. "
            "نفسُ قاعدة `compose_no_default_secrets_guard`."
        )


def test_every_client_url_carries_the_credentials():
    """وإلّا صار الإغلاقُ كسراً: وسيطٌ يرفض وعملاءُ لا يعرفون.

    والمقيسُ **كلُّ** ظهورٍ لا عيّنة: كانت ستُّ خدماتٍ تستوفي المتغيّر وسبعٌ تكتب
    العنوانَ حرفيّاً، وذلك الانقسامُ بعينه هو ما يجعل إصلاحاً جزئيّاً يبدو تامّاً.
    """
    offenders: list[str] = []
    for name, service in _services().items():
        env = service.get("environment") or {}
        if not isinstance(env, dict):
            continue
        url = env.get("NATS_URL")
        if url is None:
            continue
        if "${NATS_USER}" not in str(url) or "${NATS_PASSWORD}" not in str(url):
            offenders.append(f"{name}: {url}")
    assert not offenders, "خدماتٌ تتّصل بالوسيط بلا اعتماد:\n  " + "\n  ".join(offenders)


def test_the_measured_client_count_is_pinned_so_a_new_service_cannot_slip_in():
    """أرضيّةُ جرد: صفرُ خدماتٍ ⇒ صفرُ مخالفين ⇒ خضرةٌ عن لا شيء."""
    urls = [
        s.get("environment", {}).get("NATS_URL")
        for s in _services().values()
        if isinstance(s.get("environment"), dict)
    ]
    assert len([u for u in urls if u]) == 13, (
        "تغيّر عددُ عملاء NATS في المكدّس — راجِع أنّ الجديد يحمل الاعتماد ثمّ حدّث العدد"
    )


def test_only_this_stack_mounts_the_hardened_config():
    """حدُّ صدقٍ **مُختبَر**: المكدّساتُ الأخرى تُشغّل NATS بلا هذا الملفّ.

    فلا يُدَّعى أنّ الشريحةَ أغلقت الوسيطَ في كلّ مكان. وإن رُكِّب الملفُّ في مكدّسٍ
    آخر وجب أن يحمل عملاؤه الاعتمادَ أيضاً — فتحمرّ هذه الحالةُ لتُلفِت إليه.
    """
    mounting = sorted(
        p.name
        for p in ROOT.glob("docker-compose*.yml")
        if "nats/nats.conf" in p.read_text(encoding="utf-8")
    )
    assert mounting == [STACK], f"تغيّر مَن يُركّب nats.conf: {mounting}"


# ── ③ ولا يُطبَع الاعتمادُ في سجلّ ─────────────────────────────────────────────


def test_no_site_logs_the_broker_url_unredacted():
    """العلاجُ وضع السرَّ في عنوانٍ **كان يُطبَع** — فالتنقيةُ جزءٌ من الإصلاح لا زينة."""
    offenders: list[str] = []
    for path in sorted(ROOT.glob("services/**/*.py")) + sorted(ROOT.glob("shared/**/*.py")):
        if path.name == "broker_url.py":
            continue
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            stripped = line.strip()
            if not re.search(r"\b(logger|logging)\.\w+\(", stripped):
                continue
            if re.search(r"\bnats_url\b", stripped) and "redact_broker_url" not in stripped:
                offenders.append(f"{path.relative_to(ROOT)}:{number}: {stripped[:88]}")
    assert not offenders, "عنوانُ الوسيط يُطبَع خاماً وفيه الاعتماد:\n  " + "\n  ".join(offenders)


def test_the_redaction_actually_removes_the_secret():
    """شاهدٌ موجب: بلا هذا تمرّ تنقيةٌ تُعيد العنوانَ كما هو."""
    import sys

    sys.path.insert(0, str(ROOT))
    from shared.broker_url import redact_broker_url

    assert (
        redact_broker_url("nats://u:s3cr3t@sahool-nats:4222") == "nats://***:***@sahool-nats:4222"
    )
    assert "s3cr3t" not in redact_broker_url("nats://u:s3cr3t@sahool-nats:4222")
    # وعنوانٌ بلا اعتماد يعود كما هو — لا تُقلِق قارئَه بتنقيةٍ لم تقع.
    assert redact_broker_url("nats://sahool-nats:4222") == "nats://sahool-nats:4222"
    assert redact_broker_url(None) == ""


# ── الفجوةُ الفرعيّة المقيسة عرضاً في الصفّ نفسِه ─────────────────────────────


#: مطلوباتُ العقد التي **ما تزال** بلا سطحِ تزويد، كلٌّ بسببه. راتشِتٌ يتقلّص ولا ينمو.
#:
#: **وُجِدت بتعميم الحالة لا بالصفّ:** سجّل الصفُّ `ACTUATOR_ADAPTER_CONFIG_JSON`
#: وحدَه، فلمّا عُمِّم السؤالُ على كلّ `required_config` ظهرت ثلاثةٌ أخرى من الصنف
#: نفسِه. وإصلاحُها هنا توسيعٌ للشريحة إلى نظامَين آخرَين (تنفيذُ الملحقات · خدمةُ
#: النماذج) بلا قياسٍ لهما؛ وإسقاطُها صمتٌ. فالثالثةُ: تُسمّى وتُسقَّف.
UNPROVISIONED_REQUIRED_CONFIG = {
    "MODEL_SERVING_BACKEND_URL": "خدمةُ النماذج — نظامٌ آخر، لم يُقَس في هذه الشريحة",
    "MODEL_SERVING_ENABLED": "خدمةُ النماذج — نظامٌ آخر، لم يُقَس في هذه الشريحة",
    "PLUGIN_EXECUTOR_URL": "تنفيذُ الملحقات — نظامٌ آخر، لم يُقَس في هذه الشريحة",
}


def test_a_config_the_worker_contract_requires_has_a_provisioning_surface():
    """`ACTUATOR_ADAPTER_CONFIG_JSON` مطلوبٌ في العقد ولم يكن في `.env.example`.

    مطلوبٌ مُعلَنٌ بلا سطحِ تزويد يُضبَط بمعرفةٍ ضمنيّة أو لا يُضبَط أصلاً — وهو ما
    قاسه صفُّ الفجوة عرضاً. أُغلِق هنا، والباقي مُسمًّى في الراتشِت أعلاه.
    """
    contracts = (ROOT / "shared" / "runtime_worker_contracts.py").read_text(encoding="utf-8")
    required = set(re.findall(r"required_config=\(([^)]*)\)", contracts))
    names = {n.strip().strip("\",'") for group in required for n in group.split(",") if n.strip()}
    assert "ACTUATOR_ADAPTER_CONFIG_JSON" in names, "تغيّر العقد — أعِد قياسَ ما يشترطه"

    env_example = (ROOT / ".env.example").read_text(encoding="utf-8")
    declared = {
        line.split("=", 1)[0].strip()
        for line in env_example.splitlines()
        if "=" in line and not line.lstrip().startswith("#")
    }
    missing = {n for n in names if n and n not in declared}

    assert "ACTUATOR_ADAPTER_CONFIG_JSON" not in missing, (
        "`ACTUATOR_ADAPTER_CONFIG_JSON` عاد بلا سطحِ تزويد — وهو ما أغلقته هذه الشريحة"
    )
    unknown = sorted(missing - set(UNPROVISIONED_REQUIRED_CONFIG))
    assert not unknown, (
        f"مطلوبٌ جديدٌ في عقد العمّال بلا سطحِ تزويد: {unknown}\n"
        "  إمّا يُضاف إلى .env.example، وإمّا يُسمّى في UNPROVISIONED_REQUIRED_CONFIG بسببه."
    )


def test_the_unprovisioned_baseline_only_shrinks():
    """أساسٌ يحمل ما لا وجودَ له يُدرِّب قارئَه على تجاهله — والراتشِت لا يصعد."""
    contracts = (ROOT / "shared" / "runtime_worker_contracts.py").read_text(encoding="utf-8")
    required = set(re.findall(r"required_config=\(([^)]*)\)", contracts))
    names = {n.strip().strip("\",'") for group in required for n in group.split(",") if n.strip()}
    env_example = (ROOT / ".env.example").read_text(encoding="utf-8")
    declared = {
        line.split("=", 1)[0].strip()
        for line in env_example.splitlines()
        if "=" in line and not line.lstrip().startswith("#")
    }
    missing = {n for n in names if n and n not in declared}
    stale = sorted(set(UNPROVISIONED_REQUIRED_CONFIG) - missing)
    assert not stale, f"أُغلِقت فعلاً فتُحذَف من الأساس: {stale}"
    assert len(UNPROVISIONED_REQUIRED_CONFIG) <= 3, "الدَّينُ يتقلّص ولا ينمو"
