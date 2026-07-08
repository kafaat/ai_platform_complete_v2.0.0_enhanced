"""حُرّاس تقوية سلامة الموسم — منطق نقيّ (date-order + custom_stages)."""

from __future__ import annotations

from datetime import date

from api.season_integrity import (
    parse_iso_date,
    resolve_and_check_date_order,
    validate_custom_stages,
)


class TestParseIsoDate:
    def test_valid_iso(self):
        assert parse_iso_date("2026-03-15") == date(2026, 3, 15)

    def test_rejects_bad_format_and_type(self):
        for bad in ("15/03/2026", "2026-3-5", "2026-13-01", "not-a-date", "", "2026-02-30"):
            assert parse_iso_date(bad) is None
        assert parse_iso_date(None) is None  # type: ignore[arg-type]


class TestResolveDateOrder:
    def test_end_only_update_caught_against_stored_sowing(self):
        # جوهر الثغرة #1: تُرسَل النهاية وحدها فتقع قبل البذار المخزّن.
        err = resolve_and_check_date_order(
            current_sowing=date(2026, 5, 1),
            current_end=date(2026, 9, 1),
            new_end=date(2026, 3, 1),  # قبل البذار المخزّن
        )
        assert err is not None

    def test_sowing_only_update_caught_against_stored_end(self):
        err = resolve_and_check_date_order(
            current_sowing=date(2026, 1, 1),
            current_end=date(2026, 4, 1),
            new_sowing=date(2026, 6, 1),  # بعد النهاية المخزّنة
        )
        assert err is not None

    def test_valid_partial_update_passes(self):
        assert (
            resolve_and_check_date_order(
                current_sowing=date(2026, 5, 1),
                current_end=date(2026, 9, 1),
                new_end=date(2026, 10, 1),
            )
            is None
        )

    def test_unset_keeps_stored_values(self):
        # لا تعديل على التواريخ ⇒ يُفحَص المخزّن فقط (سليم هنا).
        assert (
            resolve_and_check_date_order(
                current_sowing=date(2026, 5, 1), current_end=date(2026, 9, 1)
            )
            is None
        )

    def test_none_stored_dates_are_safe(self):
        # موسم بلا تواريخ مخزّنة ⇒ لا قيد (لا شيء لمقارنته).
        assert resolve_and_check_date_order(current_sowing=None, current_end=None) is None
        assert (
            resolve_and_check_date_order(
                current_sowing=None, current_end=None, new_end=date(2026, 3, 1)
            )
            is None
        )

    def test_both_updated_together_still_checked(self):
        err = resolve_and_check_date_order(
            current_sowing=None,
            current_end=None,
            new_sowing=date(2026, 9, 1),
            new_end=date(2026, 5, 1),
        )
        assert err is not None


class TestValidateCustomStages:
    def test_empty_stages_dropped_silently(self):
        cleaned, errors = validate_custom_stages(
            [{"name": "", "date": "", "notes": ""}, {"name": " ", "date": "", "notes": ""}]
        )
        assert cleaned == [] and errors == []

    def test_valid_ordered_stages_within_window(self):
        cleaned, errors = validate_custom_stages(
            [
                {"name": "إنبات", "date": "2026-05-05", "notes": ""},
                {"name": "تزهير", "date": "2026-07-01", "notes": "ذروة"},
            ],
            sowing_date=date(2026, 5, 1),
            season_end=date(2026, 9, 1),
        )
        assert errors == []
        assert [s["name"] for s in cleaned] == ["إنبات", "تزهير"]

    def test_bad_date_format_flagged(self):
        _, errors = validate_custom_stages([{"name": "إنبات", "date": "05-05-2026", "notes": ""}])
        assert any("غير صالح" in e for e in errors)

    def test_stage_before_sowing_flagged(self):
        _, errors = validate_custom_stages(
            [{"name": "إنبات", "date": "2026-04-01", "notes": ""}],
            sowing_date=date(2026, 5, 1),
        )
        assert any("قبل تاريخ البذار" in e for e in errors)

    def test_stage_after_season_end_flagged(self):
        _, errors = validate_custom_stages(
            [{"name": "حصاد", "date": "2026-10-01", "notes": ""}],
            season_end=date(2026, 9, 1),
        )
        assert any("بعد نهاية الموسم" in e for e in errors)

    def test_backwards_order_flagged(self):
        _, errors = validate_custom_stages(
            [
                {"name": "تزهير", "date": "2026-07-01", "notes": ""},
                {"name": "إنبات", "date": "2026-05-05", "notes": ""},  # متراجع
            ]
        )
        assert any("متراجع" in e for e in errors)

    def test_duplicate_names_flagged_case_insensitive(self):
        _, errors = validate_custom_stages(
            [
                {"name": "Flowering", "date": "", "notes": ""},
                {"name": "flowering", "date": "", "notes": ""},
            ]
        )
        assert any("مكرّر" in e for e in errors)

    def test_accepts_pydantic_like_objects(self):
        class _S:
            def __init__(self, name, d, notes):
                self.name, self.date, self.notes = name, d, notes

        cleaned, errors = validate_custom_stages([_S("إنبات", "2026-05-05", "")])
        assert errors == [] and cleaned[0]["name"] == "إنبات"

    def test_name_only_stage_kept_no_date_checks(self):
        cleaned, errors = validate_custom_stages(
            [{"name": "مرحلة بلا تاريخ", "date": "", "notes": ""}],
            sowing_date=date(2026, 5, 1),
            season_end=date(2026, 9, 1),
        )
        assert errors == [] and len(cleaned) == 1
