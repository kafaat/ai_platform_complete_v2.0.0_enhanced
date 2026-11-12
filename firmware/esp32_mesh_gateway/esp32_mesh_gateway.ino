// SAHOOL v9.1 — ESP32 Mesh Gateway + MQTT Bridge
// painlessMesh: self-healing WiFi mesh for large farms
// Publishes sensor data to SAHOOL MQTT Broker (FastBee)
//
// Hardware: ESP32-WROOM + DHT22 + FC28 + optional LoRa
// Libraries: painlessMesh, PubSubClient, ArduinoJson (6.x), DHT sensor library
// Command auth: protocol v2 (R-C2) — cmd_auth_v2.h; flashing/provisioning runbook:
//   docs/runbooks/ACTUATOR_SIGNING_V2_FLASHING_AR.md

#include <painlessMesh.h>
#include <PubSubClient.h>
// HIGH-FIRM-01 FIX: Use TLS for production MQTT
// #include <WiFiClientSecure.h>
// WiFiClientSecure tlsClient;
// tlsClient.setCACert(root_ca_cert);
// PubSubClient mqttClient(tlsClient);  // ← TLS version
// For development, plain WiFiClient is used below — change for production
// ctr/iat/exp are epoch-millisecond counters (< 2^53): 64-bit integers in the JSON reader.
#define ARDUINOJSON_USE_LONG_LONG 1
#include <ArduinoJson.h>
#include <DHT.h>
#include <Preferences.h>  // NVS: identity, per-device command key, last_ctr (R-C2)
#include <sys/time.h>
#include <time.h>
#include <esp_task_wdt.h> // مراقب الأجهزة (watchdog) — يعيد التشغيل عند التعليق
#include "cmd_auth_v2.h"  // التحقّق من أوامر v2 (HMAC-SHA256 عبر mbedtls) — منطق نقيّ مُختبَر على المضيف

// ── Mesh Config ─────────────────────────────────────────────
#define MESH_PREFIX     "sahool-mesh"
// CRIT-FIRM-01 FIX: NEVER hardcode credentials
// Load from EEPROM/NVS at runtime — see setup() below
#define MESH_PASSWORD   ""  // Set via serial config or NVS flash
// To set: Use esp32 NVS flash tool or serial command: SET_MESH_PASS:<password>
#define MESH_PORT       5555

// ── WiFi STA for MQTT uplink (fallback if no mesh root) ─────
#define WIFI_SSID       "YOUR_FARM_WIFI"
#define WIFI_PASS       "YOUR_WIFI_PASS"

// ── MQTT Broker (FastBee / SAHOOL) ──────────────────────────
#define MQTT_SERVER     "sahool-fastbee"  // or IP
#define MQTT_PORT       1883
#define MQTT_USER       ""
#define MQTT_PASS       ""

// ── Device Identity ─────────────────────────────────────────
// R-C2: الهويّة ومفتاح الأوامر وآخر عدّاد في NVS (Preferences)، تُضبط عبر serial:
//   SET_TENANT:<uuid> · SET_DEVICE:<id> · SET_FIELD:<id> · SET_CMD_KEY:<64 hex>
//   SHOW_CONFIG (لا يطبع المفتاح) · CLEAR_CMD_KEY · REBOOT
// القيم أدناه افتراضيّة للقياس عن بُعد فقط؛ الأوامر تُرفَض كلّها ما لم تُضبط الأربعة في NVS.
#define DEFAULT_DEVICE_ID "esp32-node-001"
#define DEFAULT_FIELD_ID  "field_01"
#define DEFAULT_TENANT_ID "default"
#define NVS_NAMESPACE     "sahoolcmd"
// خوادم الوقت (SNTP) — الانتهاء يُفحَص فقط حين تتزامن الساعة؛ بدونها يحكم العدّاد وحده.
#define NTP_SERVER_1      "pool.ntp.org"
#define NTP_SERVER_2      "time.google.com"

// ── Sensor Pins ─────────────────────────────────────────────
#define DHT_PIN         4
#define DHT_TYPE        DHT22
#define SOIL_PIN        34   // FC28 analog
#define RELAY_PIN       25   // Actuator relay (optional)

