"""تحميل ``main.py`` لخدمة بعينها رغم عموميّة الاسم عبر ٢٤ خدمة (نمط #570).

كلّ خدمة تحمل ``main.py`` في جذرها، و``sys.modules`` مفتاحه الاسم لا المسار — فاستيراد
``main`` بعد استيراد خدمة أخرى يُعيد الوحدة البائتة بصمت. الخطر ليس فشلاً بل **نجاحاً
كاذباً**: اختبار يفحص مسارات خدمة (أ) بينما يقرأ فعليّاً وحدة الخدمة (ب).
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

# أسماء وحدات عامّة تتكرّر عبر الخدمات؛ تُنظَّف بالبادئة لا بالاسم المضبوط، لأنّ
# `routers` وحدها لا تُزيل `routers.equipment` المُحمَّلة من خدمة أخرى.
_GENERIC_ROOTS = {"main", "router_registry", "routers"}


def purge_generic_modules() -> None:
    """يُزيل كلّ وحدة اسمها الجذريّ عامّ، مع فروعها."""
    for name in list(sys.modules):
        if name.split(".")[0] in _GENERIC_ROOTS:
            sys.modules.pop(name, None)


def _belongs_to(module, root: Path) -> bool:
    """هل هذه الوحدة من داخل جذر الخدمة؟ — بالمسار لا بالسمات."""
    try:
        return Path(module.__file__ or "").resolve().is_relative_to(root)
    except (AttributeError, OSError, ValueError):
        return False


_REPO_ROOT = Path(__file__).resolve().parents[1]
_SERVICES_ROOT = (_REPO_ROOT / "services").resolve()


def _is_other_service_path(entry: str, root: Path) -> bool:
    """هل عنصر ``sys.path`` جذرُ استيرادٍ لخدمةٍ **أخرى** في أيّ عمقٍ تحت ``services/``؟

    اختبارات الخدمات تضيف جذوراً عديدة إلى ``sys.path`` في العملية نفسها. إبقاءُ جذر
    خدمةٍ سابقة يسمح لـ``router_registry``/``routers`` العامّين أن يُحلّا من الخدمة
    الخطأ بعد حذف الملفّ من الخدمة الجاري اختبارها. نعزل **جذور الخدمات فقط**؛ لا
    نحذف جذر المستودع ولا site-packages، حتى تبقى التبعيات المشتركة والخارجية مرئية.

    **العمقُ مقيسٌ لا مفترَض (#1017):** الصياغةُ الأولى اشترطت ``parent ==
    services/`` فأفلتت الجذورَ المتداخلة، وأكثرُ ما يُضاف في هذه الشجرة منها:
    ``services/sahool-platform/api`` (``tests_v9/test_alert_delivery.py:83`` وأخواتها)
    — وهو بالضبط الجذرُ الذي يوفّر ``router_registry``. فسقط شاهدُ الحذف نفسُه.
    """
    if not entry:
        return False
    try:
        candidate = Path(entry).resolve()
        current = root.resolve()
    except (OSError, ValueError):
        return False
    if not candidate.is_relative_to(_SERVICES_ROOT) or not candidate.is_dir():
        return False
    # جذرُ الخدمة الجاري تحميلُها، أو ما يحويه أو يقع تحته، ليس «خدمةً أخرى».
    return not (
        candidate == current
        or candidate.is_relative_to(current)
        or current.is_relative_to(candidate)
    )


def _is_internal_module(name: str | None, root: Path) -> bool:
    """هل الوحدةُ الغائبة داخليّةٌ (فشلٌ صريح) أم حزمةٌ خارجيّة (تخطٍّ مُعلَّل)؟

    **التصنيفُ بالمسار لا بالتخمين**، وهذه حدودُه كما تُقاس لا كما نتمنّاها:

    - داخليّة: ``main`` نفسُها · اسمٌ جذرُه في :data:`_GENERIC_ROOTS` (وهي أسماءُ
      توصيلٍ لا تُنشَر على PyPI، فتبقى داخليّةً حتّى لو حُذِف ملفُّها) · اسمٌ له ملفٌّ
      أو مجلَّدٌ تحت جذر الخدمة أو جذر المستودع.
    - خارجيّة: كلُّ ما عدا ذلك.

    **فالمجهولُ يُصنَّف خارجيّاً، لا داخليّاً.** هذا ليس سهواً بل مقايضةٌ معلنة: الفشلُ
    المغلق على كلّ اسمٍ مجهول يقلب غيابَ أيّ حزمةٍ خارجيّة (اسمُ استيرادها كثيراً ما
    يخالف اسمَ توزيعها: ``yaml`` ← PyYAML، ``jose`` ← python-jose) إلى حمرةٍ كاذبة في
    بيئةٍ بلا سائق — وهو ما يوجد التخطّي أصلاً لأجله. **الحدُّ المتبقّي المعلن:** وحدةٌ
    داخليّة باسمٍ غيرِ عامّ حُذِف ملفُّها وبقي استيرادُها تُقرأ خارجيّةً فتُتخطّى؛ ما
    يغطّيها هو :data:`_GENERIC_ROOTS` لأسماء التوصيل، وهي التي قِيس عليها العطل.
    """
    if not name or name == "main":
        return True
    top = name.split(".")[0]
    if top in _GENERIC_ROOTS:
        return True
    return any(
        (base / top).is_dir() or (base / f"{top}.py").is_file() for base in (root, _REPO_ROOT)
    )


def load_service_main(service_dir: str, *, required_attrs: tuple[str, ...]):
    """يُحمّل main.py لخدمة بعينها رغم عموميّة الاسم عبر الخدمات (نمط #570)."""
    root = Path(service_dir).resolve()

    # SERVICE-LOADER-CROSS-SERVICE-PATH-CONTAMINATION-01: لا يكفي تنظيف
    # ``sys.modules``. جذرُ خدمةٍ سابقة في ``sys.path`` يستطيع توفير اسم عام مثل
    # ``router_registry`` لخدمةٍ أخرى، فيتحول «ملف داخلي محذوف» إلى ImportError من
    # الملف الخطأ. أزل جذور الخدمات الأخرى قبل الاستيراد، واترك repo/site-packages.
    #
    # **والعزلُ مؤقَّتٌ بمدّة الاستيراد وحدَه — لا أثرَ عالميّاً باقياً.** الصياغةُ الأولى
    # حذفت تلك الجذور من ``sys.path`` **إلى الأبد**، والمقيس (#1017) أنّ ذلك أسقط
    # اختباراتٍ لم يُعدَّل فيها سطر: وحداتٌ تُثبّت جذورَها مرّةً واحدة وقتَ الجمع ثمّ
    # تستورد منها وقتَ التنفيذ (``tests_v9/test_fertigation_ec.py:17-22`` ⇒ 7 إخفاقات
    # في ``tiers``، و``test_rs_anomaly_pg_isolation_integration.py`` ⇒ ``anomaly_store``).
    # فالاستعادةُ في ``finally`` تُعيد الحالةَ إلى ما كانت عليه قبل النداء، مع إبقاء جذر
    # هذه الخدمة في الصدارة كما كان العقدُ دائماً. حدُّه المعلن: الاستيرادُ الكسول بعد
    # العودة يرى الجذورَ المستعادة — العزلُ يحرس لحظةَ الاستيراد، وهي موضعُ العطل المقيس.
    root_s = str(root)
    saved_path = list(sys.path)
    try:
        return _import_isolated(root, root_s, required_attrs)
    finally:
        sys.path[:] = [root_s] + [p for p in saved_path if p != root_s]


def _import_isolated(root: Path, root_s: str, required_attrs: tuple[str, ...]):
    """يستورد ``main`` وجذورُ الخدمات الأخرى معزولة؛ المُستدعي يستعيد ``sys.path``."""
    sys.path[:] = [p for p in sys.path if not _is_other_service_path(p, root)]
    while root_s in sys.path:
        sys.path.remove(root_s)
    sys.path.insert(0, root_s)

    # **إعادةُ الاستيراد ليست مجّانيّة.** لو كانت وحدةُ الخدمة نفسها محمَّلةً سلفاً،
    # فالإسقاطُ ثمّ الاستيراد يُنتج كائنَ وحدةٍ **ثانياً** لنفس الملفّ — ومن استورد
    # الأولى يبقى عليها بينما ``sys.modules["main"]`` صار الثانية. وكلُّ من يحلّ
    # ``import main`` **وقتَ الاستدعاء** (نمط شائع لتفادي دورات الإقلاع) يقرأ الثانية.
    #
    # مقيسٌ لا مفترَض (2026-08-25، #927): ``mfa_runtime._main()`` يستورد ``main``
    # عند كلّ نداء؛ فلمّا أعاد ملفٌّ لاحق استيرادَ خدمة auth، صار ترقيعُ
    # ``main._pool`` في اختبار MFA يقع على الكائن الأوّل والقراءةُ على الثاني —
    # فسقط ``test_correct_code_is_true`` بلا أن يتغيّر سطرٌ فيه.
    #
    # فالإسقاط يقع **فقط** حين تكون المُخبّأة وحدةَ خدمةٍ أخرى — وهو الغرض أصلاً.
    cached = sys.modules.get("main")
    if cached is not None and _belongs_to(cached, root):
        missing_cached = [a for a in required_attrs if not hasattr(cached, a)]
        if not missing_cached:
            return cached

    purge_generic_modules()
    try:
        mod = importlib.import_module("main")
    except ModuleNotFoundError as e:
        # **التخطّي لحزمةٍ خارجيّة غائبة فقط.** كان كلُّ `ImportError` يصير تخطّياً، فانكسارُ
        # `router_registry` أو `routers.validation` — التوصيلُ الذي يقيسه عقدُ HTTP على
        # الخدمة نفسها — كان يُتخطّى وCI أخضر (مراجعة Copilot على #1014؛ صنف «التخطّي
        # الصامت يُقرَأ نجاحاً»). الداخليُّ يُصنَّف بالمسار: وحدةٌ لها ملفٌّ تحت جذر الخدمة
        # أو جذر المستودع، أو الخدمةُ نفسُها (`main`)، أو اسمُ توصيلٍ عامّ حتّى لو حُذِف
        # ملفُّه. والمجهولُ خارجيٌّ بمقايضةٍ معلنة — انظر `_is_internal_module`.
        if _is_internal_module(e.name, root):
            raise AssertionError(
                f"فشلُ استيرادٍ داخليّ في {root.name}: {e} — انحدارُ توصيلٍ لا تبعيّةٌ ناقصة"
            ) from e
        pytest.skip(f"تبعيّة خارجيّة ناقصة: {e}", allow_module_level=True)
    except ImportError as e:
        # `ImportError` بلا `ModuleNotFoundError`: الوحدةُ وُجِدت وانكسر استيرادُها
        # (اسمٌ غائب من وحدةٍ داخليّة، أو استيرادٌ دائريّ) — عطلٌ في الشجرة لا في البيئة.
        raise AssertionError(f"انكسر استيرادُ {root.name}: {e}") from e

    # هويّة الوحدة تُثبَت بمسارها، لا تُستدَلّ من سماتها: خدمتان تحملان `app` و`router`
    # معاً تمرّان فحص السمات وهما وحدتان مختلفتان.
    loaded = Path(mod.__file__ or "").resolve()
    if not loaded.is_relative_to(root):
        raise AssertionError(f"استُورد main خاطئ (تصادم أسماء): {loaded} خارج {root}")
    missing = [a for a in required_attrs if not hasattr(mod, a)]
    if missing:
        raise AssertionError(f"استُورد main خاطئ (تصادم أسماء) — ينقصه {missing}")
    return mod
