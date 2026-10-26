// SAHOOL — features/activities/data/activities_api.dart
// نقاط ميزة activities. أُنشئ فارغاً ليملأه وكيل الميزة وحده. يملكه وكيل الميزة.
import 'package:sahool_app/core/network/api_client.dart';

class ActivitiesApi {
  ActivitiesApi([ApiClient? client]) : _client = client ?? ApiClient.instance;
  static final ActivitiesApi instance = ActivitiesApi();
  // ignore: unused_field
  final ApiClient _client;
}
