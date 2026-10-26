// SAHOOL — features/activities/data/activities_api.dart
// نقاط الأنشطة الزراعيّة. يملكه وكيل ميزة الأنشطة.
//
//   POST /api/v1/fields/{id}/activities   (fields.py:2905) — field:edit، 201،
//        Idempotency-Key (UUID) يمنع تكرار التسجيل عند إعادة الموبايل.
//   GET  /api/v1/fields/{id}/activities   (fields.py:3043) — الأحدث أوّلاً، limit/offset
//        (الافتراضيّ أحدث 100).
//   GET  /api/v1/fields/{id}/unified-timeline (field_workspace_timeline.py:31) —
//        أحداث حقيقيّة فقط من جدول events؛ degraded=true عند تعذّر القاعدة.
// لا نقطة «أنشطة المزرعة كلّها»: الموجز يجمع أنشطة كلّ حقل (انظر FarmFeedCubit).
import 'package:sahool_app/core/network/api_client.dart';
import 'package:sahool_app/core/network/idempotency.dart';
import 'package:sahool_app/core/network/response_shape.dart';

import 'field_activity.dart';

class ActivitiesApi {
  ActivitiesApi([ApiClient? client]) : _client = client ?? ApiClient.instance;
  static final ActivitiesApi instance = ActivitiesApi();
  final ApiClient _client;

  static String activitiesPath(String fieldId) =>
      '/api/v1/fields/${Uri.encodeComponent(fieldId)}/activities';

  /// يسجّل نشاطاً بجسم ActivityCreateRequest ويُرجِع ما خزّنه الخادم.
  Future<FieldActivity> createActivity(
    String fieldId,
    Map<String, dynamic> body, {
    IdempotencyKey? idempotencyKey,
  }) async => FieldActivity.fromJson(
    asJsonMap(
      await _client.post(
        activitiesPath(fieldId),
        data: body,
        idempotencyKey: idempotencyKey,
      ),
    ),
  );

  Future<List<FieldActivity>> listFieldActivities(
    String fieldId, {
    int? limit,
    int? offset,
  }) async {
    final rows = asJsonList(
      await _client.get(
        activitiesPath(fieldId),
        query: {'limit': ?limit, 'offset': ?offset},
      ),
    );
    return rows.map(FieldActivity.fromJson).toList();
  }

  Future<FieldTimelineData> fetchUnifiedTimeline(
    String fieldId, {
    int limit = 200,
  }) async => FieldTimelineData.fromJson(
    asJsonMap(
      await _client.get(
        '/api/v1/fields/${Uri.encodeComponent(fieldId)}/unified-timeline',
        query: {'limit': limit, 'newest_first': true},
      ),
    ),
  );
}
