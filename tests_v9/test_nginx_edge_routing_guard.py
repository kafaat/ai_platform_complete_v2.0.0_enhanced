"""حارس توجيه استدلال الحافة (edge-inference) في nginx (وحدة).

السياق: تطبيق الموبايل يستدعي `/api/edge/inference/pest-detect` بـJWT المستخدم. نقطة
edge محميّة بتوكن خدمة (`X-Agent-Token`) لا بـJWT، و`proxy_params.conf` يمسح ذلك الرأس.
لذا المسار الصحيح في البوّابة القانونيّة (معماريّة المنصّة، المُقولَبة عبر envsubst) هو:
تحقّق JWT عبر `auth_request /_auth_verify` ثمّ حقن `X-Agent-Token` من سرّ خادميّ.

الحارس يمنع:
  • أيّ `upstream edge_backend` يشير لمنفذ خاطئ (الخدمة تستمع 8100 لا 8000).
  • أيّ بوّابة معماريّة-منصّة تكشف `/api/edge/` بلا تحقّق JWT أو بلا حقن توكن الخدمة
    (تمرير مكشوف ⇒ 401 أو تسريب). (nginx.fixed.conf بوّابة تطوير غير مُقولَبة بلا
    auth_request — لا تُعرّف edge_backend فتُستثنى.)
"""

import re
from pathlib import Path

import pytest

NGINX_DIR = Path(__file__).resolve().parents[1] / "nginx"


def _conf_files() -> list[Path]:
    return sorted(NGINX_DIR.glob("*.conf"))


def _is_platform_arch(text: str) -> bool:
    return "upstream platform_backend" in text and "sahool-platform" in text


def _edge_location_block(text: str) -> str | None:
    m = re.search(r"location\s+/api/edge/\s*\{(.*?)\n\s*\}", text, re.DOTALL)
    return m.group(1) if m else None


_CONFS_WITH_EDGE_UPSTREAM = [
    p for p in _conf_files() if "upstream edge_backend" in p.read_text(encoding="utf-8")
]


@pytest.mark.unit
@pytest.mark.parametrize("conf", _CONFS_WITH_EDGE_UPSTREAM, ids=lambda p: p.name)
def test_edge_upstream_uses_correct_port(conf: Path):
    """edge-inference يستمع 8100 (uvicorn) — كلّ upstream edge_backend يجب أن يستهدفه."""
    text = conf.read_text(encoding="utf-8")
    m = re.search(r"upstream\s+edge_backend\s*\{[^}]*server\s+([^;\s]+)", text)
    assert m, f"{conf.name}: تعذّر تحليل upstream edge_backend"
    target = m.group(1)
    assert target.endswith(":8100"), (
        f"{conf.name}: edge_backend يجب أن يكون sahool-edge:8100 (لا :8000) — {target}"
    )


@pytest.mark.unit
def test_v9_exposes_edge_via_platform_proxy():
    """البوّابة القانونيّة (v9) توجّه /api/edge/ إلى المنصّة (service_proxy) لا إلى edge مباشرةً.

    المعماريّة المعتمَدة: المنصّة (sahool-platform) تتحقّق من JWT ثمّ تحقن X-Agent-Token
    خادميّاً قبل تمريره إلى edge — فالبوّابة تمرّر فقط، ولا تحقن السرّ ولا تذهب للجذع.
    """
    v9 = NGINX_DIR / "nginx.v9.conf"
    text = v9.read_text(encoding="utf-8")
    assert _is_platform_arch(text)
    block = _edge_location_block(text)
    assert block is not None, "nginx.v9.conf: مسار /api/edge/ مفقود (pest-detect لا يصل)"
    assert "platform_backend" in block, (
        "nginx.v9.conf: /api/edge/ يجب أن يُمرَّر إلى platform_backend (service_proxy يحقن التوكن)"
    )
    # لا يُمرَّر مباشرةً إلى upstream edge (الحقن صار في المنصّة لا البوّابة).
    assert "edge_backend" not in block, (
        "nginx.v9.conf: /api/edge/ لم يعد يذهب مباشرةً إلى edge_backend — يمرّ عبر المنصّة."
    )
