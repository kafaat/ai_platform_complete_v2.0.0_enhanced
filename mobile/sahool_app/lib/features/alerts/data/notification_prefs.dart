// SAHOOL — features/alerts/data/notification_prefs.dart
// تفضيلات الإشعار: قراءة قبل الكتابة، ولا قيمة افتراضيّة فوق قيمة مجهولة.
//
// لماذا: PUT /api/v1/notifications/preferences يستبدل الصفّ كاملاً (upsert)،
// فأيّ مفتاح غائب عن الجسم يرجع إلى افتراضيّ النموذج (false/null). تدقيق الخدمات
// وجد أنّ تسجيل رمز الدفع كان يمحو البريد/SMS/واتساب حين تفشل القراءة. هنا:
//   1) لا نموذج تعديل أصلاً بلا قراءة ناجحة (الشاشة تعرض الخطأ لا نموذجاً فارغاً).
//   2) عند الحفظ نعيد القراءة، ونطبّق **تعديلات المستخدم وحدها** فوق ما يحفظه
//      الخادم الآن (لا فوق نسخة قديمة، ولا فوق افتراضيّات)، ثمّ نكتب.
//   3) فشل إعادة القراءة ⇒ لا كتابة إطلاقاً.
//   4) المفاتيح التي لا نعرفها (وpush_token الذي يديره PushService) تُعاد كما
//      قرأناها حرفيّاً.
import 'package:flutter/foundation.dart';
import 'package:sahool_app/core/network/idempotency.dart';
import 'package:sahool_app/core/utils/formatters.dart';

import 'alerts_api.dart';

/// أنواع أحداث الإشعار التي يقبلها الخادم (api/main.py _NOTIF_EVENT_TYPES).
const Map<String, String> kNotifEventTypesAr = {
  'weather_alert': 'تنبيهات الطقس',
  'pest_alert': 'تنبيهات الآفات',
  'disease_risk': 'خطر الأمراض',
  'low_moisture': 'رطوبة منخفضة',
  'heavy_rain': 'أمطار غزيرة',
  'heat_stress': 'إجهاد حراريّ',
  'frost_risk': 'خطر صقيع',
  'irrigation_rec': 'توصيات الريّ',
  'fertilizer_rec': 'توصيات التسميد',
  'satellite': 'صور الأقمار الصناعيّة',
  'task_assigned': 'إسناد المهام',
  'low_stock': 'نفاد المخزون',
  'economic_analysis': 'التحليل الاقتصاديّ',
  'other': 'تنبيهات أخرى',
};

/// قنوات التسليم القابلة للتعديل: مفتاح التفعيل ← مفتاح العنوان.
enum NotifChannel {
  push('push_enabled', null, 'إشعارات التطبيق'),
  email('email_enabled', 'email_address', 'البريد الإلكترونيّ'),
  sms('sms_enabled', 'sms_number', 'رسائل SMS'),
  whatsapp('whatsapp_enabled', 'whatsapp_number', 'واتساب');

  const NotifChannel(this.enabledKey, this.addressKey, this.labelAr);
  final String enabledKey;
  final String? addressKey;
  final String labelAr;
}

/// قراءة مُنمَّطة لصفّ التفضيلات كما وصل (لا تُعدِّله).
@immutable
class NotificationPrefs {
  const NotificationPrefs(this.raw);
  final Map<String, dynamic> raw;

  /// null ⇒ المفتاح غائب أو بنوع غير متوقّع (لا نفترض false).
  bool? enabled(NotifChannel c) {
    final v = raw[c.enabledKey];
    return v is bool ? v : null;
  }

  String? address(NotifChannel c) {
    final k = c.addressKey;
    if (k == null) return null;
    final v = raw[k];
    return v is String && v.isNotEmpty ? v : null;
  }

  List<String> get eventTypes {
    final v = raw['event_types'];
    return v is List ? v.map((e) => e.toString()).toList() : const [];
  }

  String? get minSeverity {
    final v = raw['min_severity'];
    return v is String && v.isNotEmpty ? v : null;
  }
}

