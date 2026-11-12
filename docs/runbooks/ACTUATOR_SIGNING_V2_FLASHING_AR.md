# توقيع أوامر المشغّلات v2 — برمجة ESP32 وتهيئته (R-C2)

> **الحدّ:** هذا الدليل يصف خطواتٍ يُنفّذها إنسانٌ على الجهاز. لا شيء في المستودع يُثبت أنّ جهازاً
> بُرمِج أو هُيِّئ؛ الإثبات هو إقرار `device_acked` لأمرٍ موقَّع v2 من ذلك الجهاز (الخطوة ٥).

## لماذا

v1 كان يوقّع `cmd|ts|duration_ms` بسرٍّ واحد (`CMD_HMAC_SECRET`) لكلّ الأجهزة، والبرنامج الثابت يحفظ
آخر ١٦ طابعاً في الذاكرة. فأمرٌ مُلتقَط يُعاد إلى صمّام مستأجرٍ آخر (السرّ نفسه، ولا ربط بالمستأجر أو
الجهاز أو الحقل)، وإلى الصمّام نفسه بعد إعادة التشغيل. الفجوة: `SUP-08-DEVICE-COMMAND-SIGNATURE-UNBOUND-TO-DEVICE-01`.

v2:

- **مفتاحٌ لكلّ جهاز** يُشتقّ في الخادم: `HMAC_SHA256(CMD_HMAC_MASTER_KEY, "sahool-cmd-key-v2|tenant|device")`.
  لا تخزين لكلّ جهاز في القاعدة.
- **رسالةٌ مربوطة:** `v2|tenant|device|field|id|cmd|duration_ms|iat|exp|ctr`.
- **عدّادٌ متزايد** (`ctr`) يحفظه الجهاز في NVS قبل التحريك، فيصمد عبر إعادة التشغيل.
- **انتهاء** (`exp`، افتراضيّاً ١٢٠ ثانية) يُفحَص فقط حين تتزامن ساعة الجهاز (SNTP). **الإغلاق
  (CLOSE/OFF) لا يُرفَض للانتهاء أبداً**، لكنّه يخضع للتوقيع والربط والعدّاد.

المصادر: `services/actuator-service/cmd_signing_v2.py` · `firmware/esp32_mesh_gateway/cmd_auth_v2.h` ·
`firmware/esp32_mesh_gateway/esp32_mesh_gateway.ino`.

## ١. الأدوات والمكتبات

| البند | القيمة |
|---|---|
| اللوحة | ESP32-WROOM — `esp32:esp32:esp32` (ESP32 Dev Module) |
| نواة esp32 | `esp32:esp32@2.0.17` (الرسم يستعمل `esp_task_wdt_init(30, true)` بصيغة 2.x) |
| رابط مدير اللوحات | `https://espressif.github.io/arduino-esp32/package_esp32_index.json` |
| المكتبات | `painlessMesh` · `PubSubClient` · `ArduinoJson@6.21.5` (6.x) · `DHT sensor library` · `Adafruit Unified Sensor` |
| مضمَّن في النواة | `Preferences` (NVS) · `mbedtls` (HMAC-SHA256) |

**arduino-cli:**

```bash
arduino-cli config init
arduino-cli config set board_manager.additional_urls https://espressif.github.io/arduino-esp32/package_esp32_index.json
arduino-cli core update-index
arduino-cli core install esp32:esp32@2.0.17
arduino-cli lib install "painlessMesh" "PubSubClient" "ArduinoJson@6.21.5" "DHT sensor library" "Adafruit Unified Sensor"
arduino-cli compile --fqbn esp32:esp32:esp32 firmware/esp32_mesh_gateway
```

**Arduino IDE:** Preferences ← Additional boards manager URLs ← الرابط أعلاه؛ Boards Manager ← `esp32`
الإصدار 2.0.17؛ Library Manager ← المكتبات أعلاه؛ افتح `firmware/esp32_mesh_gateway/esp32_mesh_gateway.ino`
(الملفّ `cmd_auth_v2.h` في المجلّد نفسه ويُضمَّن تلقائيّاً).

**قبل البرمجة — اختبار المنطق على المضيف** (g++ وOpenSSL، يقرأ متّجهات Python نفسها):

```bash
make -C firmware/esp32_mesh_gateway/test
python firmware/esp32_mesh_gateway/test/gen_cmd_auth_v2_vectors.py --check
```

