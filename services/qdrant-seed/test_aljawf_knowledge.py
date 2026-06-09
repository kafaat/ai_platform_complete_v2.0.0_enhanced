"""Tests for aljawf_knowledge.py - lives OUTSIDE core/tests.
Ensures data integrity for Qdrant seeding without polluting core neutrality."""
import sys
from pathlib import Path

# قبل الاختبار: تأكّد أنّ المسار صحيح
sys.path.insert(0, str(Path(__file__).parent))

from aljawf_knowledge import ALJAWF_KNOWLEDGE, validate_entries


class TestDataIntegrity:
    """التحقّق الأساسي من سلامة البيانات."""

    def test_has_expected_count(self):
        # 54 قاعدة (IDs 100-153؛ +SAL-SOIL-05/06 لسدّ فجوة EC 2-4 و6-8)
        assert len(ALJAWF_KNOWLEDGE) == 54

    def test_all_ids_unique(self):
        ids = [e["id"] for e in ALJAWF_KNOWLEDGE]
        assert len(ids) == len(set(ids)), "IDs مكرّرة"

    def test_id_range(self):
        ids = [e["id"] for e in ALJAWF_KNOWLEDGE]
        assert min(ids) == 100
        assert max(ids) == 153

    def test_required_fields_present(self):
        required = {"id", "text", "topic", "source"}
        for e in ALJAWF_KNOWLEDGE:
            missing = required - set(e.keys())
            assert not missing, f"entry {e.get('id')}: حقول ناقصة {missing}"

    def test_no_empty_texts(self):
        for e in ALJAWF_KNOWLEDGE:
            assert len(e["text"].strip()) >= 20, \
                f"entry {e['id']}: نصّ قصير جدّاً"


class TestSampleNamingCorrection:
    """CRITICAL: التحقّق من تصحيح S1 → SA1..SA13."""

    def test_sa_naming_in_sunaydar_entries(self):
        # العيّنات يجب أن تُسمّى SA1..SA13، لا S1..S13
        sunaydar_entries = [
            e for e in ALJAWF_KNOWLEDGE
            if "السنيدار" in e["text"] or "السنيدار" in e["source"]
        ]
        assert len(sunaydar_entries) >= 5

        for e in sunaydar_entries:
            text_lower = (e["text"] + " " + e["source"]).lower()
            # لو ذكر "S1.."، يجب أن يكون "SA1.." أو يشرح أنّه تصنيف Sodium
            if "SA1" in e["text"] + e["source"]:
                # ✓ الصياغة الجديدة الصحيحة
                pass
            elif " S1 " in e["text"] or "(S1)" in e["text"]:
                # يجب أن يحوي توضيح أنّ S1 هنا تصنيف SAR
                assert "SAR" in e["text"] or "Sodium Hazard" in e["text"], (
                    f"entry {e['id']}: ذكر S1 بدون توضيح أنّه تصنيف SAR"
                )

    def test_sa_range_documented(self):
        # على الأقلّ بعض الـentries تذكر SA1..SA13
        sa_mentions = [
            e for e in ALJAWF_KNOWLEDGE
            if "SA1..SA13" in e["text"] or "SA1..SA13" in e["source"]
        ]
        assert len(sa_mentions) >= 3, \
            f"يجب توثيق SA1..SA13 في ≥3 entries، وُجد {len(sa_mentions)}"

    def test_water_sample_distinguishes_sa_from_sodium_class(self):
        # entry 110 (مياه آبار) يجب أن يميّز بين أسماء العيّنات و
        # تصنيف Sodium Hazard
        water_entry = next((e for e in ALJAWF_KNOWLEDGE
                           if e["id"] == 110), None)
        assert water_entry is not None
        text = water_entry["text"]
        # يجب ذكر كلاهما مع التمييز
        assert "S1" in text, "تصنيف SAR S1 يجب أن يبقى للمياه"
        assert ("SA1..SA13" in text or
                "أسماء العيّنات" in text or
                "USDA" in text or
                "تصنيف" in text), (
            "يجب توضيح التمييز بين S1 (SAR) و SA1..SA13 (أسماء)"
        )