/// تعديلات المستخدم وحدها — لا تحمل أيّ قيمة لم يلمسها.
@immutable
class PrefsDraft {
  const PrefsDraft({
    this.fields = const {},
    this.addEvents = const {},
    this.removeEvents = const {},
  });

  /// مفاتيح عدّلها المستخدم ← قيمها الجديدة.
  final Map<String, Object?> fields;
  final Set<String> addEvents;
  final Set<String> removeEvents;

  bool get isEmpty =>
      fields.isEmpty && addEvents.isEmpty && removeEvents.isEmpty;

  PrefsDraft setField(String key, Object? value) => PrefsDraft(
    fields: {...fields, key: value},
    addEvents: addEvents,
    removeEvents: removeEvents,
  );

  PrefsDraft toggleEvent(String type, {required bool on}) => PrefsDraft(
    fields: fields,
    addEvents: on ? {...addEvents, type} : ({...addEvents}..remove(type)),
    removeEvents: on
        ? ({...removeEvents}..remove(type))
        : {...removeEvents, type},
  );

  /// يطبّق التعديلات فوق [server] (القراءة الأحدث). لا مفتاح خارج التعديلات
  /// يتغيّر.
  Map<String, dynamic> applyTo(Map<String, dynamic> server) {
    final out = Map<String, dynamic>.from(server);
    fields.forEach((k, v) {
      out[k] = v is String ? _cleanAddress(k, v) : v;
    });
    if (addEvents.isNotEmpty || removeEvents.isNotEmpty) {
      final current = NotificationPrefs(server).eventTypes;
      final next = <String>[
        for (final e in current)
          if (!removeEvents.contains(e)) e,
        for (final e in addEvents)
          if (!current.contains(e)) e,
      ];
      out['event_types'] = next;
    }
    return out;
  }

  /// أرقام الهاتف قد تُكتب بأرقام عربيّة-هنديّة؛ نطبّعها. فارغ ⇒ null.
  static Object? _cleanAddress(String key, String v) {
    final t = v.trim();
    if (t.isEmpty) return null;
    if (key.endsWith('_number')) {
      return normalizeDigits(t).replaceAll(' ', '');
    }
    return t;
  }

  /// القيمة المعروضة: تعديل المستخدم إن وُجد، وإلّا قيمة الخادم.
  bool? enabledOf(NotificationPrefs p, NotifChannel c) =>
      fields.containsKey(c.enabledKey)
      ? fields[c.enabledKey] as bool?
      : p.enabled(c);

  String? addressOf(NotificationPrefs p, NotifChannel c) {
    final k = c.addressKey;
    if (k == null) return null;
    return fields.containsKey(k) ? fields[k] as String? : p.address(c);
  }

  bool eventOn(NotificationPrefs p, String type) {
    if (addEvents.contains(type)) return true;
    if (removeEvents.contains(type)) return false;
    return p.eventTypes.contains(type);
  }

  String? minSeverityOf(NotificationPrefs p) =>
      fields.containsKey('min_severity')
      ? fields['min_severity'] as String?
      : p.minSeverity;
}

/// يحفظ التعديلات بقراءة-ثمّ-كتابة.
class NotificationPrefsRepository {
  NotificationPrefsRepository([AlertsApi? api])
    : _api = api ?? AlertsApi.instance;
  final AlertsApi _api;

  Future<NotificationPrefs> load() async =>
      NotificationPrefs(await _api.getNotificationPreferences());

  /// يعيد قراءة الخادم ثمّ يكتب [draft] فوقها. إن فشلت القراءة يرمي خطأها ولا
  /// يُرسَل PUT.
  Future<NotificationPrefs> save(
    PrefsDraft draft, {
    IdempotencyKey? idempotencyKey,
  }) async {
    final fresh = await _api.getNotificationPreferences();
    final body = draft.applyTo(fresh);
    final saved = await _api.putNotificationPreferences(
      body,
      idempotencyKey: idempotencyKey,
    );
    return NotificationPrefs(saved);
  }
}
