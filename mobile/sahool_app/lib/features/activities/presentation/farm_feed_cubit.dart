// SAHOOL — features/activities/presentation/farm_feed_cubit.dart
// موجز أنشطة المزرعة: لا نقطة خادم تجمع الأنشطة كلّها، فيُقرأ أحدث [perField]
// نشاط لكلّ حقل (بتوازٍ محدود) ويُدمج. فشل بعض الحقول يُعلَن بعدده — لا يُعرَض
// الموجز الجزئيّ كأنّه كامل.
import 'package:flutter/foundation.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:sahool_app/core/network/api_exception.dart';
import 'package:sahool_app/features/activities/data/activities_api.dart';
import 'package:sahool_app/features/activities/data/activity_writer.dart';
import 'package:sahool_app/features/activities/data/field_activity.dart';
import 'package:sahool_app/features/fields/data/fields_api.dart';

@immutable
class FeedField {
  const FeedField(this.id, this.name);
  final String id;
  final String name;
}

enum FeedLoad { loading, loaded, failed }

@immutable
class FarmFeedState {
  const FarmFeedState({
    this.load = FeedLoad.loading,
    this.fields = const [],
    this.items = const [],
    this.failedFields = 0,
    this.error,
    this.typeFilter,
    this.refreshing = false,
  });

  final FeedLoad load;
  final List<FeedField> fields;

  /// أنشطة الخادم مدموجة، الأحدث أوّلاً.
  final List<FieldActivity> items;

  /// عدد الحقول التي تعذّرت قراءة أنشطتها.
  final int failedFields;
  final ApiException? error;
  final String? typeFilter;
  final bool refreshing;

  String fieldName(String id) {
    for (final f in fields) {
      if (f.id == id) return f.name;
    }
    return 'حقل $id';
  }

  FarmFeedState copyWith({
    FeedLoad? load,
    List<FeedField>? fields,
    List<FieldActivity>? items,
    int? failedFields,
    ApiException? error,
    bool clearError = false,
    String? typeFilter,
    bool clearType = false,
    bool? refreshing,
  }) => FarmFeedState(
    load: load ?? this.load,
    fields: fields ?? this.fields,
    items: items ?? this.items,
    failedFields: failedFields ?? this.failedFields,
    error: clearError ? null : (error ?? this.error),
    typeFilter: clearType ? null : (typeFilter ?? this.typeFilter),
    refreshing: refreshing ?? this.refreshing,
  );
}

/// يرتّب الأحدث أوّلاً (تاريخ التنفيذ/الجدولة ثمّ وقت الإنشاء).
int newestFirst(FieldActivity a, FieldActivity b) {
  final c = b.sortKey.compareTo(a.sortKey);
  if (c != 0) return c;
  return (b.createdAt ?? DateTime(0)).compareTo(a.createdAt ?? DateTime(0));
}

class FarmFeedCubit extends Cubit<FarmFeedState> {
  FarmFeedCubit({
    ActivitiesApi? api,
    FieldsApi? fieldsApi,
    PendingActivities? pending,
    this.perField = 20,
    this.concurrency = 4,
  }) : _api = api ?? ActivitiesApi.instance,
       _fieldsApi = fieldsApi ?? FieldsApi.instance,
       _pending = pending ?? PendingActivities.instance,
       super(const FarmFeedState());

  final ActivitiesApi _api;
  final FieldsApi _fieldsApi;
  final PendingActivities _pending;
  final int perField;
  final int concurrency;

  void _emit(FarmFeedState s) {
    if (!isClosed) emit(s);
  }

  Future<void> load() async {
    final hasData = state.load == FeedLoad.loaded;
    _emit(
      hasData
          ? state.copyWith(refreshing: true)
          : state.copyWith(load: FeedLoad.loading, clearError: true),
    );
    final List<FeedField> fields;
    try {
      final raw = await _fieldsApi.listFields();
      fields = [
        for (final f in raw)
          if ((f['field_id'] ?? f['id']) != null)
            FeedField(
              (f['field_id'] ?? f['id']).toString(),
              (f['name']?.toString().trim().isNotEmpty ?? false)
                  ? f['name'].toString()
                  : 'حقل ${f['field_id'] ?? f['id']}',
            ),
      ];
    } catch (e) {
      final err = ApiException.from(e);
      _emit(
        hasData
            ? state.copyWith(refreshing: false, error: err)
            : state.copyWith(load: FeedLoad.failed, error: err),
      );
      return;
    }

    final items = <FieldActivity>[];
    var failed = 0;
    ApiException? lastError;
    for (var i = 0; i < fields.length; i += concurrency) {
      final batch = fields.skip(i).take(concurrency);
      await Future.wait(
        batch.map((f) async {
          try {
            final list = await _api.listFieldActivities(f.id, limit: perField);
            _pending.reconcile(f.id, list);
            items.addAll(list);
          } catch (e) {
            failed++;
            lastError = ApiException.from(e);
          }
        }),
      );
    }
    items.sort(newestFirst);
    if (fields.isNotEmpty && failed == fields.length) {
      _emit(
        hasData
            ? state.copyWith(refreshing: false, error: lastError)
            : state.copyWith(load: FeedLoad.failed, error: lastError),
      );
      return;
    }
    _emit(
      state.copyWith(
        load: FeedLoad.loaded,
        fields: fields,
        items: items,
        failedFields: failed,
        error: failed > 0 ? lastError : null,
        clearError: failed == 0,
        refreshing: false,
      ),
    );
  }

  void setTypeFilter(String? t) => _emit(
    t == null ? state.copyWith(clearType: true) : state.copyWith(typeFilter: t),
  );
}