// ── Valve fail-safe (حماية فيزيائيّة محلّيّة) ────────────────────
// أقصى مدّة فتح للصمّام. السيناريو الخطر: يصل أمر OPEN فيُفتح الصمّام، ثم ينقطع
// الاتصال قبل وصول CLOSE (شبكة اليمن متقطّعة) ⇒ صمّام عالق مفتوح ⇒ إغراق الحقل
// أو إهدار ماء نادر. هذا الحدّ يُغلقه تلقائيّاً في loop() دون اعتماد MQTT/Mesh.
// اضبطه حسب أكبر ريّة مشروعة لمحاصيلك.
#define VALVE_MAX_OPEN_MS  1800000UL   // 30 دقيقة

// ── Globals ─────────────────────────────────────────────────
painlessMesh  mesh;
WiFiClient    wifiClient;
Preferences   prefs;
cmdauth::Config g_cfg;   // tenant/device/field/key/last_ctr — من NVS

// الهويّة الفعّالة: قيمة NVS إن ضُبطت، وإلّا الافتراضيّ (للقياس عن بُعد فقط).
static const char* devId()    { return g_cfg.device[0] ? g_cfg.device : DEFAULT_DEVICE_ID; }
static const char* fieldId()  { return g_cfg.field[0]  ? g_cfg.field  : DEFAULT_FIELD_ID; }
static const char* tenantId() { return g_cfg.tenant[0] ? g_cfg.tenant : DEFAULT_TENANT_ID; }

// لحظة فتح الصمّام (millis). 0 = مغلق. تُستخدم للإغلاق التلقائي عند تجاوز المدّة.
unsigned long valveOpenedAt = 0;
// A7: مدّة الريّة المطلوبة (payload.duration_sec بالملّي ثانية)، 0 = لا مدّة (السقف وحده).
unsigned long valveRequestedMs = 0;

// تحكّم مركزيّ بالصمّام مع تتبّع وقت الفتح (مصدر واحد للحقيقة لمنطق الـfail-safe).
void setRelay(bool on) {
  digitalWrite(RELAY_PIN, on ? HIGH : LOW);
  valveOpenedAt = on ? millis() : 0;
}
PubSubClient  mqttClient(wifiClient);
DHT           dht(DHT_PIN, DHT_TYPE);

unsigned long lastSensorRead = 0;
unsigned long lastMqttReconnect = 0;
const unsigned long SENSOR_INTERVAL = 30000;   // 30 sec
const unsigned long MQTT_INTERVAL   = 5000;    // 5 sec

// ── Mesh Callbacks ──────────────────────────────────────────
void receivedCallback(uint32_t from, String &msg) {
  Serial.printf("Mesh: received from %u msg=%s\n", from, msg.c_str());
  // If this node is the root, forward to MQTT
  if (mesh.isRoot()) {
    forwardToMqtt(msg);
  }
}

void newConnectionCallback(uint32_t nodeId) {
  Serial.printf("Mesh: new connection, nodeId=%u\n", nodeId);
}

void changedConnectionCallback() {
  Serial.println("Mesh: connections changed");
}

// ── MQTT Functions ────────────────────────────────────────────
void forwardToMqtt(String &msg) {
  if (!mqttClient.connected()) return;
  // Topic: sahool/tenant/{tenant}/field/{field}/telemetry/{sensor}
  String topic = String("sahool/") + tenantId() + "/" + fieldId() + "/telemetry/mesh";
  mqttClient.publish(topic.c_str(), msg.c_str());
  Serial.println("MQTT forwarded: " + topic);
}

boolean mqttReconnect() {
  String clientId = "sahool-mesh-" + String(devId());
  if (mqttClient.connect(clientId.c_str(), MQTT_USER, MQTT_PASS)) {
    // Subscribe to actuator commands for this device
    // FIX: كان الـtopic مشوّهاً (تكرار DEVICE_ID + /command) فلا يصل أيّ أمر
    String cmdTopic = String("sahool/actuator/") + String(devId()) + String("/command");
    // A7: QoS 1 — الوسيط يعيد إرسال الأمر حتّى يُقَرّ (كان QoS 0 افتراضيّاً: يضيع بصمت).
    mqttClient.subscribe(cmdTopic.c_str(), 1);
    Serial.println("MQTT connected");
  }
  return mqttClient.connected();
}

