"""انحدارات اعتماد مُثبَّتة — فحوص ساكنة صرفة.

**العلامة ليست تفصيلاً إداريّاً:** `pytest.ini` يحصر الوظائف بالعلامات، فملفٌّ بلا
`pytestmark` **لا يعمل في أيّ وظيفة CI** — يُكتَب ويُقرأ ويُظنّ حارساً وهو لا يجري.
وهو صنف «قدرة موجودة لا تجري» المسجَّل في هذا المستودع، وقد شُحِن هذا الملفّ بلا علامة
فأمسكه `test_marker_coverage_guard`.
"""

from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]


def test_probe_newservice_is_not_a_production_route():
    text = (ROOT / "services/sahool-platform/api/routers/compat_gateway.py").read_text(
        encoding="utf-8"
    )
    assert "/api/probe-newservice/readyz" not in text
    assert "probe_unadjudicated_alias_" not in text


def test_scout_projection_healthcheck_uses_pid1_not_missing_pgrep():
    compose = yaml.safe_load((ROOT / "docker-compose.v9.yml").read_text(encoding="utf-8"))
    check = compose["services"]["sahool-scout-ingest-projection"]["healthcheck"]["test"]
    joined = " ".join(check)
    assert "kill -0 1" in joined
    assert "pgrep" not in joined


def test_certification_orchestrator_is_versioned_with_probe_contract():
    """**المنسّق نسخةٌ واحدة، والمقيس عليها هي المُصلَحة.**

    أوّل صياغة أكّدت وجود `scripts/ops/sahool_production_runbook_v2_2.py` و
    `config/production_probe_config_v2_2.example.json` — وهما **النسخة الأصليّة
    بعيوبها الخمسة** بجوار المُصلَحة: بلا توسيع متغيّرات البيئة (فيُرسَل الرمز
    حرفيّاً)، وبلا عدّ المتخطّى الحَرِج، وبافتراضيّ `argparse` تراكميّ، وبعناوين
    `127.0.0.1:8000/:8001` لا وجود لها. ومشغّلٌ يمدّ يده إلى أيّهما اتّفق.

    وأخطر ما فيه أنّ `scripts/ops/` **خارج `_SCRIPT_DIRS`**، فلا تراه مكنسة
    `verify_all_generated` ولا أيّ بوّابة — يهبط صامتاً. حُذِفت النسخة المكرّرة،
    والتأكيد هنا انتقل إلى الأداة القانونيّة.
    """
    orchestrator = ROOT / "scripts/release/production_readiness_orchestrator.py"
    probes = ROOT / "runtime-verification/production_readiness_probes.example.json"
    assert orchestrator.is_file()
    assert probes.is_file()
    text = orchestrator.read_text(encoding="utf-8")
    assert "production_certified_candidate" in text
    assert "runtime_sha_bound" in text
    assert '"production_certified": False' in text
    # الإصلاحات الثلاثة التي تفصل هذه النسخة عن الأصل — وجود الملفّ لا يكفي.
    assert "def expand_env" in text
    assert "critical_skipped" in text
    assert "default=None" in text
    # ولا نسخة ثانية: تكرار الأداة هو العطل نفسه بصياغة أخرى.
    assert not (ROOT / "scripts/ops/sahool_production_runbook_v2_2.py").exists()
