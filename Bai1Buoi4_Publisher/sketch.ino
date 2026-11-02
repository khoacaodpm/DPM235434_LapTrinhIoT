#include <WiFi.h>
#include <PubSubClient.h>
#include "DHT.h"

const char* ssid = "Wokwi-GUEST";
const char* password = "";
const char* mqtt_server = "broker.hivemq.com";

WiFiClient espClient;
PubSubClient client(espClient);
DHT dht(15, DHT22); // Chân GPIO 15

// Các biến lưu trữ thời gian cho hàm millis()
unsigned long lastReadTime = 0;
unsigned long lastReconnectTime = 0;
unsigned long lastWifiPrintTime = 0;

void setup() {
  Serial.begin(115200);
  dht.begin();
  WiFi.begin(ssid, password);
  
  Serial.print("Đang kết nối WiFi");
  while (WiFi.status() != WL_CONNECTED) { 
    // Thay thế delay(500) trong setup
    if (millis() - lastWifiPrintTime >= 500) {
      Serial.print("."); 
      lastWifiPrintTime = millis();
    }
  }
  Serial.println("\nWiFi đã kết nối!");
  
  client.setServer(mqtt_server, 1883);
}

void loop() {
  // Kiểm tra và kết nối lại MQTT Broker mà không chặn chương trình
  if (!client.connected()) {
    if (millis() - lastReconnectTime >= 5000) { // Thay thế delay(5000)
      lastReconnectTime = millis();
      if (client.connect("WokwiPubClient123")) {
        Serial.println("Đã kết nối MQTT Broker");
      }
    }
  } else {
    client.loop();
    
    // Gửi dữ liệu mỗi 3 giây mà không dùng delay(3000)
    if (millis() - lastReadTime >= 3000) {
      lastReadTime = millis();
      
      float t = dht.readTemperature();
      if (!isnan(t)) {
        char tempString[8];
        dtostrf(t, 1, 2, tempString);
        client.publish("wokwi/iot/temp_status", tempString);
        Serial.println("Đã gửi nhiệt độ: " + String(tempString));
      }
    }
  }
}