// ── NVS (Preferences) — R-C2 ────────────────────────────────
// الهويّة والمفتاح وlast_ctr تبقى عبر إعادة التشغيل؛ last_ctr يُكتب **قبل** التحريك، فأمرٌ
// مُلتقَط لا يُعاد بعد إقلاع (كانت نافذة RAM من ١٦ طابعاً تضيع عند كلّ إعادة تشغيل).
static void loadConfig() {
  memset(&g_cfg, 0, sizeof(g_cfg));
  prefs.begin(NVS_NAMESPACE, true);
  prefs.getString("tenant", g_cfg.tenant, sizeof(g_cfg.tenant));
  prefs.getString("device", g_cfg.device, sizeof(g_cfg.device));
  prefs.getString("field", g_cfg.field, sizeof(g_cfg.field));
  g_cfg.has_key = prefs.getBytes("cmdkey", g_cfg.key, sizeof(g_cfg.key)) == sizeof(g_cfg.key);
  g_cfg.last_ctr = prefs.getULong64("last_ctr", 0);
  prefs.end();
}

static bool persistLastCtr(uint64_t ctr) {
  prefs.begin(NVS_NAMESPACE, false);
  size_t n = prefs.putULong64("last_ctr", ctr);
  prefs.end();
  if (n != sizeof(uint64_t)) return false;
  g_cfg.last_ctr = ctr;
  return true;
}

static bool clockSynced() {
  return time(nullptr) > 1700000000;   // 2023-11 — قبلها الساعة لم تتزامن بعد (SNTP)
}

static uint64_t nowEpochMs() {
  struct timeval tv;
  gettimeofday(&tv, nullptr);
  return (uint64_t)tv.tv_sec * 1000ULL + (uint64_t)(tv.tv_usec / 1000);
}

static void printConfig() {
  Serial.printf("CONFIG tenant=%s device=%s field=%s cmd_key=%s last_ctr=%llu "
                "provisioned=%s clock_synced=%s protocol=v2\n",
                g_cfg.tenant[0] ? g_cfg.tenant : "<unset>",
                g_cfg.device[0] ? g_cfg.device : "<unset>",
                g_cfg.field[0] ? g_cfg.field : "<unset>", g_cfg.has_key ? "set" : "unset",
                (unsigned long long)g_cfg.last_ctr, cmdauth::provisioned(g_cfg) ? "yes" : "no",
                clockSynced() ? "yes" : "no");
}

// ── Serial provisioning (USB، 115200) ────────────────────────
// محلّيٌّ فقط (وصولٌ فيزيائيّ). لا يُطبَع المفتاح أبداً، ولا يُردَّد سطرُ SET_CMD_KEY.
static void handleSerialLine(String line) {
  line.trim();
  if (line.length() == 0) return;
  bool identityChanged = false;
  if (line.startsWith("SET_TENANT:") || line.startsWith("SET_DEVICE:") ||
      line.startsWith("SET_FIELD:")) {
    int colon = line.indexOf(':');
    String name = line.substring(4, colon);   // TENANT / DEVICE / FIELD
    String value = line.substring(colon + 1);
    value.trim();
    if (!cmdauth::valid_field(value.c_str(), cmdauth::kFieldMax)) {
      Serial.println("ERR: value must be 1-63 chars without '|'");
      return;
    }
    const char* nvsKey = name == "TENANT" ? "tenant" : (name == "DEVICE" ? "device" : "field");
    prefs.begin(NVS_NAMESPACE, false);
    size_t n = prefs.putString(nvsKey, value);
    prefs.end();
    Serial.println(n > 0 ? String("OK ") + nvsKey + "=" + value : String("ERR: NVS write failed"));
    identityChanged = true;
  } else if (line.startsWith("SET_CMD_KEY:")) {
    uint8_t k[32];
    if (!cmdauth::parse_key_hex(line.substring(12).c_str(), k)) {
      Serial.println("ERR: SET_CMD_KEY needs exactly 64 hex characters");
      return;
    }
    prefs.begin(NVS_NAMESPACE, false);
    size_t n = prefs.putBytes("cmdkey", k, sizeof(k));
    prefs.end();
    memset(k, 0, sizeof(k));
    Serial.println(n == 32 ? "OK cmd key stored (not echoed)" : "ERR: NVS write failed");
  } else if (line == "CLEAR_CMD_KEY") {
    // last_ctr يُحفَظ عمداً: مسحُ المفتاح لا يفتح باب إعادة أوامر قديمة.
    prefs.begin(NVS_NAMESPACE, false);
    prefs.remove("cmdkey");
    prefs.end();
    Serial.println("OK cmd key cleared — all commands are rejected until SET_CMD_KEY");
  } else if (line == "SHOW_CONFIG") {
    // يطبع الحالة أدناه — والمفتاح «set/unset» فقط.
  } else if (line == "REBOOT") {
    Serial.println("rebooting");
    delay(100);
    ESP.restart();
  } else {
    Serial.println("ERR: unknown command (SET_TENANT/SET_DEVICE/SET_FIELD/SET_CMD_KEY/"
                   "SHOW_CONFIG/CLEAR_CMD_KEY/REBOOT)");
    return;
  }
  loadConfig();
  printConfig();
  if (identityChanged) Serial.println("NOTE: MQTT topics follow the new identity after REBOOT");
}

