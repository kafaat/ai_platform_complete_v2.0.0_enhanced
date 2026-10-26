// SAHOOL — features/scouting/data/scouting_api.dart
// نقاط ميزة scouting. أُنشئ فارغاً ليملأه وكيل الميزة وحده. يملكه وكيل الميزة.
import 'package:sahool_app/core/network/api_client.dart';

class ScoutingApi {
  ScoutingApi([ApiClient? client]) : _client = client ?? ApiClient.instance;
  static final ScoutingApi instance = ScoutingApi();
  // ignore: unused_field
  final ApiClient _client;
}
