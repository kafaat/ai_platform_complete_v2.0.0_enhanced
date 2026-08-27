#!/usr/bin/env python3
"""حارس CI: كلُّ مسارٍ يطلبه عميلُ خدمةٍ في المنصّة **مُعلَنٌ** في الخدمة التي يناديها.

**الصنفُ الذي وُجِد لأجله — `CONTRACT-WHOSE-TWO-ENDS-ARE-TESTED-APART-01`:** عقدٌ
طرفاه في خدمتين، وكلٌّ منهما مختبَرٌ وحدَه. اختبارُ العميل يزيّف الاستجابة،
واختبارُ الخدمة ينادي مسارَها الصحيح — فيمرّ الطرفان خضراوين **والقفزةُ بينهما لا
يفحصها أحد**. أصابنا ثلاثَ مرّاتٍ في أسبوع، وأوضحُها
`WEATHER-CLIENT-ASKS-A-PATH-THE-SERVICE-NEVER-DECLARED-01`: العميلُ يطلب
``/v1/weather/tile-cache/stats`` والخدمةُ تُعلن ``/v1/weather/cache-stats`` — **٤٠٤
حتميّ لا احتماليّ**، وانحرافُ سلسلةٍ نصّيّةٍ واحدة لا يراه أيُّ اختبار.

عولِجت تلك الحادثةُ بشاهدِ قفزةٍ **لعقدٍ واحد**. وهذا يعمّمه على كلّ عقدٍ عابر
يُكتشَف من الشجرة.

**واكتشافُ النطاق مُشتقٌّ لا مكتوب.** العملاءُ يُعرَّفون بحملهم عنوانَ خدمةٍ
داخليّة (``http://sahool-<اسم>-service:<منفذ>``)، ومنه تُشتقّ الخدمةُ الهدف
(``services/<اسم>-service``). فعميلٌ خامسٌ يدخل الشجرة غداً يدخل النطاق معه، ولا
يُنتظَر أن يتذكّره أحد.

**والاستخراجُ بنيويٌّ (``ast``) لسببٍ مقيس، لا احتياطاً.** أوّلُ قراءةٍ لي كتبتها
بتعبيرٍ نمطيّ يبحث عن ``*_get_json("/…")``، فأعطت:

    weather 18 مساراً · decision 27 · raster 16 · **soil صفر**

وصفرُ التربة لم يكن عقداً نظيفاً بل **قارئاً أعمى**: ``soil_hydraulic_client``
ينادي ``httpx`` مباشرةً بسلسلةٍ مُنسَّقة (``f"{base}/v1/fields/{id}/soil/…"``)، لا
عبر غلافٍ باسمٍ معروف. فالقراءةُ الصفريّة **تمرّ خضراء** وهي لم تفحص شيئاً — وهو
الصنفُ الذي يحرسه هذا الملفّ واقعاً فيه.

ولذلك يقرأ المستخرِجُ الشكلين معاً من شجرة البناء: السلسلةَ الحرفيّة والسلسلةَ
المُنسَّقة (تُطبَّع حقولُها إلى ``{}``). **ويُغلَق على نفسه:** عميلٌ يُقرأ منه صفرُ
مسارٍ **يُفشِل الحارس** بدل أن يمرّ صامتاً.

**وحدُّ صدقٍ يُقال:** هذا فحصٌ ساكن. لا يقيس أنّ الخدمة تستجيب ولا أنّ الحمولة
تطابق، بل أنّ المسارَ المطلوب **مُعلَنٌ** فيها. وهو بالضبط الصنفُ الذي أفلت —
انحرافُ سلسلةٍ بين طرفين لا يلتقيان في أيّ اختبار.

    python scripts/ci/cross_service_path_contract_guard.py
"""

from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path

# GUARD-DIES-PRINTING-ITS-OWN-SUCCESS-UNDER-C-LOCALE-01: مخرَجُ هذا الحارس عربيّ،
# و`print` يُرمّز بلغة الآلة. فتحت `LC_ALL=C` كان **يحسب صحيحاً** (٨ عقود، صفرُ
# انحراف) ثمّ يموت وهو يطبع نجاحَه — `UnicodeEncodeError` على `→` ⇒ خروجٌ بـ1
# يُقرَأ «الحارسُ يحجب» وهو قد مرّ. مقيسٌ بالتنفيذ قبل الإصلاح:
#   env -u PYTHONIOENCODING LC_ALL=C LANG=C PYTHONUTF8=0 … ⇒ exit=1
# وحارسٌ يُبلِغ فشلاً لأنّه عجز عن طباعة نجاحه أسوأُ من صامت: الصامتُ يُرى
# غيابُه، وهذا يُرى **ضدّ** ما قاس. **عند التحميل لا داخل `main()`** — فبعض
# الحرّاس بلا `main` أصلاً وتطبع من جسدها.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[2]
CLIENT_DIR = ROOT / "services" / "sahool-platform" / "api"

