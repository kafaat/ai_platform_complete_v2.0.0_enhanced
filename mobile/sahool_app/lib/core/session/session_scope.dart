// SAHOOL — lib/core/session/session_scope.dart
// نقطة واحدة لتنظيف حالة المستخدم عند الخروج الصريح.
//
// كلّ ميزة تملك حالةً خاصّة بالمستخدم (سجلّ محادثة، طوابير، كاش، صناديق Hive)
// تُعلن دالّة تنظيف في ملفّ مساراتها (`FeatureModule.onSessionEnd`)، فتسجّلها
// AppRouter عند الإقلاع. ApiService.logout يستدعي [SessionScope.endSession] قبل
// مسح التوكنات، فتعرف كلّ دالّة المستأجِر/المستخدم المنتهية جلسته.
//
// فشل دالّة لا يوقف البقيّة ولا يمنع الخروج (الخروج يبقى fail-closed محليّاً).
import 'package:flutter/foundation.dart';

/// هويّة الجلسة المنتهية — تُلتقَط قبل مسح التوكنات.
class SessionEnd {
  final String? tenantId;
  final String? userId;

  /// true للخروج الذي طلبه المستخدم؛ false لانتهاء الجلسة قسراً (رفض التحديث).
  final bool userInitiated;
  const SessionEnd({this.tenantId, this.userId, this.userInitiated = true});
}

typedef SessionCleanup = Future<void> Function(SessionEnd end);

class SessionScope {
  SessionScope();

  static final SessionScope instance = SessionScope();

  final Map<String, SessionCleanup> _cleanups = {};

  /// يسجّل (أو يستبدل) دالّة تنظيف باسم مالكها. الاسم = معرّف الميزة.
  void register(String owner, SessionCleanup cleanup) {
    _cleanups[owner] = cleanup;
  }

  void unregister(String owner) => _cleanups.remove(owner);

  @visibleForTesting
  Iterable<String> get owners => _cleanups.keys;

  /// يشغّل كلّ دوالّ التنظيف. يُعيد أسماء المالكين التي فشلت (للتشخيص).
  Future<List<String>> endSession(SessionEnd end) async {
    final failed = <String>[];
    for (final entry in _cleanups.entries.toList()) {
      try {
        await entry.value(end);
      } catch (e) {
        debugPrint('SessionScope cleanup "${entry.key}" failed: $e');
        failed.add(entry.key);
      }
    }
    return failed;
  }
}
