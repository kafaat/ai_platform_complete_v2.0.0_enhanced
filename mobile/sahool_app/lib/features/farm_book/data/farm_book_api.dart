// SAHOOL — features/farm_book/data/farm_book_api.dart
// نقاط ميزة farm_book. أُنشئ فارغاً ليملأه وكيل الميزة وحده. يملكه وكيل الميزة.
import 'package:sahool_app/core/network/api_client.dart';

class FarmBookApi {
  FarmBookApi([ApiClient? client]) : _client = client ?? ApiClient.instance;
  static final FarmBookApi instance = FarmBookApi();
  // ignore: unused_field
  final ApiClient _client;
}