# عنوانُ خدمةٍ داخليّة — منه يُشتقّ اسمُ الخدمة الهدف.
_INTERNAL_HOST = re.compile(r"https?://sahool-([a-z0-9-]+?)-service(?::\d+)?")

# إعلانُ الخدمة: `app.get("/…")` · `@router.post("/…")` · وكلُّ الأفعال.
_DECLARED = re.compile(r"""@?(?:app|router)\.(?:get|post|put|patch|delete)\(\s*["']([^"']+)["']""")

_PARAM = re.compile(r"\{[^}]*\}")


def normalise(path: str) -> str:
    """يُطبَّع الشكلُ لا القيمة: مقاطعُ المسار المتغيّرة تصير `{}`، وتُزال الذيول."""
    return _PARAM.sub("{}", path.split("?", 1)[0].rstrip("/")) or "/"


def _literal_path(node: ast.AST) -> str | None:
    """يُعيد المسارَ من سلسلةٍ حرفيّة أو مُنسَّقة — والشكلان مُستعمَلان في الشجرة.

    السلسلةُ المُنسَّقة تُبنى بوضع `{}` مكان كلّ حقلٍ مُقحَم، ثمّ يُقتطَع ما قبل
    أوّلَ `/` (فهو جذرُ العنوان `{base}` لا جزءاً من المسار).
    """
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        text = node.value
    elif isinstance(node, ast.JoinedStr):
        parts = []
        for piece in node.values:
            if isinstance(piece, ast.Constant) and isinstance(piece.value, str):
                parts.append(piece.value)
            else:
                parts.append("{}")
        text = "".join(parts)
    else:
        return None
    index = text.find("/")
    if index < 0:
        return None
    candidate = text[index:]
    # مسارٌ حقيقيّ يحمل مقطعاً واحداً على الأقلّ بعد الشرطة الأولى.
    if len(candidate) < 2 or candidate.startswith("//"):
        return None
    return normalise(candidate)


# مسارٌ يُثبَّت في ثابتٍ على مستوى الوحدة — شكلٌ ثانٍ مقيسٌ في الشجرة.
_PATH_SHAPED = re.compile(r"^/(?:v\d+|api|internal)/")

# أغلفةُ النقل: `weather_get_json` · `raster_get_json_sync` · `decision_post_json` …
_JSON_WRAPPER = re.compile(r"_(?:get|post|put|patch|delete)_json(?:_\w+)?$")


def requested_paths(source: str) -> set[str]:
    """المساراتُ التي يطلبها العميل — من موضعين مقيسين لا من كلّ سلسلة.

    ① **عند موضع النداء:** الوسيطُ الأوّل لنداءٍ يبدو نداءَ نقل (`*_get_json`
       وأخواتها، أو `client.get`/`.post`/… من `httpx`).

    ② **ثابتٌ على مستوى الوحدة بشكل مسار** (`^/v1/…` · `^/api/…`). وهذا أُضيف
       **بعد أن أفلت عقدٌ حقيقيّ**: `irrigation_activation_gate` يحمل
       `GATE_ENFORCE_PATH = "/v1/activation/irr_f01_reservation/enforce"` ويبنيه
       داخل `_decision_url()`، فلا يُرى عند موضع النداء إطلاقاً — قراءةٌ صفريّة
       من وحدةٍ تنادي خدمةً فعلاً. ووحدةٌ تحمل عنوانَ خدمةٍ وثابتاً بشكل مسار
       **تُصرّح بذلك المسار** أينما بنته.

    وسلسلةٌ في رسالة خطأ أو تعليقٍ تبقى خارج الجرد: الشرطُ موضعُ نداءٍ أو ثابتٌ
    مُسمًّى على مستوى الوحدة، لا أيُّ سلسلةٍ تبدأ بشرطة.
    """
    tree = ast.parse(source)
    found: set[str] = set()

    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        value = node.value
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            if _PATH_SHAPED.match(value.value):
                found.add(normalise(value.value))

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not node.args:
            continue
        func = node.func
        name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
        # **يُطابَق الاحتواءُ لا النهاية.** كان الشرطُ `endswith` فأفلت
        # `raster_get_json_sync` — لاحقةٌ واحدة (`_sync`) تُخفي مسارَين حقيقيَّين.
        # وكُشِف بمقابلة قارئَين لا بقراءةٍ واحدة: التعبيرُ النمطيّ أعطى ١٦
        # و`ast` أعطى ١٤، والفرقُ هو العطل. **قارئٌ واحدٌ لا يُكذِّب نفسَه.**
        is_wrapper = bool(_JSON_WRAPPER.search(name))
        is_httpx = name in {"get", "post", "put", "patch", "delete", "request", "stream"}
        if not (is_wrapper or is_httpx):
            continue
        # `client.request("GET", url)` يضع الفعلَ أوّلاً والعنوانَ ثانياً.
        for arg in node.args[:2]:
            path = _literal_path(arg)
            if path:
                found.add(path)
                break
    return found


