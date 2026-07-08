from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
ROUTER = ROOT / "services" / "sahool-platform" / "api" / "routers" / "field_ai_context.py"
CHAT = ROOT / "frontend" / "src" / "sections" / "ChatbotPage.tsx"


def test_field_ai_context_router_contract():
    src = ROUTER.read_text(encoding="utf-8")
    assert "/api/v1/fields/{field_id}/ai-context-pack" in src
    assert "FieldAiContextPack" in src
    assert "imagery_timeline" in src
    assert "weather_history" in src
    assert "drawing_context" in src
    assert "operations_timeline" in src
    assert "require_permission(Permission.FIELD_VIEW)" in src


def test_two_year_context_sources_are_explicit():
    src = ROUTER.read_text(encoding="utf-8")
    assert "days: int = Query(730" in src
    assert "fetch_historical" in src
    # P2.2 raster facade cleanup: the available-dates read moved from an open-coded
    # endpoint literal into the raster_service_client facade. The source stays explicit
    # (the router still fetches available dates), it just goes through the boundary client.
    assert "get_available_dates" in src
    assert "truecolor" in src
    assert "ndvi" in src
    assert "ndmi" in src


def test_chatbot_injects_ai_context_pack():
    src = CHAT.read_text(encoding="utf-8")
    assert "ai-context-pack" in src
    assert "FieldAiContextPack" in src
    assert "ai_context_pack: aiContext" in src
    assert "ai_context_summary_ar" in src
    assert "سياق الحقل للذكاء" in src
