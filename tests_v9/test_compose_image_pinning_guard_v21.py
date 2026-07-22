"""حارس CT-07 (container-audit V21 §6): منع الوسوم العائمة/العامّة لصور الحاويات.

الخلفيّة: مراجعة الحاويات V21 §6 رصدت وسوماً عائمة/عامّة في ``docker-compose.v9.yml``.
معظم الصور مثبَّتة على إصدار محدَّد أصلاً؛ الوحيد العائم فعليّاً كان
``zlmediakit/zlmediakit:master`` (وسم فرع متحرّك). هذا الحارس يقفل الثابتة (invariant)
المضادّة للعوم: لكلّ خدمة لها ``image``، الوسم الفعّال — بعد تجريد صيغة
``${VAR:-default}`` إلى افتراضها — يجب أن يكون:

  * موجوداً صراحةً (لا صورة بلا وسم)، و
  * ليس ``master`` ولا ``latest`` (ولا وسم فرع/متحرّك معروف)، أو
  * مثبَّتاً بمِعرِّف محتوى ``@sha256:...`` (وهو الأقوى).

صيغة الحقن الإلزاميّ ``${VAR:?رسالة}`` (بلا افتراض داخل الملفّ) هي **الأقوى**: لا صورة
ثابتة في الملفّ إطلاقاً، والمُشغِّل مُلزَم بحقن مِعرِّف ``sha256`` عبر البيئة وإلّا يرفض
compose الإقلاع بصوت عالٍ. تُقبَل كتثبيت (نظير ``@sha256:...``). هذا ما اعتمده
``ZLMEDIAKIT_IMAGE`` بعد ترقية التثبيت: ``${ZLMEDIAKIT_IMAGE:?...}`` مع
``.env.example`` يحمل ``zlmediakit/zlmediakit@sha256:...`` — فلم تعُد هناك حاجة إلى
استثناء allowlist لوسم متحرّك (الصورة الرسميّة لا تنشر وسم إصدار، والتثبيت صار إلزاميّاً
عبر البيئة). قائمة السماح تبقى آليّةً لأيّ حاجة مستقبليّة لكنّها فارغة الآن.

فحص ملفّات نقيّ: يُحمِّل ``docker-compose.v9.yml`` بـ``yaml.safe_load`` ويمرّ على الخدمات.
يعمل تحت ``pytest -m unit`` (بلا خدمات). التثبيت بمِعرِّف ``sha256`` هو المتابعة اللاحقة
لخطّ الإصدار؛ هذا الحارس يمنع الانحدار إلى الوسوم المتحرّكة ويسمح بأن يُبنى تثبيت المِعرِّف
فوقه لاحقاً (ratchet).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

# جذر المستودع (هذا الملفّ في tests_v9/ تحت الجذر مباشرةً).
_REPO_ROOT = Path(__file__).resolve().parent.parent
_COMPOSE = _REPO_ROOT / "docker-compose.v9.yml"

# وسوم متحرّكة ممنوعة (master/latest صراحةً حسب V21 §6، مع نظائرها الواضحة).
_MOVING_TAGS = {"master", "latest", "main", "edge", "nightly", "rolling"}

# قائمة السماح: صورة → سبب موثَّق. أبقِها صغيرة جدّاً. أيّ إضافة تتطلّب سبباً حقيقيّاً
# (صورة بنية تحتيّة لا تنشر أيّ وسم إصدار). راجع docstring الوحدة لـzlmediakit.
_ALLOWLIST: dict[str, str] = {}

# صيغة الحقن الإلزاميّ: ``${VAR:?رسالة}`` — بلا افتراض داخل الملفّ، ويرفض compose الإقلاع
# إن لم يُحقَن مِعرِّف sha256 عبر البيئة. تُعامَل كتثبيت (الأقوى)، نظير ``@sha256:...``.
_REQUIRED_ENV_PIN = re.compile(r"\$\{[^:}]+:\?[^}]*\}")


def _is_required_env_pin(image_value: str) -> bool:
    """هل الصورة بصيغة الحقن الإلزاميّ ``${VAR:?...}`` (بلا افتراض داخل الملفّ)؟"""
    v = image_value.strip().strip("\"'").strip()
    return bool(_REQUIRED_ENV_PIN.fullmatch(v))


def _effective_default(image_value: str) -> str | None:
    """جرِّد ``${VAR:-default}`` (أو ``${VAR-default}``) إلى افتراضها.

    يعيد القيمة الحرفيّة كما هي إن لم تكن indirection. يعيد ``None`` لصيغة ``${VAR}``
    بلا افتراض (لا مِعرِّف ثابت داخل الملفّ ⇒ تُعامَل كمخالفة، ما لم تكن صيغة الحقن
    الإلزاميّ ``${VAR:?...}`` التي يفحصها ``_is_required_env_pin`` منفصلاً).
    """
    v = image_value.strip().strip("\"'").strip()
    m = re.fullmatch(r"\$\{[^:}-]+:?-(?P<default>[^}]*)\}", v)
    if m:
        return m.group("default").strip()
    if v.startswith("${") and v.endswith("}"):
        return None
    return v


def _split_ref(ref: str) -> tuple[str, str | None, bool]:
    """قسّم مِعرِّف الصورة إلى (repo, tag, is_digest).

    يدعم registry:port/path، والمِعرِّف ``@sha256:...``. الوسم هو ما بعد آخر نقطتين
    تأتيان بعد آخر شرطة مائلة.
    """
    if "@" in ref:
        repo = ref.split("@", 1)[0]
        return repo, None, True
    last_slash = ref.rfind("/")
    last_colon = ref.rfind(":")
    if last_colon > last_slash:
        return ref[:last_colon], ref[last_colon + 1 :], False
    return ref, None, False


def _service_images() -> list[tuple[str, str]]:
    """أعِد [(اسم الخدمة, قيمة image الخام)] لكلّ خدمة لها مفتاح image."""
    data = yaml.safe_load(_COMPOSE.read_text(encoding="utf-8"))
    assert isinstance(data, dict), "docker-compose.v9.yml لم يُحلَّل إلى خريطة"
    services = data.get("services") or {}
    out: list[tuple[str, str]] = []
    for name, spec in services.items():
        if isinstance(spec, dict) and "image" in spec:
            out.append((name, str(spec["image"])))
    assert out, "لم تُعثَر أيّ خدمة لها image في docker-compose.v9.yml"
    return out


@pytest.mark.unit
def test_compose_parses():
    """docker-compose.v9.yml يجب أن يُحلَّل بـyaml.safe_load (لا انحدار في البنية)."""
    assert _COMPOSE.exists(), "docker-compose.v9.yml مفقود"
    data = yaml.safe_load(_COMPOSE.read_text(encoding="utf-8"))
    assert isinstance(data, dict) and data.get("services"), "لا خدمات في compose"


@pytest.mark.unit
def test_no_floating_or_untagged_image_tags():
    """كلّ صورة خدمة يجب أن تكون مثبَّتة: وسم صريح ليس master/latest، أو مِعرِّف sha256.

    صيغة ``${VAR:-default}`` تُجرَّد إلى افتراضها قبل الفحص. ``zlmediakit/zlmediakit``
    وحده مُستثنى (allowlist موثَّق) لأنّ المنبع لا ينشر أيّ وسم إصدار.
    """
    offenders: list[str] = []
    for name, raw in _service_images():
        # صيغة الحقن الإلزاميّ ``${VAR:?...}`` = الأقوى (لا صورة ثابتة داخل الملفّ؛ يُرفَض
        # الإقلاع بلا مِعرِّف sha256 محقون) ⇒ مقبولة كتثبيت.
        if _is_required_env_pin(raw):
            continue
        default = _effective_default(raw)
        if default is None:
            offenders.append(
                f"{name}: image={raw!r} — لا افتراض ثابت داخل الملفّ (${{VAR}} بلا :-default)"
            )
            continue
        repo, tag, is_digest = _split_ref(default)
        if repo in _ALLOWLIST:
            continue
        if is_digest:
            continue
        if tag is None:
            offenders.append(f"{name}: image={default!r} — بلا وسم صريح (untagged)")
            continue
        if tag.lower() in _MOVING_TAGS:
            offenders.append(f"{name}: image={default!r} — وسم متحرّك ممنوع (:{tag})")

    assert not offenders, (
        "صور غير مثبَّتة (وسم عائم/متحرّك أو بلا وسم) في docker-compose.v9.yml — "
        "ثبِّتها على وسم إصدار صريح (ليس master/latest) أو مِعرِّف @sha256:... :\n  "
        + "\n  ".join(offenders)
    )


@pytest.mark.unit
def test_allowlist_is_minimal_and_documented():
    """قائمة السماح يجب أن تبقى صغيرة، موثَّقة، ومقتصرة على صور موجودة فعلاً في compose."""
    assert len(_ALLOWLIST) <= 2, (
        "قائمة سماح تثبيت الصور نمت — كلّ استثناء يجب أن يكون لصورة بنية تحتيّة لا تنشر "
        "أيّ وسم إصدار. راجع الأسباب قبل التوسيع."
    )
    for repo, reason in _ALLOWLIST.items():
        assert reason.strip(), f"إدخال allowlist بلا سبب موثَّق: {repo}"

    used_repos = set()
    for _name, raw in _service_images():
        default = _effective_default(raw)
        if default is None:
            continue
        repo, _tag, _is_digest = _split_ref(default)
        used_repos.add(repo)
    stale = sorted(set(_ALLOWLIST) - used_repos)
    assert not stale, (
        f"قائمة السماح تحوي صوراً لم تعُد مُستخدَمة في docker-compose.v9.yml: {stale} — "
        "أزِلها لإبقاء الاستثناءات دقيقة."
    )