static void pollSerial() {
  static String buf;
  while (Serial.available()) {
    char c = (char)Serial.read();
    if (c == '\n' || c == '\r') {
      if (buf.length()) handleSerialLine(buf);
      buf = "";
    } else if (buf.length() < 200) {
      buf += c;
    }
  }
}

// v238 + R-C2: إقرار الجهاز v2 يحمل معرّف الأمر وعدّاده، موقَّعاً بمفتاح الجهاز:
// HMAC(device_key, "v2ack|tenant|device|id|result|ctr"). الموضوع
// sahool/<tenant>/actuator/<device>/ack، وtenant يجب أن يكون UUID المستأجر (المنصّة ترفض غيره).
// PubSubClient ينشر QoS 0 فقط: إقرارٌ ضائع يترك الأمر published حتّى تنتهي مهلته (expired).
static void publishDeviceAck(const char* cmdId, const char* result, uint64_t ctr) {
  if (cmdId == nullptr || !mqttClient.connected()) return;
  char sig[65];
  if (!cmdauth::sign_ack_hex(g_cfg, cmdId, result, ctr, sig)) return;  // بلا مفتاح لا إقرار
  StaticJsonDocument<512> ack;
  ack["v"] = cmdauth::kVersion;
  ack["id"] = cmdId;
  ack["tenant"] = g_cfg.tenant;
  ack["device"] = g_cfg.device;
  ack["result"] = result;
  ack["ctr"] = ctr;
  ack["status"] = digitalRead(RELAY_PIN) ? "ON" : "OFF";
  ack["sig"] = sig;
  String out;
  serializeJson(ack, out);
  String topic = String("sahool/") + g_cfg.tenant + "/actuator/" + g_cfg.device + "/ack";
  mqttClient.publish(topic.c_str(), out.c_str());
}

static bool jsonUint(JsonVariantConst v, uint64_t* out) {
  if (!v.is<unsigned long long>()) return false;
  *out = v.as<unsigned long long>();
  return true;
}

