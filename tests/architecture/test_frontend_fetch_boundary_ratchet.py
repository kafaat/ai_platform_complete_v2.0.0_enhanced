"""`fetch(` خارج طبقة الـAPI في الواجهة — راتشِت يتقلّص ولا ينمو.

``FRONTEND-FETCH-OUTSIDE-API-LAYER-01`` (المراجعة البنيويّة 2026-09-13 §٥، **بعد تصحيح
القياس**: العدُّ الأوّل ٦٢ ملفّاً كان يلتقط ``refetch``/``prefetch`` من TanStack Query؛
المقيسُ بحدّ الكلمة **٨ مواضع في ٣ ملفّات**، كلُّها في وحدة الطقس على الخريطة وكلُّها
تمرّر ``weatherFetchHeaders()``).

**لماذا يستحقّ حارساً رغم صغره:** #993 أثبت أنّ تغييرَ ترويسة مصادقةٍ أو مسارٍ يحتاج
مسحاً لا تعديلاً في مكانٍ واحد كلّما وُجِد ``fetch`` خارج ``services/api.ts`` — وهذه
الثلاثةُ هي بالضبط ما يُفلت من ذلك المكان الواحد. الراتشِت يُبقيها ثلاثةً حتّى تُنقَل.

**القاعدة:** ملفٌّ جديد يستدعي ``fetch(`` مباشرةً يسقط · زيادةٌ في ملفٍّ مُعلَن تسقط ·
نقصانٌ بلا خفضِ الأساس يسقط. تُستثنى ملفّاتُ الاختبار و``services/api.ts`` نفسُه.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[2]
FRONTEND_SRC = "frontend/src"
API_LAYER = "frontend/src/services/api.ts"
# لا حرفَ كلمةٍ قبلها (فيُستثنى `refetch(`/`prefetch(`/`useFetch(`) — لكنّ النقطةَ **مقبولة**:
# `window.fetch(`/`globalThis.fetch(` نداءُ شبكةٍ مباشر مثلُ `fetch(` تماماً (مراجعة Copilot
# على #995 أمسكت أنّ النسخةَ الأولى كانت تستثنيه فتُقنّن التفافاً).
_FETCH = re.compile(r"(?<!\w)fetch\(")

#: الأساسُ المُجمَّد — مقيسٌ على `9613db9a`. **يُخفَّض عند النقل إلى services/api.ts ولا يُرفَع.**
FROZEN_SITES: dict[str, int] = {
    "frontend/src/components/maphub/weather/WeatherProbePopup.ts": 6,
    "frontend/src/components/maphub/weather/WeatherTileLayer.ts": 1,
    "frontend/src/components/maphub/weather/WeatherHoverReadout.ts": 1,
}


def _is_test_path(rel: str) -> bool:
    return ".test." in rel or ".spec." in rel or "/test/" in rel or "/__tests__/" in rel


def count_fetch_sites(root: Path = ROOT) -> dict[str, int]:
    found: dict[str, int] = {}
    base = root / FRONTEND_SRC
    if not base.exists():
        return found
    for path in sorted(list(base.rglob("*.ts")) + list(base.rglob("*.tsx"))):
        rel = path.relative_to(root).as_posix()
        if rel == API_LAYER or _is_test_path(rel) or rel.endswith(".d.ts"):
            continue
        text = path.read_text(encoding="utf-8")
        # نداءً نداءً لا سطراً سطراً: نداءان في سطرٍ واحد اثنان، وإلّا التفّ النموُّ على الراتشِت.
        n = sum(
            len(_FETCH.findall(line))
            for line in text.splitlines()
            if not line.lstrip().startswith("//")
        )
        if n:
            found[rel] = n
    return found


def test_no_new_direct_fetch_outside_the_api_layer():
    live = count_fetch_sites()
    new_files = sorted(set(live) - set(FROZEN_SITES))
    grown = sorted(f for f in live if f in FROZEN_SITES and live[f] > FROZEN_SITES[f])
    assert not new_files, (
        f"FRONTEND-FETCH-OUTSIDE-API-LAYER-01: استدعِ services/api.ts بدل fetch المباشر: {new_files}"
    )
    assert not grown, "FRONTEND-FETCH-OUTSIDE-API-LAYER-01: مواضعُ جديدة — " + ", ".join(
        f"{f}: {live[f]} > {FROZEN_SITES[f]}" for f in grown
    )


def test_the_frozen_baseline_is_lowered_when_a_site_is_migrated():
    live = count_fetch_sites()
    stale = sorted(f for f, cap in FROZEN_SITES.items() if live.get(f, 0) < cap)
    assert not stale, "الأساسُ يصف كوناً زال — خفِّضه: " + ", ".join(
        f"{f}: live={live.get(f, 0)} < frozen={FROZEN_SITES[f]}" for f in stale
    )


def test_the_detector_ignores_refetch_prefetch_comments_tests_and_the_api_layer(tmp_path):
    """تكذيبٌ ذاتيّ — وهو بعينه الخطأُ الذي أنتج الرقمَ ٦٢: `refetch(` ليس `fetch(`.
    و`window.fetch(` **هو** `fetch(` (كان يُستثنى)، ونداءان في سطرٍ اثنان (كانا واحداً)."""
    src = tmp_path / "frontend" / "src"
    (src / "services").mkdir(parents=True)
    (src / "hooks").mkdir()
    (src / "services" / "api.ts").write_text("fetch(u)\n", encoding="utf-8")
    (src / "hooks" / "useX.ts").write_text(
        "q.refetch()\nqueryClient.prefetch(k)\nuseFetch(k)\n// fetch(x)\nwindow.fetch(u)\n",
        encoding="utf-8",
    )
    (src / "hooks" / "useX.test.ts").write_text("fetch(u)\n", encoding="utf-8")
    (src / "hooks" / "raw.ts").write_text(
        "const r = await fetch('/api')\nconst [a, b] = [fetch('/a'), globalThis.fetch('/b')]\n",
        encoding="utf-8",
    )
    assert count_fetch_sites(tmp_path) == {
        "frontend/src/hooks/useX.ts": 1,
        "frontend/src/hooks/raw.ts": 3,
    }
