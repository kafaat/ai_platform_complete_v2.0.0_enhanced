"""حارس توجيه صحّة الوكيل في nginx (وحدة).

الواجهة تطلب `/api/agent/health`، لكنّ خدمة المشرف (supervisor-agent) تعرض `/health`
(و`/healthz`/`/readyz`) لا `/agent/health`. وبادئة `location /api/agent/` تمرّر إلى
`/agent/...` ⇒ `/api/agent/health` → `/agent/health` → 404. الإصلاح: تطابق دقيق
`location = /api/agent/health` يوجّه إلى `supervisor_backend/health`.

الحارس يفرض هذا التطابق الدقيق في كلّ بوّابة تعرّف `supervisor_backend` وتمرّر
`/api/agent/` (يمنع انحدار 404 على فحص صحّة الوكيل).
"""

import re
from pathlib import Path

import pytest

NGINX_DIR = Path(__file__).resolve().parents[1] / "nginx"


def _conf_files() -> list[Path]:
    return sorted(NGINX_DIR.glob("*.conf"))


_CONFS_WITH_AGENT = [
    p
    for p in _conf_files()
    if "supervisor_backend" in p.read_text(encoding="utf-8")
    and "/api/agent/" in p.read_text(encoding="utf-8")
]


@pytest.mark.unit
@pytest.mark.parametrize("conf", _CONFS_WITH_AGENT, ids=lambda p: p.name)
def test_agent_health_exact_match_to_supervisor_health(conf: Path):
    """/api/agent/health يجب أن يُطابَق بدقّة ويُوجَّه إلى supervisor_backend/health."""
    text = conf.read_text(encoding="utf-8")
    # تطابق دقيق صريح يفوز: يجب أن يوجّه إلى .../health.
    exact = re.search(
        r"location\s*=\s*/api/agent/health\s*\{[^}]*?proxy_pass\s+([^;\s]+)", text, re.DOTALL
    )
    if exact:
        target = exact.group(1).rstrip("/")
        assert target.endswith("/health") and "supervisor_backend" in target, (
            f"{conf.name}: التطابق الدقيق يجب أن يوجّه /api/agent/health إلى "
            f"supervisor_backend/health — {target}"
        )
        return
    # لا تطابق دقيق: بادئة /api/agent/ يجب ألّا تُجرّد إلى /agent/ (وإلّا health ⇒ 404).
    pm = re.search(r"location\s+/api/agent/\s*\{.*?proxy_pass\s+([^;\s]+);", text, re.DOTALL)
    assert pm, f"{conf.name}: لا بادئة /api/agent/ ولا تطابق صحّة دقيق."
    base = pm.group(1).rstrip("/")
    assert not base.endswith("/agent"), (
        f"{conf.name}: /api/agent/ يُجرّد إلى /agent/ ⇒ /api/agent/health=404؛ يلزم "
        f"`location = /api/agent/health → supervisor_backend/health` (كـv9/fixed). الهدف: {base}/"
    )
