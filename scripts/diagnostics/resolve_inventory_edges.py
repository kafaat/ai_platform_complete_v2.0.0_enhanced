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
_PATH = re.compile(r"/[A-Za-z0-9/_{}.-]*")
_PARAMETER = re.compile(r"\$\{[A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)*\}")
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
            location = (found.group(2), number)
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
            if not _ANY_CALL.match(code, pos):
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
                    candidate = _PARAMETER.sub("{}", raw) if text[i] == "`" else raw
                    tail = code[end:].lstrip()
                    if (
                        text[end - 1] == text[i]
                        and _PATH.fullmatch(candidate)
                        and tail.startswith((",", ")"))
                    ):
                        value = candidate
            if value is None:
                (tests if test_source else blind).append(
                    {**call, "reason": "unsupported_or_dynamic_path"}
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
