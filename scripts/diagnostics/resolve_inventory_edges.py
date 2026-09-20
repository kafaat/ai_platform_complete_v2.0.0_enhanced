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
#: `rasterApi.get('/v1/x')` · `rasterApi.post(\n  '/v1/x'` — النقطةُ ثمّ الفعلُ ثمّ المسار.
_CALL = re.compile(
    r"\b([A-Za-z0-9_]+Api)\s*\.\s*(get|post|put|patch|delete)\s*[(<][^'\"`)]{0,120}?"
    r"['\"`](/[A-Za-z0-9/_\-.${}]*)"
)
#: **كلُّ** نداءٍ على نسخةِ عميل، بمسارٍ حرفيٍّ أو بغيره. الفرقُ بينه وبين
#: `_CALL` هو حجمُ ما لا يراه الماسحُ الساكن — ويُعَدّ لا يُهمَل.
_ANY_CALL = re.compile(r"\b([A-Za-z0-9_]+Api)\s*\.\s*(?:get|post|put|patch|delete)\s*[(<]")
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


def call_sites(root: Path = ROOT) -> tuple[list[dict[str, Any]], int]:
    """مواضعُ النداء الحرفيّة — الخطوةُ ٣ — وعددُ ما لا يراه الماسح."""
    source = root / "frontend/src"
    if not source.exists():
        return [], 0
    calls: list[dict[str, Any]] = []
    blind = 0
    for path in sorted(source.rglob("*.ts*")):
        text = path.read_text(encoding="utf-8", errors="replace")
        relative = path.relative_to(root)
        for number, line in enumerate(text.splitlines(), 1):
            for match in _CALL.finditer(line):
                calls.append(
                    {
                        "instance": match.group(1),
                        "method": match.group(2).upper(),
                        "path": match.group(3),
                        "site": f"{relative}:{number}",
                    }
                )
            # نداءٌ بلا مسارٍ حرفيّ: يُعَدّ ولا يُدَّعى شيءٌ عنه. الفرقُ بين العدّين
            # هو حجمُ عمى الماسح — يُصدَّر كي لا يُقرأ الباقي عطلاً وهو رؤية.
            blind += len(_ANY_CALL.findall(line)) - len(_CALL.findall(line))
    return calls, max(blind, 0)


def resolve(
    edges: list[dict[str, Any]], components: list[dict[str, Any]], root: Path = ROOT
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    """يُعيد (المحسومة، الباقية على حالها، تقريرَ القياس)."""
    prefixes = client_prefixes(root)
    gate = gateway(root, components)
    calls, blind = call_sites(root)

    proxies = sorted(
        [route for route in gate["routes"] if route["kind"] == "proxy"],
        key=lambda route: -len(route["client"]),
    )
    rewrites = [route for route in gate["routes"] if route["kind"] == "rewrite"]

    # (مكوّن، مسارٌ داخليّ مُطبَّع) ⇒ سلسلةُ الدليل
    index: dict[tuple[str, str], dict[str, Any]] = {}
    for call in calls:
        client = prefixes.get(call["instance"])
        if client is None:
            continue
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
            index.setdefault(
                (component, service_path),
                {
                    "call_site": call["site"],
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
        chain = None
        for entrypoint in edge.get("entrypoints") or []:
            declared = entrypoint.split(" ", 1)[1] if " " in entrypoint else entrypoint
            chain = index.get((edge["from"], normalise(declared)))
            if chain:
                matched = entrypoint
                break
        if not chain:
            remaining.append(edge)
            continue
        resolved.append(
            {
                **edge,
                "evidence_state": "resolved",
                "resolved_entrypoint": matched,
                "evidence": {
                    "kind": "frontend_call_site_through_gateway",
                    **chain,
                },
            }
        )
    report = {
        "frontend_clients": len(prefixes),
        "gateway_rules": len(gate["routes"]),
        "gateway_upstreams_mapped": sum(1 for v in gate["upstreams"].values() if v),
        "gateway_upstreams_unmapped": sum(1 for v in gate["upstreams"].values() if not v),
        "literal_call_sites": len(calls),
        # **حدُّ الماسح، مُعلَناً بعدده:** غيابُ الدليل هنا قد يكون غيابَ رؤية.
        "scanner_blind_spots": blind,
        "resolved": len(resolved),
        "still_unresolved": len(remaining),
    }
    return resolved, remaining, report
