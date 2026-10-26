// SAHOOL — features/advisor/data/advisor_api.dart
// المستشار الزراعيّ الذكيّ وكشف الآفات بالصورة. يملكه وكيل ميزة المستشار.
//
// ملاحظة مسار مُثبَّت: نداء المحادثة (/api/ai-agronomist/chat) يبقى نصّاً في
// lib/services/api_service.dart لأنّ tests/mobile/test_phase11_mobile_offline_sync_runtime.py
// يقرأ ذلك الملفّ بالمسار. [askAgent] هنا يفوّض إليه؛ وكيل المستشار هو المالك
// الوحيد لدالّة ApiService.askAgent (انظر ARCHITECTURE.md «المسارات المُثبَّتة»).
import 'dart:io';

import 'package:dio/dio.dart';
import 'package:sahool_app/core/network/api_client.dart';
import 'package:sahool_app/core/network/response_shape.dart';
import 'package:sahool_app/services/api_service.dart';

class AdvisorApi {
  AdvisorApi([ApiClient? client]) : _client = client ?? ApiClient.instance;
  static final AdvisorApi instance = AdvisorApi();
  final ApiClient _client;

  /// سؤال المستشار (POST /api/ai-agronomist/chat) — انظر ApiService.askAgent.
  Future<Map<String, dynamic>> askAgent(String query, {String? fieldId}) =>
      ApiService.instance.askAgent(query, fieldId: fieldId);

  /// H06: كشف الآفات بالصورة — رفع multipart إلى خدمة الاستدلال الحافيّة عبر
  /// البوّابة (/api/edge/ → v1/inference/pest-detect). يستخدم نفس Dio (توكن، إعادة
  /// محاولة، كشف انقطاع). صدق: يردّ استجابة الخادم كما هي (detections/alert_ar)
  /// أو يرمي خطأً صريحاً ليعرض الـUI حالة فشل واضحة — لا كشف مُلفَّق.
  Future<Map<String, dynamic>> analyzePestImage(
    File image, {
    String? fieldId,
    String crop = 'wheat',
  }) async {
    final fileName = image.path.split('/').last;
    final form = FormData.fromMap({
      'file': await MultipartFile.fromFile(image.path, filename: fileName),
      if (fieldId != null) 'field_id': fieldId,
      'crop': crop,
    });
    final r = await _client.send(
      'POST',
      '/api/edge/v1/inference/pest-detect',
      data: form,
      contentType: 'multipart/form-data',
      sendTimeout: const Duration(seconds: 120),
      receiveTimeout: const Duration(seconds: 120),
    );
    return asJsonMap(r);
  }
}
