"""كتالوج أنواع أجهزة IoT — سجلّ بيانات (metadata) يتيح التسجيل اللحظيّ (plug-and-play).

المشكلة المسدودة: بدل ترميز أنواع الأجهزة في الكود (`if sensor == "soil_moisture"`)،
نُعلن كلّ نوع جهاز كبيانات (DeviceType) في سجلّ واحد. هكذا يُسجَّل نوع جهاز جديد
بإضافة سطر بيانات لا بتعديل منطق — ويبقى مصدراً واحداً لـ:
  • القدرات (capabilities) التي يدعمها الجهاز،
  • حقول القياس (telemetry_fields) التي يُنتجها (تطابق device_telemetry.sensor_type في v24)،
  • الأوامر (commands) المقبولة للمشغّلات (actuators).

الاستخدام لاحقاً (متابعة): طبقة الابتلاع (ingest_telemetry في main.py) ينبغي أن تتحقّق
من الجهاز الوارد مقابل هذا السجلّ — نوع معروف، وحقل قياس ضمن telemetry_fields، وأمر
ضمن commands — قبل القبول. هذا الملف نقيّ تماماً: لا قاعدة، لا شبكة، قابل للاختبار offline.

التأريض (grounding): الأنواع وحقول القياس مأخوذة من مخطّط v24_iot_devices.sql
(iot_devices.type CHECK + device_telemetry.sensor_type)، ومن main.py (DeviceRequest.type،
_latest_soil_moisture يقرأ sensor_type='soil_moisture')، ومن actuator-service/main.py
(_INVERSE_COMMANDS: open↔close). الحقول المُستنتَجة (لا نصّ صريح في المخطّط) مُعلَّمة
بكلمة "مُستنتَج" في الوصف ولا نخترع أنواعاً تتجاوز ما يدعمه CHECK في iot_devices.
"""

from __future__ import annotations

from dataclasses import dataclass

# أنواع الأجهزة المسموح بها (kind) — تطابق دلالة iot_devices.type في v24:
# المستشعر (sensor) يقرأ ويبلّغ، المشغّل (actuator) ينفّذ أوامر، الكاميرا (camera)
# عين بصريّة، والبوّابة (gateway) تجمّع/تمرّر (mesh gateway في esp32_mesh_gateway.ino).
ALLOWED_KINDS: tuple[str, ...] = ("sensor", "actuator", "camera", "gateway")


@dataclass(frozen=True)
class DeviceType:
    """نوع جهاز مُعلَن كبيانات — وحدة الكتالوج الواحدة (plug-and-play).

    - `id`: معرّف ثابت قابل للبرمجة (مثل "soil_moisture_sensor").
    - `name_ar`: اسم معروض بالعربيّة.
    - `kind`: صنف الجهاز ضمن ALLOWED_KINDS.
    - `capabilities`: ما يستطيع الجهاز فعله (مثل "read_soil_moisture", "open_valve").
    - `telemetry_fields`: أسماء حقول القياس التي يُنتجها (تطابق device_telemetry.sensor_type).
    - `commands`: الأوامر المقبولة (للمشغّلات؛ فارغة للمستشعرات/الكاميرا).
    - `description_ar`: وصف موجز + تعليم الحقول المُستنتَجة عند غياب نصّ صريح في المخطّط.
    """

    id: str
    name_ar: str
    kind: str
    capabilities: tuple[str, ...]
    telemetry_fields: tuple[str, ...]
    commands: tuple[str, ...] = ()
    description_ar: str = ""
    #: إيقاعُ الإبلاغ المتوقَّع (ثوانٍ) وسقفُ عمر القراءة المشتقُّ منه — **إعلانٌ لا قياس**:
    #: لا حقلَ إيقاعٍ في المخطّط اليوم؛ الطزاجةُ تُربَط بإعلانٍ مسمًّى لا برقمٍ سحريّ في المستهلك.
    expected_report_interval_s: int | None = None
    max_reading_age_s: int | None = None

    def as_dict(self) -> dict:
        """تشكيل JSON لطبقة الـAPI (الصفوف tuple تُسلسَل قوائمَ)."""
        return {
            "id": self.id,
            "name_ar": self.name_ar,
            "kind": self.kind,
            "capabilities": list(self.capabilities),
            "telemetry_fields": list(self.telemetry_fields),
            "commands": list(self.commands),
            "description_ar": self.description_ar,
            "expected_report_interval_s": self.expected_report_interval_s,
            "max_reading_age_s": self.max_reading_age_s,
        }


