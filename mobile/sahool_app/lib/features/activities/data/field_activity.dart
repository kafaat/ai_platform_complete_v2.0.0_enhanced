// SAHOOL — features/activities/data/field_activity.dart
// نماذج الأنشطة كما يردّها الخادم:
//  * ActivitySummary (api_models.py:74): activity_id, field_id, season_id,
//    activity_type, title_ar, details{notes?}, scheduled_for, performed_on
//    (YYYY-MM-DD), status(done/planned), created_at.
//  * الخطّ الزمنيّ الموحّد (field_workspace_timeline.py:31 + field_timeline.py):
//    {events:[{timestamp, event_type, category, summary_ar, actor_id, payload}],
//     total_events, category_counts, degraded, note_ar?/error?}.
// ومسودّة نموذج التسجيل السريع بتحقّقها.
import 'package:flutter/foundation.dart';

/// أنواع العمليّات التي يقبلها الخادم (`_ACTIVITY_TYPES`, api/main.py:1416).
/// غيرها يُرفَض بـ422، فلا خيار «أخرى» في النموذج.
const List<String> kActivityTypes = [
  'spraying',
  'fertilization',
  'irrigation',
  'planting',
  'harvest',
  'pruning',
  'scouting',
];

/// أقصى طول للعنوان (ActivityCreateRequest.title_ar max_length=200).
const int kActivityTitleMax = 200;
const int kActivityNotesMax = 2000;

String? _str(Object? v) {
  final s = v?.toString().trim() ?? '';
  return s.isEmpty ? null : s;
}

@immutable
class FieldActivity {
  const FieldActivity({
    required this.id,
    required this.fieldId,
    required this.type,
    required this.status,
    this.seasonId,
    this.titleAr,
    this.notes,
    this.scheduledFor,
    this.performedOn,
    this.createdAt,
    this.pendingSync = false,
  });

  final String id;
  final String fieldId;
  final String type;

  /// done / planned (كما يحسبه الخادم من performed_on).
  final String status;
  final String? seasonId;
  final String? titleAr;
  final String? notes;

  /// تواريخ تقويميّة YYYY-MM-DD (لا لحظات زمنيّة).
  final String? scheduledFor;
  final String? performedOn;
  final DateTime? createdAt;

  /// محفوظ في صندوق الإرسال ولم يصل الخادم بعد.
  final bool pendingSync;

  bool get isDone => status == 'done';

  /// مفتاح الترتيب: تاريخ التنفيذ ثمّ الجدولة ثمّ الإنشاء.
  String get sortKey =>
      performedOn ??
      scheduledFor ??
      (createdAt?.toLocal().toIso8601String().substring(0, 10) ?? '');

  factory FieldActivity.fromJson(Map<String, dynamic> j) {
    final id = _str(j['activity_id']);
    if (id == null) {
      throw const FormatException('استجابة غير متوقّعة: نشاط بلا معرّف.');
    }
    final details = j['details'];
    return FieldActivity(
      id: id,
      fieldId: _str(j['field_id']) ?? '',
      type: _str(j['activity_type']) ?? '',
      status: _str(j['status']) ?? '',
      seasonId: _str(j['season_id']),
      titleAr: _str(j['title_ar']),
      notes: details is Map ? _str(details['notes']) : null,
      scheduledFor: _str(j['scheduled_for']),
      performedOn: _str(j['performed_on']),
      createdAt: DateTime.tryParse(_str(j['created_at']) ?? ''),
    );
  }

  /// نسخة محلّيّة لنشاطٍ أودِع صندوق الإرسال (يُعرَض بشارة «بانتظار المزامنة»).
  factory FieldActivity.pending(
    String localId,
    String fieldId,
    Map<String, dynamic> body,
    DateTime now,
  ) {
    final details = body['details'];
    return FieldActivity(
      id: localId,
      fieldId: fieldId,
      type: body['activity_type'] as String,
      status: body['performed_on'] != null ? 'done' : 'planned',
      titleAr: body['title_ar'] as String?,
      notes: details is Map ? details['notes'] as String? : null,
      scheduledFor: body['scheduled_for'] as String?,
      performedOn: body['performed_on'] as String?,
      createdAt: now,
      pendingSync: true,
    );
  }

  /// هل يطابق هذا النشاطُ من الخادم نسخةً محلّيّة منتظرة؟ (وصلت المزامنة)
  bool sameAs(FieldActivity o) =>
      fieldId == o.fieldId &&
      type == o.type &&
      titleAr == o.titleAr &&
      notes == o.notes &&
      performedOn == o.performedOn &&
      scheduledFor == o.scheduledFor;
}

/// متى نُفِّذ النشاط في نموذج التسجيل.
enum ActivityWhen { today, onDate, planned }

/// يحوّل تاريخاً محلّيّاً إلى YYYY-MM-DD.
String isoDay(DateTime d) {
  final l = DateTime(d.year, d.month, d.day);
  return '${l.year.toString().padLeft(4, '0')}-'
      '${l.month.toString().padLeft(2, '0')}-'
      '${l.day.toString().padLeft(2, '0')}';
}

/// مسودّة التسجيل السريع.
@immutable
class ActivityDraft {
  const ActivityDraft({
    this.type,
    this.title = '',
    this.notes = '',
    this.when = ActivityWhen.today,
    this.date,
  });