## ٢. البرمجة عبر USB

1. صِل اللوحة بـUSB، وحدّد المنفذ: `arduino-cli board list` (مثلاً `/dev/ttyUSB0` أو `COM5`).
2. اضبط `WIFI_SSID`/`WIFI_PASS`/`MQTT_SERVER` في الرسم كما في نشرك (لا تلتزمها في المستودع).
3. ارفع:

   ```bash
   arduino-cli upload -p /dev/ttyUSB0 --fqbn esp32:esp32:esp32 firmware/esp32_mesh_gateway
   ```

   إن تعذّر الاتّصال: اضغط زرّ **BOOT** مع بداية الرفع.
4. افتح المراقب: `arduino-cli monitor -p /dev/ttyUSB0 -c baudrate=115200`. يجب أن ترى:
   `cmd auth v2: provisioned=no — all commands rejected`. هذا هو السلوك الآمن: بلا تهيئة كاملة
   يُرفَض كلّ أمر.

## ٣. التهيئة عبر serial (بمخرجات الأداة)

على جهاز المشغّل (لا في CI ولا في سجلّ)، والمفتاح الرئيس من البيئة فقط — الأداة لا تقبله معاملاً:

```bash
export CMD_HMAC_MASTER_KEY='<من مدير الأسرار — نفس قيمة actuator-service>'
python services/actuator-service/provision_device_key.py \
  --tenant <tenant-uuid> --device <device_id كما في iot_devices> --field <field_id كما في iot_devices>
unset CMD_HMAC_MASTER_KEY
```

المخرجات (المفتاح سرّ — لا يُلصق في تذكرة أو محادثة):

```text
# SAHOOL actuator command key v2 — tenant=<uuid> device=<id>
# SECRET: paste into the device serial console only; do not store or share.
device_key=<64 hex>
# serial provisioning lines (115200 baud, newline-terminated):
SET_TENANT:<uuid>
SET_DEVICE:<id>
SET_FIELD:<field>
SET_CMD_KEY:<64 hex>
SHOW_CONFIG
```

الصق الأسطر الخمسة في المراقب سطراً سطراً. الجهاز يردّ `OK ...` لكلّ سطر، و`SET_CMD_KEY` يردّ
`OK cmd key stored (not echoed)`. ثمّ `SHOW_CONFIG` يطبع:

```text
CONFIG tenant=<uuid> device=<id> field=<field> cmd_key=set last_ctr=0 provisioned=yes clock_synced=yes protocol=v2
```

`SHOW_CONFIG` لا يطبع المفتاح أبداً (`set`/`unset` فقط). أرسل `REBOOT` كي تتبع مواضيع MQTT الهويّة الجديدة.

أوامر أخرى: `CLEAR_CMD_KEY` يمسح المفتاح (فيُرفَض كلّ أمر) ويُبقي `last_ctr` عمداً.

**شروط الصحّة:** `tenant` و`device` و`field` يجب أن تطابق صفّ الجهاز في `iot_devices` حرفيّاً — الخادم
يوقّع بحقل الجهاز من السجلّ، والجهاز يرفض ما لا يطابق NVS (`binding_mismatch`).

## ٤. إعداد الخادم

في بيئة actuator-service (`docker-compose.v9.yml` يمرّرها):

- `CMD_HMAC_MASTER_KEY` — ≥٣٢ حرفاً من مدير الأسرار. بدونه **لا يُنشَر أيّ أمر** لجهازٍ غير مُدرَج.
- `ACTUATOR_LEGACY_V1_DEVICES` — قائمة بفواصل للأجهزة التي لم تُبرمَج بعد (v1). كلّ إرسالٍ لها يُسجّل تحذيراً.
- `CMD_HMAC_SECRET` — سرّ v1 للأجهزة المُدرَجة فقط. جهازٌ مُدرَج بلا هذا السرّ لا يُرسَل إليه شيء.
- `ACTUATOR_CMD_EXPIRY_SECONDS` — افتراضيّاً 120 (يُقصّ إلى [10, 3600]).

## ٥. التحقّق من صمّامٍ واحد بأمر OPEN/CLOSE موقَّع