def declared_paths(service_dir: Path) -> set[str]:
    declared: set[str] = set()
    for file in sorted(service_dir.rglob("*.py")):
        text = file.as_posix()
        if "__pycache__" in text or "/tests/" in text:
            continue
        declared |= {
            normalise(m)
            for m in _DECLARED.findall(file.read_text(encoding="utf-8", errors="ignore"))
        }
    return declared


def discover_contracts() -> dict[str, dict]:
    """يُشتقّ العملاءُ وخدماتُهم من الشجرة — لا من قائمةٍ مكتوبة.

    القائمةُ المكتوبة تبيت: عميلٌ خامسٌ يدخل غداً فلا يدخل النطاق معه، ويبقى
    الحارسُ أخضرَ عن سؤالٍ لم يعد يطرحه.
    """
    contracts: dict[str, dict] = {}
    for file in sorted(CLIENT_DIR.rglob("*.py")):
        if "__pycache__" in file.as_posix():
            continue
        source = file.read_text(encoding="utf-8", errors="ignore")
        hosts = {m for m in _INTERNAL_HOST.findall(source)}
        # عميلُ خدمةٍ واحدة: عنوانٌ داخليٌّ واحد. المُركَّبُ خارج النطاق بلا ادّعاء.
        if len(hosts) != 1:
            continue
        service = f"{hosts.pop()}-service"
        service_dir = ROOT / "services" / service
        if not service_dir.is_dir():
            continue
        contracts[file.relative_to(ROOT).as_posix()] = {
            "service": service,
            "service_dir": service_dir,
        }
    return contracts


# وحداتٌ تحمل عنوانَ خدمةٍ ولا مسارَ ثابتاً لها — **وسببُ كلٍّ مكتوب**.
#
# وهذا **حدٌّ مُعلَنٌ لا إعفاءٌ مريح.** الفحصُ الساكن لا يُميّز «مُمرِّرٌ ديناميّ
# بلا عقدٍ ثابت» من «مسارٌ حرفيٌّ عجز مستخرِجي عن رؤيته» — والثاني هو بعينه ما
# وقع مع `soil_hydraulic_client` (شكلُ نداءٍ ثانٍ) و`irrigation_activation_gate`
# (ثابتٌ على مستوى الوحدة)، وكلاهما أُغلِق باتّساع المستخرِج لا باستثناء.
#
# فالقائمةُ مغلقةٌ بالمساواة: وحدةٌ جديدةٌ بصفر مسارٍ **تُفشِل الحارس** حتّى
# يقرّر إنسانٌ أيَّ الحالتين هي. وحذفُ مدخلٍ صار له مسارٌ يُفشِله أيضاً.
PATH_LESS_BY_DESIGN = {
    "services/sahool-platform/api/routers/service_proxy.py": (
        "مُمرِّرٌ عامّ: المسارُ مُعامِلُ تشغيلٍ (`/api/soil/{path:path}`) يُعاد بناؤه "
        "من طلب المستخدم، فلا مسارَ ثابتاً يُقابَل بإعلان الخدمة. العقدُ هنا "
        "«مرّر ما وصل»، وفحصُه يخصّ التفويضَ لا انحرافَ السلاسل."
    ),
}