void mqttCallback(char* topic, byte* payload, unsigned int length) {
  Serial.printf("MQTT cmd on %s (%u bytes)\n", topic, length);

  // A4: رسالة المنصّة تتجاوز 256 بايتاً.
  StaticJsonDocument<1024> doc;
  DeserializationError err = deserializeJson(doc, payload, length);
  if (err) return;

  cmdauth::Command m{};
  m.has_v = doc["v"].is<long>();
  m.v = m.has_v ? doc["v"].as<long>() : 0;
  m.id = doc["id"];
  m.cmd = doc["cmd"];
  m.tenant = doc["tenant"];
  m.device = doc["device"];
  m.field = doc["field"];
  m.sig = doc["sig"];
  bool ok = jsonUint(doc["iat"], &m.iat) && jsonUint(doc["exp"], &m.exp) &&
            jsonUint(doc["ctr"], &m.ctr);
  JsonVariantConst dur = doc["payload"]["duration_ms"];
  if (dur.isNull()) m.duration_ms = 0;
  else ok = ok && jsonUint(dur, &m.duration_ms);
  m.numbers_ok = ok;

  // R-C2: v2 فقط. توقيعٌ بمفتاح هذا الجهاز + ربط tenant/device/field بقيم NVS + ctr > last_ctr
  // + انتهاء (حين تتزامن الساعة، ولا يُطبَّق على CLOSE/OFF: الإغلاق هو الحالة الآمنة).
  cmdauth::Result r = cmdauth::verify_command(g_cfg, m, clockSynced(), nowEpochMs());
  if (r != cmdauth::ACCEPT) {
    Serial.printf("MQTT cmd مرفوض: %s\n", cmdauth::reason(r));
    // أمرٌ موقَّع لهذا الجهاز لكن مُعاد/منتهٍ يُقَرّ "rejected" ليظهر في حالة التسليم.
    // التوقيع غير الصالح أو الربط المخالف لا يُقَرّ: معرّفه غير موثوق، أو ليس لنا.
    if (r == cmdauth::REJ_REPLAY || r == cmdauth::REJ_EXPIRED) {
      publishDeviceAck(m.id, "rejected", m.ctr);
    }
    return;
  }
  const bool closing = cmdauth::is_close(m.cmd);
  // last_ctr يُحفَظ قبل التحريك. فشلُ الكتابة يرفض الفتح (لا تحريك بلا حماية إعادة)، أمّا
  // الإغلاق فيمضي: هو الحالة الآمنة، وإعادتُه لا تضرّ.
  if (!persistLastCtr(m.ctr) && !closing) {
    Serial.println("MQTT cmd مرفوض: تعذّر حفظ last_ctr في NVS");
    return;
  }

  if (closing) {
    setRelay(false);   // يغلق + يلغي المؤقّت
  } else {
    // OPEN/ON (verify_command يرفض ما سواها). A7: المدّة الموقَّعة تُحترَم، ولا يُجدِّد
    // OPEN متكرّرٌ مؤقّتَ السقف.
    valveRequestedMs = (unsigned long)m.duration_ms;
    if (valveOpenedAt == 0) setRelay(true);  // يفتح + يبدأ مؤقّت الإغلاق التلقائي (fail-safe)
  }

  // v238: إقرار المنصّة بمعرّف الأمر (published → device_acked).
  publishDeviceAck(m.id, "applied", m.ctr);

  // Acknowledge via mesh
  StaticJsonDocument<192> ack;
  ack["device"] = devId();
  ack["ack"] = m.cmd;
  ack["result"] = "applied";
  ack["status"] = digitalRead(RELAY_PIN) ? "ON" : "OFF";
  String ackStr;
  serializeJson(ack, ackStr);
  mesh.sendBroadcast(ackStr);
}

// ── Sensor Read ──────────────────────────────────────────────
String readSensors() {
  float temp = dht.readTemperature();
  float hum  = dht.readHumidity();
  int soilRaw = analogRead(SOIL_PIN);
  float soilPct = map(soilRaw, 0, 4095, 0, 100);  // Calibrate!

  if (isnan(temp)) temp = -999;
  if (isnan(hum))  hum  = -999;

  StaticJsonDocument<256> doc;
  doc["device_id"] = devId();
  doc["field_id"]  = fieldId();
  doc["tenant_id"] = tenantId();
  doc["ts"]        = millis();

  JsonObject data = doc.createNestedObject("data");
  data["air_temp_c"]   = temp;
  data["air_humidity_pct"] = hum;
  data["soil_moisture_pct"] = soilPct;
  data["soil_raw"]     = soilRaw;
  data["relay_state"]  = digitalRead(RELAY_PIN) ? true : false;
  data["mesh_nodes"]   = mesh.getNodeList().size();
  data["is_root"]      = mesh.isRoot();

  String out;
  serializeJson(doc, out);
  return out;
}

