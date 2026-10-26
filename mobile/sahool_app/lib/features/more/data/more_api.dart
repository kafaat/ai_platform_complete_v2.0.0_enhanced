// SAHOOL — features/more/data/more_api.dart
// نقاط «المزيد». لا نقاط لهذه الميزة بعد: الشاشة تجمع وحدات ميزات أخرى.
// الملفّ موجود ليضيف مالك الميزة نقاطه هنا لا في ملفّ مشترك.
import 'package:sahool_app/core/network/api_client.dart';

class MoreApi {
  MoreApi([ApiClient? client]) : client = client ?? ApiClient.instance;
  static final MoreApi instance = MoreApi();
  final ApiClient client;
}
