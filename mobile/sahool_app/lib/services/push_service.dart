// SAHOOL v9.1.0 — lib/services/push_service.dart
// C4/M1: غراء عميل Push (FCM) لـFlutter — تسجيل رمز الجهاز + إشعارات أماميّة.
//
// مُهيّأ دفاعيّاً: يُبادر Firebase وfirebase_messaging داخل try/catch خلف علَم
// تشغيل (_enabled)، فيعمل التطبيق (وflutter analyze/test) دون
// google-services.json / GoogleService-Info.plist (غير مُلتزَمَين في المستودع).
// عند غياب التهيئة لا ينهار أبداً — يُسجّل ويتجاهل (no-op).
//
// ─── خطوات البيئة المتبقّية (خارج النطاق — تُنفَّذ قبل أيّ push حيّ) ───────────
//   1) مشروع Firebase + تطبيق Android/iOS مُسجَّل.
//   2) Android: ضَع google-services.json تحت android/app/.
//   3) iOS: ضَع GoogleService-Info.plist + مفتاح APNs في Firebase Console.
//   4) الخادم: عيّن FCM_SERVER_KEY (مسار FCM legacy المُنفَّذ في
//      services/sahool-platform/api/alert_senders.py) لإرسال الدفع فعليّاً.
//   5) جهاز/محاكي حقيقيّ (الدفع لا يعمل على محاكيات بلا Google Play غالباً).
// دون هذه الخطوات يبقى PushService صامتاً (no-op) ولا يكسر شيئاً.

import 'package:firebase_core/firebase_core.dart';
import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter_local_notifications/flutter_local_notifications.dart';
import 'package:logger/logger.dart';

import 'api_service.dart';

/// خدمة الدفع (FCM) — مفردة على نمط [WebSocketService]/[ApiService].
///
/// [init] دفاعيّ: أيّ تعذّر (Firebase غير مُهيّأ، صلاحيّة مرفوضة، منصّة غير
/// مدعومة) يُسجَّل ويُتجاهَل — لا يُرمى استثناء يكسر إقلاع التطبيق.
class PushService {
  static final PushService instance = PushService._internal();
  PushService._internal();

  final _logger = Logger();

  // قناة إشعارات أندرويد (لازمة لعرض الإشعارات الأماميّة على Android 8+).
  static const _androidChannelId = 'sahool_alerts';
  static const _androidChannelName = 'تنبيهات سهول';
  static const _androidChannelDescription = 'تنبيهات الحقول والإشعارات الزراعيّة';

  final FlutterLocalNotificationsPlugin _localNotifications =
      FlutterLocalNotificationsPlugin();

  // علَم التشغيل: يبقى false إن لم تكتمل التهيئة (لا google-services / منصّة
  // غير مدعومة)، فتُصبح كلّ العمليّات اللاحقة no-op صامتة.
  bool _enabled = false;
  bool _initialized = false;

