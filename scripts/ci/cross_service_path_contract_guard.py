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

**W1-02 — النطاقُ صار ``api/`` و``core/`` وكلَّ مضيفٍ في compose.** كان النطاقُ
``api/`` وحدَه، والمضيفُ يُعرَف بلاحقة ``-service``، والوحدةُ متعدّدةُ المضيفين تُسقَط
كلُّها. فمرّ ``soil_adapter`` في ``core/field_intelligence_adapters.py`` (أربعةُ
مضيفين) وهو يطلب ``/api/v1/soil/{id}`` الذي لا تُعلنه soil-service — ٤٠٤ حتميّ.
والآن:

* **المضيفون من compose لا من نمطٍ اسميّ:** كلُّ خدمةٍ مبنيّةٍ في ``docker-compose*.yml``
  (``build``) تُربَط بمجلّد مصدرها؛ فـ``sahool-guardrails-engine`` و``sahool-edge``
  و``sahool-field-segmentation`` و``sahool-scout-ingest`` و``sahool-vegetation-analysis``
  دخلت النطاق. مضيفٌ بصورةٍ جاهزة بلا مصدر (ollama · vllm) خارجيٌّ بالتصريح. ومضيفٌ
  داخليٌّ لا يعرفه compose **يُفشِل الحارس** (اسمٌ لا يُحَلّ).
* **الوحدةُ متعدّدةُ المضيفين تُنسَب نداءً نداءً:** المضيفُ يُقرأ من تعبير العنوان نفسه
  (``f"{SOIL_URL}/…"`` ⇐ ``SOIL_URL = os.getenv(…, "http://sahool-soil-service…")``)
  بنطاق الدالّة ثمّ الوحدة. نداءٌ لا يُنسَب لمضيفٍ واحدٍ **يُفشِل الحارس** بدل أن يسقط.
* **المُمرِّرُ يُفحَص بقوائمه:** ``service_proxy`` بلا مسارٍ ثابت، لكنّ قوائمَ سماحه
  (``_SOIL_ROUTES`` …) ومساراتِه المُقالَبة (``path=f"internal/field-forms/{…}"``)
  تُقابَل بإعلان الخدمة: كلُّ مسارٍ تكشفه القائمة يجب أن تُعلنه الخدمةُ الهدف.

    python scripts/ci/cross_service_path_contract_guard.py
