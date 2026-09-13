"""فكُّ JWT خارج `shared/security/` — راتشِت يتقلّص ولا ينمو.

``JWT-DECODE-OUTSIDE-SHARED-SECURITY-01`` (المراجعة البنيويّة 2026-09-13 §٢.٤).

**المقيس الذي أوجب هذا الحارس:** `shared/security/` ناضج (`jwt_key_validation` ·
`tenant_context` · `trusted_tenant` · `decision_service_auth`) و**١٢ خدمة** تستورده — ومع
ذلك يظهر ``jwt.decode(`` في **١٦ ملفّاً** خارجه، بعضُها يستورد ``shared.security`` ويفكّ
التوكن بنفسه أيضاً. كلُّ موضعٍ منها سطحٌ مستقلّ يمكن أن ينحرف عن سياسة المفاتيح المركزيّة
(الخوارزميّة · الجمهور · المُصدِر · قائمةُ الإبطال) **بلا أن يحمرّ شيء** — وقد حدث بالفعل
في هذا المستودع: تعارضُ ``X-Agent-Token``/``Bearer`` (#990) كان انحرافَ موضعٍ واحدٍ عن
العقد المشترَك.

**القاعدة راتشِت لا حائط:** المواضعُ القائمة دَينٌ مُعلَن بأعداده لكلّ ملفّ. ملفٌّ جديد
يفكّ JWT بنفسه يسقط · زيادةٌ في ملفٍّ قائم تسقط · و**نقصانٌ لا يُخفَّض معه الأساس يسقط
أيضاً** (وإلّا وصف الرقمُ كوناً زال). المخرجُ الوحيد هو النقلُ إلى ``shared.security``.

**حدُّ صدق:** ``services/auth/`` هو **المُصدِر** فيفكّ توكناته بحقّ (تحديث الجلسة ·
التحقّق الذاتيّ) — يبقى في الأساس مُعلَناً لا مُعفىً، لأنّ الهدفَ النهائيّ هو أن يفكّ
عبر الوحدة المشتركة أيضاً. ولا يُقاس هنا ``jwt.encode`` ولا ``PyJWKClient`` — الادّعاءُ
أضيق: **لا موضعَ فكٍّ جديد خارج الوحدة المشتركة.**

يُشغَّل في ``capability-governance.yml`` مع بقيّة حرّاس ``tests/architecture/``
(``ARCH-TESTS-UNLISTED-IN-CI-01``).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[2]
SEARCH_ROOTS = ("services", "shared", "agents", "bots")
CANONICAL = "shared/security/"
# الاسمُ المستعار شائع في هذه الشجرة (`_jwt` · `_jjwt` · `_v_jwt`): أيُّ معرِّفٍ ينتهي بـ`jwt`.
_DECODE = re.compile(r"\b[A-Za-z_][A-Za-z0-9_]*jwt\.decode\(|\bjwt\.decode\(")

#: الأساسُ المُجمَّد — مقيسٌ على `9613db9a`. كلُّ مدخلٍ دَينٌ مُعلَن والقيمةُ سقفُه.
#: **يُخفَّض عند النقل إلى `shared.security` ولا يُرفَع.**
FROZEN_SITES: dict[str, int] = {
    "agents/notification/agent.py": 1,
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


def count_decode_sites(root: Path = ROOT) -> dict[str, int]:
    """مواضعُ `jwt.decode(` في ملفّات الإنتاج خارج `shared/security/` (نقيّة، قابلة للاختبار)."""
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
            n = sum(
                1
                for line in text.splitlines()
                if not line.lstrip().startswith("#") and _DECODE.search(line)
            )
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
        "JWT-DECODE-OUTSIDE-SHARED-SECURITY-01: مواضعُ فكٍّ جديدة في ملفٍّ مُعلَن — "
        + ", ".join(f"{f}: {live[f]} > {FROZEN_SITES[f]}" for f in grown)
    )


def test_the_frozen_baseline_is_lowered_when_a_site_is_migrated():
    live = count_decode_sites()
    stale = sorted(f for f, cap in FROZEN_SITES.items() if live.get(f, 0) < cap)
    assert not stale, "الأساسُ يصف كوناً زال — خفِّضه: " + ", ".join(
        f"{f}: live={live.get(f, 0)} < frozen={FROZEN_SITES[f]}" for f in stale
    )


def test_the_detector_sees_a_decode_call_and_ignores_comments_tests_and_the_canonical_module(
    tmp_path,
):
    """تكذيبٌ ذاتيّ: كاشفٌ يمرّ على شجرةٍ سليمة يمرّ أيضاً لو لم يفعل شيئاً."""
    (tmp_path / "services" / "x").mkdir(parents=True)
    (tmp_path / "services" / "x" / "main.py").write_text(
        "import jwt\n# jwt.decode(comment)\nclaims = jwt.decode(tok, key, algorithms=['RS256'])\n"
        "import jwt as _v_jwt\npayload = _v_jwt.decode(tok, key)\n",
        encoding="utf-8",
    )
    (tmp_path / "services" / "x" / "test_main.py").write_text("jwt.decode(t)\n", encoding="utf-8")
    (tmp_path / "shared" / "security").mkdir(parents=True)
    (tmp_path / "shared" / "security" / "core.py").write_text("jwt.decode(t)\n", encoding="utf-8")
    assert count_decode_sites(tmp_path) == {"services/x/main.py": 2}
