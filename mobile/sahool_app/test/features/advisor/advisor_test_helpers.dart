// أدوات مشتركة لاختبارات المستشار: عميل HTTP مزيّف (ApiClient الحقيقيّ بمحوّل
// يسجّل الطلبات)، واستجابة /v1/chat بالشكل الذي يُرجعه ai_evidence_runtime.py.
import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:sahool_app/core/network/api_exception.dart';
import 'package:sahool_app/core/theme/app_theme.dart';
import 'package:sahool_app/features/advisor/data/advisor_api.dart';

import '../../core/fake_http.dart';

AdvisorApi fakeAdvisorApi(FakeAdapter adapter) => AdvisorApi(
  testClient(
    adapter,
    MemoryTokenStore(accessToken: fakeJwt(const Duration(hours: 1))),
  ),
);

/// استجابة /v1/chat كما يبنيها build_evidence_response (المفاتيح الحقيقيّة).
Map<String, dynamic> chatReply({
  String answer = 'المصادر المتاحة: RAG، حالة الحقل.',
  String generationStatus = 'not_attempted',
  double confidence = 0.42,
  bool calibrated = false,
  String? fieldId,
  Map<String, dynamic>? validation,
}) => {
  'status': 'ok',
  'mode': 'evidence_only',
  'generation_status': generationStatus,
  'endpoint_mode': 'chat',
  'answer_ar': answer,
  'message': answer,
  'field_id': fieldId,
  'evidence_ids': ['rag:1'],
  'evidence_sources': [
    {'key': 'rag', 'label_ar': 'RAG', 'available': true, 'count': 3},
    {
      'key': 'knowledge_graph',
      'label_ar': 'Knowledge Graph',
      'available': false,
      'count': 0,
    },
  ],
  'confidence': confidence,
  'confidence_basis': 'owner_reported_evidence_quality',
  'confidence_calibrated': calibrated,
  'advisory_validation': validation,
  'pending_approvals': <Object>[],
  'advisory': {
    'schema': 'sahool.advisory_envelope/1',
    'limitations': ['generation_disabled_evidence_only'],
    'requires_human_review': true,
  },
};

/// خطأ تحقّق FastAPI كما يُرجعه الخادم حين يغيب `question`.
Map<String, dynamic> fastApi422() => {
  'detail': [
    {
      'type': 'missing',
      'loc': ['body', 'question'],
      'msg': 'Field required',
    },
  ],
};

Widget hostApp(Widget child) => MaterialApp(
  theme: AppTheme.light,
  locale: const Locale('ar'),
  supportedLocales: const [Locale('ar'), Locale('en')],
  localizationsDelegates: GlobalMaterialLocalizations.delegates,
  home: child,
);

Map<String, dynamic> jsonBody(Object? data) =>
    (data as Map).map((k, v) => MapEntry(k.toString(), v));

/// ApiException كما يبنيه ApiClient من استجابة خطأ حقيقيّة.
ApiException apiError(int status, Object? body) {
  final o = RequestOptions(path: '/x');
  return ApiException.fromDio(
    DioException(
      requestOptions: o,
      response: Response(requestOptions: o, statusCode: status, data: body),
      type: DioExceptionType.badResponse,
    ),
  );
}