def classify(client: str, requested: set[str], declared: set[str]) -> dict:
    """يُصنّف عقداً واحداً — **دالّةٌ نقيّةٌ عمداً**.

    كانت هذه الأسطرُ داخل `audit()` تقرأ الشجرة، فلم يكن للعمى شاهدٌ **موجب**:
    اختبارُه أكّد أنّ القائمة فارغةٌ على شجرةٍ سليمة، وهي تبقى فارغةً أيضاً لو
    عُطِّل الكشفُ رأساً. **فالطفرةُ التي تُطفئه نجت** — وهي حالةُ «تأكيدُ غيابٍ
    بلا شاهدِ حضور»، أي الصنفُ الذي يحرسه هذا الملفّ في طبقةِ اختباره هو.

    فأُخرِج التصنيفُ نقيّاً كي يُقاس بمُدخَلٍ مُصطنَع: عقدٌ بلا مسارٍ **يُعلَن
    أعمى** بالإيجاب، لا بانتظار أن تُنتِجه شجرةٌ معطوبة.
    """
    blind_reasons: list[str] = []
    # قراءةٌ صفريّة ليست عقداً نظيفاً بل قارئاً أعمى — وهي كيف يمرّ هذا الصنفُ
    # نفسُه. مقيس: شكلُ نداءٍ ثانٍ في `soil_hydraulic_client` أعطى صفراً.
    if not requested and client not in PATH_LESS_BY_DESIGN:
        blind_reasons.append(client)
    if not declared:
        blind_reasons.append(f"{client}: صفرُ إعلان")
    return {
        "undeclared": sorted(requested - declared),
        "blind": blind_reasons,
        "path_less": not requested,
    }


def audit() -> dict:
    report: dict = {
        "contracts": {},
        "blind_clients": [],
        "undeclared": [],
        "path_less": [],
        "stale_exemptions": [],
    }
    for client, meta in discover_contracts().items():
        requested = requested_paths((ROOT / client).read_text(encoding="utf-8"))
        declared = declared_paths(meta["service_dir"])
        verdict = classify(client, requested, declared)
        report["contracts"][client] = {
            "service": meta["service"],
            "requested": len(requested),
            "declared": len(declared),
            "undeclared": verdict["undeclared"],
        }
        if verdict["path_less"]:
            report["path_less"].append(client)
        report["blind_clients"] += verdict["blind"]
        report["undeclared"] += [
            f"{client} → {meta['service']}: {p}" for p in verdict["undeclared"]
        ]

    # مدخلٌ بائتٌ يُخفي انحداراً قادماً: صار للوحدة مسارٌ ولم يُنزَع إعفاؤها.
    report["stale_exemptions"] = sorted(set(PATH_LESS_BY_DESIGN) - set(report["path_less"]))
    return report


def main() -> int:
    report = audit()
    if not report["contracts"]:
        print("cross_service_path_contract_guard FAILED — لم يُكتشَف أيُّ عقدٍ عابر.")
        print("  تغيّر شكلُ عناوين الخدمات الداخليّة والحارسُ صار أعمى — لا عقدَ سليم.")
        return 1

    for client, data in report["contracts"].items():
        print(f"  {client} → {data['service']}: يطلب {data['requested']} · تُعلن {data['declared']}")

    failed = False
    if report["blind_clients"]:
        failed = True
        print("\ncross_service_path_contract_guard FAILED — قراءةٌ صفريّة تمرّ خضراء:")
        for entry in report["blind_clients"]:
            print(f"  ✗ {entry}")
        print("  صفرُ مسارٍ ليس عقداً نظيفاً بل شكلَ نداءٍ لم يعرفه المستخرِج.")

    if report["stale_exemptions"]:
        failed = True
        print("\ncross_service_path_contract_guard FAILED — إعفاءٌ بائتٌ يُخفي انحداراً قادماً:")
        for entry in report["stale_exemptions"]:
            print(f"  ✗ {entry}: صار لها مسارٌ ثابت — انزع مدخلها من PATH_LESS_BY_DESIGN")

    if report["undeclared"]:
        failed = True
        print("\ncross_service_path_contract_guard FAILED — مساراتٌ تُطلَب ولا تُعلَن (٤٠٤ حتميّ):")
        for entry in report["undeclared"]:
            print(f"  ✗ {entry}")

    if failed:
        return 1
    exempt = len(report["path_less"])
    print(
        f"\ncross_service_path_contract_guard_ok "
        f"({len(report['contracts'])} عقداً عابراً · {exempt} بلا مسارٍ ثابتٍ بسببٍ مكتوب)"
    )
    return 0


if __name__ == "__main__":
    if "--json" in sys.argv:
        data = audit()
        data["contracts"] = {
            k: {kk: vv for kk, vv in v.items() if kk != "service_dir"}
            for k, v in data["contracts"].items()
        }
        print(json.dumps(data, ensure_ascii=False, indent=2))
        raise SystemExit(0)
    raise SystemExit(main())
