#!/usr/bin/env python3
"""حسمُ حوافِّ الجرد إلى أدلّةِ مصدر — أو إبقاؤها مجهولةً بصدق.

``AN-UNMEASURED-SURFACE-SERIALISED-AS-AN-EMPTY-LIST-READS-AS-NO-RELATIONS-01``
جعلت الأسطحَ تقول «لم أُقَس». وهذه الوحدةُ تقيس **صنفاً واحداً** منها: حافّةَ
«الواجهةُ تستهلك قدرةَ خدمة»، وهي الأغلبُ الساحقُ من الحوافّ المُعلَنة.

**والحسمُ هنا اشتقاقٌ من أربع خطوات، كلُّها في الشجرة ولا واحدةَ منها مكتوبةٌ بيد:**

1. ``frontend/src/config/endpoints.ts`` — الاسمُ المنطقيّ ⇒ بادئةُ العميل
   (``raster`` ⇒ ``/api/raster``).
2. ``frontend/src/services/api/client.ts`` — نسخةُ axios ⇒ تلك البادئة
   (``rasterApi`` ⇒ ``RASTER_URL`` ⇒ ``ENDPOINTS.raster``).
3. موضعُ النداء — ``rasterApi.get('/v1/cog/validate')``.
4. ``frontend/nginx.conf`` — البادئةُ ⇒ مُجرىً أعلى ⇒ مكوّنٌ ومسارٌ داخليّ.

فالحافّةُ لا تُرقّى إلى ``resolved`` إلّا بسلسلةٍ كاملة، ويحمل دليلُها **سطرَ كلِّ
خطوة**. وما انقطعت سلسلتُه يبقى ``unresolved`` — ولا يُقال عنه إنّه غيرُ موجود.

**وحدُّ صدقٍ يُعلَن في المصنوعة لا في التعليق:** هذا ماسحٌ ساكن. نداءٌ يُبنى مسارُه
في وقت التشغيل (تسلسلُ نصوصٍ أو متغيّر) **لا يراه**، فغيابُ الدليل غيابُ رؤيةٍ لا
غيابُ علاقة. ولذلك يُصدَّر ``scanner_blind_spots`` بعددِه: قارئٌ يرى عددَ المحسوم
بلا أن يرى حجمَ ما لا يبلغه الماسحُ أصلاً يقرأ الباقيَ عطلاً وهو قد يكون رؤية.

**ولا عددَ في هذا النصّ عمداً.** الأعدادُ كلُّها في المصنوعة، تُشتقُّ عند كلّ تشغيل —
ورقمٌ يُكتب في توثيقٍ يبيت عن مقياسه، وهو الصنفُ المُسجَّل
``A-HAND-WRITTEN-COUNT-IN-THE-JOURNAL-DRIFTS-FROM-ITS-OWN-MEASUREMENT-01``.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]

#: نسخةُ axios ⇒ الاسمُ المنطقيّ في `ENDPOINTS`. مُشتقٌّ من `client.ts` نفسِه.
_CLIENT_DEF = re.compile(r"^export const ([A-Za-z0-9_]+Api)\s*=\s*makeClient\(([A-Z0-9_]+)\)", re.M)
_CONST_DEF = re.compile(r"^const ([A-Z0-9_]+)\s*=\s*ENDPOINTS\.([A-Za-z0-9_]+)", re.M)
#: `raster: resolveHttpBase('VITE_…', '/api/raster', …)` ⇒ البادئةُ المستعمَلة في المتصفّح.
_ENDPOINT_DEF = re.compile(
    r"^\s+([a-z][A-Za-z0-9_]*):\s*resolveHttpBase\(\s*'[^']*'\s*,\s*'([^']*)'", re.M
)
# Match only on a lexical code mask; strings/comments are never executable evidence.
_ANY_CALL = re.compile(
    r"(?<![\w$.])([A-Za-z_$][\w$]*)\s*\.\s*(get|post|put|patch|delete|head|options)\s*(?=[(<])"
)


def _is_direct_receiver(code: str, start: int) -> bool:
    """Reject property-qualified receivers even when trivia separates the tokens.

    Comments are whitespace in the lexical code mask, so checking the previous
    non-whitespace token rejects `obj . clientApi.get(...)` and the equivalent
    newline/comment forms without treating a bare imported identifier as a property.
    """
    return not code[:start].rstrip().endswith(".")


_PATH = re.compile(r"/[A-Za-z0-9/_{}.-]*")
_PARAMETER = re.compile(r"\$\{[A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)*\}")
#: `${fieldId}` · `${tile!.z}` · `${a.b!}` — عضوٌ بسيط، وتوكيدُ TypeScript غيرِ الفارغ (`!`) لا يغيّر القيمة.
_MEMBER = re.compile(r"[A-Za-z_$][\w$]*!?(?:\.[A-Za-z_$][\w$]*!?)*")


def _expression_end(raw: str, start: int) -> int | None:
    """نهايةُ `${…}` (موضعُ `}` المطابِقة) مع تخطّي النصوص داخلها؛ ``None`` إن لم تُغلق."""
    depth, i = 1, start
    while i < len(raw):
        if raw[i] in "\"'`":
            i = _literal_end(raw, i)
            continue
        depth += (raw[i] == "{") - (raw[i] == "}")
        if depth == 0:
            return i
        i += 1
    return None


def _encoded_value(expr: str) -> bool:
    """`encodeURIComponent(<أيُّ تعبير>)` بقوسَين متطابقَين يحيطان بالتعبير كلِّه — قيمةٌ مُرمَّزةٌ لمقطعٍ واحد."""
    if not (expr.startswith("encodeURIComponent(") and expr.endswith(")")):
        return False
    depth, opening = 0, len("encodeURIComponent")
    for index in range(opening, len(expr)):
        depth += (expr[index] == "(") - (expr[index] == ")")
        if depth == 0 and index != len(expr) - 1:
            return False  # `encodeURIComponent(a) + b`: القوسُ الأوّل لا يحيط بالتعبير كلِّه
    return depth == 0


def template_path(raw: str) -> str | None:
    """قالبُ مسارٍ ⇒ مسارٌ بوسائط `{}`، أو ``None`` إن تعذّر القولُ ما المسار.

    يُقبل: عضوٌ بسيط في أيّ موضع (كما سبق، و`!` غيرُ الفارغ)، و`encodeURIComponent(…)`
    **يملأ مقطعاً كاملاً** (بين `/` و`/` أو `?` أو النهاية): الترميزُ يمنع أن تحمل القيمةُ
    `/` فلا تُغيّر عددَ المقاطع. ويُسقَط ما بعد `?` — الاستعلامُ ليس جزءاً من المسار المطابَق.
    وما سوى ذلك (نداءٌ آخر، تسلسلٌ، لاحقةٌ ديناميّة) يبقى غيرَ مقروء: عمىً معلَن لا تخمين.
    """
    out: list[str] = []
    i = 0
    while i < len(raw):
        if raw.startswith("${", i):
            end = _expression_end(raw, i + 2)
            if end is None:
                return None
            expr = raw[i + 2 : end].strip()
            before, after = "".join(out), raw[end + 1 :]
            whole_segment = before.endswith("/") and (after == "" or after[0] in "/?")
            if not (_MEMBER.fullmatch(expr) or (whole_segment and _encoded_value(expr))):
                return None
            out.append("{}")
            i = end + 1
        else:
            out.append(raw[i])
            i += 1
    return "".join(out).split("?", 1)[0]


_UPSTREAM = re.compile(r"^\s*upstream\s+([A-Za-z0-9_]+)\s*\{")
_SERVER = re.compile(r"^\s*server\s+([A-Za-z0-9.-]+):\d+")
_LOCATION = re.compile(r"^\s*location\s+(?:(=|\^~|~\*)\s+)?(\S+)\s*\{")
_PROXY_PASS = re.compile(r"^\s*proxy_pass\s+http://([A-Za-z0-9_]+)([^;\s]*);")
_REWRITE = re.compile(r"^\s*rewrite\s+(\S+)\s+(\S+)\s+break;")


def normalise(path: str) -> str:
    """مسارٌ مُطبَّع: الوسائطُ تصير `{}`، والشُّرَطُ المكرّرة واحدة.

    `${fieldId}` و`{field_id}` اسمان لشيءٍ واحد عند المقارنة — والفرقُ بينهما
    لغةٌ لا دلالة.
    """
    path = re.sub(r"\$\{[^}]*\}", "{}", path)
    path = re.sub(r"\{[^}]*\}", "{}", path)
    path = re.sub(r"/{2,}", "/", path)
    return path.rstrip("/") or "/"


def client_prefixes(root: Path = ROOT) -> dict[str, dict[str, Any]]:
    """`rasterApi` ⇒ بادئتُه وموضعُ تعريفها — الخطوتان ١ و٢."""
    endpoints_src = root / "frontend/src/config/endpoints.ts"
    client_src = root / "frontend/src/services/api/client.ts"
    if not endpoints_src.exists() or not client_src.exists():
        return {}
    endpoints_text = endpoints_src.read_text(encoding="utf-8")
    client_text = client_src.read_text(encoding="utf-8")

    prefix_of_name = {}
    for match in _ENDPOINT_DEF.finditer(endpoints_text):
        line = endpoints_text[: match.start()].count("\n") + 1
        prefix_of_name[match.group(1)] = (match.group(2), line)
    const_to_name = dict(_CONST_DEF.findall(client_text))

    result: dict[str, dict[str, Any]] = {}
    for match in _CLIENT_DEF.finditer(client_text):
        instance, const = match.group(1), match.group(2)
        logical = const_to_name.get(const)
        if logical is None or logical not in prefix_of_name:
            continue
        prefix, endpoint_line = prefix_of_name[logical]
        result[instance] = {
            "prefix": prefix,
            "endpoints_line": f"frontend/src/config/endpoints.ts:{endpoint_line}",
            "client_line": f"frontend/src/services/api/client.ts:"
            f"{client_text[: match.start()].count(chr(10)) + 1}",
        }
    return result


def gateway(root: Path = ROOT, components: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """بادئةُ عميلٍ ⇒ (مكوّن، مسارٌ داخليّ) — الخطوةُ ٤، مقروءةً من `nginx.conf`.

    واسمُ المضيف يُترجَم إلى معرّف مكوّنٍ من **جرد المكوّنات نفسِه** (الأسماءُ
    المستعارة وخدماتُ compose)، لا من جدولٍ يدويٍّ ينحرف عن الشجرة.
    """
    conf = root / "frontend/nginx.conf"
    if not conf.exists():
        return {"routes": [], "upstreams": {}}
    host_to_component: dict[str, str] = {}
    for component in components or []:
        names = [component["component_id"], *component["aliases"], *component["compose_services"]]
        for name in names:
            host_to_component.setdefault(name, component["component_id"])
            host_to_component.setdefault(f"sahool-{name}", component["component_id"])

    upstreams: dict[str, str] = {}
    routes: list[dict[str, Any]] = []
    current_upstream: str | None = None
    location: tuple[str, int] | None = None
    for number, line in enumerate(conf.read_text(encoding="utf-8").splitlines(), 1):
        found = _UPSTREAM.match(line)
        if found:
            current_upstream = found.group(1)
            continue
        found = _SERVER.match(line)
        if found and current_upstream:
            upstreams[current_upstream] = host_to_component.get(found.group(1), "")
            current_upstream = None
            continue
        found = _LOCATION.match(line)
        if found:
            location = (found.group(2), number, found.group(1) == "=")
            continue
        if location is None:
            continue
        found = _REWRITE.match(line)
        if found:
            routes.append(
                {
                    "kind": "rewrite",
                    "client": location[0],
                    "pattern": found.group(1),
                    "replacement": found.group(2),
                    "line": f"frontend/nginx.conf:{number}",
                }
            )
            continue
        found = _PROXY_PASS.match(line)
        if found:
            routes.append(
                {
                    "kind": "proxy",
                    "client": location[0],
                    "upstream": found.group(1),
                    "service_path": found.group(2) or "/",
                    "line": f"frontend/nginx.conf:{number}",
                    **({"exact": True} if location[2] else {}),
                }
            )
    return {"routes": routes, "upstreams": upstreams}


def _literal_end(text: str, start: int) -> int:
    """Skip a JS literal, including nested literals in template expressions."""
    quote = text[start]
    i = start + 1
    while i < len(text):
        if text[i] == "\\":
            i += 2
        elif text[i] == quote:
            return i + 1
        elif quote == "`" and text.startswith("${", i):
            i += 2
            depth = 1
            while i < len(text) and depth:
                if text[i] in "\"'`":
                    i = _literal_end(text, i)
                elif text.startswith("/*", i):
                    end = text.find("*/", i + 2)
                    i = len(text) if end < 0 else end + 2
                elif text.startswith("//", i):
                    end = text.find("\n", i + 2)
                    i = len(text) if end < 0 else end
                else:
                    depth += (text[i] == "{") - (text[i] == "}")
                    i += 1
        else:
            i += 1
    return len(text)


class _UnparsedSource(ValueError):
    """A lexical boundary is ambiguous: do not infer executable evidence."""


class _CodeMask:
    """Bounded lexical mask with separate code, JSX-text and template modes.

    This does not prove import binding or execution/reachability. Unsupported or
    unterminated constructs fail closed for the file and are reported separately.
    """

    _JSX_OPEN = re.compile(r"<([A-Za-z_$][\w$.:\-]*(?=[\s/><])|(?=>))")

    _JSX_CLOSE = re.compile(r"</([A-Za-z_$][\w$.:\-]*|)\s*>")
    _GENERIC_ARROW = re.compile(r"<[A-Za-z_$][\w$]*(?:\s+extends\b[^<>]*|,)\s*>\s*\(")

    def __init__(self, text: str, *, jsx: bool):
        self.text = text
        self.mask = list(text)
        self.jsx_enabled = jsx
        self.depth = 0
        self._context_end = 0
        self._last_significant = -1
        self._control_parentheses: list[bool] = []
        self._last_control_close = False

    def hide(self, start: int, end: int) -> None:
        for i in range(start, end):
            if self.text[i] != "\n":
                self.mask[i] = " "

    def comment(self, i: int) -> int:
        if self.text.startswith("//", i):
            end = self.text.find("\n", i + 2)
            end = len(self.text) if end < 0 else end
        else:
            end = self.text.find("*/", i + 2)
            if end < 0:
                raise _UnparsedSource("unterminated_comment")
            end += 2
        self.hide(i, end)
        return end

    def quoted(self, i: int) -> int:
        quote = self.text[i]
        start = i
        i += 1
        while i < len(self.text):
            if self.text[i] == "\\":
                i += 2
            elif self.text[i] == quote:
                self.hide(start, i + 1)
                self.mask[start] = self.text[start]
                self.mask[i] = self.text[i]
                return i + 1
            elif self.text[i] in "\r\n":
                raise _UnparsedSource("unterminated_quoted_literal")
            else:
                i += 1
        raise _UnparsedSource("unterminated_quoted_literal")

    def template(self, i: int) -> int:
        self.mask[i] = "`"
        i += 1
        while i < len(self.text):
            if self.text[i] == "\\":
                end = min(i + 2, len(self.text))
                self.hide(i, end)
                i = end
            elif self.text[i] == "`":
                self.mask[i] = "`"
                return i + 1
            elif self.text.startswith("${", i):
                self.hide(i, i + 1)
                i = self.code(i + 2, stop_at_brace=True)
            else:
                self.hide(i, i + 1)
                i += 1
        raise _UnparsedSource("unterminated_template_literal")

    def regex(self, i: int) -> int:
        start = i
        in_class = False
        i += 1
        while i < len(self.text) and self.text[i] not in "\r\n":
            if self.text[i] == "\\":
                i += 2
                continue
            if self.text[i] == "[":
                in_class = True
            elif self.text[i] == "]":
                in_class = False
            elif self.text[i] == "/" and not in_class:
                self.hide(start, i + 1)
                self.mask[start] = self.text[start]
                self.mask[i] = self.text[i]
                return i + 1
            i += 1
        raise _UnparsedSource("unterminated_or_ambiguous_regex")

    def _preceding_keyword(self, words: tuple[str, ...]) -> bool:
        end = self._last_significant + 1
        for word in words:
            start = end - len(word)
            if start < 0 or "".join(self.mask[start:end]) != word:
                continue
            if start == 0 or not (self.mask[start - 1].isalnum() or self.mask[start - 1] == "_"):
                return True
        return False

    def expression_position(self, i: int) -> bool:
        # Consume each masked prefix character once, including across recursive
        # JSX/template expressions. Never join or rescan the whole source prefix.
        for pos in range(self._context_end, i):
            ch = self.mask[pos]
            if ch.isspace():
                continue
            control_close = False
            if ch == "(":
                self._control_parentheses.append(
                    self._preceding_keyword(("if", "while", "for", "with"))
                )
            elif ch == ")" and self._control_parentheses:
                control_close = self._control_parentheses.pop()
            self._last_significant = pos
            self._last_control_close = control_close
        self._context_end = i
        last = self._last_significant
        return (
            last < 0
            or self.mask[last] in "=(:,[!&|?;{}><+-*%/^~"
            or self._preceding_keyword(
                (
                    "return",
                    "throw",
                    "case",
                    "yield",
                    "await",
                    "else",
                    "do",
                    "void",
                    "typeof",
                    "delete",
                    "in",
                    "of",
                )
            )
            or (self.mask[last] == ")" and self._last_control_close)
        )

    def jsx(self, i: int) -> int:
        opening = self._JSX_OPEN.match(self.text, i)
        if opening is None:
            raise _UnparsedSource("unsupported_jsx_opening")
        name = opening.group(1)
        self.hide(i, opening.end())
        i = opening.end()
        if name and i < len(self.text) and self.text[i] == "<":
            # Typed JSX components, e.g. <DataTable<Row> ... />. Type arguments
            # are not executable expressions; retain only attribute expressions.
            start = i
            nesting = 1
            i += 1
            while i < len(self.text) and nesting:
                if self.text[i] in "\"'`":
                    i = _literal_end(self.text, i)
                    continue
                if self.text.startswith(("//", "/*"), i):
                    i = self.comment(i)
                    continue
                if self.text[i] == "<":
                    nesting += 1
                elif self.text[i] == ">" and self.text[i - 1] != "=":
                    nesting -= 1
                i += 1
            if nesting:
                raise _UnparsedSource("unterminated_jsx_type_arguments")
            self.hide(start, i)
        while i < len(self.text):
            if self.text.startswith("/>", i):
                self.hide(i, i + 2)
                return i + 2
            if self.text[i] == ">":
                self.hide(i, i + 1)
                i += 1
                break
            if self.text[i] in "\"'":
                # JSX attribute strings may span lines and do not use JS escapes.
                end = self.text.find(self.text[i], i + 1)
                if end < 0:
                    raise _UnparsedSource("unterminated_jsx_attribute")
                self.hide(i, end + 1)
                i = end + 1
            elif self.text[i] == "{":
                i = self.code(i + 1, stop_at_brace=True)
            else:
                self.hide(i, i + 1)
                i += 1
        else:
            raise _UnparsedSource("unterminated_jsx_opening")

        while i < len(self.text):
            if self.text.startswith("</", i):
                closing = self._JSX_CLOSE.match(self.text, i)
                if closing is None or closing.group(1) != name:
                    raise _UnparsedSource("mismatched_jsx_closing")
                end = closing.end()
                self.hide(i, end)
                return end
            if self.text[i] == "<":
                self.depth += 1
                if self.depth > 96:
                    raise _UnparsedSource("lexical_nesting_limit")
                i = self.jsx(i)
                self.depth -= 1
            elif self.text[i] == "{":
                i = self.code(i + 1, stop_at_brace=True)
            else:
                # Apostrophes, quotes and apparent calls here are JSX text.
                self.hide(i, i + 1)
                i += 1
        raise _UnparsedSource("unterminated_jsx_element")

    def code(self, i: int = 0, *, stop_at_brace: bool = False) -> int:
        self.depth += 1
        if self.depth > 96:
            raise _UnparsedSource("lexical_nesting_limit")
        braces = 0
        while i < len(self.text):
            ch = self.text[i]
            if self.text.startswith(("//", "/*"), i):
                i = self.comment(i)
            elif ch in "\"'":
                i = self.quoted(i)
            elif ch == "`":
                i = self.template(i)
            elif ch == "<" and self.jsx_enabled and self.expression_position(i):
                # Generic calls follow a callee, not an expression-opening token.
                generic_arrow = self._GENERIC_ARROW.match(self.text, i)
                if generic_arrow:
                    # TSX permits constrained/comma-marked generic arrow parameters.
                    # The parameter/body code is still scanned normally.
                    i = generic_arrow.end() - 1
                elif self._JSX_OPEN.match(self.text, i):
                    i = self.jsx(i)
                else:
                    i += 1
            elif ch == "/" and self.expression_position(i):
                i = self.regex(i)
            elif ch == "{":
                braces += 1
                i += 1
            elif ch == "}" and stop_at_brace and braces == 0:
                self.depth -= 1
                return i + 1
            else:
                if ch == "}":
                    braces -= 1
                i += 1
        self.depth -= 1
        if stop_at_brace:
            raise _UnparsedSource("unterminated_expression")
        return i


def _scan_code(text: str, *, jsx: bool = True) -> tuple[str, str | None]:
    scanner = _CodeMask(text, jsx=jsx)
    try:
        scanner.code()
    except (_UnparsedSource, RecursionError) as exc:
        # Do not count this as zero calls or a complete scan. There is no sound
        # call count for a source region whose lexical boundaries are unknown.
        return "".join("\n" if c == "\n" else " " for c in text), str(exc)
    return "".join(scanner.mask), None


def _code_mask(text: str) -> str:
    """Compatibility helper; the scanner also consumes _scan_code diagnostics."""
    return _scan_code(text)[0]


def _is_test_source(path: Path) -> bool:
    return bool(re.search(r"\.(?:test|spec)\.tsx?$", path.name)) or bool(
        {"tests", "__tests__", "__mocks__"}.intersection(path.parts)
    )


class _ClientBindings:
    """Prove named relative imports/re-exports; reject ambiguous identifier uses.

    Without a semantic TS parser, an identifier used anywhere other than an
    import/re-export or a direct HTTP receiver invalidates that file's binding.
    This deliberately rejects some valid programs instead of accepting shadows.
    """

    _LINK = re.compile(r"\b(import|export)\s+(type\s+)?\{([^{}]*)\}\s+from\s*([\"\'])")

    def __init__(self, root, prefixes):
        self.root = root.resolve()
        self.canonical = (root / "frontend/src/services/api/client.ts").resolve()
        self.prefixes = prefixes
        self.modules = {}

    def module(self, path):
        path = path.resolve()
        if path in self.modules:
            return self.modules[path]
        text = path.read_text(encoding="utf-8")
        code, error = _scan_code(text, jsx=path.suffix == ".tsx")
        links = []
        if not error:
            for match in self._LINK.finditer(code):
                start = match.end() - 1
                end = _literal_end(text, start)
                target = text[start + 1 : end - 1]
                if match.group(2) or not target.startswith("."):
                    continue
                base = path.parent / target
                options = (
                    [base]
                    if base.suffix in {".ts", ".tsx"}
                    else [
                        Path(f"{base}.ts"),
                        Path(f"{base}.tsx"),
                        base / "index.ts",
                        base / "index.tsx",
                    ]
                )
                options = [
                    p.resolve()
                    for p in options
                    if p.is_file() and p.resolve().is_relative_to(self.root)
                ]
                if len(options) != 1:
                    continue
                for item in match.group(3).split(","):
                    names = re.fullmatch(
                        r"\s*([A-Za-z_$][\w$]*)(?:\s+as\s+([A-Za-z_$][\w$]*))?\s*", item
                    )
                    if names:
                        links.append(
                            {
                                "kind": match.group(1),
                                "original": names[1],
                                "local": names[2] or names[1],
                                "target": options[0],
                                "span": (match.start(), end),
                                "site": f"{path.relative_to(self.root)}:{text[: match.start()].count(chr(10)) + 1}",
                            }
                        )
        self.modules[path] = (code, error, links)
        return self.modules[path]

    def exported(self, path, name, seen):
        key = (path, name)
        if key in seen or len(seen) >= 24:
            return None
        if path == self.canonical:
            return (name, []) if name in self.prefixes else None
        _, error, links = self.module(path)
        matches = [x for x in links if x["kind"] == "export" and x["local"] == name]
        if error or len(matches) != 1:
            return None
        link = matches[0]
        result = self.exported(link["target"], link["original"], seen | {key})
        return (result[0], [link["site"], *result[1]]) if result else None

    def resolve(self, path, name):
        path = path.resolve()
        code, error, links = self.module(path)
        matches = [x for x in links if x["kind"] == "import" and x["local"] == name]
        if error or len(matches) != 1:
            return None
        # Every other occurrence must be a direct receiver, never a parameter,
        # declaration, assignment, property alias, destructuring or indirect use.
        spans = [x["span"] for x in links]
        for occurrence in re.finditer(r"(?<![\w$])" + re.escape(name) + r"(?![\w$])", code):
            pos = occurrence.start()
            if any(a <= pos < b for a, b in spans):
                continue
            if not _is_direct_receiver(code, pos) or not _ANY_CALL.match(code, pos):
                return None
        link = matches[0]
        result = self.exported(link["target"], link["original"], set())
        return (result[0], [link["site"], *result[1]]) if result else None


def _scan_calls(
    root: Path,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    calls: list[dict[str, Any]] = []
    tests: list[dict[str, Any]] = []
    blind: list[dict[str, Any]] = []
    source = root / "frontend/src"
    binding_reader = _ClientBindings(root, client_prefixes(root))
    for path in sorted(source.rglob("*.ts*")):
        if path.suffix not in {".ts", ".tsx"}:
            continue
        text = path.read_text(encoding="utf-8", errors="strict")
        code, lexical_error = _scan_code(text, jsx=path.suffix == ".tsx")
        relative = path.relative_to(root)
        test_source = _is_test_source(relative)
        if lexical_error:
            blind.append(
                {
                    "site": f"{relative}:1",
                    "source_kind": "test" if test_source else "application",
                    "reason": "unparsed_source_file",
                    "detail": lexical_error,
                    "count_unit": "file_not_calls",
                }
            )
            continue
        imported_names = {
            x["local"] for x in binding_reader.module(path)[2] if x["kind"] == "import"
        }
        for match in _ANY_CALL.finditer(code):
            if not _is_direct_receiver(code, match.start()):
                continue
            if not match.group(1).endswith("Api") and match.group(1) not in imported_names:
                continue
            call = {
                "instance": match.group(1),
                "column": match.start() - text.rfind("\n", 0, match.start()),
                "method": match.group(2).upper(),
                "site": f"{relative}:{text[: match.start()].count(chr(10)) + 1}",
                "source_kind": "test" if test_source else "application",
            }
            i = match.end()
            if code[i] == "<":
                depth = 1
                i += 1
                while i < len(code) and depth:
                    depth += (code[i] == "<") - (code[i] == ">")
                    i += 1
                while i < len(code) and code[i].isspace():
                    i += 1
            value = None
            # ما يُعرف من المسار الديناميّ: نصُّه الحرفيّ قبل أوّل جزءٍ يُبنى وقتَ التشغيل ("" إن لم يكن نصّاً)
            literal_prefix = ""
            if i < len(code) and code[i] == "(":
                i += 1
                # Whitespace/comments may separate the first argument from '('.
                while i < len(text):
                    if text[i].isspace():
                        i += 1
                    elif text.startswith("/*", i):
                        end = text.find("*/", i + 2)
                        i = len(text) if end < 0 else end + 2
                    elif text.startswith("//", i):
                        end = text.find("\n", i + 2)
                        i = len(text) if end < 0 else end
                    else:
                        break
                if i < len(text) and text[i] in "\"'`":
                    end = _literal_end(text, i)
                    raw = text[i + 1 : end - 1]
                    candidate = template_path(raw) if text[i] == "`" else raw.split("?", 1)[0]
                    literal_prefix = (raw.split("${", 1)[0] if text[i] == "`" else raw).split("?")[
                        0
                    ]
                    tail = code[end:].lstrip()
                    if (
                        text[end - 1] == text[i]
                        and candidate is not None
                        and _PATH.fullmatch(candidate)
                        and tail.startswith((",", ")"))
                    ):
                        value = candidate
            if value is None:
                (tests if test_source else blind).append(
                    {
                        **call,
                        "reason": "unsupported_or_dynamic_path",
                        "literal_prefix": literal_prefix,
                    }
                )
            else:
                (tests if test_source else calls).append({**call, "path": value})
    return calls, tests, blind


def _test_references(root: Path) -> list[dict[str, Any]]:
    """Retain quoted/commented test references without asserting consumption."""
    references = []
    for path in sorted((root / "frontend/src").rglob("*.ts*")):
        relative = path.relative_to(root)
        if path.suffix not in {".ts", ".tsx"} or not _is_test_source(relative):
            continue
        text = path.read_text(encoding="utf-8")
        code, lexical_error = _scan_code(text, jsx=path.suffix == ".tsx")
        if lexical_error:
            # Unknown lexical regions are not evidence of non-executable text.
            # _scan_calls reports this file separately instead.
            continue
        for match in _ANY_CALL.finditer(text):
            if _ANY_CALL.match(code, match.start()) is None:
                references.append(
                    {
                        "site": f"{relative}:{text[: match.start()].count(chr(10)) + 1}",
                        "instance": match.group(1),
                        "method": match.group(2).upper(),
                        "kind": "non_executable_test_reference",
                    }
                )
    return references


def call_sites(root: Path = ROOT) -> tuple[list[dict[str, Any]], int]:
    """Application call sites and *detected* unsupported application call count.

    Files that cannot be lexed have no meaningful call count. Callers requiring
    scan completeness must consume the `unparsed_source_files` field in the
    report returned by resolve() rather than interpreting this count as total missing calls.
    """
    calls, _, blind = _scan_calls(root)
    return calls, sum(
        item["source_kind"] == "application" and item["reason"] == "unsupported_or_dynamic_path"
        for item in blind
    )


def resolve(
    edges: list[dict[str, Any]], components: list[dict[str, Any]], root: Path = ROOT
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    """يُعيد (المحسومة، الباقية على حالها، تقريرَ القياس)."""
    prefixes = client_prefixes(root)
    gate = gateway(root, components)
    calls, test_calls, blind_calls = _scan_calls(root)
    blind = sum(
        item["source_kind"] == "application" and item["reason"] == "unsupported_or_dynamic_path"
        for item in blind_calls
    )

    proxies = sorted(
        [route for route in gate["routes"] if route["kind"] == "proxy"],
        key=lambda route: -len(route["client"]),
    )
    rewrites = [route for route in gate["routes"] if route["kind"] == "rewrite"]

    # (component, HTTP method, normalised service path) => evidence chain
    index: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    bindings = _ClientBindings(root, prefixes)
    unproven_bindings = []
    for call in calls:
        binding = bindings.resolve(root / call["site"].rsplit(":", 1)[0], call["instance"])
        if binding is None:
            unproven_bindings.append(
                {**call, "reason": "unproven_import_or_ambiguous_identifier_use"}
            )
            continue
        client = prefixes[binding[0]]
        browser_path = normalise(client["prefix"] + call["path"])
        for route in proxies:
            base = route["client"].rstrip("/")
            if browser_path != base and not browser_path.startswith(base + "/"):
                continue
            component = gate["upstreams"].get(route["upstream"], "")
            if not component:
                break
            tail = browser_path[len(base) :].lstrip("/")
            service_path = normalise(route["service_path"] + "/" + tail)
            rule_line = route["line"]
            for rewrite in rewrites:
                if rewrite["client"] != route["client"]:
                    continue
                applied = re.match(rewrite["pattern"], browser_path)
                if applied:
                    service_path = normalise(
                        re.sub(rewrite["pattern"], rewrite["replacement"], browser_path)
                    )
                    rule_line = rewrite["line"]
                    break
            index.setdefault((component, call["method"], service_path), []).append(
                {
                    "import_chain": binding[1],
                    "call_site": call["site"],
                    "call_column": call["column"],
                    "method": call["method"],
                    "source_kind": call["source_kind"],
                    "evidence_scope": "static_source_only",
                    "client_prefix": client["prefix"],
                    "client_binding": client["client_line"],
                    "endpoint_binding": client["endpoints_line"],
                    "gateway_rule": rule_line,
                    "browser_path": browser_path,
                },
            )
            break

    resolved: list[dict[str, Any]] = []
    remaining: list[dict[str, Any]] = []
    for edge in edges:
        pending = []
        entrypoints = edge.get("entrypoints") or []
        for entrypoint in dict.fromkeys(entrypoints):
            parts = entrypoint.split(None, 1)
            chains = (
                index.get((edge["from"], parts[0].upper(), normalise(parts[1])), [])
                if len(parts) == 2
                else []
            )
            if not chains:
                pending.append(entrypoint)
                continue
            for chain in chains:
                resolved.append(
                    {
                        **edge,
                        "entrypoints": [entrypoint],
                        "evidence_state": "resolved",
                        "resolved_entrypoint": entrypoint,
                        "evidence": {"kind": "frontend_call_site_through_gateway", **chain},
                    }
                )
        if pending or not entrypoints:
            remaining.append({**edge, "entrypoints": pending})
    report = {
        "frontend_clients": len(prefixes),
        "gateway_rules": len(gate["routes"]),
        "gateway_upstreams_mapped": sum(1 for v in gate["upstreams"].values() if v),
        "gateway_upstreams_unmapped": sum(1 for v in gate["upstreams"].values() if not v),
        "literal_call_sites": len(calls),
        # **حدُّ الماسح، مُعلَناً بعدده:** غيابُ الدليل هنا قد يكون غيابَ رؤية.
        "scanner_blind_spots": blind,
        "unsupported_call_sites": [
            item
            for item in blind_calls
            if item["source_kind"] == "application"
            and item["reason"] == "unsupported_or_dynamic_path"
        ],
        "unparsed_source_files": [
            item for item in blind_calls if item["reason"] == "unparsed_source_file"
        ],
        "lexical_scan_complete": not any(
            item["reason"] == "unparsed_source_file" for item in blind_calls
        ),
        "scanner_blind_spots_are_exhaustive": False,
        "scanner_blind_spots_unit": "detected_unsupported_application_calls",
        "unproven_client_bindings": unproven_bindings,
        "resolved_count_unit": "operation_call_site_evidence_rows",
        "unresolved_count_unit": "declared_groups_with_pending_operations",
        "test_call_sites": test_calls,
        "non_executable_test_references": _test_references(root),
        "evidence_scope": "static_source_only",
        "scanner_limitations": [
            "No runtime reachability; named relative imports/re-exports only",
            "Ambiguous identifier uses reject the entire file binding conservatively",
            "Bounded lexical JSX/template scan, not TypeScript semantic analysis",
            "Unparsed files are reported separately; blind spots are not an exhaustive call count",
            "One resolved row per matched operation and call site; pending operations remain declared",
            "Only literal paths and simple template member parameters are resolved",
        ],
        "resolved": len(resolved),
        "still_unresolved": len(remaining),
    }
    return resolved, remaining, report


# ── ما بعد الحسم: كلُّ عمليّةٍ معلَنة مُثبَتة أو منفيّة أو مجهولةٌ **بسببٍ مسمّى وموضع** ─────────────────────
#
# ``A-DECLARED-EDGE-WITHOUT-A-CALL-SITE-IS-NEITHER-PROVEN-NOR-ABSENT-01``. الباقي بعد الحسم كان «declared» بلا تمييز:
# ما يبنيه العميلُ ديناميّاً، وما لا يبلغه الماسح، وما لا يُنادى أصلاً — كلُّه في سلّةٍ واحدة. والتمييزُ هنا ثلاثُ
# حالاتٍ لا اثنتان، ولا تُرقّى حالةٌ إلى أقوى منها بلا دليلها:
#
# * **مُثبَتة** — سلسلةُ أدلّةٍ كاملة: نداءٌ في الواجهة عبر البوّابة (أعلاه)، أو **اشتراكُ NATS في مصدر Python**
#   (صفُّ جدول الاشتراكات · استيرادُه · حلقتُه · نداءُ ``subscribe`` بمتغيّرها) — صنفُ الدليل الثاني.
# * **منفيّة في نطاقٍ مسمّى** — المتصفّحُ لا يبلغ إلّا ما يوجّهه ``nginx.conf``؛ منتِجٌ بلا مُجرىً أعلى هناك لا تصله
#   نداءاتُ الواجهة **في وضع البوّابة** (``gateway_mode``). وضعُ التطوير المباشر (``VITE_*_BASE_URL``) خارج النطاق، ويُقال.
# * **مجهولة** — بسببٍ من أصنافٍ مسمّاة، ولكلٍّ موضعُه ``path:line``. صنفٌ جديدٌ لا يُقبل بصمت: سجلُّ
#   ``docs/architecture/inventory_edge_exemptions.json`` يُعلن كلَّ صنفٍ مقبولٍ بمبرّره وشرط إغلاقه (``exemption_problems``).

#: الأصنافُ المجهولة، من الأقوى دليلاً إلى الأضعف — الأوّلُ في صفّ العمليّة سببُها الرئيس.
UNKNOWN_REASON_ORDER = (
    "call_site_binding_unproven",
    "dynamic_call_may_reach",
    "client_passed_as_value",
    "unparsed_source_may_call",
    "not_seen_by_axios_scanner",
    "no_static_evidence_class_for_this_edge_kind",
)
_NATS_CONSUMER = re.compile(r"^(?P<component>[\w.-]+) \((?P<durable>[\w.-]+)\)$")
_SUBSCRIBE_CALLS = {"subscribe", "subscribe_bind", "pull_subscribe"}


def _segments_compatible(prefix: str, browser_path: str) -> bool:
    """هل يمكن لمسارٍ يبدأ بالنصّ ``prefix`` (معروفٌ حرفيّاً، وما بعده يُبنى وقتَ التشغيل) أن يكون ``browser_path``؟
    ``{}`` في المسار المطبَّع يطابق أيَّ مقطع، والمقطعُ الأخيرُ من البادئة قد يكون جزئيّاً."""
    pre = re.sub(r"/{2,}", "/", prefix).split("/")
    full = browser_path.split("/")
    if len(pre) > len(full):
        return False
    for index, part in enumerate(pre):
        target = full[index]
        last = index == len(pre) - 1
        if target == "{}" or part == target or (last and target.startswith(part)):
            continue
        return False
    return True


def _route_for(browser_path: str, proxies: list[dict[str, Any]]) -> dict[str, Any] | None:
    """الموقعُ الذي يختاره nginx: المطابقةُ التامّة (``location =``) أوّلاً، ثمّ أطولُ بادئة."""
    for route in proxies:
        if route.get("exact") and normalise(route["client"]) == browser_path:
            return route
    for route in proxies:
        base = route["client"].rstrip("/")
        if not route.get("exact") and (browser_path == base or browser_path.startswith(base + "/")):
            return route
    return None


def _method_can_match(call_method: str | None, operation_method: str) -> bool:
    """axios لا يفتح WebSocket؛ و``ANY`` تقبل كلَّ فعل؛ ونسخةٌ مُمرَّرةٌ قيمةً (``None``) قد تُستعمل بأيّ فعل."""
    if operation_method == "WEBSOCKET":
        return False
    return call_method is None or operation_method == "ANY" or call_method == operation_method


def _browser_paths(component: str, service_path: str, gate: dict, proxies: list) -> list[tuple]:
    """كلُّ مسارٍ في المتصفّح توجّهه البوّابةُ إلى ``(component, service_path)`` — بعكس قاعدة proxy_pass؛
    ومواقعُ ``rewrite`` (لا يُعكس تعبيرُها النمطيّ) تُعاد بمسارٍ ``None``: تبلغ كلَّ عمليّات المكوّن بلا تحديد."""
    out = []
    for route in proxies:
        if gate["upstreams"].get(route["upstream"]) != component:
            continue
        if any(r["kind"] == "rewrite" and r["client"] == route["client"] for r in gate["routes"]):
            out.append((None, route))
            continue
        head = normalise(route["service_path"])
        if route.get("exact"):
            if service_path == head and _route_for(normalise(route["client"]), proxies) is route:
                out.append((normalise(route["client"]), route))
            continue
        if service_path != head and not service_path.startswith(head.rstrip("/") + "/"):
            continue
        tail = service_path[len(head) :].lstrip("/") if head != "/" else service_path.lstrip("/")
        browser = normalise(route["client"].rstrip("/") + "/" + tail)
        if _route_for(browser, proxies) is route:
            out.append((browser, route))
    return out


def _value_uses(root: Path, prefixes: dict[str, Any]) -> list[dict[str, Any]]:
    """نسخةُ عميلٍ تُستعمل **قيمةً** (تُمرَّر أو تُسنَد أو ``.request(...)``) لا مستقبِلَ نداءٍ مباشر: لا يُعرف أيُّ مسارٍ
    يُطلب عبرها — يُعاد موضعُها لا يُخمَّن مسارُها."""
    out: list[dict[str, Any]] = []
    canonical = (root / "frontend/src/services/api/client.ts").resolve()
    if not prefixes:
        return out
    names = re.compile(r"(?<![\w$.])(" + "|".join(map(re.escape, sorted(prefixes))) + r")(?![\w$])")
    bindings = _ClientBindings(root, prefixes)
    for path in sorted((root / "frontend/src").rglob("*.ts*")):
        relative = path.relative_to(root)
        if path.suffix not in {".ts", ".tsx"} or _is_test_source(relative):
            continue
        if path.resolve() == canonical:
            continue
        code, error, links = bindings.module(path)
        if error:
            continue
        spans = [x["span"] for x in links]
        text = path.read_text(encoding="utf-8")
        for match in names.finditer(code):
            pos = match.start()
            if any(a <= pos < b for a, b in spans) or not _is_direct_receiver(code, pos):
                continue
            if _ANY_CALL.match(code, pos):
                continue  # نداءٌ مباشر: حرفيُّه في calls، وديناميُّه في unsupported_call_sites
            after = code[match.end() :].lstrip()
            if re.match(r"\.\s*(defaults|interceptors)\b", after):
                continue  # إعدادُ النسخة لا طلبٌ عبرها
            out.append(
                {
                    "instance": match.group(1),
                    "site": f"{relative}:{text[:pos].count(chr(10)) + 1}",
                }
            )
    return out


def nats_subscriptions(root: Path, components: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """صنفُ الدليل الثاني: ``(component, durable, subject)`` لكلّ اشتراكٍ في مصدر Python للمكوّن، بسلسلةٍ مقروءةٍ
    بـ``ast`` لا بنمطٍ نصّيّ: جدولٌ من ثنائيّاتٍ حرفيّة (``SUBSCRIPTIONS = [("subject", "durable"), …]``) يستورده
    مصدرُ المكوّن، ويمرّ عليه بحلقة ``for subject, durable in …``، وفي جسدها ``…subscribe(subject, …)``.
    كلُّ خطوةٍ بسطرها؛ وغيابُ خطوةٍ يُسقط الدليل كلَّه (لا ترقيةَ بنصف سلسلة)."""
    import ast

    found: list[dict[str, Any]] = []
    for component in components:
        source = component.get("source_path") or ""
        base = root / source
        if not source or not base.is_dir():
            continue
        for path in sorted(base.rglob("*.py")):
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"))
            except (SyntaxError, UnicodeDecodeError):
                continue
            imports = {}
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                    for alias in node.names:
                        imports[alias.asname or alias.name] = (node.module, alias.name, node.lineno)
            for loop in ast.walk(tree):
                if not (
                    isinstance(loop, ast.For)
                    and isinstance(loop.iter, ast.Name)
                    and loop.iter.id in imports
                    and isinstance(loop.target, ast.Tuple)
                    and len(loop.target.elts) == 2
                    and all(isinstance(e, ast.Name) for e in loop.target.elts)
                ):
                    continue
                subject_var = loop.target.elts[0].id
                calls = sorted(
                    node.lineno
                    for node in ast.walk(loop)
                    if isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr in _SUBSCRIBE_CALLS
                    and (
                        (
                            node.args
                            and isinstance(node.args[0], ast.Name)
                            and node.args[0].id == subject_var
                        )
                        or any(
                            isinstance(k.value, ast.Call)
                            and any(
                                isinstance(a, ast.Name) and a.id == loop.target.elts[1].id
                                for a in ast.walk(k.value)
                            )
                            for k in node.keywords
                        )
                    )
                )
                if not calls:
                    continue
                module, name, import_line = imports[loop.iter.id]
                table_path = root / (module.replace(".", "/") + ".py")
                if not table_path.is_file():
                    continue
                table = ast.parse(table_path.read_text(encoding="utf-8"))
                for node in table.body:
                    if not (
                        isinstance(node, ast.Assign)
                        and any(isinstance(t, ast.Name) and t.id == name for t in node.targets)
                        and isinstance(node.value, (ast.List, ast.Tuple))
                    ):
                        continue
                    for row in node.value.elts:
                        if (
                            isinstance(row, ast.Tuple)
                            and len(row.elts) == 2
                            and all(
                                isinstance(e, ast.Constant) and isinstance(e.value, str)
                                for e in row.elts
                            )
                        ):
                            found.append(
                                {
                                    "component": component["component_id"],
                                    "subject": row.elts[0].value,
                                    "durable": row.elts[1].value,
                                    "table_row": f"{table_path.relative_to(root)}:{row.lineno}",
                                    "import": f"{path.relative_to(root)}:{import_line}",
                                    "loop": f"{path.relative_to(root)}:{loop.lineno}",
                                    "subscribe_calls": [
                                        f"{path.relative_to(root)}:{line}" for line in calls
                                    ],
                                }
                            )
    return sorted(found, key=lambda x: (x["component"], x["durable"], x["table_row"]))


# ── صنفُ الدليل الثالث: نداءُ HTTP في مصدر Python (خدمةٌ ⇒ خدمة) ─────────────────────────────────────────────
#
# ``A-DECLARED-EDGE-WITHOUT-A-CALL-SITE-IS-NEITHER-PROVEN-NOR-ABSENT-01`` سمّت الخطوةَ التالية: حافّةُ خدمةٍ إلى خدمة
# (field-segmentation⇒SAM2) لا يثبتها نداءٌ في الواجهة، بل موضعُ نداءٍ في مصدر Python. والسلسلةُ هنا خمسُ خطوات،
# كلُّها بسطرها ومشتقّةٌ من الشجرة:
#
# 1. موضعُ النداء: ``<client>.<verb>(url)`` حيث ``client`` مُثبَتٌ عميلَ HTTP (``httpx``/``requests`` نفسُهما، أو
#    اسمٌ رُبط بـ``with httpx.Client(...) as c`` / ``c = httpx.AsyncClient(...)`` / ``aiohttp.ClientSession()``).
#    ``.get`` على قاموسٍ ليس نداءً — فالمستقبِلُ الذي لا يُثبَت عميلاً لا يُقرأ أصلاً (حدٌّ معلَن).
# 2. قراءةُ البيئة: ``os.getenv("X", default)`` / ``os.environ[...]`` يبلغها التعبيرُ عبر روابطَ بسيطةٍ (اسمٌ مُسنَدٌ
#    مرّةً واحدة · ``self.attr`` · دالّةٌ بلا وسائط تُعيد تعبيراً · f-string · ``+`` · ``strip``/``rstrip``).
# 3. قيمةُ البيئة في ``docker-compose.v9.yml`` لخدمة compose المستهلكة (``${X:-http://host:port/...}``)، أو — إن لم
#    يُعلنها compose — الافتراضيُّ الحرفيُّ في الكود.
# 4. المضيفُ ⇒ خدمةُ compose (أو ``container_name`` / اسمٌ مستعار) لمكوّنٍ في الجرد؛ والمنفذُ ⇒ منفذٌ يستمع عليه
#    ذاك المكوّن (``ports``/``expose``/``command``/``healthcheck`` أو ``EXPOSE``/``--port`` في Dockerfile).
# 5. المسارُ ⇒ مسارٌ مُعلَنٌ للمنتِج في ``route_inventory.generated.json`` (الجردُ نفسُه، لا جدولٌ يدويّ).
#
# والمسارُ الديناميّ لا يُطابَق إلّا قالباً: بادئةٌ حرفيّة (المقطعُ الأوّلُ ثابت) وكلُّ جزءٍ متغيّرٍ يملأ مقطعاً كاملاً؛
# وما سوى ذلك يبقى مجهولاً بسببٍ مسمّى (``dynamic_path``). ولا نفيَ من غياب: ما لا يُرى يبقى ``unknown``.

COMPOSE_FILE = "docker-compose.v9.yml"
ROUTE_INVENTORY = "route_inventory.generated.json"
_HTTP_VERBS = ("get", "post", "put", "patch", "delete", "head", "options")
_HTTP_MODULES = {"httpx", "requests"}
_CLIENT_FACTORIES = {
    ("httpx", "Client"),
    ("httpx", "AsyncClient"),
    ("requests", "Session"),
    ("aiohttp", "ClientSession"),
}
_DYN = "\x00"
_COMPOSE_DEFAULT = re.compile(r"^\$\{([A-Za-z_][A-Za-z0-9_]*):?-([^{}$]*)\}$")
_URL = re.compile(r"^(https?)://([^/:?#\x00]+)(?::(\d+))?(/[^#]*)?$")
_PORT_FLAG = re.compile(r"(?:--port[=\s]+|--bind[=\s]+\S*?:|-b\s+\S*?:)(\d{2,5})\b")
_LOCAL_PORT = re.compile(r"\blocalhost:(\d{2,5})\b")
#: أسبابُ «مجهول» لحوافّ مستهلكُها مكوّنُ Python — **غيرُ معلَنةٍ في سجلّ الاستثناءات** ما دامت لا تقع: حافّةُ خدمةٍ
#: معلَنةٌ تبقى بلا دليلٍ تُحمِّر ``exemption_problems`` (``unlisted_reason``) حتّى يُقرَّر سببُها — لا مجهولَ صامت.
PYTHON_UNKNOWN_REASONS = (
    "dynamic_path",
    "base_url_unresolved",
    "not_seen_by_python_http_scanner",
)


class _Unresolved(Exception):
    """تعبيرُ URL لا يُقرأ ساكناً — يُعاد سببُه لا يُخمَّن."""


def _line(path: str, number: int) -> str:
    return f"{path}:{number}"


def _compose_value(raw: str) -> str | None:
    """قيمةُ متغيّرٍ في compose: حرفيٌّ، أو افتراضيُّ ``${X:-v}``؛ و``${X:?…}``/``${X}`` يقدّمها المشغّل ⇒ ``None``."""
    raw = raw.strip()
    if "$" not in raw:
        return raw or None
    found = _COMPOSE_DEFAULT.match(raw)
    return (found.group(2) or None) if found else None


def compose_services(root: Path = ROOT) -> dict[str, dict[str, Any]]:
    """كلُّ خدمة compose ⇒ بيئتُها ومضيفوها ومنافذُها، **بأسطرها** (عُقَد ``yaml.compose`` تحمل موضعها)."""
    import yaml

    path = root / COMPOSE_FILE
    if not path.is_file():
        return {}
    document = yaml.compose(path.read_text(encoding="utf-8"))

    def child(node, key):
        if not isinstance(node, yaml.MappingNode):
            return None, None
        for k, v in node.value:
            if isinstance(k, yaml.ScalarNode) and k.value == key:
                return k, v
        return None, None

    def scalars(node):
        if isinstance(node, yaml.ScalarNode):
            yield node
        elif isinstance(node, yaml.SequenceNode):
            for item in node.value:
                yield from scalars(item)
        elif isinstance(node, yaml.MappingNode):
            for _, item in node.value:
                yield from scalars(item)

    _, services = child(document, "services")
    out: dict[str, dict[str, Any]] = {}
    for key, node in services.value if isinstance(services, yaml.MappingNode) else ():
        name = key.value
        entry: dict[str, Any] = {
            "env": {},
            "hosts": {name: _line(COMPOSE_FILE, key.start_mark.line + 1)},
            "ports": {},
        }
        _, env = child(node, "environment")
        if isinstance(env, yaml.MappingNode):
            for k, v in env.value:
                if isinstance(v, yaml.ScalarNode):
                    entry["env"][k.value] = (v.value, _line(COMPOSE_FILE, v.start_mark.line + 1))
        elif isinstance(env, yaml.SequenceNode):
            for item in env.value:
                if isinstance(item, yaml.ScalarNode) and "=" in item.value:
                    k, v = item.value.split("=", 1)
                    entry["env"][k] = (v, _line(COMPOSE_FILE, item.start_mark.line + 1))
        _, container = child(node, "container_name")
        if isinstance(container, yaml.ScalarNode):
            entry["hosts"].setdefault(
                container.value, _line(COMPOSE_FILE, container.start_mark.line + 1)
            )
        _, networks = child(node, "networks")
        if isinstance(networks, yaml.MappingNode):
            for _, net in networks.value:
                _, aliases = child(net, "aliases")
                for alias in scalars(aliases) if aliases is not None else ():
                    entry["hosts"].setdefault(
                        alias.value, _line(COMPOSE_FILE, alias.start_mark.line + 1)
                    )

        def port(value: str, line: str, ports: dict = entry["ports"]) -> None:
            if value.isdigit():
                ports.setdefault(int(value), line)

        for field in ("ports", "expose"):
            _, ports = child(node, field)
            for item in scalars(ports) if ports is not None else ():
                text = str(item.value).split("/", 1)[0]
                port(text.rsplit(":", 1)[-1], _line(COMPOSE_FILE, item.start_mark.line + 1))
        for field, pattern in (("command", _PORT_FLAG), ("healthcheck", _LOCAL_PORT)):
            _, value = child(node, field)
            items = list(scalars(value)) if value is not None else []
            for index, item in enumerate(items):
                text = str(item.value)
                if field == "command" and text == "--port" and index + 1 < len(items):
                    text = f"--port {items[index + 1].value}"
                for found in pattern.finditer(text):
                    port(found.group(1), _line(COMPOSE_FILE, item.start_mark.line + 1))
        _, build = child(node, "build")
        _, dockerfile = child(build, "dockerfile")
        _, context = child(build, "context")
        if isinstance(dockerfile, yaml.ScalarNode):
            base = root / (context.value if isinstance(context, yaml.ScalarNode) else ".")
            docker = (base / dockerfile.value).resolve()
            if docker.is_file() and docker.is_relative_to(root.resolve()):
                relative = str(docker.relative_to(root.resolve()))
                for number, text in enumerate(docker.read_text(encoding="utf-8").splitlines(), 1):
                    stripped = text.strip()
                    if stripped.upper().startswith("EXPOSE"):
                        for value in stripped.split()[1:]:
                            port(value.split("/", 1)[0], _line(relative, number))
                    elif stripped.upper().startswith("CMD") or stripped.upper().startswith(
                        "ENTRYPOINT"
                    ):
                        flat = re.sub(r'"\s*,\s*"', " ", stripped)
                        for found in _PORT_FLAG.finditer(flat):
                            port(found.group(1), _line(relative, number))
        out[name] = entry
    return out


def _provider_routes(root: Path, host_to_component: dict[str, str]) -> dict[str, list[dict]]:
    """مساراتُ كلِّ منتِجٍ من ``route_inventory.generated.json`` — ``service`` ⇒ مكوّنٌ بأسماء الجرد نفسِه."""
    path = root / ROUTE_INVENTORY
    if not path.is_file():
        return {}
    import json

    rows = json.loads(path.read_text(encoding="utf-8"))
    rows = rows if isinstance(rows, list) else rows.get("routes") or []
    out: dict[str, list[dict]] = {}
    for row in rows:
        component = host_to_component.get(str(row.get("service") or ""))
        if component and row.get("file") and row.get("line") and row.get("path"):
            out.setdefault(component, []).append(row)
    return out


class _PyScope:
    """قارئُ تعبيرات URL في ملفّ Python واحد — روابطُ بسيطةٌ تُتبَع بأسطرها، وما سواها ``_Unresolved``."""

    def __init__(self, tree, relative: str):
        import ast

        self.ast = ast
        self.relative = relative
        self.module: dict[str, list] = {}
        self.functions: dict[str, Any] = {}
        self.classes: dict[str, dict[str, list]] = {}
        self.classes_nodes: dict[str, Any] = {}
        for node in tree.body:
            if isinstance(node, ast.Assign) and len(node.targets) == 1:
                target = node.targets[0]
                if isinstance(target, ast.Name):
                    self.module.setdefault(target.id, []).append(node)
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                if node.value is not None:
                    self.module.setdefault(node.target.id, []).append(node)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self.functions[node.name] = node
            elif isinstance(node, ast.ClassDef):
                self.classes_nodes[node.name] = node
                attrs: dict[str, list] = {}
                for inner in ast.walk(node):
                    if isinstance(inner, ast.Assign) and len(inner.targets) == 1:
                        target = inner.targets[0]
                        if (
                            isinstance(target, ast.Attribute)
                            and isinstance(target.value, ast.Name)
                            and target.value.id == "self"
                        ):
                            attrs.setdefault(target.attr, []).append(inner)
                self.classes[node.name] = attrs

    def _env_read(self, node) -> tuple[str, Any] | None:
        """``os.getenv("X", d)`` · ``os.environ.get("X", d)`` · ``os.environ["X"]`` ⇒ (الاسم، عقدةُ الافتراضيّ)."""
        ast = self.ast
        if isinstance(node, ast.Subscript):
            base = ast.unparse(node.value)
            key = node.slice
            if base in {"os.environ", "environ"} and isinstance(key, ast.Constant):
                return (str(key.value), None) if isinstance(key.value, str) else None
            return None
        if not isinstance(node, ast.Call):
            return None
        name = ast.unparse(node.func)
        if name not in {"os.getenv", "getenv", "os.environ.get", "environ.get"}:
            return None
        if not node.args or not isinstance(node.args[0], ast.Constant):
            return None
        if not isinstance(node.args[0].value, str):
            return None
        default = node.args[1] if len(node.args) > 1 else None
        for keyword in node.keywords:
            if keyword.arg == "default":
                default = keyword.value
        return node.args[0].value, default

    def evaluate(self, node, ctx: dict[str, Any], steps: list[str], depth: int = 0) -> list:
        """تعبيرٌ ⇒ أجزاء: ``("lit", s)`` · ``("env", var, default|None, read_line)`` · ``("dyn", why)``."""
        ast = self.ast
        if depth > 8:
            raise _Unresolved("binding_depth_exceeded")
        if isinstance(node, ast.Constant):
            if isinstance(node.value, str):
                return [("lit", node.value)]
            raise _Unresolved("non_string_constant")
        read = self._env_read(node)
        if read is not None:
            var, default = read
            default_value = None
            if default is not None:
                try:
                    parts = self.evaluate(default, ctx, [], depth + 1)
                except _Unresolved:
                    parts = []
                if parts and all(p[0] == "lit" for p in parts):
                    default_value = "".join(p[1] for p in parts)
            return [("env", var, default_value, _line(self.relative, node.lineno))]
        if isinstance(node, ast.JoinedStr):
            out: list = []
            for value in node.values:
                if isinstance(value, ast.Constant):
                    out.append(("lit", str(value.value)))
                elif isinstance(value, ast.FormattedValue):
                    try:
                        out.extend(self.evaluate(value.value, ctx, steps, depth + 1))
                    except _Unresolved as exc:
                        out.append(("dyn", str(exc)))
            return out
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
            left = self.evaluate(node.left, ctx, steps, depth + 1)
            try:
                right = self.evaluate(node.right, ctx, steps, depth + 1)
            except _Unresolved as exc:
                right = [("dyn", str(exc))]
            return left + right
        if isinstance(node, ast.BoolOp) and isinstance(node.op, ast.Or) and len(node.values) == 2:
            first = self.evaluate(node.values[0], ctx, steps, depth + 1)
            second = self.evaluate(node.values[1], ctx, [], depth + 1)
            if (
                len(first) == 1
                and first[0][0] == "env"
                and all(p[0] == "lit" for p in second)
                and second
            ):
                return [("env", first[0][1], "".join(p[1] for p in second), first[0][3])]
            raise _Unresolved("runtime_alternative")
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr in {"strip", "rstrip", "lstrip"} and all(
                isinstance(a, ast.Constant) for a in node.args
            ):
                return self.evaluate(node.func.value, ctx, steps, depth + 1)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and not node.args:
            function = self.functions.get(node.func.id)
            if function is not None and not (
                function.args.args or function.args.posonlyargs or function.args.kwonlyargs
            ):
                returns = [n for n in ast.walk(function) if isinstance(n, ast.Return)]
                if len(returns) == 1 and returns[0].value is not None:
                    steps.append(_line(self.relative, returns[0].lineno))
                    inner = {"locals": _locals(ast, function), "params": set(), "cls": None}
                    return self.evaluate(returns[0].value, inner, steps, depth + 1)
            raise _Unresolved("call_not_followed")
        if isinstance(node, ast.Name):
            if node.id in ctx["params"]:
                raise _Unresolved("parameter")
            bound = ctx["locals"].get(node.id) or self.module.get(node.id) or []
            if len(bound) != 1:
                raise _Unresolved("unbound_or_rebound_name")
            steps.append(_line(self.relative, bound[0].lineno))
            scope = (
                ctx if node.id in ctx["locals"] else {"locals": {}, "params": set(), "cls": None}
            )
            return self.evaluate(bound[0].value, scope, steps, depth + 1)
        if (
            isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id == "self"
            and ctx.get("cls") in self.classes
        ):
            bound = self.classes[ctx["cls"]].get(node.attr) or []
            if len(bound) != 1:
                raise _Unresolved("unbound_or_rebound_attribute")
            steps.append(_line(self.relative, bound[0].lineno))
            owner = _enclosing_function(ast, self.classes_nodes[ctx["cls"]], bound[0])
            scope = {
                "locals": _locals(ast, owner) if owner else {},
                "params": _params(owner) if owner else set(),
                "cls": ctx["cls"],
            }
            return self.evaluate(bound[0].value, scope, steps, depth + 1)
        raise _Unresolved(type(node).__name__.lower())


def _locals(ast, function) -> dict[str, list]:
    out: dict[str, list] = {}
    for node in ast.walk(function):
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            if isinstance(node.targets[0], ast.Name):
                out.setdefault(node.targets[0].id, []).append(node)
        elif isinstance(node, (ast.AugAssign, ast.AnnAssign)) and isinstance(node.target, ast.Name):
            out.setdefault(node.target.id, []).append(node)
        elif isinstance(node, (ast.For, ast.AsyncFor, ast.comprehension)):
            for name in ast.walk(node.target):
                if isinstance(name, ast.Name):
                    out.setdefault(name.id, []).extend([node, node])  # إسنادٌ متكرّر ⇒ غيرُ ثابت
    return out


def _params(function) -> set[str]:
    args = function.args
    names = [a.arg for a in (*args.posonlyargs, *args.args, *args.kwonlyargs)]
    names += [a.arg for a in (args.vararg, args.kwarg) if a is not None]
    return set(names)


def _enclosing_function(ast, root_node, target):
    for node in ast.walk(root_node):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and any(
            inner is target for inner in ast.walk(node)
        ):
            return node
    return None


def _client_factory(ast, call, modules: dict) -> tuple[str, str] | None:
    """``httpx.AsyncClient(...)`` وأخواتُها — والوحدةُ مُثبَتةٌ بـ``import`` في الملفّ نفسِه لا باسمٍ يشبهها."""
    if not isinstance(call, ast.Call) or not isinstance(call.func, ast.Attribute):
        return None
    if not isinstance(call.func.value, ast.Name):
        return None
    module = modules.get(call.func.value.id)
    if module and (module[0], call.func.attr) in _CLIENT_FACTORIES:
        return module[0], call.func.attr
    return None


def _is_test_python(relative: Path) -> bool:
    return (
        relative.name.startswith("test_")
        or relative.name.endswith("_test.py")
        or relative.name == "conftest.py"
        or bool({"tests", "test", "__tests__"}.intersection(relative.parts))
    )


def _python_call_sites(root: Path, components: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """كلُّ نداءِ HTTP بمستقبِلٍ مُثبَتٍ عميلاً في مصدر Python للمكوّنات — بأجزاء URL وأسطر روابطها."""
    import ast

    found: list[dict[str, Any]] = []
    for component in components:
        source = component.get("source_path") or ""
        base = root / source
        if not source or not base.is_dir() or component.get("component_kind") == "frontend":
            continue
        for path in sorted(base.rglob("*.py")):
            relative_path = path.relative_to(root)
            if _is_test_python(relative_path):
                continue
            try:
                text = path.read_text(encoding="utf-8")
                tree = ast.parse(text)
            except (SyntaxError, UnicodeDecodeError):
                continue
            if not any(token in text for token in ("httpx", "requests", "aiohttp")):
                continue
            relative = str(relative_path)
            modules = {}
            for node in tree.body:
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name in _HTTP_MODULES | {"aiohttp"}:
                            modules[alias.asname or alias.name] = (alias.name, node.lineno)
            scope = _PyScope(tree, relative)
            owners: dict[int, tuple] = {}
            for cls in [n for n in tree.body if isinstance(n, ast.ClassDef)]:
                for fn in cls.body:
                    if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        owners[id(fn)] = (fn, cls.name)
            for fn in tree.body:
                if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    owners[id(fn)] = (fn, None)
            for fn, cls_name in owners.values():
                clients: dict[str, dict[str, Any]] = {}
                rebound: set[str] = set()

                for node in ast.walk(fn):
                    if isinstance(node, (ast.With, ast.AsyncWith)):
                        for item in node.items:
                            made = _client_factory(ast, item.context_expr, modules)
                            if made and isinstance(item.optional_vars, ast.Name):
                                name = item.optional_vars.id
                                if name in clients:
                                    rebound.add(name)
                                base_url = next(
                                    (
                                        k.value
                                        for k in item.context_expr.keywords
                                        if k.arg == "base_url"
                                    ),
                                    None,
                                )
                                clients[name] = {"line": node.lineno, "base_url": base_url}
                    elif isinstance(node, ast.Assign) and len(node.targets) == 1:
                        made = _client_factory(ast, node.value, modules)
                        if made and isinstance(node.targets[0], ast.Name):
                            name = node.targets[0].id
                            if name in clients:
                                rebound.add(name)
                            base_url = next(
                                (k.value for k in node.value.keywords if k.arg == "base_url"), None
                            )
                            clients[name] = {"line": node.lineno, "base_url": base_url}
                ctx = {"locals": _locals(ast, fn), "params": _params(fn), "cls": cls_name}
                for node in ast.walk(fn):
                    if not (
                        isinstance(node, ast.Call)
                        and isinstance(node.func, ast.Attribute)
                        and isinstance(node.func.value, ast.Name)
                    ):
                        continue
                    receiver, verb = node.func.value.id, node.func.attr
                    if receiver in modules and modules[receiver][0] in _HTTP_MODULES:
                        binding = _line(relative, modules[receiver][1])
                        base_url = None
                    elif receiver in clients and receiver not in rebound:
                        binding = _line(relative, clients[receiver]["line"])
                        base_url = clients[receiver]["base_url"]
                    else:
                        continue
                    args = list(node.args)
                    if verb == "request":
                        if not args or not isinstance(args[0], ast.Constant):
                            continue
                        method, args = str(args[0].value).upper(), args[1:]
                    elif verb in _HTTP_VERBS:
                        method = verb.upper()
                    else:
                        continue
                    target = (
                        args[0]
                        if args
                        else next((k.value for k in node.keywords if k.arg == "url"), None)
                    )
                    if target is None:
                        continue
                    steps: list[str] = []
                    try:
                        parts = scope.evaluate(target, ctx, steps)
                        if base_url is not None:
                            parts = scope.evaluate(base_url, ctx, steps) + parts
                        error = None
                    except _Unresolved as exc:
                        parts, error = [], str(exc)
                    found.append(
                        {
                            "consumer": component["component_id"],
                            "call_site": _line(relative, node.lineno),
                            "client_binding": binding,
                            "method": method,
                            "parts": parts,
                            "url_bindings": steps,
                            "error": error,
                        }
                    )
    return sorted(found, key=lambda c: (c["consumer"], c["call_site"], c["method"]))


def _assemble(call, env, components_by_service, hosts, compose) -> list[dict[str, Any]]:
    """أجزاءُ URL + بيئةُ خدمةِ compose المستهلكة ⇒ (مضيفٌ، منفذٌ، مسار) بأسطر كلِّ خطوة — أو سببُ الانقطاع."""
    text, env_steps = "", []
    for part in call["parts"]:
        if part[0] == "lit":
            text += part[1]
        elif part[0] == "dyn":
            text += _DYN
        else:
            _, var, default, read_line = part
            if var in env:
                raw, compose_line = env[var]
                value = _compose_value(raw)
                if value is None:
                    return [{"reason": "base_url_unresolved", "why": f"compose_value_unset:{var}"}]
                env_steps.append({"env_var": var, "env_read": read_line, "env_value": compose_line})
            elif default:
                value = default
                env_steps.append({"env_var": var, "env_read": read_line, "env_value": read_line})
            else:
                return [{"reason": "base_url_unresolved", "why": f"env_without_value:{var}"}]
            text += value
    if call["error"] or not text:
        return [{"reason": "base_url_unresolved", "why": call["error"] or "empty_url"}]
    found = _URL.match(text)
    if not found:
        first_dynamic = next((p[1] for p in call["parts"] if p[0] == "dyn"), "")
        return [
            {
                "reason": "base_url_unresolved",
                "why": "url_not_static_up_to_path" + (f":{first_dynamic}" if first_dynamic else ""),
            }
        ]
    scheme, host, port, path = found.groups()
    port = int(port) if port else (443 if scheme == "https" else 80)
    path = (path or "/").split("?", 1)[0]
    segments = re.sub(r"/{2,}", "/", path).strip("/").split("/")
    if _DYN in path:
        if not segments or _DYN in segments[0] or any(_DYN in s and s != _DYN for s in segments):
            if host not in hosts:
                return [{"reason": "external_or_unknown_host", "host": host}]
            return [
                {
                    "reason": "dynamic_path",
                    "host": host,
                    "provider": components_by_service.get(hosts[host], ""),
                }
            ]
        path = "/" + "/".join("{}" if s == _DYN else s for s in segments)
    service = hosts.get(host)
    if service is None:
        return [{"reason": "external_or_unknown_host", "host": host}]
    return [
        {
            "host": host,
            "port": port,
            "path": normalise(path),
            "provider_service": service,
            "provider": components_by_service.get(service, ""),
            "env_steps": env_steps,
            "host_binding": compose[service]["hosts"][host],
            "port_binding": compose[service]["ports"].get(port),
            "provider_ports": sorted(compose[service]["ports"]),
        }
    ]


def python_http_edges(root: Path, components: list[dict[str, Any]]) -> dict[str, Any]:
    """صنفُ الدليل الثالث كاملاً: سلاسلُ مُثبَتة (``chains``) + نداءاتٌ لم تكتمل سلاسلُها بسببها (``unresolved``)."""
    compose = compose_services(root)
    name_to_component: dict[str, str] = {}
    for component in components:
        for name in (
            component["component_id"],
            *component.get("aliases", []),
            *component.get("compose_services", []),
        ):
            name_to_component.setdefault(name, component["component_id"])
    components_by_service = {
        service: name_to_component[service] for service in compose if service in name_to_component
    }
    hosts: dict[str, str] = {}
    for service, entry in compose.items():
        for host in entry["hosts"]:
            hosts.setdefault(host, service)
    routes = _provider_routes(root, name_to_component)
    consumer_services = {
        c["component_id"]: [s for s in c.get("compose_services", []) if s in compose]
        for c in components
    }

    chains: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []
    for call in _python_call_sites(root, components):
        services = consumer_services.get(call["consumer"]) or [None]
        outcomes = []
        for service in services:
            env = compose[service]["env"] if service else {}
            for result in _assemble(call, env, components_by_service, hosts, compose):
                outcomes.append((service, result))
        for service, result in outcomes:
            if "reason" in result:
                if result["reason"] != "external_or_unknown_host":
                    unresolved.append(
                        {
                            "consumer": call["consumer"],
                            "consumer_service": service,
                            "call_site": call["call_site"],
                            "method": call["method"],
                            **result,
                        }
                    )
                continue
            if not result["provider"]:
                continue
            if result["port_binding"] is None:
                unresolved.append(
                    {
                        "consumer": call["consumer"],
                        "consumer_service": service,
                        "call_site": call["call_site"],
                        "method": call["method"],
                        "reason": "base_url_unresolved",
                        "why": f"port_not_served:{result['port']} not in {result['provider_ports']}",
                        "provider": result["provider"],
                    }
                )
                continue
            matched = [
                r
                for r in routes.get(result["provider"], [])
                if str(r["method"]).upper() == call["method"]
                and normalise(r["path"]) == result["path"]
            ]
            if not matched:
                unresolved.append(
                    {
                        "consumer": call["consumer"],
                        "consumer_service": service,
                        "call_site": call["call_site"],
                        "method": call["method"],
                        "reason": "no_provider_route_matches",
                        "provider": result["provider"],
                        "path": result["path"],
                    }
                )
                continue
            for route in matched:
                chains.append(
                    {
                        "consumer": call["consumer"],
                        "consumer_service": service,
                        "provider": result["provider"],
                        "provider_service": result["provider_service"],
                        "operation": f"{call['method']} {route['path']}",
                        "call_site": call["call_site"],
                        "client_binding": call["client_binding"],
                        "url_bindings": call["url_bindings"],
                        "env_steps": result["env_steps"],
                        "host": result["host"],
                        "host_binding": result["host_binding"],
                        "port": result["port"],
                        "port_binding": result["port_binding"],
                        "provider_route": _line(route["file"], route["line"]),
                    }
                )
    # مكوّنٌ بعدّة خدمات compose (منصّةٌ وعمّالُها) يُنتج النداءَ نفسَه مرّاتٍ بالبيئة نفسِها: صفٌّ واحدٌ لكلّ (نداء، عمليّة)،
    # بأسطر أوّل خدمةٍ حلّته، والخدماتُ الأخرى التي حلّته مثلَه أسماءً — تكرارٌ لا دليلٌ زائد.
    merged: dict[tuple, dict[str, Any]] = {}
    for chain in sorted(chains, key=lambda c: c["consumer_service"] or ""):
        key = (chain["consumer"], chain["provider"], chain["operation"], chain["call_site"])
        if key in merged:
            merged[key]["consumer_services"].append(chain["consumer_service"])
        else:
            merged[key] = {**chain, "consumer_services": [chain["consumer_service"]]}
    misses: dict[tuple, dict[str, Any]] = {}
    for item in sorted(unresolved, key=lambda u: u["consumer_service"] or ""):
        key = tuple(sorted((k, str(v)) for k, v in item.items() if k != "consumer_service"))
        misses.setdefault(key, item)
    return {
        "chains": sorted(
            merged.values(),
            key=lambda c: (c["consumer"], c["provider"], c["operation"], c["call_site"]),
        ),
        "unresolved": sorted(
            misses.values(), key=lambda u: (u["consumer"], u["call_site"], u["reason"])
        ),
        "routes": routes,
    }


def _python_unknown_reasons(
    edge: dict[str, Any], method: str, path: str, py: dict[str, Any]
) -> list[dict[str, Any]]:
    """لماذا لم تُثبَت حافّةُ خدمةٍ معلَنة — بموضع كلّ سبب، ولا يُنفى شيءٌ من غياب."""
    found: dict[str, list[str]] = {}
    for item in py["unresolved"]:
        if item["consumer"] != edge["to"] or item["method"] != method:
            continue
        if item.get("provider") not in (None, edge["from"]):
            continue
        if item["reason"] == "dynamic_path" or item["reason"] == "base_url_unresolved":
            found.setdefault(item["reason"], []).append(item["call_site"])
    if not found:
        sites = [
            _line(r["file"], r["line"])
            for r in py["routes"].get(edge["from"], [])
            if str(r["method"]).upper() == method and normalise(r["path"]) == path
        ]
        found["not_seen_by_python_http_scanner"] = sites or [
            f"{ROUTE_INVENTORY}#{edge['from']} {method} {path}"
        ]
    return [
        {"reason": kind, "sites": sorted(set(found[kind]))}
        for kind in PYTHON_UNKNOWN_REASONS
        if kind in found
    ]


def classify(
    edges: list[dict[str, Any]], components: list[dict[str, Any]], root: Path = ROOT
) -> dict[str, Any]:
    """كلُّ عمليّةٍ معلَنة ⇒ مُثبَتة (``proven``) · منفيّة في نطاقها (``refuted``) · مجهولةٌ بأسبابٍ مسمّاة (``unknown``).

    ``proven`` = صفوفُ ``resolve`` + اشتراكاتُ NATS المُثبَتة. ``unknown`` صفوفُ الحوافّ الباقية كما هي، وكلُّ عمليّةٍ
    فيها تحمل ``unknown_reasons[entrypoint] = [{reason, sites}]`` — لا عمليّةَ بلا سبب."""
    resolved, remaining, report = resolve(edges, components, root)
    prefixes = client_prefixes(root)
    gate = gateway(root, components)
    proxies = sorted(
        [route for route in gate["routes"] if route["kind"] == "proxy"],
        key=lambda route: -len(route["client"]),
    )
    reachable = {c for c in gate["upstreams"].values() if c}
    upstream_lines = {}
    conf = root / "frontend/nginx.conf"
    if conf.exists():
        current = None
        for number, line in enumerate(conf.read_text(encoding="utf-8").splitlines(), 1):
            found = _UPSTREAM.match(line)
            if found:
                current = found.group(1)
            elif _SERVER.match(line) and current:
                upstream_lines[current] = f"frontend/nginx.conf:{number}"
                current = None

    subscriptions = nats_subscriptions(root, components)
    py = python_http_edges(root, components)
    python_consumers = {
        c["component_id"]
        for c in components
        if c.get("component_kind") != "frontend"
        and c.get("source_path")
        and (root / c["source_path"]).is_dir()
    }
    dynamic = [
        item
        for item in report["unsupported_call_sites"]
        if item["source_kind"] == "application" and item["instance"] in prefixes
    ]
    value_uses = _value_uses(root, prefixes)
    unparsed = [item["site"] for item in report["unparsed_source_files"]]

    proven = list(resolved)
    refuted: list[dict[str, Any]] = []
    unknown: list[dict[str, Any]] = []
    for edge in remaining:
        pending = list(dict.fromkeys(edge.get("entrypoints") or []))
        reasons: dict[str, list[dict[str, Any]]] = {}
        still: list[str] = []
        consumer = _NATS_CONSUMER.match(edge["to"])
        for entrypoint in pending:
            parts = entrypoint.split(None, 1)
            if consumer and len(parts) == 2 and parts[0] == "NATS":
                matches = [
                    s
                    for s in subscriptions
                    if s["component"] == consumer["component"]
                    and s["durable"] == consumer["durable"]
                    and s["subject"] == parts[1]
                ]
                if matches:
                    for chain in matches:
                        proven.append(
                            {
                                **edge,
                                "entrypoints": [entrypoint],
                                "evidence_state": "resolved",
                                "resolved_entrypoint": entrypoint,
                                "evidence": {
                                    "kind": "python_nats_subscription",
                                    "evidence_scope": "static_source_only",
                                    **{k: v for k, v in chain.items() if k != "component"},
                                },
                            }
                        )
                    continue
            if (
                edge["to"] in python_consumers
                and len(parts) == 2
                and parts[0].lower() in _HTTP_VERBS
            ):
                # صنفُ الدليل الثالث: المستهلكُ خدمةُ Python — موضعُ نداءٍ في مصدرها أو سببٌ مسمّى، لا نفيٌ من غياب.
                method, service_path = parts[0].upper(), normalise(parts[1])
                matches = [
                    chain
                    for chain in py["chains"]
                    if chain["consumer"] == edge["to"]
                    and chain["provider"] == edge["from"]
                    and chain["operation"].split(None, 1)[0] == method
                    and normalise(chain["operation"].split(None, 1)[1]) == service_path
                ]
                for chain in matches:
                    proven.append(
                        {
                            **edge,
                            "entrypoints": [entrypoint],
                            "evidence_state": "resolved",
                            "resolved_entrypoint": entrypoint,
                            "evidence": {
                                "kind": "python_http_call_site",
                                "evidence_scope": "static_source_only",
                                **{k: v for k, v in chain.items() if k != "consumer"},
                            },
                        }
                    )
                if not matches:
                    reasons[entrypoint] = _python_unknown_reasons(edge, method, service_path, py)
                    still.append(entrypoint)
                continue
            if edge["to"] != "frontend" or len(parts) != 2 or not conf.exists():
                # لا صنفَ دليلٍ ساكناً لهذا النوع من الحوافّ — أو لا بوّابةَ مقروءة: غيابُ الملفّ ليس دليلَ نفي
                reasons[entrypoint] = [
                    {
                        "reason": "no_static_evidence_class_for_this_edge_kind",
                        "sites": [f"platform_catalog.generated.json#{edge['capability_id']}"],
                        "detail": f"consumer={edge['to']!r} entrypoint={entrypoint!r}",
                    }
                ]
                still.append(entrypoint)
                continue
            method, service_path = parts[0].upper(), normalise(parts[1])
            browsers = _browser_paths(edge["from"], service_path, gate, proxies)
            if edge["from"] not in reachable or not browsers:
                kind = (
                    "producer_has_no_gateway_upstream"
                    if edge["from"] not in reachable
                    else "operation_not_routed_by_gateway"
                )
                refuted.append(
                    {
                        **edge,
                        "entrypoints": [entrypoint],
                        "evidence_state": "refuted",
                        "refutation": {
                            "kind": kind,
                            "scope": "gateway_mode",
                            "producer": edge["from"],
                            "gateway_upstreams": dict(sorted(gate["upstreams"].items())),
                            "upstream_declarations": sorted(upstream_lines.values()),
                            "producer_routes": sorted(
                                r["line"]
                                for r in gate["routes"]
                                if r["kind"] == "proxy"
                                and gate["upstreams"].get(r["upstream"]) == edge["from"]
                            ),
                            "why": (
                                "the browser reaches only what frontend/nginx.conf routes; no upstream "
                                "there resolves to this producer"
                                if kind == "producer_has_no_gateway_upstream"
                                else "every gateway location routed to this producer maps to other "
                                "service paths (or a longer/exact location shadows it), so no "
                                "browser path reaches this operation"
                            )
                            + " — in gateway mode; direct VITE_*_BASE_URL dev mode is out of scope",
                        },
                    }
                )
                continue
            found: dict[str, list[str]] = {}
            for call in report["unproven_client_bindings"]:
                client = prefixes.get(call["instance"])
                if client is None or not _method_can_match(call["method"], method):
                    continue
                browser = normalise(client["prefix"] + call["path"])
                if any(b == browser for b, _ in browsers if b is not None) or any(
                    b is None and _route_for(browser, proxies) is r for b, r in browsers
                ):
                    found.setdefault("call_site_binding_unproven", []).append(call["site"])
            for call in dynamic:
                if not _method_can_match(call["method"], method):
                    continue
                known = prefixes[call["instance"]]["prefix"] + call.get("literal_prefix", "")
                if any(
                    (b is None and _segments_compatible(known, normalise(r["client"])))
                    or (b is not None and _segments_compatible(known, b))
                    for b, r in browsers
                ):
                    found.setdefault("dynamic_call_may_reach", []).append(call["site"])
            for use in value_uses if _method_can_match(None, method) else ():
                known = prefixes[use["instance"]]["prefix"]
                if any(
                    _segments_compatible(known, b if b is not None else normalise(r["client"]))
                    for b, r in browsers
                ):
                    found.setdefault("client_passed_as_value", []).append(use["site"])
            if unparsed and browsers:
                found["unparsed_source_may_call"] = list(unparsed)
            if not found:
                # تبلغها البوّابة ولم يُرَ نداءٌ: الماسحُ يقرأ نداءاتِ axios وحدها — fetch وWebSocket وEventSource
                # وروابطُ الأصول (بلاطاتُ الخرائط) خارجه. فالغيابُ هنا غيابُ رؤية، وموضعُه قاعدةُ البوّابة التي تبلغها.
                found["not_seen_by_axios_scanner"] = [r["line"] for _, r in browsers]
            reasons[entrypoint] = [
                {"reason": kind, "sites": sorted(set(found[kind]))}
                for kind in UNKNOWN_REASON_ORDER
                if kind in found
            ]
            still.append(entrypoint)
        if still:
            unknown.append(
                {
                    **edge,
                    "entrypoints": still,
                    "unknown_reasons": {e: reasons.get(e, []) for e in still},
                }
            )

    def count(rows):
        return sum(len(r.get("entrypoints") or []) for r in rows)

    by_reason: dict[str, int] = {}
    for row in unknown:
        for entry in row["unknown_reasons"].values():
            key = entry[0]["reason"] if entry else "none"
            by_reason[key] = by_reason.get(key, 0) + 1
    summary = {
        "proven_rows": len(proven),
        "proven_nats_rows": sum(
            1 for r in proven if r["evidence"].get("kind") == "python_nats_subscription"
        ),
        "refuted_operations": count(refuted),
        "refuted_by_producer": {
            p: sum(1 for r in refuted if r["from"] == p)
            for p in sorted({r["from"] for r in refuted})
        },
        "refutation_scope": "gateway_mode",
        "unknown_operations": count(unknown),
        "unknown_by_primary_reason": dict(sorted(by_reason.items())),
        "unknown_operations_without_reason": by_reason.get("none", 0),
        "nats_subscriptions_located": len(subscriptions),
        "proven_python_http_rows": sum(
            1 for r in proven if r["evidence"].get("kind") == "python_http_call_site"
        ),
        # الصنفُ الثالث مقيساً على الشجرة كلِّها — لا على الحوافّ المعلَنة وحدها: سلسلةٌ كاملةٌ لا يقابلها إعلانٌ في
        # الكتالوج تُعرَض هنا **اكتشافاً** (``observed_undeclared``) لا ترقيةً؛ الإعلانُ قرارُ مالكه لا قرارُ الماسح.
        "python_http": {
            "compose_file": COMPOSE_FILE,
            "route_inventory": ROUTE_INVENTORY,
            "chains_located": len(py["chains"]),
            "observed_undeclared": [
                {k: chain[k] for k in ("consumer", "provider", "operation", "call_site")}
                for chain in py["chains"]
                if not any(
                    e["to"] == chain["consumer"]
                    and e["from"] == chain["provider"]
                    and any(
                        len(op.split(None, 1)) == 2
                        and op.split(None, 1)[0].upper() == chain["operation"].split(None, 1)[0]
                        and normalise(op.split(None, 1)[1])
                        == normalise(chain["operation"].split(None, 1)[1])
                        for op in e.get("entrypoints") or []
                    )
                    for e in edges
                )
            ],
            # نداءاتٌ بمستقبِلٍ مُثبَتٍ عميلاً انقطعت سلسلتُها — بموضعها وسببها؛ ليست حوافَّ منفيّة بل رؤيةً ناقصة،
            # إلّا ``no_provider_route_matches``: سلسلةٌ كاملةٌ حتّى منتِجٍ لا يُعلن ذلك المسار في جرد المسارات.
            "unresolved_calls": py["unresolved"],
            "unresolved_calls_by_reason": {
                kind: sum(1 for item in py["unresolved"] if item["reason"] == kind)
                for kind in sorted({item["reason"] for item in py["unresolved"]})
            },
            "scanner_limitations": [
                "Receivers are read only when proven HTTP clients (httpx/requests modules, or a name "
                "bound in the same function to httpx.Client/AsyncClient, requests.Session, "
                "aiohttp.ClientSession); wrapper clients and self._client attributes are not followed",
                "URL bindings followed: single assignment (module or function), self.attr in the same "
                "class, zero-argument functions with one return, f-strings, +, strip/rstrip/lstrip, "
                "`env or literal`",
                "Environment values come from " + COMPOSE_FILE + " only; other compose files, .env "
                "files and deployment platforms are out of scope",
                "A dynamic path matches only as a template: a static first segment and every runtime "
                "part filling a whole segment",
                "Calls to hosts that are not compose services of an inventory component are not edges here",
            ],
        },
        "client_value_uses": value_uses,
    }
    return {
        "proven": proven,
        "refuted": refuted,
        "unknown": unknown,
        "report": {**report, "classification": summary},
    }


EXEMPTIONS = ROOT / "docs/architecture/inventory_edge_exemptions.json"


def exemption_problems(unknown: list[dict[str, Any]], exemptions: dict[str, Any]) -> list[str]:
    """كلُّ سببِ «مجهول» مستعمَلٍ يجب أن يكون معلَناً بمبرّرٍ وشرطِ إغلاق؛ وما أُعلن ولم يعد مستعمَلاً بائتٌ يُزال —
    سجلٌّ يطول بأسبابٍ لا تقع يصير إذناً مسبقاً لا قراراً. وعمليّةٌ بلا سببٍ أو سببٌ بلا موضع ⇒ مشكلة."""
    problems: list[str] = []
    listed = exemptions.get("accepted_unknown_reasons") or {}
    used: set[str] = set()
    for row in unknown:
        for entrypoint, entries in (row.get("unknown_reasons") or {}).items():
            if not entries:
                problems.append(f"unknown_without_reason: {row['from']} {entrypoint}")
            for entry in entries:
                used.add(entry["reason"])
                if not entry.get("sites"):
                    problems.append(
                        f"reason_without_site: {entry['reason']} {row['from']} {entrypoint}"
                    )
    for kind in sorted(used - set(listed)):
        problems.append(f"unlisted_reason: {kind}")
    for kind, decision in sorted(listed.items()):
        if not isinstance(decision, dict) or not all(
            str(decision.get(k) or "").strip() for k in ("justification", "closing_condition")
        ):
            problems.append(f"unjustified_reason: {kind}")
        if kind not in used:
            problems.append(f"stale_reason: {kind}")
    return problems