class TestTopicCoverage:
    """تغطية المواضيع المهمّة."""

    def test_has_geography(self):
        topics = {e["topic"] for e in ALJAWF_KNOWLEDGE}
        assert "geography" in topics

    def test_has_decision_rules(self):
        rules = [e for e in ALJAWF_KNOWLEDGE
                if e["topic"] == "decision_rule"]
        # على الأقلّ 30 قاعدة قرار (115-151)
        assert len(rules) >= 30

    def test_decision_rules_have_code(self):
        # كل قاعدة قرار يجب أن تحوي رمزاً [XXX-NN] أو [XXX-YY-NN]
        import re
        rules = [e for e in ALJAWF_KNOWLEDGE
                if e["topic"] == "decision_rule"]
        pattern = re.compile(r"\[[A-Z]+(-[A-Z]+)?-\d+\]")
        for r in rules:
            assert pattern.search(r["text"]), (
                f"قاعدة قرار {r['id']} بلا رمز [XXX-NN] أو [XXX-YY-NN]"
            )

    def test_quality_standards_referenced(self):
        # YSMO 72/2006 و 156/2001 يجب أن تظهر
        all_sources = " ".join(e["source"] for e in ALJAWF_KNOWLEDGE)
        assert "72/2006" in all_sources or "YSMO 72" in all_sources
        assert "156/2001" in all_sources or "YSMO 156" in all_sources


class TestValidationHelper:
    """validate_entries() نفسها تعمل بدقّة."""

    def test_validate_passes_for_clean_data(self):
        result = validate_entries(ALJAWF_KNOWLEDGE)
        assert result["valid"], (
            f"البيانات الأساسية يجب أن تكون صالحة، "
            f"وُجد: {result['errors'][:3]}"
        )

    def test_validate_detects_duplicate_ids(self):
        # CRITICAL: لا اختراع - الـvalidator يكشف فعلاً
        bad = [
            {"id": 1, "text": "a"*30, "topic": "x", "source": "s"},
            {"id": 1, "text": "b"*30, "topic": "y", "source": "s"},
        ]
        result = validate_entries(bad)
        assert not result["valid"]
        assert any("مكرّر" in e for e in result["errors"])

    def test_validate_detects_missing_fields(self):
        bad = [{"id": 1, "text": "x" * 30}]   # ينقص topic + source
        result = validate_entries(bad)
        assert not result["valid"]

    def test_validate_detects_short_text(self):
        bad = [{"id": 1, "text": "قصير", "topic": "x", "source": "s"}]
        result = validate_entries(bad)
        assert not result["valid"]


class TestNoCoreLeakage:
    """تأكيد: aljawf_knowledge يعيش خارج النواة كلياً."""

    def test_lives_outside_core(self):
        # الملفّ في services/qdrant-seed/، ليس في sahool-platform/core/
        file_path = Path(__file__).parent / "aljawf_knowledge.py"
        assert file_path.exists()
        assert "core" not in str(file_path).split("/sahool-platform/")[-1]\
            .split("/")[0] if "/sahool-platform/" in str(file_path) else True

    def test_no_core_imports(self):
        # CRITICAL: aljawf_knowledge.py لا يستورد من core/
        content = (Path(__file__).parent / "aljawf_knowledge.py").read_text(
            encoding="utf-8")
        forbidden = [
            "from core",
            "import core",
            "from sahool_core",
            "from services.sahool-platform",
        ]
        for bad in forbidden:
            assert bad not in content, (
                f"aljawf_knowledge يستورد من النواة: '{bad}'"
            )


if __name__ == "__main__":
    # تشغيل يدوي بدون pytest
    classes = [TestDataIntegrity, TestSampleNamingCorrection,
              TestTopicCoverage, TestValidationHelper, TestNoCoreLeakage]
    passed = failed = 0
    failures = []
    for cls in classes:
        inst = cls()
        for name in dir(inst):
            if name.startswith("test_"):
                try:
                    getattr(inst, name)()
                    passed += 1
                except AssertionError as e:
                    failed += 1
                    failures.append(f"{cls.__name__}.{name}: {e}")
    print(f"{'🎉' if failed == 0 else '⚠️'} {passed} passed, {failed} failed")
    for f in failures[:5]:
        print(f"  • {f}")
