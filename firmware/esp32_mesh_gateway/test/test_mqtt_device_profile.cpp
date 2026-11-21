#include "../mqtt_device_profile.h"
#include <cassert>
#include <iostream>
#include <string>

int main() {
  using namespace mqttprofile;
  assert(segment("node-1_2.3"));
  for (const char* invalid : {"", "+", "#", "a/b", " x", "x\ny", "x|y", ".x"}) {
    assert(!segment(invalid));
  }
  assert(!segment(nullptr));
  assert(!segment(std::string(64, 'x').c_str()));
  const char* ca = "-----BEGIN CERTIFICATE-----\nfixture\n-----END CERTIFICATE-----";
  assert(ready("tenant", "field", "node", "broker", "password", ca));
  assert(!ready("tenant", "field", "node", "broker", "", ca));
  assert(!ready("tenant", "field", "node", "broker", "password", ""));
  assert(!ready("tenant", "field", "+", "broker", "password", ca));
  assert(local_source("t", "f", "n", "t", "f", "n"));
  assert(!local_source("t", "f", "peer", "t", "f", "n"));
  assert(!local_source("other", "f", "n", "t", "f", "n"));
  assert(!local_source("t", "other", "n", "t", "f", "n"));
  assert(!local_source(nullptr, "f", "n", "t", "f", "n"));
  assert(!local_source("t", "f", "n", nullptr, "f", "n"));
  assert(calibrated_soil(3500, 800));
  assert(calibrated_soil(800, 3500));
  assert(!calibrated_soil(-1, -1));
  assert(!calibrated_soil(100, 100));
  assert(!calibrated_soil(4096, 100));
  int adc = -1;
  assert(adc_value("4095", &adc) && adc == 4095);
  assert(adc_value("0", &adc) && adc == 0);
  for (const char* invalid : {"", "-1", "4096", "0x99", "5.5", "bad", "1234567890"}) {
    assert(!adc_value(invalid, &adc));
  }
  std::cout << "mqtt_device_profile: all checks passed\n";
}
