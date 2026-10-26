// SAHOOL — features/activities/presentation/field_activities_cubit.dart
// سجلّ أنشطة حقل + خطّه الزمنيّ الموحّد. القراءتان مستقلّتان: فشل إحداهما لا
// يُخفي الأخرى.
import 'package:flutter/foundation.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:sahool_app/core/network/api_exception.dart';
import 'package:sahool_app/features/activities/data/activities_api.dart';
import 'package:sahool_app/features/activities/data/activity_writer.dart';
import 'package:sahool_app/features/activities/data/field_activity.dart';

/// قراءة واحدة: جارية، أو بيانات، أو فشل مُنمَّط.
@immutable
class Slice<T> {
  const Slice.loading() : data = null, error = null, loading = true;
  const Slice.data(T this.data) : error = null, loading = false;
  const Slice.failed(ApiException this.error) : data = null, loading = false;

  final T? data;
  final ApiException? error;
  final bool loading;
}

@immutable
class FieldActivitiesState {
  const FieldActivitiesState({
    this.activities = const Slice.loading(),
    this.timeline = const Slice.loading(),
    this.category,
  });

  final Slice<List<FieldActivity>> activities;
  final Slice<FieldTimelineData> timeline;

  /// فئة الخطّ الزمنيّ المختارة (null = الكلّ).
  final String? category;

  List<TimelineEvent> get visibleEvents {
    final events = timeline.data?.events ?? const <TimelineEvent>[];
    return category == null
        ? events
        : events.where((e) => e.category == category).toList();
  }

  FieldActivitiesState copyWith({
    Slice<List<FieldActivity>>? activities,
    Slice<FieldTimelineData>? timeline,
    String? category,
    bool clearCategory = false,
  }) => FieldActivitiesState(
    activities: activities ?? this.activities,
    timeline: timeline ?? this.timeline,
    category: clearCategory ? null : (category ?? this.category),
  );
}

class FieldActivitiesCubit extends Cubit<FieldActivitiesState> {
  FieldActivitiesCubit(
    this.fieldId, {
    ActivitiesApi? api,
    PendingActivities? pending,
  }) : _api = api ?? ActivitiesApi.instance,
       _pending = pending ?? PendingActivities.instance,
       super(const FieldActivitiesState());

  final String fieldId;
  final ActivitiesApi _api;
  final PendingActivities _pending;

  Future<void> load() =>
      Future.wait([loadActivities(), loadTimeline()]).then((_) {});

  Future<void> loadActivities() async {
    if (state.activities.data == null) {
      _emit(state.copyWith(activities: const Slice.loading()));
    }
    try {
      final list = await _api.listFieldActivities(fieldId, limit: 100);
      _pending.reconcile(fieldId, list);
      _emit(state.copyWith(activities: Slice.data(list)));
    } catch (e) {
      _emit(state.copyWith(activities: Slice.failed(ApiException.from(e))));
    }
  }

  Future<void> loadTimeline() async {
    if (state.timeline.data == null) {
      _emit(state.copyWith(timeline: const Slice.loading()));
    }
    try {
      final t = await _api.fetchUnifiedTimeline(fieldId);
      _emit(state.copyWith(timeline: Slice.data(t)));
    } catch (e) {
      _emit(state.copyWith(timeline: Slice.failed(ApiException.from(e))));
    }
  }

  void setCategory(String? c) => _emit(
    c == null
        ? state.copyWith(clearCategory: true)
        : state.copyWith(category: c),
  );

  void _emit(FieldActivitiesState s) {
    if (!isClosed) emit(s);
  }
}