1. تأكّد أنّ الجهاز **ليس** في `ACTUATOR_LEGACY_V1_DEVICES`.
2. أرسل فتحاً قصيراً بمدّة صريحة (الفتح بلا مدّة يُرفَض 422):

   ```bash
   curl -sS -X POST "$ACTUATOR_URL/v1/command" -H "Authorization: Bearer $TOKEN" \
     -H 'Content-Type: application/json' \
     -d '{"device_id":"<id>","command":"open","payload":{"duration_sec":30}}'
   ```

   سجّل `command_id` من الردّ (`delivery_state: published`).
3. على مراقب serial لا يظهر `MQTT cmd مرفوض`، والصمّام يفتح.
4. `GET /v1/commands/<command_id>` ← `delivery_state: device_acked` (إقرار v2 موقَّع بمفتاح الجهاز).
5. أرسل `{"command":"close"}` وتحقّق بالطريقة نفسها: يُغلق ويُقَرّ.
6. **اختبار سلبيّ:** أعِد نشر رسالة الفتح نفسها على الموضوع (مثلاً بـ`mosquitto_pub`) ← الجهاز يطبع
   `MQTT cmd مرفوض: replay` ولا يتحرّك. أعِد تشغيله وكرّر ← المرفوض نفسه (العدّاد في NVS).

إن ظهر `bad_signature`: المفتاح الرئيس أو الهويّة لا تطابق ما اشتُقّ به المفتاح. `binding_mismatch`: الحقل
أو المستأجر في NVS يخالف السجلّ. `expired`: ساعة الخادم أو الجهاز منحرفة أو الرسالة تأخّرت.

## ٦. إخراج الأجهزة من `ACTUATOR_LEGACY_V1_DEVICES` واحداً واحداً

لكلّ جهاز في القائمة:

1. برمِجه (§٢) وهيّئه (§٣).
2. احذفه من `ACTUATOR_LEGACY_V1_DEVICES` وأعِد تشغيل actuator-service.
3. تحقّق منه (§٥). إن فشل، أعِده إلى القائمة **و**أعِد برمجته بالنسخة السابقة: البرنامج الثابت v2 لا
   يقبل v1 أبداً، فجهازٌ مُبرمَج v2 ومُدرَج في القائمة لن يتحرّك.

حين تفرغ القائمة: احذف `CMD_HMAC_SECRET` من البيئة. إقرارات v1 تُرفَض حينها (`legacy_v1_ack_not_allowed`).

## ٧. تدوير المفتاح الرئيس (يعيد تهيئة كلّ الأجهزة)

كلّ مفاتيح الأجهزة مشتقّة من المفتاح الرئيس، فتدويره يُبطل كلّ جهازٍ حتّى يُعاد تهيئته:

1. ولِّد مفتاحاً رئيساً جديداً في مدير الأسرار (لا تحذف القديم بعد).
2. لكلّ جهاز: شغّل الأداة بالمفتاح **الجديد** وأرسل `SET_CMD_KEY:<المفتاح الجديد>` فقط (الهويّة لا تتغيّر).
   من هذه اللحظة يرفض الجهاز أوامر المفتاح القديم — فرتِّب التدوير في نافذة صيانة أو حقلاً حقلاً.
3. حدّث `CMD_HMAC_MASTER_KEY` في actuator-service وأعِد تشغيله.
4. تحقّق من كلّ جهاز (§٥)، ثمّ احذف المفتاح القديم.

`last_ctr` يبقى في NVS عبر التدوير، والعدّاد مشتقّ من الزمن فيبقى متزايداً.

## حدود معروفة

- **العدّاد زمنيّ:** `ctr = epoch_ms × 1000 + خانة`. أمرٌ من مستهلك الإرسال يحمل عدّاداً من `requested_at`
  (ثابتٌ عبر إعادة النشر)، فإن أُرسل للجهاز نفسه أمرٌ أحدث قبله رُفِض القديم (`replay` ← إقرار `rejected`).
  ونسختان من الخدمة بساعتين منحرفتين قد تتسابقان للجهاز نفسه.
- **الانتهاء** لا يُفحَص قبل تزامن SNTP؛ العدّاد وحده يحكم حينها.
- **فشل كتابة NVS** يرفض الفتح، ويمضي بالإغلاق (الحالة الآمنة).
- الرسم لم يُترجَم في CI؛ اختبار المضيف يغطّي المنطق النقيّ في `cmd_auth_v2.h` وحده.
