"""Tests for source_of_truth arbitration.
The 'sources of truth conflict' problem from Digital Agriculture OS document."""
from datetime import datetime, timedelta
from core.source_of_truth import (
    Observation, arbitrate, arbitrate_summary,
    ConflictSeverity, set_source_priority, get_source_priority,
    reset_priorities_to_default)
from core.canonical_schemas import ObservationSource


def _obs(value, source, confidence="medium", days_ago=1, observable_id="ndvi"):
    measured = (datetime.now() - timedelta(days=days_ago)).isoformat()
    return Observation(value=value, source=source, confidence=confidence,
                      measured_at=measured, observable_id=observable_id)


class TestSinglePath:
    """مصدر واحد = لا arbitration، فقط شفّافية."""

    def test_single_observation_passes_through(self):
        result = arbitrate([_obs(0.55, ObservationSource.SENSOR)])
        assert result.canonical_value == 0.55
        assert result.canonical_source == ObservationSource.SENSOR
        assert result.severity == ConflictSeverity.NONE

    def test_empty_list_returns_none(self):
        # CRITICAL: صفر اختراع - قائمة فارغة = None صريح
        result = arbitrate([])
        assert result.canonical_value is None
        assert "لا مشاهدات" in result.reasoning_ar

    def test_all_none_values_rejected(self):
        obs = [Observation(value=None, source=ObservationSource.SENSOR,
                          confidence="low", measured_at="2026-01-01",
                          observable_id="ndvi")]
        result = arbitrate(obs)
        assert result.canonical_value is None


class TestPriorityOrder:
    """LAB > MANUAL > SENSOR > DRONE > SATELLITE > HISTORICAL."""

    def setup_method(self):
        reset_priorities_to_default()

    def test_lab_beats_sensor(self):
        # CRITICAL: مبدأ سهولي #٢ - المختبر يحكم
        obs = [
            _obs(0.55, ObservationSource.SENSOR, confidence="high"),
            _obs(0.62, ObservationSource.LAB, confidence="high"),
        ]
        result = arbitrate(obs)
        assert result.canonical_source == ObservationSource.LAB
        assert result.canonical_value == 0.62

    def test_manual_beats_satellite(self):
        obs = [
            _obs(0.55, ObservationSource.SATELLITE, confidence="medium"),
            _obs(0.60, ObservationSource.MANUAL, confidence="medium"),
        ]
        result = arbitrate(obs)
        assert result.canonical_source == ObservationSource.MANUAL

    def test_sensor_beats_satellite(self):
        obs = [
            _obs(0.50, ObservationSource.SATELLITE, confidence="medium"),
            _obs(0.55, ObservationSource.SENSOR, confidence="medium"),
        ]
        result = arbitrate(obs)
        assert result.canonical_source == ObservationSource.SENSOR


class TestAgeDecay:
    """قراءة حديثة تتفوّق على قديمة من نفس المصدر."""

    def test_recent_beats_old_same_source(self):
        # نفس المصدر، فرق العمر يحسم
        obs = [
            _obs(0.50, ObservationSource.SENSOR, days_ago=60),   # شهران
            _obs(0.55, ObservationSource.SENSOR, days_ago=1),    # حديث
        ]
        result = arbitrate(obs)
        # حديث = أعلى score بسبب decay
        assert result.canonical_value == 0.55

    def test_invalid_date_no_penalty(self):
        # صفر اختراع: لو التاريخ غير قابل للفهم، لا decay
        obs = [
            Observation(value=0.55, source=ObservationSource.SENSOR,
                       confidence="medium", measured_at="not-a-date",
                       observable_id="ndvi"),
        ]
        result = arbitrate(obs)
        # يجب أن يعمل، لا exception
        assert result.canonical_value == 0.55


class TestCriticalSpread:
    """تباين >50% = لا canonical، يحتاج مراجعة بشرية."""

    def test_critical_spread_returns_none(self):
        # CRITICAL: 0.20 vs 0.85 = تباين 76% → critical
        obs = [
            _obs(0.20, ObservationSource.SATELLITE),
            _obs(0.85, ObservationSource.SENSOR),
        ]
        result = arbitrate(obs)
        assert result.canonical_value is None
        assert result.severity == ConflictSeverity.CRITICAL
        assert result.requires_human_review

    def test_critical_lists_all_rejected(self):
        obs = [
            _obs(0.20, ObservationSource.SATELLITE),
            _obs(0.85, ObservationSource.SENSOR),
            _obs(0.50, ObservationSource.MANUAL),
        ]
        result = arbitrate(obs)
        # كل القيم في rejected_sources (لا اختيار صامت)
        assert len(result.rejected_sources) == 3

    def test_agreement_keeps_confidence(self):
        # توافق (<15% spread) → الثقة كما هي
        obs = [
            _obs(0.55, ObservationSource.SENSOR, confidence="high"),
            _obs(0.57, ObservationSource.LAB, confidence="high"),
        ]
        result = arbitrate(obs)
        assert result.severity == ConflictSeverity.AGREEMENT
        assert result.canonical_confidence == "high"   # كما هي

    def test_major_spread_drops_confidence(self):
        # تباين major (30-50%) → الثقة تنخفض لـlow
        obs = [
            _obs(0.45, ObservationSource.SENSOR, confidence="high"),
            _obs(0.75, ObservationSource.LAB, confidence="high"),   # 40% فرق
        ]
        result = arbitrate(obs)
        assert result.severity == ConflictSeverity.MAJOR
        # major: high → low (دائماً)
        assert result.canonical_confidence == "low"


class TestConfigurablePriorities:
    """priorities قابلة للتخصيص (للمعايرة)."""

    def setup_method(self):
        reset_priorities_to_default()

    def test_can_override_priority(self):
        # في منطقة معيّنة، satellite أدقّ من sensor
        set_source_priority(ObservationSource.SATELLITE, 200)
        assert get_source_priority(ObservationSource.SATELLITE) == 200

    def test_reset_restores_defaults(self):
        set_source_priority(ObservationSource.SATELLITE, 999)
        reset_priorities_to_default()
        assert get_source_priority(ObservationSource.SATELLITE) == 40
