"""فكُّ JWT خارج `shared/security/` — راتشِت يتقلّص ولا ينمو.

``JWT-DECODE-OUTSIDE-SHARED-SECURITY-01`` (المراجعة البنيويّة 2026-09-13 §٢.٤).

**المقيس الذي أوجب هذا الحارس:** `shared/security/` ناضج (`jwt_key_validation` ·
`tenant_context` · `trusted_tenant` · `decision_service_auth`) و**١٢ خدمة** تستورده — ومع
ذلك يظهر فكُّ JWT في **١٦ ملفّاً** خارجه، بعضُها يستورد ``shared.security`` ويفكّ التوكن
بنفسه أيضاً. كلُّ موضعٍ منها سطحٌ مستقلّ يمكن أن ينحرف عن سياسة المفاتيح المركزيّة
(الخوارزميّة · الجمهور · المُصدِر · قائمةُ الإبطال) **بلا أن يحمرّ شيء** — وقد حدث بالفعل
في هذا المستودع: تعارضُ ``X-Agent-Token``/``Bearer`` (#990) كان انحرافَ موضعٍ واحدٍ عن
العقد المشترَك.

**القاعدة راتشِت لا حائط:** المواضعُ القائمة دَينٌ مُعلَن بأعداده لكلّ ملفّ. ملفٌّ جديد
يفكّ JWT بنفسه يسقط · زيادةٌ في ملفٍّ قائم تسقط · و**نقصانٌ لا يُخفَّض معه الأساس يسقط
أيضاً** (وإلّا وصف الرقمُ كوناً زال). المخرجُ الوحيد هو النقلُ إلى ``shared.security``.

**الكاشفُ يتبع الاستيراد لا الاسم** (مراجعة Copilot على #995، وكانت صحيحة): نسختُه الأولى
كانت تعبيراً نمطيّاً يلتقط ``jwt.decode(`` ومعرِّفاتٍ تنتهي بـ``jwt`` — فـ``import jwt as
token; token.decode(...)`` أو ``from jwt import decode`` كانا يمرّان. الآن يُحلَّل الملفُّ
بـ``ast``: كلُّ اسمٍ مربوطٍ بوحدة ``jwt`` أو ``jose.jwt`` (بأيّ اسمٍ مستعار) يُعدّ فكُّ
``.decode`` عليه، وكلُّ دالّةٍ مستورَدةٍ باسم ``decode`` من تلك الوحدات (بأيّ اسم) يُعدّ
نداؤها — **نداءً نداءً لا سطراً سطراً**، فنداءان في سطرٍ واحد اثنان.

**حدُّ صدق:** ``services/auth/`` هو **المُصدِر** فيفكّ توكناته بحقّ (تحديث الجلسة ·
التحقّق الذاتيّ) — يبقى في الأساس مُعلَناً لا مُعفىً، لأنّ الهدفَ النهائيّ أن يفكّ عبر
الوحدة المشتركة أيضاً. ولا يُقاس ``jwt.encode`` ولا ``PyJWKClient`` ولا فكٌّ عبر متغيّرٍ
يحمل الوحدةَ ديناميكيّاً (``importlib``) — الادّعاءُ أضيق: **لا موضعَ فكٍّ جديد يُستورَد
صراحةً خارج الوحدة المشتركة.**

يُشغَّل في ``capability-governance.yml`` مع بقيّة حرّاس ``tests/architecture/``
(``ARCH-TESTS-UNLISTED-IN-CI-01``).
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[2]
SEARCH_ROOTS = ("services", "shared", "agents", "bots")
CANONICAL = "shared/security/"
#: الوحداتُ التي تُصدِر فكَّ JWT: PyJWT و python-jose.
JWT_MODULES = frozenset({"jwt", "jose.jwt"})

#: الأساسُ المُجمَّد — مقيسٌ على `9613db9a` بالكاشف الـAST. كلُّ مدخلٍ دَينٌ مُعلَن والقيمةُ
#: سقفُه (عددُ النداءات). **يُخفَّض عند النقل إلى `shared.security` ولا يُرفَع.**
FROZEN_SITES: dict[str, int] = {
    # notification moved to shared/security/access_tokens.py in #997 (f7cd7848; local 1091c55).
    "services/actuator-service/actuator_runtime.py": 1,
    "services/auth/main.py": 2,
    "services/auth/routers/session.py": 1,
    "services/guardrails-engine/main.py": 2,
    "services/local-ai-rag/main.py": 1,
    "services/mcp_servers/market_server.py": 1,
    "services/mcp_servers/shared/oauth_middleware.py": 1,
    "services/odoo-bridge/main.py": 1,
    "services/sahool-platform/api/chat_proxy_reference.py": 2,
    "services/sahool-platform/api/main.py": 1,
    "services/sahool-platform/api/routers/auth.py": 1,
    "services/supervisor-agent/main.py": 1,
    "services/tts-service/main.py": 1,
    "services/vegetation-analysis-service/vegetation_runtime.py": 1,
    "services/video-processor/main.py": 1,
}


def _is_test_path(rel: str) -> bool:
    parts = rel.split("/")
    name = parts[-1]
    return (
        name.startswith("test_")
        or name.endswith("_test.py")
        or "tests" in parts
        or "__pycache__" in parts
    )


def _is_jwt_module(name: str) -> bool:
    return name in JWT_MODULES


class _DecodeCounter(ast.NodeVisitor):
    """يتبع الأسماءَ المربوطة بوحدة JWT وبدالّة `decode` المستورَدة منها، ويعدّ النداءات."""

    def __init__(self) -> None:
        self.module_aliases: set[str] = set()  # `import jwt as X` · `from jose import jwt as X`
        self.decode_aliases: set[str] = set()  # `from jwt import decode as Y`
        self.calls = 0

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            if _is_jwt_module(alias.name):
                self.module_aliases.add(alias.asname or alias.name.split(".")[0])
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        module = node.module or ""
        for alias in node.names:
            if _is_jwt_module(f"{module}.{alias.name}"):  # from jose import jwt
                self.module_aliases.add(alias.asname or alias.name)
            elif _is_jwt_module(module) and alias.name == "decode":  # from jwt import decode
                self.decode_aliases.add(alias.asname or alias.name)
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        func = node.func
        if (
            isinstance(func, ast.Attribute)
            and func.attr == "decode"
            and isinstance(func.value, ast.Name)
            and func.value.id in self.module_aliases
        ):
            self.calls += 1
        elif isinstance(func, ast.Name) and func.id in self.decode_aliases:
            self.calls += 1
        self.generic_visit(node)


def count_decode_calls_in_source(source: str) -> int:
    """نقيّة: عددُ نداءات فكّ JWT في نصّ Python واحد (صفرٌ إن لم يُعرَب)."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return 0
    counter = _DecodeCounter()
    counter.visit(tree)
    return counter.calls


