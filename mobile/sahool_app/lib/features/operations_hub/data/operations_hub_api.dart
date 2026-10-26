// SAHOOL — features/operations_hub/data/operations_hub_api.dart
// نقاط مركز العمليّات. لا نقاط لهذه الميزة بعد: الشاشة تجمع وحدات ميزات أخرى.
// الملفّ موجود ليضيف مالك الميزة نقاطه هنا لا في ملفّ مشترك.
import 'package:sahool_app/core/network/api_client.dart';

class OperationsHubApi {
  OperationsHubApi([ApiClient? client]) : client = client ?? ApiClient.instance;
  static final OperationsHubApi instance = OperationsHubApi();
  final ApiClient client;
}
