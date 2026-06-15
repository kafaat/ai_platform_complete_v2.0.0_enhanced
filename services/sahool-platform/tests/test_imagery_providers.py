"""tests/test_imagery_providers.py — اختبارات سجلّ مزوّدي الصور.

تتحقّق من: السجلّ غير فارغ، المعرّفات فريدة، الحالات ضمن المجموعة المسموحة،
active_providers() يُرجِع النشِط فقط (Sentinel-2)، get_provider يعمل ويُرجِع None
للمجهول، وكلّ مزوّد نشِط له نطاقات.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.imagery_providers import (
    _ALLOWED_KINDS,
    _ALLOWED_STATUSES,
    ImageryProvider,
    active_providers,
    for_kind,
    get_provider,
    list_providers,
)


class TestImageryProviders:
    def test_registry_non_empty(self):
        """السجلّ غير فارغ."""
        assert len(list_providers()) > 0

    def test_ids_unique(self):
        """المعرّفات فريدة."""
        ids = [p.id for p in list_providers()]
        assert len(ids) == len(set(ids)), f"معرّفات مكرّرة: {ids}"

    def test_statuses_in_allowed_set(self):
        """كلّ حالة ضمن المجموعة المسموحة."""
        for p in list_providers():
            assert p.status in _ALLOWED_STATUSES, f"{p.id}: حالة غير مسموحة {p.status}"

    def test_kinds_in_allowed_set(self):
        """كلّ نوع منصّة ضمن المجموعة المسموحة."""
        for p in list_providers():
            assert p.kind in _ALLOWED_KINDS, f"{p.id}: نوع غير مسموح {p.kind}"

    def test_active_providers_are_exactly_sentinel2(self):
        """النشِط فعليّاً = Sentinel-2 فقط (المزوّد الوحيد الموصول اليوم)."""
        active_ids = sorted(p.id for p in active_providers())
        assert active_ids == ["sentinel2"], f"النشِط المتوقَّع sentinel2 فقط، وجدنا: {active_ids}"
        for p in active_providers():
            assert p.status == "active"

    def test_get_provider_known(self):
        """get_provider يُرجِع المزوّد المعروف بمعرّفه."""
        p = get_provider("sentinel2")
        assert p is not None
        assert isinstance(p, ImageryProvider)
        assert p.id == "sentinel2"
        assert p.status == "active"

    def test_get_provider_unknown_returns_none(self):
        """get_provider يُرجِع None لمعرّف مجهول (لا استثناء)."""
        assert get_provider("no-such-provider") is None

    def test_every_active_provider_has_bands(self):
        """كلّ مزوّد نشِط له نطاقات (لا معالجة دون نطاقات)."""
        for p in active_providers():
            assert len(p.bands) > 0, f"{p.id}: مزوّد نشِط بلا نطاقات"

    def test_sentinel2_grounded_facts(self):
        """أرقام Sentinel-2 مؤصَّلة: نطاقات NDVI، 10م، ~5 أيّام، قمر صناعيّ."""
        p = get_provider("sentinel2")
        assert p is not None
        assert p.kind == "satellite"
        assert p.resolution_m == 10.0
        assert p.revisit_days == 5
        assert "B08" in p.bands and "B04" in p.bands  # NIR + أحمر لـNDVI

    def test_planned_providers_present_and_not_active(self):
        """نقاط التوسّع المخطّطة موجودة وليست نشِطة (لا تلفيق ربط)."""
        for pid in ("landsat8", "planet", "drone"):
            p = get_provider(pid)
            assert p is not None, f"{pid} مفقود من السجلّ"
            assert p.status == "planned", f"{pid} يجب أن يكون مخطّطاً لا {p.status}"

    def test_for_kind_filters(self):
        """for_kind يرشّح حسب نوع المنصّة."""
        sats = for_kind("satellite")
        assert all(p.kind == "satellite" for p in sats)
        assert any(p.id == "sentinel2" for p in sats)
        drones = for_kind("drone")
        assert all(p.kind == "drone" for p in drones)

    def test_provider_is_frozen(self):
        """ImageryProvider غير قابل للتعديل (frozen dataclass)."""
        import dataclasses

        p = get_provider("sentinel2")
        assert p is not None
        try:
            p.status = "planned"  # type: ignore[misc]
            raise AssertionError("كان يجب أن يُرفض التعديل (frozen)")
        except dataclasses.FrozenInstanceError:
            pass
