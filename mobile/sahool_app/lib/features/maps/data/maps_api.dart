// SAHOOL — features/maps/data/maps_api.dart
// نقاط ميزة maps. أُنشئ فارغاً ليملأه وكيل الميزة وحده. يملكه وكيل الميزة.
import 'package:sahool_app/core/network/api_client.dart';

class MapsApi {
  MapsApi([ApiClient? client]) : _client = client ?? ApiClient.instance;
  static final MapsApi instance = MapsApi();
  // ignore: unused_field
  final ApiClient _client;
}