"""

from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlsplit

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
PLATFORM_DIR = ROOT / "services" / "sahool-platform"
# W1-02: ``core/`` يحمل محوّلاتٍ حيّةً تنادي الخدمات (field-intelligence · pest escalation).
CLIENT_DIRS = (PLATFORM_DIR / "api", PLATFORM_DIR / "core")

# عنوانُ خدمةٍ داخليّة — اسمُ المضيف كاملاً؛ يُحَلّ إلى مجلّد مصدره من compose.
_INTERNAL_HOST = re.compile(r"https?://(sahool-[a-z0-9-]+)")

# إعلانُ الخدمة: `app.get("/…")` · `@router.post("/…")` · وكلُّ الأفعال.
_DECLARED = re.compile(r"""@?(?:app|router)\.(?:get|post|put|patch|delete)\(\s*["']([^"']+)["']""")

_PARAM = re.compile(r"\{[^}]*\}")


def normalise(path: str) -> str:
    """يُطبَّع الشكلُ لا القيمة: مقاطعُ المسار المتغيّرة تصير `{}`، وتُزال الذيول."""
    return _PARAM.sub("{}", path.split("?", 1)[0].rstrip("/")) or "/"


def _render(node: ast.AST, assigns: dict[str, ast.AST] | None = None, depth: int = 0) -> str | None:
    """يُعيد نصَّ العنوان من سلسلةٍ حرفيّة أو مُنسَّقة أو جمعِ سلاسل (`base + "/v1/…"`).

    الحقلُ المُقحَمُ يصير `{}`. واسمٌ محلّيٌّ مُسنَدٌ في الدالّة نفسها (`url = … + "/v1/x"`
    ثمّ `client.post(url)`) يُتبَع إسنادُه — شكلٌ مقيسٌ في `pest_escalation_flow`.
    """
    if depth > 4:
        return None
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        parts = []
        for piece in node.values:
            if isinstance(piece, ast.Constant) and isinstance(piece.value, str):
                parts.append(piece.value)
            else:
                parts.append("{}")
        return "".join(parts)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left = _render(node.left, assigns, depth + 1)
        right = _render(node.right, assigns, depth + 1)
        return (left if left is not None else "{}") + (right or "")
    if isinstance(node, ast.IfExp):
        # لاحقةُ استعلامٍ شرطيّة (`(f"?{q}" if q else "")`): الفرعُ الأوّلُ يمثّل الشكل.
        return _render(node.body, assigns, depth + 1)
    if isinstance(node, ast.Name) and assigns and node.id in assigns:
        return _render(assigns[node.id], assigns, depth + 1)
    return None


def _literal_path(node: ast.AST, assigns: dict[str, ast.AST] | None = None) -> str | None:
    """يُعيد المسارَ من سلسلةٍ حرفيّة أو مُنسَّقة — والشكلان مُستعمَلان في الشجرة.

    السلسلةُ المُنسَّقة تُبنى بوضع `{}` مكان كلّ حقلٍ مُقحَم، ثمّ يُقتطَع ما قبل
    أوّلَ `/` (فهو جذرُ العنوان `{base}` لا جزءاً من المسار).
    """
    text = _render(node, assigns)
    if text is None:
        return None
    index = text.find("/")
    if index < 0:
        return None
    candidate = text[index:]
    # مسارٌ حقيقيّ يحمل مقطعاً واحداً على الأقلّ بعد الشرطة الأولى.
    if len(candidate) < 2 or candidate.startswith("//"):
        return None
    path = normalise(candidate)
    # `f"{base}/{path}"` داخل غلاف النقل نفسه: لا مقطعَ حرفيّ ⇒ ليس مساراً يُقابَل.
    if all(segment in {"", "{}"} for segment in path.split("/")):
        return None
    return path


# مسارٌ يُثبَّت في ثابتٍ على مستوى الوحدة — شكلٌ ثانٍ مقيسٌ في الشجرة.
_PATH_SHAPED = re.compile(r"^/(?:v\d+|api|internal)/")

# أغلفةُ النقل: `weather_get_json` · `raster_get_json_sync` · `decision_post_json` …
_JSON_WRAPPER = re.compile(r"_(?:get|post|put|patch|delete)_json(?:_\w+)?$")


def _local_assigns(scope: ast.AST) -> dict[str, ast.AST]:
    """إسناداتُ الأسماء البسيطة في نطاقٍ (دالّة أو وحدة) — آخرُ إسنادٍ يغلب."""
    assigns: dict[str, ast.AST] = {}
    body = scope.body if isinstance(scope, ast.Module) else list(ast.walk(scope))
    for node in body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    assigns[target.id] = node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.value:
            assigns[node.target.id] = node.value
    return assigns


def _scope_nodes(scope: ast.AST):
    """Walk one lexical scope without borrowing assignments from a nested definition."""
    yield scope
    for child in ast.iter_child_nodes(scope):
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
            yield child
        else:
            yield from _scope_nodes(child)


def _conditional_nodes(scope: ast.AST) -> set[int]:
    return {
        id(child)
        for node in _scope_nodes(scope)
        if isinstance(
            node, (ast.If, ast.For, ast.AsyncFor, ast.While, ast.Try, ast.TryStar, ast.Match)
        )
        for child in _scope_nodes(node)
    }


def _scope_assigns(scope: ast.AST) -> dict[str, ast.AST]:
    assigns: dict[str, ast.AST] = {}
    conditional = _conditional_nodes(scope)

    def record(name: str, value: ast.AST) -> None:
        previous = assigns.get(name)
        assigns[name] = (
            ast.Constant(None)
            if previous is not None and ast.dump(previous) != ast.dump(value)
            else value
        )

    for node in _scope_nodes(scope):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                for left, right in _assignment_pairs(target, node.value):
                    if isinstance(left, ast.Name):
                        record(left.id, ast.Constant(None) if id(node) in conditional else right)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.value:
            record(node.target.id, ast.Constant(None) if id(node) in conditional else node.value)
        elif isinstance(node, (ast.AugAssign, ast.NamedExpr)) and isinstance(node.target, ast.Name):
            record(node.target.id, ast.Constant(None))
        elif node is not scope and isinstance(
            node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
        ):
            record(node.name, ast.Constant(None))
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                record(alias.asname or alias.name.split(".")[0], ast.Constant(None))
    return assigns


def _method_scope(method: ast.AST, inherited: dict[str, ast.AST]) -> dict[str, ast.AST]:
    args = method.args.posonlyargs + method.args.args + method.args.kwonlyargs
    args += [arg for arg in (method.args.vararg, method.args.kwarg) if arg is not None]
    return inherited | {arg.arg: ast.Constant(None) for arg in args}


def _method_arguments(method: ast.AST, call: ast.Call | None) -> dict[str, ast.AST] | None:
    """Bind a local bound-method call; starred or unknown arguments stay unresolved."""
    positional = method.args.posonlyargs + method.args.args
    bound = {
        arg.arg: value
        for arg, value in zip(
            positional[len(positional) - len(method.args.defaults) :],
            method.args.defaults,
            strict=True,
        )
    }
    bound.update(
        (arg.arg, value)
        for arg, value in zip(method.args.kwonlyargs, method.args.kw_defaults, strict=True)
        if value is not None
    )
    if call is None:
        return bound
    parameters = positional[1:]
    names = {arg.arg for arg in parameters + method.args.kwonlyargs}
    if (
        len(call.args) > len(parameters)
        or any(isinstance(arg, ast.Starred) for arg in call.args)
        or any(keyword.arg not in names for keyword in call.keywords)
    ):
        return None
    bound.update((arg.arg, value) for arg, value in zip(parameters, call.args, strict=False))
    bound.update((keyword.arg, keyword.value) for keyword in call.keywords)
    return bound


def _class_text(
    node: ast.AST,
    names: dict[str, ast.AST],
    members: dict[str, ast.AST],
    depth: int = 0,
) -> str | None:
    """Resolve the measured class URL forms, refusing opaque URL builders and cycles."""
    if depth > 12:
        return None

    def read(value: ast.AST) -> str | None:
        return _class_text(value, names, members, depth + 1)

    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.Name) and node.id in names:
        return read(names[node.id])
    if (
        isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id in {"self", "cls"}
        and node.attr in members
    ):
        return read(members[node.attr])
    if isinstance(node, ast.JoinedStr):
        return "".join(
            str(part.value) if isinstance(part, ast.Constant) else read(part.value) or "{}"
            for part in node.values
        )
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left, right = read(node.left), read(node.right)
        return left + right if left is not None and right is not None else None
    if isinstance(node, ast.IfExp):
        left, right = read(node.body), read(node.orelse)
        return left if left == right else None
    if isinstance(node, ast.Call):
        if isinstance(node.func, ast.Name) and node.func.id in {"quote", "urlencode"}:
            return "{}"
        if isinstance(node.func, ast.Attribute):
            if (
                isinstance(node.func.value, ast.Name)
                and node.func.value.id == "os"
                and node.func.attr == "getenv"
            ):
                default = (
                    node.args[1]
                    if len(node.args) > 1
                    else next(
                        (keyword.value for keyword in node.keywords if keyword.arg == "default"),
                        None,
                    )
                )
                return read(default) if default is not None else None
            if node.func.attr in {"rstrip", "lstrip", "strip"} and len(node.args) <= 1:
                value = read(node.func.value)
                chars = read(node.args[0]) if node.args else None
                if value is not None and (not node.args or chars is not None):
                    return getattr(value, node.func.attr)(chars)
    return None


def _assignment_pairs(target: ast.AST, value: ast.AST):
    if isinstance(target, (ast.Tuple, ast.List)):
        if isinstance(value, (ast.Tuple, ast.List)) and len(target.elts) == len(value.elts):
            for left, right in zip(target.elts, value.elts, strict=True):
                yield from _assignment_pairs(left, right)
        else:
            for left in target.elts:
                yield from _assignment_pairs(left, ast.Constant(None))
    else:
        yield target, value


def _member_assignments(method: ast.AST):
    conditional = _conditional_nodes(method)
    for node in _scope_nodes(method):
        pairs = []
        if isinstance(node, ast.Assign):
            for target in node.targets:
                pairs.extend(_assignment_pairs(target, node.value))
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            pairs.append((node.target, node.value))
        elif isinstance(node, ast.AugAssign):
            pairs.append((node.target, ast.Constant(None)))
        elif isinstance(node, ast.Delete):
            pairs.extend((target, ast.Constant(None)) for target in node.targets)
        for target, value in pairs:
            if (
                isinstance(target, ast.Attribute)
                and isinstance(target.value, ast.Name)
                and target.value.id == "self"
            ):
                yield target.attr, ast.Constant(None) if id(node) in conditional else value


def _class_members(
    cls: ast.ClassDef,
    module_names: dict[str, ast.AST],
    definition_names: dict[str, ast.AST],
) -> dict[str, ast.AST]:
    """Trace constructor attributes from that class's own factories, never another class."""
    raw_members = _local_assigns(ast.Module(body=cls.body, type_ignores=[]))
    members = {
        name: ast.Constant(_class_text(value, definition_names | raw_members, raw_members))
        for name, value in raw_members.items()
    }
    methods = {
        node.name: node
        for node in cls.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    init = methods.get("__init__")
    if init is None:
        for method in methods.values():
            for name, _value in _member_assignments(method):
                members[name] = ast.Constant(None)
        return members
    factories: list[dict[str, ast.AST]] = []
    for method in methods.values():
        if not any(
            isinstance(dec, ast.Name) and dec.id == "classmethod" for dec in method.decorator_list
        ):
            continue
        for node in _scope_nodes(method):
            if not (
                isinstance(node, ast.Return)
                and isinstance(node.value, ast.Call)
                and isinstance(node.value.func, ast.Name)
                and node.value.func.id == "cls"
            ):
                continue
            bindings = _method_arguments(init, node.value)
            if bindings is None:
                factories.append({})
            else:
                names = _method_scope(method, module_names | members) | _scope_assigns(method)
                factories.append(
                    {
                        name: ast.Constant(_class_text(value, names, members))
                        for name, value in bindings.items()
                    }
                )
    candidates: dict[str, list[str | None]] = {}
    for bindings in factories or [_method_arguments(init, None) or {}]:
        names = _method_scope(init, module_names | members) | bindings | _scope_assigns(init)
        for name, value in _member_assignments(init):
            candidates.setdefault(name, []).append(_class_text(value, names, members))
    for name, values in candidates.items():
        members[name] = ast.Constant(values[0] if len(set(values)) == 1 else None)
    # Do not claim that a URL member remains immutable after another method
    # writes it. Unsupported flow stays unresolved instead of reusing old data.
    for method in methods.values():
        if method is not init:
            for name, _value in _member_assignments(method):
                members[name] = ast.Constant(None)
    return members


def _http_transports(method: ast.AST) -> list[tuple[ast.Call, ast.AST | None]]:
    """Only expand methods that actually call a locally created httpx client."""
    clients: set[str] = set()
    for node in _scope_nodes(method):
        if not isinstance(node, (ast.With, ast.AsyncWith)):
            continue
        for item in node.items:
            constructor = item.context_expr
            if (
                isinstance(constructor, ast.Call)
                and isinstance(constructor.func, ast.Attribute)
                and isinstance(constructor.func.value, ast.Name)
                and constructor.func.value.id == "httpx"
                and constructor.func.attr in {"Client", "AsyncClient"}
                and isinstance(item.optional_vars, ast.Name)
            ):
                clients.add(item.optional_vars.id)
    found = []
    for node in _scope_nodes(method):
        if not (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id in clients
            and node.func.attr in {"get", "post", "put", "patch", "delete", "request", "stream"}
        ):
            continue
        index = 1 if node.func.attr in {"request", "stream"} else 0
        url = (
            node.args[index]
            if len(node.args) > index
            else next((keyword.value for keyword in node.keywords if keyword.arg == "url"), None)
        )
        found.append((node, url))
    return found


def _class_request(
    cls: ast.ClassDef,
    caller: ast.AST,
    line: int,
    url: ast.AST | None,
    names: dict[str, ast.AST],
    members: dict[str, ast.AST],
) -> dict:
    text = _class_text(url, names, members) if url is not None else None
    path, hosts = None, set()
    if text is not None:
        try:
            parsed = urlsplit(text)
            path = _literal_path(ast.Constant(parsed.path))
            if parsed.scheme in {"http", "https"} and parsed.hostname:
                hosts = {parsed.hostname}
        except ValueError:
            pass
    return {
        "path": path,
        "url": url,
        "scope": caller,
        "transport_hosts": hosts,
        "unresolved": f"{cls.name}.{caller.name}:{line}: unresolved transport URL",
    }


def _class_requests(tree: ast.Module) -> tuple[list[dict], set[int]]:
    """Follow one class-local wrapper hop to its HTTP URL, binding the real signature."""
    found: list[dict] = []
    expanded: set[int] = set()
    module_names = _local_assigns(tree)
    for cls in [node for node in ast.walk(tree) if isinstance(node, ast.ClassDef)]:
        methods = {
            node.name: node
            for node in cls.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        transports = {name: _http_transports(method) for name, method in methods.items()}
        if not any(transports.values()):
            continue
        definition_names = _local_assigns(
            ast.Module(
                body=[node for node in tree.body if node.lineno < cls.lineno], type_ignores=[]
            )
        )
        members = _class_members(cls, module_names, definition_names)
        for caller in methods.values():
            for call in _scope_nodes(caller):
                if not (
                    isinstance(call, ast.Call)
                    and isinstance(call.func, ast.Attribute)
                    and isinstance(call.func.value, ast.Name)
                    and call.func.value.id == "self"
                    and transports.get(call.func.attr)
                ):
                    continue
                helper = methods[call.func.attr]
                bindings = _method_arguments(helper, call)
                caller_names = _method_scope(caller, module_names) | _scope_assigns(caller)
                arguments = {
                    name: ast.Constant(_class_text(value, caller_names, members))
                    for name, value in (bindings or {}).items()
                }
                names = _method_scope(helper, module_names) | arguments | _scope_assigns(helper)
                for transport, url in transports[call.func.attr]:
                    expanded.add(id(transport))
                    found.append(
                        _class_request(
                            cls,
                            caller,
                            call.lineno,
                            url if bindings is not None else None,
                            names,
                            members,
                        )
                    )
        # A direct public method may have no local callers. Its unknown URL must
        # still fail when another method in the same module has a known route.
        for name, calls in transports.items():
            method = methods[name]
            names = _method_scope(method, module_names) | _scope_assigns(method)
            for transport, url in calls:
                if id(transport) not in expanded:
                    expanded.add(id(transport))
                    found.append(_class_request(cls, method, transport.lineno, url, names, members))
    return found, expanded


def _requests(tree: ast.Module) -> list[dict]:
    """كلُّ طلبٍ مقروءٍ في الوحدة: المسار، وتعبيرُ العنوان، والدالّةُ المحيطة (أو None).

    ① **عند موضع النداء:** الوسيطُ الأوّل لنداءٍ يبدو نداءَ نقل (`*_get_json`
       وأخواتها، أو `client.get`/`.post`/… من `httpx`).

    ② **ثابتٌ على مستوى الوحدة بشكل مسار** (`^/v1/…` · `^/api/…`). وهذا أُضيف
       **بعد أن أفلت عقدٌ حقيقيّ**: `irrigation_activation_gate` يحمل
       `GATE_ENFORCE_PATH = "/v1/activation/irr_f01_reservation/enforce"` ويبنيه
       داخل `_decision_url()`، فلا يُرى عند موضع النداء إطلاقاً.
    """
    found, expanded = _class_requests(tree)

    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        value = node.value
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            if _PATH_SHAPED.match(value.value):
                found.append({"path": normalise(value.value), "url": value, "scope": None})

    # مُزخرِفُ المسار (`@router.get("/api/v1/…")`) **إعلانٌ** على هذا الجانب لا طلبٌ
    # إلى الخدمة — وشكلُه النحويُّ نداءٌ باسم `get`، فكان يُقرأ طلباً. وُجِد حين صار
    # موجِّهُ المؤشّرات (M4، مراجعة v25) عميلاً لـindicators-service أيضاً.
    declarations = {
        id(dec)
        for fn in ast.walk(tree)
        if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef))
        for dec in fn.decorator_list
    }

    # الدالّةُ الأعمقُ المحيطةُ بكلّ نداء — منها تُقرأ الإسناداتُ المحلّيّة والمضيف.
    enclosing: dict[int, ast.AST] = {}

    def _mark(scope: ast.AST, owner: ast.AST | None) -> None:
        for child in ast.iter_child_nodes(scope):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                _mark(child, child)
            else:
                if owner is not None:
                    enclosing[id(child)] = owner
                _mark(child, owner)

    _mark(tree, None)
    local_cache: dict[int, dict[str, ast.AST]] = {}

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not node.args:
            continue
        if id(node) in declarations:
            continue
        if id(node) in expanded:
            continue
        func = node.func
        name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
        # **يُطابَق الاحتواءُ لا النهاية.** كان الشرطُ `endswith` فأفلت
        # `raster_get_json_sync` — لاحقةٌ واحدة (`_sync`) تُخفي مسارَين حقيقيَّين.
        is_wrapper = bool(_JSON_WRAPPER.search(name))
        is_httpx = name in {"get", "post", "put", "patch", "delete", "request", "stream"}
        if not (is_wrapper or is_httpx):
            continue
        scope = enclosing.get(id(node))
        assigns = None
        if scope is not None:
            assigns = local_cache.setdefault(id(scope), _local_assigns(scope))
        # `client.request("GET", url)` يضع الفعلَ أوّلاً والعنوانَ ثانياً.
        for arg in node.args[:2]:
            path = _literal_path(arg, assigns)
            if path:
                found.append({"path": path, "url": arg, "scope": scope})
                break
    return found


def requested_paths(source: str) -> set[str]:
    """المساراتُ التي يطلبها العميل — من موضعين مقيسين لا من كلّ سلسلة.

    وسلسلةٌ في رسالة خطأ أو تعليقٍ تبقى خارج الجرد: الشرطُ موضعُ نداءٍ أو ثابتٌ
    مُسمًّى على مستوى الوحدة، لا أيُّ سلسلةٍ تبدأ بشرطة.
    """
    return {item["path"] for item in _requests(ast.parse(source)) if item["path"] is not None}


def _literal_options(node: ast.AST | None, aliases: dict[str, ast.AST], depth: int = 0):
    if depth > 8:
        return None
    if isinstance(node, ast.Name) and node.id in aliases:
        return _literal_options(aliases[node.id], aliases, depth + 1)
    if not isinstance(node, ast.Subscript):
        return None
    kind = node.value.id if isinstance(node.value, ast.Name) else getattr(node.value, "attr", "")
    values = node.slice.elts if isinstance(node.slice, ast.Tuple) else [node.slice]
    if kind == "Annotated" and values:
        return _literal_options(values[0], aliases, depth + 1)
    if kind != "Literal" or not values:
        return None
    if not all(
        isinstance(value, ast.Constant)
        and isinstance(value.value, str)
        and value.value
        and not any(char in value.value for char in "/{}")
        for value in values
    ):
        return None
    return {value.value for value in values}


def _literal_declared_paths(source: str) -> tuple[set[str], set[str]]:
    """Expand only explicitly enumerated path values; never accept arbitrary operations."""
    tree = ast.parse(source)
    found: set[str] = set()
    replaced: set[str] = set()
    unrestricted: set[str] = set()
    for method in ast.walk(tree):
        if not isinstance(method, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        aliases = (
            _local_assigns(
                ast.Module(
                    body=[node for node in tree.body if node.lineno < method.lineno],
                    type_ignores=[],
                )
            )
            if method in tree.body
            else {}
        )
        for decorator in method.decorator_list:
            if not (
                isinstance(decorator, ast.Call)
                and isinstance(decorator.func, ast.Attribute)
                and isinstance(decorator.func.value, ast.Name)
                and decorator.func.value.id in {"app", "router"}
                and decorator.func.attr in {"get", "post", "put", "patch", "delete"}
                and decorator.args
                and isinstance(decorator.args[0], ast.Constant)
                and isinstance(decorator.args[0].value, str)
            ):
                continue
            paths = {decorator.args[0].value}
            expanded = False
            for arg in method.args.posonlyargs + method.args.args + method.args.kwonlyargs:
                token = "{" + arg.arg + "}"
                options = _literal_options(arg.annotation, aliases)
                if options and any(token in path for path in paths):
                    expanded = True
                    if len(paths) * len(options) > 256:
                        paths = set()
                        break
                    paths = {path.replace(token, option) for path in paths for option in options}
            if expanded:
                found.update(normalise(path) for path in paths)
                replaced.add(normalise(decorator.args[0].value))
            else:
                unrestricted.add(normalise(decorator.args[0].value))
    return found, replaced - unrestricted


def declared_paths(service_dir: Path) -> set[str]:
    declared: set[str] = set()
    for file in sorted(service_dir.rglob("*.py")):
        text = file.as_posix()
        if "__pycache__" in text or "/tests/" in text:
            continue
        source = file.read_text(encoding="utf-8", errors="ignore")
        paths = {normalise(m) for m in _DECLARED.findall(source)}
        if "Literal" in source:
            concrete, replaced = _literal_declared_paths(source)
            paths = (paths - replaced) | concrete
        declared |= paths
    return declared


def compose_hosts() -> tuple[dict[str, Path], set[str]]:
    """كلُّ مضيفٍ في ``docker-compose*.yml`` ⇒ مجلّدُ مصدره (من ``build``).

    مفتاحُ الخدمة في compose هو اسمُ DNS الذي تناديه العملاء. خدمةٌ بلا ``build``
    (صورةٌ جاهزة: ollama · vllm · postgres) **خارجيّةٌ** — لا مصدرَ في الشجرة يُقابَل.
    """
    import yaml

    hosts: dict[str, Path] = {}
    image_only: set[str] = set()
    for compose in sorted(ROOT.glob("docker-compose*.yml")):
        data = yaml.safe_load(compose.read_text(encoding="utf-8")) or {}
        for key, spec in (data.get("services") or {}).items():
            build = (spec or {}).get("build")
            if build is None:
                image_only.add(key)
                continue
            context = build if isinstance(build, str) else build.get("context", ".")
            dockerfile = None if isinstance(build, str) else build.get("dockerfile")
            source = (
                (compose.parent / context / dockerfile).parent
                if dockerfile
                else (compose.parent / context)
            )
            hosts.setdefault(key, source.resolve())
    return hosts, image_only - set(hosts)


def _hosts_in(node: ast.AST, bindings: dict[str, set[str]]) -> set[str]:
    """المضيفون الذين يُشير إليهم تعبير: سلسلةُ عنوانٍ حرفيّة، أو اسمٌ مربوطٌ بمضيف."""
    hosts: set[str] = set()
    for sub in ast.walk(node):
        if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
            hosts |= set(_INTERNAL_HOST.findall(sub.value))
        elif isinstance(sub, ast.Name):
            hosts |= bindings.get(sub.id, set())
    return hosts


def _bindings(scope: ast.AST, inherited: dict[str, set[str]]) -> dict[str, set[str]]:
    """اسم ⇒ مضيفون، بنقطةٍ ثابتة: ``BASE = "http://sahool-x…"`` ثمّ ``def url(): return
    os.getenv(…, BASE)`` ثمّ ``SOIL_URL = url()`` — كلُّها تُربَط بالمضيف نفسه."""
    bound = dict(inherited)
    assigns = _local_assigns(scope)
    functions = (
        [n for n in scope.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
        if isinstance(scope, ast.Module)
        else []
    )
    for _ in range(4):
        changed = False
        for name, value in assigns.items():
            hosts = _hosts_in(value, bound)
            if hosts and hosts != bound.get(name):
                bound[name] = hosts
                changed = True
        for fn in functions:
            hosts: set[str] = set()
            for ret in ast.walk(fn):
                if isinstance(ret, ast.Return) and ret.value is not None:
                    hosts |= _hosts_in(ret.value, bound)
            if hosts and hosts != bound.get(fn.name):
                bound[fn.name] = hosts
                changed = True
        if not changed:
            break
    return bound


def scan_module(source: str, known: set[str]) -> dict:
    """يقرأ وحدةً عميلة: مضيفوها في النطاق، ومساراتُ كلٍّ منهم، وما لم يُنسَب.

    وحدةٌ بمضيفٍ واحد: كلُّ طلبٍ لها (السلوكُ السابق — الغلافُ يحمل العنوانَ داخله).
    وحدةٌ بأكثر: يُنسَب الطلبُ إلى المضيف الذي يُشير إليه تعبيرُ عنوانه **وحدَه**؛
    وغيرُ ذلك ``unattributed`` ⇒ فشل. لا إسقاطَ صامتاً للوحدة كلّها.
    """
    tree = ast.parse(source)
    module_bound = _bindings(tree, {})
    hosts = set(_INTERNAL_HOST.findall(source)) & known
    per_host: dict[str, set[str]] = {host: set() for host in hosts}
    unattributed: list[str] = []
    scope_bound: dict[int, dict[str, set[str]]] = {}
    for item in _requests(tree):
        if "transport_hosts" in item:
            target = item["transport_hosts"] & hosts
            if item["path"] is not None and len(target) == 1:
                per_host[target.pop()].add(item["path"])
            elif hosts:
                unattributed.append(item["path"] or item["unresolved"])
            continue
        if len(hosts) == 1:
            per_host[next(iter(hosts))].add(item["path"])
            continue
        scope = item["scope"]
        bound = module_bound
        if scope is not None:
            bound = scope_bound.setdefault(id(scope), _bindings(scope, module_bound))
        target = _hosts_in(item["url"], bound) & hosts
        if len(target) == 1:
            per_host[target.pop()].add(item["path"])
        elif hosts:
            unattributed.append(item["path"])
    return {"hosts": hosts, "requested": per_host, "unattributed": sorted(set(unattributed))}


def discover_contracts() -> dict[str, dict]:
    """يُشتقّ العملاءُ وخدماتُهم من الشجرة وcompose — لا من قائمةٍ مكتوبة.

    القائمةُ المكتوبة تبيت: عميلٌ جديدٌ يدخل غداً فلا يدخل النطاق معه، ويبقى
    الحارسُ أخضرَ عن سؤالٍ لم يعد يطرحه. والمفتاحُ ملفُّ العميل، والقيمةُ مضيفوه
    المبنيّون في compose بمجلّدات مصادرهم (مضيفٌ أو أكثر).
    """
    known, _image_only = compose_hosts()
    contracts: dict[str, dict] = {}
    for client_dir in CLIENT_DIRS:
        for file in sorted(client_dir.rglob("*.py")):
            if "__pycache__" in file.as_posix() or "tests" in file.relative_to(client_dir).parts:
                continue
            source = file.read_text(encoding="utf-8", errors="ignore")
            hosts = set(_INTERNAL_HOST.findall(source)) & set(known)
            if not hosts:
                continue
            contracts[file.relative_to(ROOT).as_posix()] = {
                "services": {host: known[host] for host in sorted(hosts)},
            }
    return contracts


def unknown_hosts() -> list[str]:
    """مضيفٌ داخليٌّ تناديه وحدةٌ ولا يعرفه أيُّ compose — اسمٌ لا يُحَلّ ⇒ فشلٌ حتميّ."""
    known, image_only = compose_hosts()
    missing: list[str] = []
    for client_dir in CLIENT_DIRS:
        for file in sorted(client_dir.rglob("*.py")):
            if "__pycache__" in file.as_posix() or "tests" in file.relative_to(client_dir).parts:
                continue
            for host in sorted(set(_INTERNAL_HOST.findall(file.read_text(encoding="utf-8")))):
                if host not in known and host not in image_only:
                    missing.append(f"{file.relative_to(ROOT).as_posix()}: {host}")
    return missing


# وحداتٌ تحمل عنوانَ خدمةٍ ولا مسارَ ثابتاً لها — **وسببُ كلٍّ مكتوب**.
#
# وهذا **حدٌّ مُعلَنٌ لا إعفاءٌ مريح.** الفحصُ الساكن لا يُميّز «مُمرِّرٌ ديناميّ
# بلا عقدٍ ثابت» من «مسارٌ حرفيٌّ عجز مستخرِجي عن رؤيته». فالقائمةُ مغلقةٌ
# بالمساواة: وحدةٌ جديدةٌ بصفر مسارٍ **تُفشِل الحارس** حتّى يقرّر إنسانٌ أيَّ
# الحالتين هي. وحذفُ مدخلٍ صار له مسارٌ يُفشِله أيضاً. **ومنذ W1-02 لا يُعفى
# المُمرِّرُ من الفحص:** قوائمُ سماحه ومساراتُه المُقالَبة تُقابَل بإعلان كلّ خدمة
# (``proxy_coverage``)، ومضيفٌ فيه بلا قائمةٍ ولا قالبٍ **يُفشِل الحارس**.
PATH_LESS_BY_DESIGN = {
    "services/sahool-platform/api/routers/service_proxy.py": (
        "مُمرِّرٌ عامّ: المسارُ مُعامِلُ تشغيلٍ (`/api/soil/{path:path}`) يُعاد بناؤه "
        "من طلب المستخدم، فلا مسارَ ثابتاً يُقابَل بإعلان الخدمة. العقدُ هنا "
        "«مرّر ما وصل» مقيَّداً بقائمة سماح، وقائمةُ السماح هي ما يُقابَل (proxy_coverage)."
    ),
}

# قائمةُ سماح المُمرِّر: ثابتُ وحدةٍ ``_<X>_ROUTES`` = صفوفٌ أوّلُها نمطُ مسار.
_ROUTES_CONSTANT = re.compile(r"^_[A-Z0-9_]*ROUTES$")
_ALTERNATION = re.compile(r"\(\?:([^()]*)\)")
_SEGMENT_CLASS = re.compile(r"\[[^\]]*\]\+")
_REGEX_META = re.compile(r"[()\[\]*+?|\\^$]")


def expand_pattern(pattern: str) -> list[str] | None:
    """يفكّ نمطَ السماح إلى مساراتٍ محدّدة: كلُّ ``(?:a|b)`` بدائلُه، وكلُّ ``[…]+`` مقطعٌ
    متغيّر ``{}``. نمطٌ يبقى فيه رمزٌ آخر ⇒ ``None`` (يُفحَص بالمطابقة لا بالفكّ)."""
    results = [pattern]
    for _ in range(8):
        expanded: list[str] = []
        progressed = False
        for text in results:
            match = _ALTERNATION.search(text)
            if not match:
                expanded.append(text)
                continue
            progressed = True
            for option in match.group(1).split("|"):
                expanded.append(text[: match.start()] + option + text[match.end() :])
        results = expanded
        if not progressed:
            break
    concrete = []
    for text in results:
        text = _SEGMENT_CLASS.sub("{}", text)
        if _REGEX_META.search(text):
            return None
        concrete.append(normalise("/" + text.lstrip("/")))
    return concrete


def _segment_match(requested: str, declared: str) -> bool:
    """``{}`` في المطلوب مقطعٌ متغيّر يطابق أيَّ مقطعٍ مُعلَن؛ والباقي حرفيّ."""
    want, have = requested.strip("/").split("/"), declared.strip("/").split("/")
    return len(want) == len(have) and all(
        w == "{}" or w == h for w, h in zip(want, have, strict=True)
    )


def proxy_coverage(source: str, known: set[str]) -> dict[str, list[str]]:
    """مضيف ⇒ المساراتُ التي يكشفها المُمرِّر إليه: من قوائم السماح ومن ``path=`` المُقالَب.

    القائمةُ تُنسَب إلى المضيف بالدالّة التي تحملهما معاً (مباشرةً أو عبر مُساعدٍ
    واحد، مثل ``_authorize_soil_path``). نمطٌ لا يُفَكّ يُعاد كما هو (``re:…``).
    """
    tree = ast.parse(source)
    module_bound = _bindings(tree, {})
    routes: dict[str, list[str]] = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if not (isinstance(target, ast.Name) and _ROUTES_CONSTANT.match(target.id)):
            continue
        if not isinstance(node.value, ast.Tuple):
            continue
        patterns = []
        for row in node.value.elts:
            if isinstance(row, ast.Tuple) and row.elts:
                first = row.elts[0]
                if isinstance(first, ast.Constant) and isinstance(first.value, str):
                    patterns.append(first.value)
        routes[target.id] = patterns
    functions = {
        n.name: n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
    }

    def _names(fn: ast.AST) -> set[str]:
        return {n.id for n in ast.walk(fn) if isinstance(n, ast.Name)}

    coverage: dict[str, list[str]] = {}
    for fn in functions.values():
        bound = _bindings(fn, module_bound)
        fn_hosts: set[str] = set()
        for sub in ast.walk(fn):
            if isinstance(sub, ast.Assign):
                fn_hosts |= _hosts_in(sub.value, bound)
        fn_hosts &= known
        if len(fn_hosts) != 1:
            continue
        host = next(iter(fn_hosts))
        names = _names(fn)
        for helper in names & set(functions):
            names |= _names(functions[helper])
        for constant in sorted(names & set(routes)):
            for pattern in routes[constant]:
                concrete = expand_pattern(pattern)
                coverage.setdefault(host, []).extend(concrete or [f"re:{pattern}"])
        for call in ast.walk(fn):
            if not isinstance(call, ast.Call):
                continue
            for keyword in call.keywords:
                if keyword.arg == "path" and not isinstance(keyword.value, ast.Name):
                    text = _render(keyword.value)
                    if text:
                        coverage.setdefault(host, []).append(normalise("/" + text.lstrip("/")))
    return {host: sorted(set(paths)) for host, paths in coverage.items()}


def proxied_undeclared(exposed: list[str], declared: set[str]) -> list[str]:
    """مسارٌ يكشفه المُمرِّر ولا تُعلنه الخدمة ⇒ ٤٠٤ حتميّ خلف قائمة سماحٍ صحيحة الشكل."""
    missing = []
    for path in exposed:
        if path.startswith("re:"):
            pattern = re.compile(path[3:])
            if not any(pattern.fullmatch(d.strip("/").replace("{}", "x")) for d in declared):
                missing.append(path)
        elif not any(_segment_match(path, d) for d in declared):
            missing.append(path)
    return missing


def classify(client: str, requested: set[str], declared: set[str]) -> dict:
    """يُصنّف عقداً واحداً — **دالّةٌ نقيّةٌ عمداً**.

    كانت هذه الأسطرُ داخل `audit()` تقرأ الشجرة، فلم يكن للعمى شاهدٌ **موجب**:
    اختبارُه أكّد أنّ القائمة فارغةٌ على شجرةٍ سليمة، وهي تبقى فارغةً أيضاً لو
    عُطِّل الكشفُ رأساً. **فالطفرةُ التي تُطفئه نجت**. فأُخرِج التصنيفُ نقيّاً كي
    يُقاس بمُدخَلٍ مُصطنَع: عقدٌ بلا مسارٍ **يُعلَن أعمى** بالإيجاب.
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
        "unattributed": [],
        "unknown_hosts": unknown_hosts(),
    }
    known, _image_only = compose_hosts()
    declared_cache: dict[Path, set[str]] = {}
    path_less_modules: set[str] = set()
    for client, meta in discover_contracts().items():
        source = (ROOT / client).read_text(encoding="utf-8")
        scan = scan_module(source, set(known))
        proxied = proxy_coverage(source, set(known)) if client in PATH_LESS_BY_DESIGN else {}
        report["unattributed"] += [f"{client}: {p}" for p in scan["unattributed"]]
        if not any(scan["requested"].values()) and not scan["unattributed"]:
            path_less_modules.add(client)
        for host, service_dir in meta["services"].items():
            service = service_dir.relative_to(ROOT).as_posix()
            declared = declared_cache.setdefault(service_dir, declared_paths(service_dir))
            requested = scan["requested"].get(host, set())
            single = len(meta["services"]) == 1 or client in PATH_LESS_BY_DESIGN
            label = client if single else f"{client} → {host}"
            verdict = classify(label, requested, declared)
            undeclared = verdict["undeclared"] + proxied_undeclared(proxied.get(host, []), declared)
            report["contracts"][f"{client} → {host}"] = {
                "service": service,
                "requested": len(requested),
                "proxied": len(proxied.get(host, [])),
                "declared": len(declared),
                "undeclared": undeclared,
            }
            blind = verdict["blind"]
            if client in PATH_LESS_BY_DESIGN and not proxied.get(host):
                # مُمرِّرٌ إلى مضيفٍ بلا قائمة سماحٍ ولا قالبٍ مقروء — صفرُ فحصٍ يمرّ أخضر.
                blind = blind + [f"{client} → {host}: لا قائمةَ سماحٍ مقروءة"]
            report["blind_clients"] += blind
            report["undeclared"] += [f"{client} → {service}: {p}" for p in undeclared]
    report["path_less"] = sorted(path_less_modules)

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
        print(
            f"  {client} ({data['service']}): يطلب {data['requested']}"
            f" · يُمرِّر {data.get('proxied', 0)} · تُعلن {data['declared']}"
        )

    failed = False
    if report.get("unknown_hosts"):
        failed = True
        print("\ncross_service_path_contract_guard FAILED — مضيفٌ داخليٌّ لا يعرفه أيُّ compose:")
        for entry in report["unknown_hosts"]:
            print(f"  ✗ {entry}")

    if report.get("unattributed"):
        failed = True
        print("\ncross_service_path_contract_guard FAILED — طلبٌ في وحدةٍ متعدّدة المضيفين لا يُنسَب:")
        for entry in report["unattributed"]:
            print(f"  ✗ {entry}")
        print("  اربط العنوانَ باسمٍ يحمل عنوانَ الخدمة (``X_URL = os.getenv(…, 'http://…')``).")

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
        print(json.dumps(audit(), ensure_ascii=False, indent=2))
        raise SystemExit(0)
    raise SystemExit(main())
