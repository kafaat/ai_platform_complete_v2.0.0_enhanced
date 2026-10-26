// SAHOOL — features/weather/weather_paths.dart
// المسارات القانونيّة لميزة الطقس. عامّة لميزات أخرى (لوحة المعلومات، الحقول).
abstract final class WeatherPaths {
  /// طقس الحقول: بلا field_id يعرض اختيار الحقل.
  static const weather = '/weather';

  /// `/weather?field_id=<id>`
  static String field(String fieldId) =>
      '$weather?field_id=${Uri.encodeQueryComponent(fieldId)}';
}
