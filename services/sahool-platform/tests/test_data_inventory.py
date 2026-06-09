"""tests/test_data_inventory.py — اختبارات قارئ سجلّ المصادر."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.data_inventory import (
    _reset_cache,
    active_sources_for_theme,
    find_source,
    gaps_report,
    load_inventory,
    planned_sources_with_triggers,
    sources_by_criticality,
    sources_for_theme,
)


class TestDataInventory:
    def setup_method(self):
        _reset_cache()

    def test_yaml_loads_successfully(self):
        """data_inventory.yaml يقرأ بنجاح."""
        themes = load_inventory()
        assert len(themes) >= 10, f"عدد المواضيع قليل: {len(themes)}"
        assert "vegetation" in themes
        assert "soil" in themes
        assert "weather" in themes

    def test_themes_have_arabic_names(self):
        """كل theme له اسم عربي."""
        themes = load_inventory()
        for theme_id, theme in themes.items():
            assert theme.name_ar, f"{theme_id} بلا name_ar"

    def test_sources_have_required_fields(self):
        """كل source له id, status, criticality."""
        themes = load_inventory()
        for theme in themes.values():
            for source in theme.sources:
                assert source.source_id
                assert source.status in ("active", "planned", "rejected")
                assert source.criticality in ("A", "B", "C")

    def test_vegetation_has_sentinel2(self):
        """theme vegetation يحوي sentinel2."""
        sources = sources_for_theme("vegetation")
        sentinel = [s for s in sources if "sentinel2" in s.source_id]
        assert len(sentinel) >= 1

    def test_active_sources_only(self):
        """active_sources_for_theme لا يُرجع planned."""
        active = active_sources_for_theme("vegetation")
        for s in active:
            assert s.status == "active"

    def test_criticality_filter(self):
        """sources_by_criticality يفرز صحيحاً."""
        critical_a = sources_by_criticality("A")
        for s in critical_a:
            assert s.criticality == "A"
        # يجب أن يوجد عدد معقول من A
        assert len(critical_a) >= 5

    def test_planned_sources_have_triggers(self):
        """المصادر المُؤجَّلة المُسجَّلة بـtriggers."""
        planned = planned_sources_with_triggers()
        for s in planned:
            assert s.status == "planned"
            assert s.trigger, f"{s.source_id} planned بلا trigger"

    def test_find_source_by_id(self):
        """find_source يستعيد مصدر."""
        s = find_source("sentinel2_optical")
        assert s is not None
        assert s.theme_id == "vegetation"

    def test_find_nonexistent_returns_none(self):
        """مصدر غير موجود → None."""
        s = find_source("nonexistent_xyz")
        assert s is None

    def test_invalid_criticality_raises(self):
        """criticality غير صالحة → ValueError."""
        try:
            sources_by_criticality("X")
            raise AssertionError
        except ValueError:
            pass

    def test_unknown_theme_raises(self):
        """theme غير مُسجَّل → KeyError."""
        try:
            sources_for_theme("unknown_theme_xyz")
            raise AssertionError
        except KeyError:
            pass

    def test_status_distribution(self):
        """التوزيع المُعلَن يطابق الواقع."""
        themes = load_inventory()
        all_sources = [s for t in themes.values() for s in t.sources]
        active = [s for s in all_sources if s.status == "active"]
        planned = [s for s in all_sources if s.status == "planned"]
        # يجب أن يكون بضعة active على الأقلّ
        assert len(active) >= 10
        # وعدّة planned
        assert len(planned) >= 3

    def test_critical_sources_in_governance(self):
        """theme governance يحوي مصادر criticality A."""
        sources = sources_for_theme("governance")
        critical = [s for s in sources if s.criticality == "A"]
        assert len(critical) >= 2  # RBAC + guardrails
