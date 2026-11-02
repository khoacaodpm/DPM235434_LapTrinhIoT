#include <WiFi.h>
#include <PubSubClient.h>
#include <LiquidCrystal_I2C.h>

// 1. Đã sửa lỗi khai báo biến con trỏ char*
const char* ssid = "Wokwi-GUEST";
const char* password = "";
const char* mqtt_server = "broker.hivemq.com";
#define LED_PIN 2

WiFiClient espClient;
PubSubClient client(espClient);
LiquidCrystal_I2C lcd(0x27, 16, 2);

// Khai báo các biến lưu trữ thời gian cho hàm millis()
unsigned long lastReconnectTime = 0;
unsigned long lastWifiPrintTime = 0;

// 2. Đã sửa lỗi tham số truyền vào: char* topic và byte* payload
void callback(char* topic, byte* payload, unsigned int length) {
  String msg;
  for (int i = 0; i < length; i++) msg += (char)payload[i];
  float temp = msg.toFloat();
  
  Serial.print("Đã nhận nhiệt độ từ MQTT: ");
  Serial.println(temp);

  lcd.clear();
  lcd.setCursor(0, 0);
  lcd.print("Nhiet do: ");
  lcd.print(temp);
  lcd.print(" C");

  // Cảnh báo nếu lớn hơn 35 độ
  if (temp > 35.0) {
    digitalWrite(LED_PIN, HIGH);
    lcd.setCursor(0, 1);
    lcd.print("Canh bao nong!");
  } else {
    digitalWrite(LED_PIN, LOW);
    lcd.setCursor(0, 1);
    lcd.print("Binh thuong");
  }
}

void setup() {
  Serial.begin(115200); 
  pinMode(LED_PIN, OUTPUT);
  lcd.init();
  lcd.backlight();
  
  Serial.print("Đang kết nối WiFi");
  WiFi.begin(ssid, password);
  
  // Thay thế delay(500) khi chờ kết nối WiFi
  while (WiFi.status() != WL_CONNECTED) { 
    if (millis() - lastWifiPrintTime >= 500) {
      Serial.print("."); 
      lastWifiPrintTime = millis();
    }
  }
  Serial.println("\nĐã kết nối WiFi!");
  
  client.setServer(mqtt_server, 1883);
  client.setCallback(callback);
}

void loop() {
  // Thay thế delay(5000) khi thử kết nối lại MQTT
  if (!client.connected()) {
    if (millis() - lastReconnectTime >= 5000) {
      lastReconnectTime = millis();
      Serial.print("Đang kết nối MQTT Broker...");
      
      if (client.connect("WokwiSubClient456")) {
        Serial.println("Thành công!");
        client.subscribe("wokwi/iot/temp_status"); 
      } else { 
        Serial.println("Thất bại, thử lại sau 5s");
      }
    }
  } else {
    client.loop(); // Chỉ duy trì vòng lặp MQTT khi đã kết nối thành công
  }
}