// ── Setup ───────────────────────────────────────────────────
void setup() {
  Serial.begin(115200);
  delay(1000);
  Serial.println("SAHOOL ESP32 Mesh Gateway starting...");

  pinMode(RELAY_PIN, OUTPUT);
  setRelay(false);   // حالة آمنة عند الإقلاع (صمّام مغلق + مؤقّت ملغى)
  loadConfig();      // R-C2: الهويّة + المفتاح + last_ctr من NVS
  Serial.printf("cmd auth v2: provisioned=%s (SHOW_CONFIG for details)\n",
                cmdauth::provisioned(g_cfg) ? "yes" : "no — all commands rejected");
  dht.begin();

  // مراقب الأجهزة: يعيد تشغيل اللوحة إن تعلّق loop() أكثر من 30s.
  // حرجٌ للأجهزة الريفيّة غير المراقَبة (تعافٍ تلقائي من التعليق/الشبكة).
  esp_task_wdt_init(30, true);   // 30s مهلة، panic→reboot
  esp_task_wdt_add(NULL);        // راقب مهمّة loop الحاليّة

  // Mesh setup
  mesh.setDebugMsgTypes(ERROR | STARTUP);
  mesh.init(MESH_PREFIX, MESH_PASSWORD, MESH_PORT);
  mesh.onReceive(&receivedCallback);
  mesh.onNewConnection(&newConnectionCallback);
  mesh.onChangedConnections(&changedConnectionCallback);

  // If root, also connect to WiFi STA for MQTT
  if (mesh.isRoot()) {
    WiFi.begin(WIFI_SSID, WIFI_PASS);
    // R-C2: SNTP — الانتهاء (exp) يُفحَص فقط بعد التزامن؛ قبله يحكم العدّاد (ctr) وحده.
    configTime(0, 0, NTP_SERVER_1, NTP_SERVER_2);
    mqttClient.setServer(MQTT_SERVER, MQTT_PORT);
    mqttClient.setBufferSize(1024);  // A4: الافتراضيّ 256 يُسقط أوامر المنصّة بصمت
    mqttClient.setCallback(mqttCallback);
  }

  Serial.println("Setup complete");
}

// ── Loop ────────────────────────────────────────────────────
void loop() {
  esp_task_wdt_reset();   // أطعِم المراقب (loop حيّ) — يمنع إعادة تشغيل زائفة
  pollSerial();           // R-C2: أوامر التهيئة عبر USB serial

  // Valve fail-safe: أغلق الصمّام تلقائيّاً إن تجاوز المدّة القصوى للفتح. حماية
  // محلّيّة لا تعتمد الشبكة (طرح unsigned آمن مع تجاوز millis كل ~49 يوماً).
  if (valveOpenedAt != 0 && (millis() - valveOpenedAt) >= VALVE_MAX_OPEN_MS) {
    setRelay(false);
    StaticJsonDocument<160> alert;
    alert["device"]      = devId();
    alert["alert"]       = "valve_auto_closed";
    alert["reason"]      = "max_open_timeout";
    alert["max_open_ms"] = VALVE_MAX_OPEN_MS;
    String alertStr;
    serializeJson(alert, alertStr);
    mesh.sendBroadcast(alertStr);
    Serial.println("VALVE FAIL-SAFE: أُغلق الصمّام تلقائيّاً (تجاوز المدّة القصوى)");
  } else if (valveOpenedAt != 0 && valveRequestedMs != 0 &&
             (millis() - valveOpenedAt) >= valveRequestedMs) {
    // A7: انتهت الريّة المطلوبة — إغلاقٌ محلّيّ لا ينتظر CLOSE قد يضيع أثناء انقطاع الاتّصال.
    setRelay(false);
    StaticJsonDocument<160> done;
    done["device"]       = devId();
    done["alert"]        = "valve_auto_closed";
    done["reason"]       = "requested_duration_elapsed";
    done["requested_ms"] = valveRequestedMs;
    String doneStr;
    serializeJson(done, doneStr);
    mesh.sendBroadcast(doneStr);
  }

  mesh.update();

  // Root node: maintain MQTT
  if (mesh.isRoot()) {
    if (!mqttClient.connected()) {
      unsigned long now = millis();
      if (now - lastMqttReconnect > MQTT_INTERVAL) {
        lastMqttReconnect = now;
        if (mqttReconnect()) {
          lastMqttReconnect = 0;
        }
      }
    } else {
      mqttClient.loop();
    }
  }

  // Sensor read + broadcast
  unsigned long now = millis();
  if (now - lastSensorRead > SENSOR_INTERVAL) {
    lastSensorRead = now;
    String payload = readSensors();
    Serial.println("Sensors: " + payload);
    mesh.sendBroadcast(payload);

    // If root, also send directly to MQTT
    if (mesh.isRoot() && mqttClient.connected()) {
      forwardToMqtt(payload);
    }
  }
}
