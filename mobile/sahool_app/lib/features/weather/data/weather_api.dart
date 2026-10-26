// SAHOOL — features/weather/data/weather_api.dart
// نقاط ميزة weather. أُنشئ فارغاً ليملأه وكيل الميزة وحده. يملكه وكيل الميزة.
import 'package:sahool_app/core/network/api_client.dart';

class WeatherApi {
  WeatherApi([ApiClient? client]) : _client = client ?? ApiClient.instance;
  static final WeatherApi instance = WeatherApi();
  // ignore: unused_field
  final ApiClient _client;
}