# ── السجلّ المركزيّ: مصدر واحد لبيانات أنواع الأجهزة ─────────────────
# كلّ مدخل مُؤرَّض على المخطّط/الكود؛ الحقول التي لا نصّ صريح لها مُعلَّمة "مُستنتَج".
_REGISTRY: dict[str, DeviceType] = {
    # مستشعر رطوبة التربة — iot_devices.type='soil_moisture' (v24 CHECK)؛
    # device_telemetry.sensor_type='soil_moisture' (main.py _latest_soil_moisture).
    "soil_moisture_sensor": DeviceType(
        id="soil_moisture_sensor",
        name_ar="مستشعر رطوبة التربة",
        kind="sensor",
        capabilities=("read_soil_moisture",),
        telemetry_fields=("soil_moisture",),
        commands=(),
        description_ar=(
            "يقيس رطوبة التربة ويبتلعها شاهداً قانونيّاً (property='soil_moisture'). "
            "وحدةُ القراءة كما يُعلنها المصدر: vwc_pct (حجميّة) أو available_pct (ماء متاح)؛ "
            "«%» وحدَها غيرُ مُعلَنة. يغذّي توصية الريّ وقاعدة low_moisture ووصلة توأم المياه."
        ),
        # إعلانٌ: إبلاغٌ كلّ ساعة، وأربعةُ أضعافه سقفُ الطزاجة (٤ ساعات) — يُراجَع بالقياس.
        expected_report_interval_s=3600,
        max_reading_age_s=4 * 3600,
    ),
    # محطّة طقس/مناخ — iot_devices.type='weather_station' (v24 CHECK).
    # حقول القياس: air_temp (تعليق v24 الصريح) + air_humidity (تعليق v20_automation).
    # rainfall/wind مُستنتَجة من حقول الطقس في init_v8 (rainfall_mm/wind_speed_kmh)
    # وskills_registry (temperature/rainfall/humidity/et0) — وحدة قياس واحدة لكلّ سطر.
    "weather_station": DeviceType(
        id="weather_station",
        name_ar="محطّة طقس",
        kind="sensor",
        capabilities=("read_air_temp", "read_air_humidity", "read_rainfall", "read_wind"),
        telemetry_fields=("air_temp", "air_humidity", "rainfall", "wind_speed"),
        commands=(),
        description_ar=(
            "محطّة مناخ ميدانيّة. air_temp مؤرَّض على تعليق v24 الصريح، air_humidity على "
            "v20_automation. rainfall/wind_speed مُستنتَجة من حقول الطقس (init_v8: "
            "rainfall_mm/wind_speed_kmh) — تُبتلَع كقياسات منفصلة بـsensor_type لكلّ منها."
        ),
    ),
    # عدّاد ماء — iot_devices.type='water_meter' (v24 CHECK).
    # حقل water_flow مُستنتَج من دلالة العدّاد + flow_rate_lpm/flow_rate_m3h في المخطّط
    # (v25_irrigation, v41_fields_irrigation) — لا sensor_type صريح في v24 لكنّه ضمن الدلالة.
    "water_meter": DeviceType(
        id="water_meter",
        name_ar="عدّاد الماء",
        kind="sensor",
        capabilities=("read_water_flow", "read_water_volume"),
        telemetry_fields=("water_flow", "water_volume"),
        commands=(),
        description_ar=(
            "يقيس تدفّق/حجم ماء الريّ. النوع مؤرَّض على iot_devices CHECK؛ "
            "حقلا water_flow/water_volume مُستنتَجان من دلالة العدّاد و flow_rate في "
            "مخطّط الريّ (v25/v41) — لا نصّ sensor_type صريح في v24."
        ),
    ),
    # مشغّل صمّام الريّ — iot_devices.type='actuator' (v24 CHECK).
    # الأوامر open/close مؤرَّضة على actuator-service _INVERSE_COMMANDS وحالة الصمّام
    # open/closed (main.py ValveStateRequest). المشغّل لا يبتلع قياسات ⇒ telemetry فارغ.
    "valve_actuator": DeviceType(
        id="valve_actuator",
        name_ar="مشغّل صمّام الريّ",
        kind="actuator",
        capabilities=("open_valve", "close_valve"),
        telemetry_fields=(),
        commands=("open", "close"),
        description_ar=(
            "صمّام ريّ يُفتَح/يُغلَق بأوامر MQTT. open/close مؤرَّضان على "
            "actuator-service (_INVERSE_COMMANDS: open↔close) وحالة الصمّام open/closed "
            "في main.py. المشغّل ينفّذ ولا يبلّغ قياسات ⇒ telemetry_fields فارغ."
        ),
    ),
    # كاميرا مراقبة — iot_devices.type='camera' (v24 CHECK)؛ تتوافق مع field_cameras.py
    # (عين ميدانيّة لا كشف آلي). لا تبتلع قياسات رقميّة في device_telemetry ⇒ telemetry فارغ.
    "field_camera": DeviceType(
        id="field_camera",
        name_ar="كاميرا حقل",
        kind="camera",
        capabilities=("capture_image", "stream_video"),
        telemetry_fields=(),
        commands=(),
        description_ar=(
            "كاميرا مراقبة ميدانيّة (تطابق field_cameras.py: عين تُري المزارع لا عقل "
            "يقرّر). تلتقط لقطات/بثّاً؛ لا قياسات رقميّة في device_telemetry ⇒ "
            "telemetry_fields فارغ. capture_image مؤرَّض على CameraType (timelapse)؛ "
            "stream_video مُستنتَج لأنواع البثّ الحيّ."
        ),
    ),
}


def list_device_types() -> list[dict]:
    """كلّ أنواع الأجهزة المُعلَنة كقوائم dict (لطبقة الـAPI)، بترتيب الإدراج."""
    return [dt.as_dict() for dt in _REGISTRY.values()]


def get_device_type(id: str) -> dict | None:
    """نوع الجهاز بمعرّفه كـdict، أو None إن لم يكن مُعلَناً (نوع مجهول ⇒ يُرفَض)."""
    dt = _REGISTRY.get(id)
    return dt.as_dict() if dt is not None else None


def kinds() -> list[str]:
    """أصناف الأجهزة المُعلَنة فعليّاً في السجلّ (مجموعة فرعيّة من ALLOWED_KINDS)، مرتّبة."""
    return sorted({dt.kind for dt in _REGISTRY.values()})


def for_kind(kind: str) -> list[dict]:
    """أنواع الأجهزة من صنف مُعطًى (مثل "sensor")، بترتيب الإدراج؛ فارغة لصنف غير موجود."""
    return [dt.as_dict() for dt in _REGISTRY.values() if dt.kind == kind]