def count_decode_sites(root: Path = ROOT) -> dict[str, int]:
    """نداءاتُ فكّ JWT في ملفّات الإنتاج خارج `shared/security/` (نقيّة، قابلة للاختبار)."""
    found: dict[str, int] = {}
    for top in SEARCH_ROOTS:
        base = root / top
        if not base.exists():
            continue
        for path in sorted(base.rglob("*.py")):
            rel = path.relative_to(root).as_posix()
            if rel.startswith(CANONICAL) or _is_test_path(rel):
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            n = count_decode_calls_in_source(text)
            if n:
                found[rel] = n
    return found


def test_no_new_jwt_decode_site_outside_shared_security():
    live = count_decode_sites()
    new_files = sorted(set(live) - set(FROZEN_SITES))
    grown = sorted(f for f in live if f in FROZEN_SITES and live[f] > FROZEN_SITES[f])
    assert not new_files, (
        "JWT-DECODE-OUTSIDE-SHARED-SECURITY-01: ملفٌّ جديد يفكّ JWT بنفسه — "
        f"انقل الفكَّ إلى shared/security/: {new_files}"
    )
    assert not grown, (
        "JWT-DECODE-OUTSIDE-SHARED-SECURITY-01: نداءاتُ فكٍّ جديدة في ملفٍّ مُعلَن — "
        + ", ".join(f"{f}: {live[f]} > {FROZEN_SITES[f]}" for f in grown)
    )


