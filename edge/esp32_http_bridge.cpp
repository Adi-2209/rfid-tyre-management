#include <Arduino.h>
#include <WiFi.h>
#include <HTTPClient.h>
#include <Preferences.h>
#include <esp_system.h>
#include <time.h>
#include <stdio.h>
#include <string.h>

// Configure these for your network and the station where this ESP32 is installed.
const char *WIFI_SSID = "YOUR_WIFI_NAME";
const char *WIFI_PASSWORD = "YOUR_WIFI_PASSWORD";
const char *API_URL = "http://192.168.1.10:8000/observations";
const char *HEARTBEAT_URL = "http://192.168.1.10:8000/readers/heartbeat";
const char *DEVICE_API_KEY = "SET_THIS_TO_RFID_DEVICE_API_KEY";
const char *READER_ID = "ESP32-BUILD-01";
const char *STATION_ID = "TYRE_BUILDING";

// UART pins vary by ESP32 board. Connect the reader TX to ESP32 RX and vice versa.
constexpr int READER_RX_PIN = 16;
constexpr int READER_TX_PIN = 17;
constexpr uint32_t READER_BAUD = 115200;
constexpr size_t QUEUE_CAPACITY = 20;
constexpr unsigned long HEARTBEAT_INTERVAL_MS = 15000;
constexpr unsigned long WIFI_RETRY_MS = 10000;
constexpr unsigned long API_RETRY_MS = 3000;

HardwareSerial ReaderSerial(2);
Preferences queueStorage;
bool queueStorageReady = false;

struct PendingObservation {
  char epc[64];
  char eventId[40];
  float rssiDbm;
  int antennaId;
  char timestamp[32];
};

PendingObservation pending[QUEUE_CAPACITY];
size_t queueHead = 0;
size_t queueCount = 0;
unsigned long lastWifiAttempt = 0;
unsigned long retryAfter = 0;
unsigned long lastHeartbeat = 0;
bool wifiAttempted = false;
bool hadWiFiConnection = false;

bool isValidEpc(const char *epc) {
  size_t length = strlen(epc);
  if (length == 0 || length % 2 != 0) return false;
  for (size_t i = 0; i < length; i++) {
    char c = epc[i];
    if (!((c >= '0' && c <= '9') || (c >= 'A' && c <= 'F') || (c >= 'a' && c <= 'f'))) {
      return false;
    }
  }
  return true;
}

void makeSlotKey(size_t slot, char *key, size_t keySize) {
  snprintf(key, keySize, "q%02u", static_cast<unsigned int>(slot));
}

uint16_t packQueueMeta(size_t head, size_t count) {
  return static_cast<uint16_t>((count << 8) | head);
}

bool saveQueueMeta(size_t head, size_t count) {
  if (!queueStorageReady) return true;
  return queueStorage.putUShort("meta", packQueueMeta(head, count)) == sizeof(uint16_t);
}

void clearPersistentQueue() {
  if (!queueStorageReady) return;
  for (size_t slot = 0; slot < QUEUE_CAPACITY; slot++) {
    char key[8];
    makeSlotKey(slot, key, sizeof(key));
    queueStorage.remove(key);
  }
  queueStorage.putUShort("meta", packQueueMeta(0, 0));
}

void restoreQueue() {
  if (!queueStorageReady) return;
  uint16_t meta = queueStorage.getUShort("meta", 0);
  size_t savedHead = meta & 0xFF;
  size_t savedCount = (meta >> 8) & 0xFF;
  if (savedHead >= QUEUE_CAPACITY || savedCount > QUEUE_CAPACITY) {
    Serial.println("Invalid saved queue metadata; clearing queued observations");
    clearPersistentQueue();
    return;
  }

  for (size_t i = 0; i < savedCount; i++) {
    size_t slot = (savedHead + i) % QUEUE_CAPACITY;
    char key[8];
    makeSlotKey(slot, key, sizeof(key));
    if (queueStorage.getBytesLength(key) != sizeof(PendingObservation) ||
        queueStorage.getBytes(key, &pending[slot], sizeof(PendingObservation)) != sizeof(PendingObservation) ||
        memchr(pending[slot].epc, '\0', sizeof(pending[slot].epc)) == nullptr ||
        memchr(pending[slot].eventId, '\0', sizeof(pending[slot].eventId)) == nullptr ||
        memchr(pending[slot].timestamp, '\0', sizeof(pending[slot].timestamp)) == nullptr ||
        !isValidEpc(pending[slot].epc) || pending[slot].eventId[0] == '\0' ||
        pending[slot].antennaId < 1) {
      Serial.println("Invalid saved observation; clearing queued observations");
      clearPersistentQueue();
      return;
    }
  }

  queueHead = savedHead;
  queueCount = savedCount;
  if (queueCount) {
    Serial.printf("Restored %u queued observation(s) from flash\n",
                  static_cast<unsigned int>(queueCount));
  }
}

