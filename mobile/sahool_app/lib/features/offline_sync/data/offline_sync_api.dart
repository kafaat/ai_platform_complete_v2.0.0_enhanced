// SAHOOL — features/offline_sync/data/offline_sync_api.dart
// نقاط ميزة offline_sync. أُنشئ فارغاً ليملأه وكيل الميزة وحده. يملكه وكيل الميزة.
import 'package:sahool_app/core/network/api_client.dart';

class OfflineSyncApi {
  OfflineSyncApi([ApiClient? client]) : _client = client ?? ApiClient.instance;
  static final OfflineSyncApi instance = OfflineSyncApi();
  // ignore: unused_field
  final ApiClient _client;
}