def test_the_frozen_baseline_is_lowered_when_a_site_is_migrated():
    live = count_decode_sites()
    stale = sorted(f for f, cap in FROZEN_SITES.items() if live.get(f, 0) < cap)
    assert not stale, "الأساسُ يصف كوناً زال — خفِّضه: " + ", ".join(
        f"{f}: live={live.get(f, 0)} < frozen={FROZEN_SITES[f]}" for f in stale
    )


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("import jwt\nclaims = jwt.decode(t, k, algorithms=['RS256'])\n", 1),
        ("import jwt as _v_jwt\np = _v_jwt.decode(t, k)\n", 1),
        # الثغرتان اللتان سمّتهما المراجعة: اسمٌ مستعارٌ لا ينتهي بـjwt، ودالّةٌ مستورَدة.
        ("import jwt as token\np = token.decode(t, k)\n", 1),
        ("from jwt import decode\np = decode(t, k)\n", 1),
        ("from jwt import decode as verify_token\np = verify_token(t, k)\n", 1),
        ("from jose import jwt\np = jwt.decode(t, k)\n", 1),
        ("from jose import jwt as J\np = J.decode(t, k)\n", 1),
        ("import jose.jwt as jj\np = jj.decode(t, k)\n", 1),
        # نداءان في سطرٍ واحد = اثنان (كان العدُّ سطراً سطراً فيبتلع الثاني).
        ("import jwt\na, b = jwt.decode(x, k), jwt.decode(y, k)\n", 2),
        # لا يُعدّ: تعليق · نصّ · `.decode` على غير وحدة JWT · `encode`.
        (
            "import jwt\n# jwt.decode(t)\ns = 'jwt.decode('\nb = data.decode('utf-8')\nw = jwt.encode(c, k)\n",
            0,
        ),
        ("import base64\np = base64.b64decode(t)\n", 0),
    ],
    ids=[
        "bare",
        "alias_ending_jwt",
        "alias_arbitrary",
        "from_import_decode",
        "from_import_decode_renamed",
        "jose_jwt",
        "jose_jwt_alias",
        "jose_dotted_alias",
        "two_calls_one_line",
        "comment_string_other_decode_encode",
        "unrelated_decode",
    ],
)
def test_the_detector_follows_imports_not_names(source, expected):
    """تكذيبٌ ذاتيّ: كاشفٌ يمرّ على شجرةٍ سليمة يمرّ أيضاً لو لم يفعل شيئاً."""
    assert count_decode_calls_in_source(source) == expected


def test_the_tree_walker_skips_tests_and_the_canonical_module(tmp_path):
    (tmp_path / "services" / "x").mkdir(parents=True)
    (tmp_path / "services" / "x" / "main.py").write_text(
        "import jwt as token\nclaims = token.decode(tok, key)\n", encoding="utf-8"
    )
    (tmp_path / "services" / "x" / "test_main.py").write_text(
        "import jwt\njwt.decode(t, k)\n", encoding="utf-8"
    )
    (tmp_path / "shared" / "security").mkdir(parents=True)
    (tmp_path / "shared" / "security" / "core.py").write_text(
        "import jwt\njwt.decode(t, k)\n", encoding="utf-8"
    )
    assert count_decode_sites(tmp_path) == {"services/x/main.py": 1}
