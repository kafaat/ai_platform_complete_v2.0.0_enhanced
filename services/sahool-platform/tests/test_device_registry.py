"""اختبارات كتالوج أنواع الأجهزة (api.device_registry) — offline، لا قاعدة/لا شبكة.

يغطّي: السجلّ غير فارغ، تفرّد المعرّفات، كلّ مدخل بصنف ضمن المسموح + اسم غير فارغ،
get_device_type يعمل ويُعيد None لمجهول، المشغّل يملك أوامر، المستشعر يملك حقول قياس،
for_kind("sensor") غير فارغة، و kinds() مجموعة فرعيّة من ALLOWED_KINDS.
"""

from api.device_registry import (
    ALLOWED_KINDS,
    DeviceType,
    for_kind,
    get_device_type,
    kinds,
    list_device_types,
)


class TestRegistryShape:
    def test_registry_not_empty(self):
        assert len(list_device_types()) > 0

    def test_ids_unique(self):
        ids = [d["id"] for d in list_device_types()]
        assert len(ids) == len(set(ids))

    def test_every_entry_has_valid_kind_and_name(self):
        for d in list_device_types():
            assert d["kind"] in ALLOWED_KINDS
            assert d["name_ar"].strip()
            assert d["id"].strip()

    def test_dataclass_is_frozen(self):
        dt = DeviceType(id="x", name_ar="س", kind="sensor", capabilities=(), telemetry_fields=())
        try:
            dt.id = "y"  # type: ignore[misc]
        except Exception:
            return
        raise AssertionError("DeviceType يجب أن يكون frozen")


class TestLookup:
    def test_get_device_type_known(self):
        d = get_device_type("soil_moisture_sensor")
        assert d is not None
        assert d["id"] == "soil_moisture_sensor"
        assert d["kind"] == "sensor"

    def test_get_device_type_unknown_returns_none(self):
        assert get_device_type("no_such_device") is None


class TestCapabilitiesAndCommands:
    def test_actuator_has_commands(self):
        actuators = for_kind("actuator")
        assert actuators
        assert all(a["commands"] for a in actuators)

    def test_sensor_has_telemetry_fields(self):
        sensors = for_kind("sensor")
        assert sensors
        assert all(s["telemetry_fields"] for s in sensors)

    def test_sensors_have_no_commands(self):
        for s in for_kind("sensor"):
            assert s["commands"] == []


class TestKinds:
    def test_for_kind_sensor_non_empty(self):
        assert for_kind("sensor")

    def test_for_kind_unknown_empty(self):
        assert for_kind("spaceship") == []

    def test_kinds_subset_of_allowed(self):
        assert set(kinds()).issubset(set(ALLOWED_KINDS))
        assert kinds()  # غير فارغة