  /// يُهيّئ Firebase + firebase_messaging + الإشعارات المحليّة، يطلب الصلاحيّة،
  /// يجلب رمز FCM ويُسجّله في الخلفيّة، ويربط معالج الرسائل الأماميّة.
  ///
  /// دفاعيّ بالكامل: لا يُرمى استثناء أبداً. عند أيّ تعذّر يبقى [_enabled] = false
  /// ويعمل التطبيق طبيعيّاً بلا دفع.
  Future<void> init() async {
    if (_initialized) return;
    _initialized = true;

    // (1) تهيئة Firebase — تفشل بهدوء إن غاب google-services.json/plist.
    try {
      await Firebase.initializeApp();
    } catch (e) {
      _logger.w('Firebase غير مُهيّأ (لا google-services؟) — الدفع مُعطَّل: $e');
      return; // _enabled يبقى false → كلّ ما يلي no-op.
    }

    // (2) تهيئة الإشعارات المحليّة (لعرض رسائل المقدّمة).
    try {
      await _initLocalNotifications();
    } catch (e) {
      _logger.w('تعذّرت تهيئة الإشعارات المحليّة — الدفع مُعطَّل: $e');
      return;
    }

    // (3) طلب الصلاحيّة + جلب الرمز + تسجيله + ربط المعالجات.
    try {
      final messaging = FirebaseMessaging.instance;

      await messaging.requestPermission(
        alert: true,
        badge: true,
        sound: true,
      );

      _enabled = true;

      // جلب الرمز الأوّليّ وتسجيله (لا يكسر الإقلاع إن فشل النداء الشبكيّ).
      final token = await messaging.getToken();
      if (token != null) {
        await _registerToken(token);
      }

      // تجديد الرمز (دوريّ أو بعد إعادة التثبيت) — يُعاد تسجيله تلقائيّاً.
      messaging.onTokenRefresh.listen(
        _registerToken,
        onError: (Object e) => _logger.w('onTokenRefresh خطأ: $e'),
      );

      // رسائل المقدّمة (التطبيق مفتوح) — تُعرَض عبر flutter_local_notifications
      // (FCM لا يعرضها تلقائيّاً في المقدّمة على Android).
      FirebaseMessaging.onMessage.listen(
        _showForegroundNotification,
        onError: (Object e) => _logger.w('onMessage خطأ: $e'),
      );

      _logger.i('PushService مُهيّأ ✅');
    } catch (e) {
      _logger.w('تعذّرت تهيئة الدفع — مُعطَّل دفاعيّاً: $e');
      _enabled = false;
    }
  }

  Future<void> _initLocalNotifications() async {
    const androidInit =
        AndroidInitializationSettings('@mipmap/ic_launcher');
    const iosInit = DarwinInitializationSettings(
      requestAlertPermission: false,
      requestBadgePermission: false,
      requestSoundPermission: false,
    );
    const initSettings =
        InitializationSettings(android: androidInit, iOS: iosInit);

    await _localNotifications.initialize(initSettings);

    // إنشاء قناة أندرويد صراحةً (لازمة على Android 8+).
    const channel = AndroidNotificationChannel(
      _androidChannelId,
      _androidChannelName,
      description: _androidChannelDescription,
      importance: Importance.high,
    );
    await _localNotifications
        .resolvePlatformSpecificImplementation<
            AndroidFlutterLocalNotificationsPlugin>()
        ?.createNotificationChannel(channel);
  }

  /// يُسجّل رمز الجهاز في الخلفيّة. دفاعيّ: فشل الشبكة/الخادم يُسجَّل ولا يُرمى
  /// (تسجيل الرمز ليس حرجاً لإقلاع التطبيق).
  Future<void> _registerToken(String token) async {
    try {
      await ApiService.instance.registerPushToken(token);
      _logger.d('رمز FCM سُجِّل في الخادم');
    } catch (e) {
      _logger.w('تعذّر تسجيل رمز FCM — سيُعاد عند التجديد: $e');
    }
  }

  /// يعرض إشعار المقدّمة عبر الإشعارات المحليّة. النصّ عربيّ (RTL).
  Future<void> _showForegroundNotification(RemoteMessage message) async {
    if (!_enabled) return;
    try {
      final notification = message.notification;
      // عنوان/نصّ افتراضيّان عربيّان إن لم يُرسلهما الخادم في حمولة الإشعار.
      final title = notification?.title ?? 'تنبيه سهول';
      final body = notification?.body ?? 'لديك تنبيه جديد من سهول';

      const androidDetails = AndroidNotificationDetails(
        _androidChannelId,
        _androidChannelName,
        channelDescription: _androidChannelDescription,
        importance: Importance.high,
        priority: Priority.high,
      );
      const iosDetails = DarwinNotificationDetails();
      const details =
          NotificationDetails(android: androidDetails, iOS: iosDetails);

      // مُعرّف مبنيّ على الوقت (يتفادى استبدال إشعار سابق).
      final id = DateTime.now().millisecondsSinceEpoch % 0x7FFFFFFF;
      await _localNotifications.show(id, title, body, details);
    } catch (e) {
      _logger.w('تعذّر عرض إشعار المقدّمة: $e');
    }
  }

  /// هل الدفع مُهيّأ فعليّاً؟ (للاختبار/التشخيص).
  @visibleForTesting
  bool get isEnabled => _enabled;
}
