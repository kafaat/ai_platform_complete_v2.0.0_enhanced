// SAHOOL — features/alerts/data/alerts_api.dart
// نقاط ميزة alerts. أُنشئ فارغاً ليملأه وكيل الميزة وحده. يملكه وكيل الميزة.
import 'package:sahool_app/core/network/api_client.dart';

class AlertsApi {
  AlertsApi([ApiClient? client]) : _client = client ?? ApiClient.instance;
  static final AlertsApi instance = AlertsApi();
  // ignore: unused_field
  final ApiClient _client;
}
