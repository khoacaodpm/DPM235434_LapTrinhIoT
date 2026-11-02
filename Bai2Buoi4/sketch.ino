#include <WiFi.h>
#include <PubSubClient.h>
#include <ESP32Servo.h>

// Đã sửa lại lỗi khai báo con trỏ chuỗi
const char* ssid = "Wokwi-GUEST";
const char* password = "";
const char* mqtt_server = "broker.hivemq.com";

#define RAIN_PIN 14
#define SERVO_PIN 12

WiFiClient espClient;
PubSubClient client(espClient);
Servo canopyServo;

bool isCanopyExtended = false; // true = đang mở (che mưa), false = đang đóng (nắng)

void setup() {
  Serial.begin(115200);

  ESP32PWM::allocateTimer(0);
  ESP32PWM::allocateTimer(1);
  ESP32PWM::allocateTimer(2);
  ESP32PWM::allocateTimer(3);

  pinMode(RAIN_PIN, INPUT_PULLUP);

  canopyServo.setPeriodHertz(50);
  canopyServo.attach(SERVO_PIN, 500, 2400);
  canopyServo.write(0); // Khởi động ở vị trí đóng mái che (0 độ)

  Serial.print("Đang kết nối WiFi");
  WiFi.begin(ssid, password);
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println("\nĐã kết nối WiFi!");

  client.setServer(mqtt_server, 1883);
}

void loop() {
  // Xử lý kết nối MQTT bằng delay
  if (!client.connected()) {
    Serial.print("Đang kết nối MQTT Broker...");
    if (client.connect("WokwiCanopyClient789")) {
      Serial.println(" Thành công!");
    } else {
      Serial.println(" Thất bại, thử lại sau 2 giây...");
      delay(2000); 
      return; // Bỏ qua phần dưới, quay lại đầu vòng lặp
    }
  } 
  client.loop();

  // Đọc cảm biến
  int rainStatus = digitalRead(RAIN_PIN);
  Serial.print("Trạng thái DO: ");
  Serial.print(rainStatus);

  // Mưa = LOW (0), Nắng = HIGH (1)
  bool isRaining = (rainStatus == LOW);

  if (isRaining) {
    Serial.println(" -> Có mưa!");
    if (!isCanopyExtended) {
      Serial.println("Kéo mái che ra (Servo quay 90 độ)...");
      canopyServo.write(90);
      isCanopyExtended = true;
      if (client.connected()) client.publish("wokwi/iot/canopy_status", "Troi mua - Da keo mai che");
    }
  } else {
    Serial.println(" -> Trời nắng!");
    if (isCanopyExtended) {
      Serial.println("Thu mái che vào (Servo quay 0 độ)...");
      canopyServo.write(0);
      isCanopyExtended = false;
      if (client.connected()) client.publish("wokwi/iot/canopy_status", "Troi nang - Da thu mai che");
    }
  }

  delay(1000); // Dùng delay 1 giây thay cho millis()
}