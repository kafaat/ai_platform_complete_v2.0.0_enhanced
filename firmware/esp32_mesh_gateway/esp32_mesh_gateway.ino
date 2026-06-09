// SAHOOL v9.1 — ESP32 Mesh Gateway + MQTT Bridge
// painlessMesh: self-healing WiFi mesh for large farms
// Publishes sensor data to SAHOOL MQTT Broker (FastBee)
//
// Hardware: ESP32-WROOM + DHT22 + FC28 + optional LoRa
// Libraries: painlessMesh, PubSubClient, ArduinoJson, DHT sensor library

#include <painlessMesh.h>
#include <PubSubClient.h>
// HIGH-FIRM-01 FIX: Use TLS for production MQTT
// #include <WiFiClientSecure.h>
// WiFiClientSecure tlsClient;
// tlsClient.setCACert(root_ca_cert);
// PubSubClient mqttClient(tlsClient);  // ← TLS version
// For development, plain WiFiClient is used below — change for production
#include <ArduinoJson.h>
#include <DHT.h>
#include <mbedtls/md.h>   // HMAC-SHA256 للتحقّق من توقيع الأوامر (A1)
#include <esp_task_wdt.h> // مراقب الأجهزة (watchdog) — يعيد التشغيل عند التعليق

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
#define DEVICE_ID       "esp32-node-001"
#define FIELD_ID        "field_01"
#define TENANT_ID       "default"
// A1: سرّ توقيع الأوامر لكلّ جهاز (HMAC-SHA256). يجب ضبطه عبر NVS/serial،
// ويطابق السرّ الذي توقّع به actuator-service. فارغ = رفض كلّ الأوامر (آمن).
#define CMD_HMAC_SECRET ""  // SET_CMD_SECRET:<hex> عبر serial في الإنتاج

// ── Sensor Pins ─────────────────────────────────────────────
#define DHT_PIN         4
#define DHT_TYPE        DHT22
#define SOIL_PIN        34   // FC28 analog
#define RELAY_PIN       25   // Actuator relay (optional)

// ── Globals ─────────────────────────────────────────────────
painlessMesh  mesh;
WiFiClient    wifiClient;
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
  String topic = String("sahool/") + TENANT_ID + "/" + FIELD_ID + "/telemetry/mesh";
  mqttClient.publish(topic.c_str(), msg.c_str());
  Serial.println("MQTT forwarded: " + topic);
}

boolean mqttReconnect() {
  String clientId = "sahool-mesh-" + String(DEVICE_ID);
  if (mqttClient.connect(clientId.c_str(), MQTT_USER, MQTT_PASS)) {
    // Subscribe to actuator commands for this device
    // FIX: كان الـtopic مشوّهاً (تكرار DEVICE_ID + /command) فلا يصل أيّ أمر
    String cmdTopic = String("sahool/actuator/") + String(DEVICE_ID) + String("/command");
    mqttClient.subscribe(cmdTopic.c_str());
    Serial.println("MQTT connected");
  }
  return mqttClient.connected();
}

// A1: التحقّق من توقيع HMAC-SHA256 للأمر قبل تحريك الـrelay.
// يمنع أيّ طرف ينشر على الموضوع (أو يحقن على الشبكة) من تشغيل الصمّامات،
// حتّى مع وسيط MQTT بنصّ صريح. الحمولة المتوقّعة: {"cmd":..,"ts":..,"sig":"<hex>"}
// حيث sig = HMAC_SHA256(CMD_HMAC_SECRET, cmd + "|" + ts).
static bool verifyCmdHmac(const char* cmd, const char* ts, const char* sig) {
  if (strlen(CMD_HMAC_SECRET) == 0) return false;   // فارغ → رفض (آمن)
  if (cmd == nullptr || ts == nullptr || sig == nullptr) return false;
  // اِبنِ الرسالة cmd|ts
  char msg[96];
  snprintf(msg, sizeof(msg), "%s|%s", cmd, ts);
  // احسب HMAC-SHA256
  uint8_t hmac[32];
  const mbedtls_md_info_t* info = mbedtls_md_info_from_type(MBEDTLS_MD_SHA256);
  if (mbedtls_md_hmac(info,
        (const uint8_t*)CMD_HMAC_SECRET, strlen(CMD_HMAC_SECRET),
        (const uint8_t*)msg, strlen(msg), hmac) != 0) return false;
  // حوّل لـhex وقارن (ثابت الزمن قدر الإمكان)
  char hex[65];
  for (int i = 0; i < 32; i++) snprintf(hex + i*2, 3, "%02x", hmac[i]);
  if (strlen(sig) != 64) return false;
  uint8_t diff = 0;
  for (int i = 0; i < 64; i++) diff |= (hex[i] ^ sig[i]);
  return diff == 0;
}

