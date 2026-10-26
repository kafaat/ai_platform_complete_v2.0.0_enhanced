// SAHOOL — features/crop_season/data/crop_season_api.dart
// نقاط ميزة crop_season. أُنشئ فارغاً ليملأه وكيل الميزة وحده. يملكه وكيل الميزة.
import 'package:sahool_app/core/network/api_client.dart';

class CropSeasonApi {
  CropSeasonApi([ApiClient? client]) : _client = client ?? ApiClient.instance;
  static final CropSeasonApi instance = CropSeasonApi();
  // ignore: unused_field
  final ApiClient _client;
}