  final String? type;
  final String title;
  final String notes;
  final ActivityWhen when;

  /// تاريخ التنفيذ (onDate) أو الجدولة (planned). يُتجاهَل لـ today.
  final DateTime? date;

  /// أخطاء التحقّق: المفتاح اسم الحقل (type/title/notes/date). فارغة ⇒ صالحة.
  Map<String, String> validate(DateTime now) {
    final errors = <String, String>{};
    final today = DateTime(now.year, now.month, now.day);
    if (type == null || !kActivityTypes.contains(type)) {
      errors['type'] = 'اختر نوع النشاط';
    }
    if (title.trim().length > kActivityTitleMax) {
      errors['title'] = 'العنوان أطول من $kActivityTitleMax حرف';
    }
    if (notes.trim().length > kActivityNotesMax) {
      errors['notes'] = 'الملاحظات أطول من $kActivityNotesMax حرف';
    }
    final d = date == null
        ? null
        : DateTime(date!.year, date!.month, date!.day);
    switch (when) {
      case ActivityWhen.today:
        break;
      case ActivityWhen.onDate:
        if (d == null) {
          errors['date'] = 'اختر تاريخ التنفيذ';
        } else if (d.isAfter(today)) {
          errors['date'] = 'تاريخ التنفيذ لا يكون في المستقبل — اختر «مُجدوَل»';
        }
      case ActivityWhen.planned:
        if (d == null) {
          errors['date'] = 'اختر تاريخ الجدولة';
        } else if (d.isBefore(today)) {
          errors['date'] = 'تاريخ الجدولة لا يكون في الماضي';
        }
    }
    return errors;
  }

  /// جسم ActivityCreateRequest. [now] يحدّد «اليوم» محلّيّاً.
  Map<String, dynamic> toJson(DateTime now) {
    final t = title.trim();
    final n = notes.trim();
    return {
      'activity_type': type,
      if (t.isNotEmpty) 'title_ar': t,
      if (when == ActivityWhen.today) 'performed_on': isoDay(now),
      if (when == ActivityWhen.onDate && date != null)
        'performed_on': isoDay(date!),
      if (when == ActivityWhen.planned && date != null)
        'scheduled_for': isoDay(date!),
      if (n.isNotEmpty) 'details': {'notes': n},
    };
  }

  ActivityDraft copyWith({
    String? type,
    String? title,
    String? notes,
    ActivityWhen? when,
    DateTime? date,
    bool clearDate = false,
  }) => ActivityDraft(
    type: type ?? this.type,
    title: title ?? this.title,
    notes: notes ?? this.notes,
    when: when ?? this.when,
    date: clearDate ? null : (date ?? this.date),
  );
}

/// حدث في الخطّ الزمنيّ الموحّد.
@immutable
class TimelineEvent {
  const TimelineEvent({
    required this.at,
    required this.rawTimestamp,
    required this.eventType,
    required this.category,
    required this.summaryAr,
    this.actorId,
  });

  /// اللحظة بالتوقيت المحلّيّ (الخادم يرسل UTC `+00:00`؛ عرضها كما هي كان
  /// يُظهر الوقت متأخّراً 3 ساعات في اليمن). null إن تعذّر التحليل.
  final DateTime? at;
  final String rawTimestamp;
  final String eventType;
  final String category;
  final String summaryAr;
  final String? actorId;

  factory TimelineEvent.fromJson(Map<String, dynamic> j) {
    final raw = _str(j['timestamp']) ?? _str(j['occurred_at']) ?? '';
    return TimelineEvent(
      at: DateTime.tryParse(raw)?.toLocal(),
      rawTimestamp: raw,
      eventType: _str(j['event_type']) ?? '',
      category: _str(j['category']) ?? 'system',
      summaryAr: _str(j['summary_ar']) ?? _str(j['event_type']) ?? '—',
      actorId: _str(j['actor_id']),
    );
  }
}

@immutable
class FieldTimelineData {
  const FieldTimelineData({
    required this.events,
    required this.categoryCounts,
    required this.degraded,
    this.degradedReasonAr,
  });

  final List<TimelineEvent> events;
  final Map<String, int> categoryCounts;

  /// الخادم لم يستطع قراءة الأحداث (لا قاعدة/فشل): القائمة الفارغة هنا ليست
  /// «لا أحداث» بل «غير متاح».
  final bool degraded;
  final String? degradedReasonAr;

  factory FieldTimelineData.fromJson(Map<String, dynamic> j) {
    final raw = j['events'];
    if (raw is! List) {
      throw const FormatException(
        'استجابة غير متوقّعة من الخادم: الخطّ الزمنيّ بلا قائمة أحداث.',
      );
    }
    final counts = <String, int>{};
    final cc = j['category_counts'];
    if (cc is Map) {
      cc.forEach((k, v) {
        if (v is num) counts[k.toString()] = v.toInt();
      });
    }
    final degraded = j['degraded'] == true;
    return FieldTimelineData(
      events: [
        for (final e in raw)
          if (e is Map) TimelineEvent.fromJson(e.cast<String, dynamic>()),
      ],
      categoryCounts: counts,
      degraded: degraded,
      degradedReasonAr: degraded
          ? (_str(j['note_ar']) ??
                (_str(j['error']) != null
                    ? 'تعذّر جلب الخطّ الزمنيّ من الخادم.'
                    : null))
          : null,
    );
  }
}
