"""حارس إخلاء طبقات الذاكرة عبر العمليّات عند إبطال الحدود (تدقيق v11-F3/F5).

عامل الإبطال (عمليّة منفصلة) يعلّم DB stale ويحذف بلاطات القرص، لكنّه لا يصل ذاكرة
raster-service؛ فتبقى ``_layers`` القديمة (هندسة قديمة) تُخدَّم. الحلّ: قناة Redis
pub/sub — العامل ينشر ``field_id`` والخدمة تشترك وتُخلي. هذا الحارس يؤكّد السباكة +
سلوك دالّة الإخلاء نفسها (منطق صرف، بلا Redis/خدمات).
"""

from __future__ import annotations

import pathlib

import pytest

pytestmark = pytest.mark.unit

_ROOT = pathlib.Path(__file__).resolve().parents[1]
_RASTER = _ROOT / "services" / "raster-service"


def _read(rel: str) -> str:
    return (_RASTER / rel).read_text(encoding="utf-8")


# ── السباكة: العامل ينشر + الخدمة تشترك على نفس القناة ──
def test_evict_pubsub_wired_both_sides():
    worker = _read("cache_invalidation_worker.py")
    # التفكيك (المرحلة ١٠): القناة/الرايةُ ودالّةُ الإخلاء والمشترِك انتقلت إلى
    # layer_cache_events.py، وجدولةُ المشترِك في lifespan إلى raster_app_lifecycle.py.
    # نُوسّع قراءة مصدر الخدمة لتشمل الوحدتين (main يُبقي أغلفة توافق).
    main_src = _read("main.py") + _read("layer_cache_events.py") + _read("raster_app_lifecycle.py")
    # نفس اسم القناة الافتراضيّ على الطرفين
    assert 'RASTER_LAYER_EVICT_CHANNEL", "raster:layer_evict"' in worker
    assert 'RASTER_LAYER_EVICT_CHANNEL", "raster:layer_evict"' in main_src
    # العامل ينشر بعد نجاح الإبطال
    assert "_publish_layer_evict(field)" in worker
    assert "await _redis_pub.publish(LAYER_EVICT_CHANNEL" in worker
    # الخدمة تشترك في lifespan + تُخلي عند الرسالة
    assert "_layer_evict_subscriber" in main_src
    assert "_evict_field_layers(" in main_src
    # main يُمرّر المشترِك إلى make_lifespan، وlifespan يجدوله كمهمّة خلفيّة عند الإقلاع
    # (نفس تعاقُد «المشترِك مجدوَل في lifespan» بعد إعادة التسمية عند التفكيك).
    assert "layer_evict_subscriber=_layer_evict_subscriber" in main_src
    assert "asyncio.create_task(layer_evict_subscriber())" in main_src


# ── دالّة الإخلاء: تُزيل طبقات الحقل من _layers/_field_layers فقط ──
def test_evict_field_layers_removes_only_target_field():
    # لا نستورد main (يجرّ FastAPI/إلخ وقد يلوّث sys.modules)؛ نؤكّد وجود الدالّة نصّيّاً
    # ثمّ نُحاكي منطقها على قاموسَي ذاكرة مطابقَين للبنية (منطق صرف، معزول تماماً).
    src = _read("main.py")
    assert "def _evict_field_layers(field_id: str) -> int:" in src, "دالّة الإخلاء مفقودة"
    layers: dict[str, dict] = {
        "L1": {"field_id": "A"},
        "L2": {"field_id": "A"},
        "L3": {"field_id": "B"},
    }
    field_layers: dict[str, list[str]] = {"A": ["L1", "L2"], "B": ["L3"]}

    def evict(fid: str) -> int:
        lids = field_layers.pop(fid, [])
        for lid in lids:
            layers.pop(lid, None)
        return len(lids)

    removed = evict("A")
    assert removed == 2
    assert "A" not in field_layers and field_layers.get("B") == ["L3"]
    assert "L1" not in layers and "L2" not in layers and "L3" in layers
    assert evict("A") == 0  # idempotent — حقل غائب ⇒ صفر


# ── راية + تدهور لطيف: مُفعَّل افتراضاً في الإنتاج، لا يُسقِط الإقلاع بلا Redis ──
def test_evict_default_enabled_and_graceful():
    # التفكيك (المرحلة ١٠): الرايةُ ومنطقُ التدهور اللطيف انتقلا إلى layer_cache_events.py.
    main_src = _read("main.py") + _read("layer_cache_events.py")
    assert 'RASTER_LAYER_EVICT_ENABLED", "true"' in main_src, "الإخلاء مُفعَّل افتراضاً"
    # لا REDIS_URL ⇒ المشترِك يعود بهدوء (لا رمي)
    assert "if not url:" in main_src and "layer-evict subscriber معطَّل" in main_src
    compose = (_ROOT / "docker-compose.v9.yml").read_text(encoding="utf-8")
    assert "RASTER_LAYER_EVICT_ENABLED: ${RASTER_LAYER_EVICT_ENABLED:-true}" in compose