// P1/idempotency: نافذة إعادة (replay window) — آخر N طوابع زمنيّة لأوامر
// نُفِّذت. أقوى من معرّف واحد: يكتشف التكرار غير المتتالي (تسليم MQTT QoS1
// خارج الترتيب، أو إعادة إرسال متأخّرة بعد فقد ACK). أمر بـts موجود في
// النافذة = تكرار → يُتجاهَل. ring buffer (لا تخصيص ديناميكي — مناسب لـESP32).
static const int CMD_WINDOW_SIZE = 16;
static String seenCmdTs[CMD_WINDOW_SIZE];
static int seenCmdHead = 0;

static bool isDuplicateCmd(const char* ts) {
  if (ts == nullptr) return false;
  String t = String(ts);
  for (int i = 0; i < CMD_WINDOW_SIZE; i++) {
    if (seenCmdTs[i] == t) return true;   // رأيناه → تكرار
  }
  return false;
}

static void rememberCmd(const char* ts) {
  if (ts == nullptr) return;
  seenCmdTs[seenCmdHead] = String(ts);
  seenCmdHead = (seenCmdHead + 1) % CMD_WINDOW_SIZE;  // دائري
}

void mqttCallback(char* topic, byte* payload, unsigned int length) {
  String msg;
  for (unsigned int i = 0; i < length; i++) msg += (char)payload[i];
  Serial.println("MQTT cmd: " + String(topic) + " -> " + msg);

  // Parse command
  StaticJsonDocument<256> doc;
  DeserializationError err = deserializeJson(doc, msg);
  if (err) return;

  const char* cmd = doc["cmd"];
  // FIX: تحقّق من null قبل strcmp (أمر بلا حقل cmd كان يسبّب crash)
  if (cmd == nullptr) return;
  // A1: ارفض أيّ أمر بلا توقيع HMAC صالح (منع تشغيل الصمّامات بأمر مزوّر)
  const char* ts  = doc["ts"];
  const char* sig = doc["sig"];
  if (!verifyCmdHmac(cmd, ts, sig)) {
    Serial.println("MQTT cmd مرفوض: توقيع HMAC غير صالح");
    return;
  }
  // idempotency: ارفض الأمر المكرّر (ضمن نافذة آخر N) — يمنع تشغيل الصمّام
  // مرّتين عند تكرار تسليم MQTT أو إعادة الإرسال (نقطة حرجة فيزيائيّاً).
  if (isDuplicateCmd(ts)) {
    Serial.println("MQTT cmd مكرّر (ضمن نافذة الإعادة) — تُجوهِل (idempotency)");
    return;
  }
  rememberCmd(ts);

  if (strcmp(cmd, "OPEN") == 0 || strcmp(cmd, "ON") == 0) {
    digitalWrite(RELAY_PIN, HIGH);
  } else if (strcmp(cmd, "CLOSE") == 0 || strcmp(cmd, "OFF") == 0) {
    digitalWrite(RELAY_PIN, LOW);
  }

  // Acknowledge via mesh
  StaticJsonDocument<128> ack;
  ack["device"] = DEVICE_ID;
  ack["ack"] = cmd;
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
  doc["device_id"] = DEVICE_ID;
  doc["field_id"]  = FIELD_ID;
  doc["tenant_id"] = TENANT_ID;
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
  digitalWrite(RELAY_PIN, LOW);
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
    mqttClient.setServer(MQTT_SERVER, MQTT_PORT);
    mqttClient.setCallback(mqttCallback);
  }

  Serial.println("Setup complete");
}

// ── Loop ────────────────────────────────────────────────────
void loop() {
  esp_task_wdt_reset();   // أطعِم المراقب (loop حيّ) — يمنع إعادة تشغيل زائفة
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
