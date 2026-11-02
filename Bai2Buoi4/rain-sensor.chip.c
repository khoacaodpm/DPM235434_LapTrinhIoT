#include "wokwi-api.h"
#include <stdlib.h>

typedef struct {
  pin_t pin_ao;
  pin_t pin_do;
  uint32_t rain_attr;
  uint32_t threshold_attr;
} chip_state_t;

static void chip_timer_event(void *user_data);

void chip_init(void) {
  chip_state_t *chip = malloc(sizeof(chip_state_t));
  chip->pin_ao = pin_init("AO", ANALOG);
  chip->pin_do = pin_init("DO", OUTPUT);

  // Vẫn khởi tạo chân để sơ đồ không báo lỗi, nhưng không dùng để check logic ảo
  pin_init("VCC", INPUT);
  pin_init("GND", INPUT);

  chip->rain_attr = attr_init("rain", 0);
  chip->threshold_attr = attr_init("threshold", 50);

  const timer_config_t timer_config = {
    .callback = chip_timer_event,
    .user_data = chip,
  };
  timer_init(&timer_config);
  timer_start(timer_init(&timer_config), 100, true);
}

void chip_timer_event(void *user_data) {
  chip_state_t *chip = (chip_state_t*)user_data;
  uint32_t rain = attr_read(chip->rain_attr);
  uint32_t threshold = attr_read(chip->threshold_attr);

  float percent = ((float)rain / 1023.0) * 100.0;
  pin_dac_write(chip->pin_ao, 5.0 * (percent / 100.0));

  // Logic cảm biến chuẩn: Có mưa (vượt ngưỡng) -> LOW, Nắng/Tạnh -> HIGH
  if (percent > threshold) {
      pin_write(chip->pin_do, HIGH);
  } else {
      pin_write(chip->pin_do, LOW);
  }
}