void maintainWiFi() {
  if (WiFi.status() == WL_CONNECTED) {
    if (!hadWiFiConnection) {
      Serial.print("Wi-Fi connected; ESP32 address: ");
      Serial.println(WiFi.localIP());
      hadWiFiConnection = true;
      retryAfter = 0;
    }
    return;
  }

  hadWiFiConnection = false;
  unsigned long now = millis();
  if (!wifiAttempted || now - lastWifiAttempt >= WIFI_RETRY_MS) {
    Serial.println("Starting Wi-Fi connection attempt");
    WiFi.mode(WIFI_STA);
    WiFi.setAutoReconnect(true);
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
    lastWifiAttempt = now;
    wifiAttempted = true;
  }
}

bool getUtcTimestamp(char *buffer, size_t bufferSize) {
  time_t now = time(nullptr);
  if (now < 1700000000) return false;  // NTP time has not been set yet.
  struct tm utc;
  gmtime_r(&now, &utc);
  return strftime(buffer, bufferSize, "%Y-%m-%dT%H:%M:%SZ", &utc) > 0;
}

bool storePending(const PendingObservation &item) {
  if (queueCount == QUEUE_CAPACITY) {
    Serial.println("Observation queue full; newest read was dropped");
    return false;
  }

  size_t tail = (queueHead + queueCount) % QUEUE_CAPACITY;
  if (queueStorageReady) {
    char key[8];
    makeSlotKey(tail, key, sizeof(key));
    if (queueStorage.putBytes(key, &item, sizeof(item)) != sizeof(item)) {
      Serial.println("Could not persist observation; read was dropped");
      return false;
    }
  }
  if (!saveQueueMeta(queueHead, queueCount + 1)) {
    if (queueStorageReady) {
      char key[8];
      makeSlotKey(tail, key, sizeof(key));
      queueStorage.remove(key);
    }
    Serial.println("Could not persist queue index; read was dropped");
    return false;
  }

  pending[tail] = item;
  queueCount++;
  Serial.printf("Queued EPC %s (%u/%u)\n", item.epc,
                static_cast<unsigned int>(queueCount),
                static_cast<unsigned int>(QUEUE_CAPACITY));
  return true;
}

int postObservation(PendingObservation &item) {
  if (WiFi.status() != WL_CONNECTED) return -1;
  if (item.timestamp[0] == '\0' && !getUtcTimestamp(item.timestamp, sizeof(item.timestamp))) {
    Serial.println("Waiting for network time; queued observation retained");
    return -1;
  }

  // EPC is hex-validated above; the other string fields are compile-time constants.
  String body = "{\"epc\":\"";
  body += item.epc;
  body += "\",\"event_id\":\"";
  body += item.eventId;
  body += "\",\"reader_id\":\"";
  body += READER_ID;
  body += "\",\"antenna_id\":";
  body += String(item.antennaId);
  body += ",\"station_id\":\"";
  body += STATION_ID;
  body += "\",\"rssi_dbm\":";
  body += String(item.rssiDbm, 1);
  body += ",\"timestamp\":\"";
  body += item.timestamp;
  body += "\"}";

  WiFiClient client;
  HTTPClient http;
  http.setTimeout(2500);
  if (!http.begin(client, API_URL)) {
    Serial.println("Could not start HTTP request");
    return -1;
  }
  http.addHeader("Content-Type", "application/json");
  http.addHeader("X-Reader-Key", DEVICE_API_KEY);
  int status = http.POST(body);
  String response = http.getString();
  http.end();

  Serial.printf("API status: %d\n", status);
  if (response.length()) Serial.println(response);
  return status;
}

int postHeartbeat() {
  if (WiFi.status() != WL_CONNECTED) return -1;

  String body = "{\"reader_id\":\"";
  body += READER_ID;
  body += "\",\"station_id\":\"";
  body += STATION_ID;
  body += "\"}";

  WiFiClient client;
  HTTPClient http;
  http.setTimeout(2500);
  if (!http.begin(client, HEARTBEAT_URL)) {
    Serial.println("Could not start heartbeat HTTP request");
    return -1;
  }
  http.addHeader("Content-Type", "application/json");
  
  int status = http.POST(body);
  String response = http.getString();
  http.end();

  if (status < 200 || status >= 300) {
    Serial.printf("Heartbeat API returned error status: %d\n", status);
  } else {
    Serial.println("Heartbeat sent successfully");
  }

  Serial.printf("Heartbeat API status: %d\n", status);
  if (response.length()) Serial.println(response);
  return status;
}

