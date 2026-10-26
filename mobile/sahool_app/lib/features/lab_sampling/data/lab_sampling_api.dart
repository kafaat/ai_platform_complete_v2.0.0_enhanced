// SAHOOL — features/lab_sampling/data/lab_sampling_api.dart
// نقاط ميزة lab_sampling. أُنشئ فارغاً ليملأه وكيل الميزة وحده. يملكه وكيل الميزة.
import 'package:sahool_app/core/network/api_client.dart';

class LabSamplingApi {
  LabSamplingApi([ApiClient? client]) : _client = client ?? ApiClient.instance;
  static final LabSamplingApi instance = LabSamplingApi();
  // ignore: unused_field
  final ApiClient _client;
}
