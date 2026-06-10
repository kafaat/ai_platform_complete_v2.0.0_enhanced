"""خطّ أنابيب الأبحاث الزراعيّة الشامل.

SAHOOL Agronomic Research Pipeline — end-to-end orchestrator.
Chains: decompose → retrieve → extract → synthesize → report.
Deterministic, no network calls, <5 s end-to-end.
"""

from __future__ import annotations

from sahool_ai.research.decomposer import _detect_region, decompose_query
from sahool_ai.research.reporter import (
    generate_json_report,
    generate_map_data,
    generate_markdown_report,
)
from sahool_ai.research.retriever import retrieve_all
from sahool_ai.research.synthesizer import synthesize_findings


def run_pipeline(query: str) -> dict:
    """تشغيل خطّ أنابيب الأبحاث الزراعيّة من البداية إلى النهاية.

    المراحل:
    1. **فكّ الاستعلام** (Decompose): تحليل الاستعلام وتوليد استعلامات فرعيّة.
    2. **الاسترجاع** (Retrieve): جلب البيانات من جميع المصادر (وهميّة).
    3. **الاستخراج** (Extract): استخراج القيم الرقميّة والأنماط والروابط السببيّة.
    4. **التوليف** (Synthesize): توليد ملخّص وعوامل وتوصيات.
    5. **التقرير** (Report): إصدار JSON وMarkdown وبيانات خريطة GeoJSON.

    Args:
        query: الاستعلام الزراعي (عربي أو إنجليزي).

    Returns:
        قاموس يحتوي على:

        - ``json``: تقرير JSON منظَّم.
        - ``markdown``: تقرير Markdown عربي.
        - ``map_data``: GeoJSON FeatureCollection.
        - ``query``: الاستعلام الأصلي.
        - ``subquery_count``: عدد الاستعلامات الفرعيّة.
        - ``sources_retrieved``: قائمة مصادر البيانات المُستردَّة.
    """
    # ── 1. Decompose ───────────────────────────────────────────────────────
    subqueries = decompose_query(query)

    # ── 2. Retrieve ────────────────────────────────────────────────────────
    raw_results = retrieve_all(subqueries)

    # ── 3. Synthesize (internally extracts) ───────────────────────────────
    synthesis = synthesize_findings(raw_results, query)

    # ── 4. Report ──────────────────────────────────────────────────────────
    region = _detect_region(query)
    json_report = generate_json_report(synthesis)
    markdown_report = generate_markdown_report(synthesis)
    map_data = generate_map_data(synthesis, region=region)

    return {
        "json": json_report,
        "markdown": markdown_report,
        "map_data": map_data,
        "query": query,
        "subquery_count": len(subqueries),
        "sources_retrieved": list(raw_results.keys()),
    }
