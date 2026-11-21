// Pure device-profile checks, usable by the sketch and host regression test.
#pragma once
#include <stddef.h>
#include <string.h>

namespace mqttprofile {

inline bool segment(const char* value) {
  if (value == nullptr || value[0] == '\0') return false;
  size_t n = 0;
  for (; value[n] != '\0'; ++n) {
    const char c = value[n];
    const bool alnum = (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') ||
                       (c >= '0' && c <= '9');
    if (n >= 63 || (!alnum && !(n > 0 && (c == '.' || c == '_' || c == '-')))) return false;
  }
  return true;
}

inline bool ready(const char* tenant, const char* field, const char* device,
                  const char* host, const char* password, const char* ca) {
  return segment(tenant) && segment(field) && segment(device) &&
         host != nullptr && host[0] != '\0' && password != nullptr && password[0] != '\0' &&
         ca != nullptr && strstr(ca, "-----BEGIN CERTIFICATE-----") != nullptr &&
         strstr(ca, "-----END CERTIFICATE-----") != nullptr;
}

inline bool local_source(const char* tenant, const char* field, const char* device,
                         const char* expected_tenant, const char* expected_field,
                         const char* expected_device) {
  return segment(tenant) && segment(field) && segment(device) &&
         segment(expected_tenant) && segment(expected_field) && segment(expected_device) &&
         strcmp(tenant, expected_tenant) == 0 && strcmp(field, expected_field) == 0 &&
         strcmp(device, expected_device) == 0;
}

inline bool calibrated_soil(int dry, int wet) {
  return dry >= 0 && dry <= 4095 && wet >= 0 && wet <= 4095 && dry != wet;
}

inline bool adc_value(const char* text, int* output) {
  if (text == nullptr || text[0] == '\0' || output == nullptr) return false;
  int value = 0;
  size_t n = 0;
  for (; text[n] != '\0'; ++n) {
    if (n >= 4 || text[n] < '0' || text[n] > '9') return false;
    value = value * 10 + (text[n] - '0');
  }
  if (value > 4095) return false;
  *output = value;
  return true;
}
}  // namespace mqttprofile
