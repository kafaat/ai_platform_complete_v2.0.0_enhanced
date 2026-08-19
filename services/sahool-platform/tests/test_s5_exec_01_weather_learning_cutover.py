from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def test_weather_decision_cutover_has_service_only_authoritative_branch():
    p = ROOT / "services/sahool-platform/api/routers/weather.py"
    t = p.read_text()
    s = t.index("async def _persist_weather_decision_record")
    e = t.index("def _recommendation_payload_from_plan", s)
    b = t[s:e]
    cs = b.index("if mode.strict_decision_service_required:")
    ce = b.index("    assert_platform_may_write_decision_sor", cs)
    cut = b[cs:ce]
    assert "conn.execute" not in cut
    assert "_emit_domain_event" not in cut
    assert "await _mirror_decision_to_service" in cut
    assert "authoritative" in cut and "persisted" in cut


# ── قطعُ `online_learning_updates` مؤجَّلٌ بقرار حوكمة، لا منسيّ ────────────────
# كانت هنا حالةٌ تفرض النظير في `api/phase_runtime_store.py`. وذلك الملفّ **مسارٌ
# مجمَّد** في `docs/architecture/gate01_policy.json` وGATE-01 حالتها `CLOSED`:
# «عملُ المرحلة ١ على الأثر الفيزيائيّ محظورٌ عالميّاً، إلّا بتفويضٍ محكَّمٍ مقيَّدٍ
# يُستهلَك مرّةً واحدة». والتفويض القائم `GATE01-ADJ-2026-08-13-001` حالته
# `CONSUMED` — و«المُستهلَك والملغى لا يُعاد استعمالهما» بنصّ الحارس.
#
# فالتعديل رُدَّ إلى نصّ `main`، ولم يُصدَر تفويضٌ ذاتيّاً: إصدارُ الإذن الذي تشترطه
# البوّابة، بيد الجهة المحجوبة بها، يُبطِل البوّابة نفسها. ويبقى القطع صحيحاً
# مطلوباً — لكنّه شريحةٌ مستقلّة بتفويضٍ مُصدَرٍ من مالك القرار (`owner_ruling_on`
# ومصدرها `sahool-brain/gaps/registry.md`)، لا حمولةً صامتة في PR أوسع.
#
# وحالةُ `weather.py` أعلاه تبقى: مسارُها **غير** مجمَّد (مقيس على القائمة العشر).