bool enqueueObservation(const char *epc, float rssiDbm, int antennaId) {
  if (!isValidEpc(epc) || antennaId < 1) {
    Serial.println("Rejected invalid EPC or antenna ID");
    return false;
  }

  PendingObservation item = {};
  strlcpy(item.epc, epc, sizeof(item.epc));
  String mac = WiFi.macAddress();
  mac.replace(":", "");
  unsigned long nonceHigh = static_cast<unsigned long>(esp_random());
  unsigned long nonceLow = static_cast<unsigned long>(esp_random());
  snprintf(item.eventId, sizeof(item.eventId), "%s-%08lX%08lX",
           mac.c_str(), nonceHigh, nonceLow);
  item.rssiDbm = rssiDbm;
  item.antennaId = antennaId;
  if (!getUtcTimestamp(item.timestamp, sizeof(item.timestamp))) item.timestamp[0] = '\0';

  // Avoid flash writes during normal operation. Persist only when sending fails
  // or there is already an older event waiting in the queue.
  if (queueCount == 0 && WiFi.status() == WL_CONNECTED &&
      static_cast<int32_t>(millis() - retryAfter) >= 0) {
    int status = postObservation(item);
    if (status >= 200 && status < 300) return true;
    if (status >= 400 && status < 500 && status != 408 && status != 429) {
      Serial.println("API permanently rejected observation; it was not queued");
      return false;
    }
    retryAfter = millis() + API_RETRY_MS;
  }

  return storePending(item);
}

bool removeQueueHead() {
  if (queueCount == 0) return true;
  size_t oldHead = queueHead;
  size_t nextHead = (queueHead + 1) % QUEUE_CAPACITY;
  size_t nextCount = queueCount - 1;

  // Save the new index before deleting the old slot. A power loss can leave an
  // orphaned slot, but it will not make the queue point at a deleted event.
  if (!saveQueueMeta(nextHead, nextCount)) return false;
  queueHead = nextHead;
  queueCount = nextCount;
  if (queueStorageReady) {
    char key[8];
    makeSlotKey(oldHead, key, sizeof(key));
    queueStorage.remove(key);
  }
  return true;
}

void flushOneObservation() {
  if (queueCount == 0 || WiFi.status() != WL_CONNECTED) return;
  if (static_cast<int32_t>(millis() - retryAfter) < 0) return;

  PendingObservation &item = pending[queueHead];
  int status = postObservation(item);
  if (status >= 200 && status < 300) {
    Serial.printf("Sent queued EPC %s\n", item.epc);
    if (!removeQueueHead()) {
      Serial.println("Could not update persistent queue index; delivery may repeat after restart");
    }
    retryAfter = millis();
    return;
  }

  if (status == 408 || status == 429 || status < 0 || status >= 500) {
    Serial.println("Temporary send failure; observation remains queued for retry");
    retryAfter = millis() + API_RETRY_MS;
  } else {
    Serial.println("API permanently rejected queued observation; removing it");
    if (!removeQueueHead()) {
      Serial.println("Could not update persistent queue index; rejected item remains queued");
    }
    retryAfter = millis();
  }
}

// Expected UART input from the RFID module: EPC,RSSI_DBM,ANTENNA_ID\n
bool parseReaderLine(const String &line, char *epc, size_t epcSize, float &rssiDbm, int &antennaId) {
  char parsedEpc[64];
  if (sscanf(line.c_str(), "%63[^,],%f,%d", parsedEpc, &rssiDbm, &antennaId) != 3) {
    return false;
  }
  if (strlen(parsedEpc) + 1 > epcSize || !isValidEpc(parsedEpc)) return false;
  strlcpy(epc, parsedEpc, epcSize);
  return antennaId > 0;
}

void setup() {
  Serial.begin(115200);
  ReaderSerial.begin(READER_BAUD, SERIAL_8N1, READER_RX_PIN, READER_TX_PIN);
  ReaderSerial.setTimeout(100);
  configTime(0, 0, "pool.ntp.org", "time.nist.gov");

  queueStorageReady = queueStorage.begin("rfidqueue", false);
  if (queueStorageReady) {
    restoreQueue();
  } else {
    Serial.println("Could not open persistent queue storage; using RAM only");
  }

  maintainWiFi();
  Serial.println("Listening for EPC,RSSI_DBM,ANTENNA_ID lines on UART2");
}

void loop() {
  maintainWiFi();

  unsigned long now = millis();
  if (WiFi.status() == WL_CONNECTED && now - lastHeartbeat >= HEARTBEAT_INTERVAL_MS) {
    int status =postHeartbeat();
    lastHeartbeat = millis() + (status >= 200 && status < 300 ? HEARTBEAT_INTERVAL_MS : API_RETRY_MS);
  }

  if (ReaderSerial.available()) {
    String line = ReaderSerial.readStringUntil('\n');
    line.trim();
    char epc[64];
    float rssiDbm;
    int antennaId;
    if (!parseReaderLine(line, epc, sizeof(epc), rssiDbm, antennaId)) {
      Serial.print("Ignored unreadable reader line: ");
      Serial.println(line);
    } else {
      enqueueObservation(epc, rssiDbm, antennaId);
    }
  }

  flushOneObservation();
  delay(5);
}
