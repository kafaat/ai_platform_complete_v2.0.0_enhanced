// SAHOOL — features/dashboard/data/dashboard_snapshot_store.dart
// آخر نسخة ناجحة من شاشة «اليوم» (حمولة اللوحة + المهامّ + المزارع) محفوظة على
// الجهاز، كي يرى المزارع على شبكة ضعيفة آخر ما عُرِف مع عمره («آخر تحديث منذ…»)
// بدل شاشة خطأ فارغة.
//
// كاش الاستجابات في core (ResponseCache) يعيش في الذاكرة 5 دقائق ويموت مع
// العمليّة؛ هذا المخزن يكمّله لفتح التطبيق دون اتّصال. المفتاح مُنطَّق
// بالمستأجِر+المستخدم، ويُمسَح الصندوق عند الخروج (dashboard_routes.dart).
// أيّ فشل في Hive ⇒ لا لقطة (لا استثناء يكسر الشاشة).
import 'dart:convert';

import 'package:hive/hive.dart';

/// لقطة محفوظة: البيانات كما وصلت من الخادم + وقت جلبها.
class DashboardSnapshot {
  const DashboardSnapshot(this.data, this.savedAt);
  final Map<String, dynamic> data;
  final DateTime savedAt;
}

abstract class DashboardSnapshotStore {
  Future<DashboardSnapshot?> read(String scope);
  Future<void> write(String scope, Map<String, dynamic> data, DateTime at);
  Future<void> clear();
}

/// للاختبارات ولغياب Hive.
class MemoryDashboardSnapshotStore implements DashboardSnapshotStore {
  final Map<String, DashboardSnapshot> _entries = {};

  @override
  Future<DashboardSnapshot?> read(String scope) async => _entries[scope];

  @override
  Future<void> write(
    String scope,
    Map<String, dynamic> data,
    DateTime at,
  ) async {
    _entries[scope] = DashboardSnapshot(data, at);
  }

  @override
  Future<void> clear() async => _entries.clear();
}

const String kDashboardSnapshotBox = 'dashboard_snapshot';

/// صندوق يفتحه main.dart عند الإقلاع — دليل أنّ Hive مهيّأ.
const String kHiveReadyProbeBox = 'settings';

class HiveDashboardSnapshotStore implements DashboardSnapshotStore {
  HiveDashboardSnapshotStore({this.boxName = kDashboardSnapshotBox});

  static final HiveDashboardSnapshotStore instance =
      HiveDashboardSnapshotStore();

  final String boxName;

  Future<Box<dynamic>?> _box() async {
    try {
      if (Hive.isBoxOpen(boxName)) return Hive.box<dynamic>(boxName);
      // main.dart يفتح 'settings' بعد Hive.initFlutter؛ غيابه ⇒ Hive غير مهيّأ
      // (اختبار عارٍ) ولا نفتح صندوقاً: openBox يُسرّب خطأً غير ملتقَط حينها.
      if (!Hive.isBoxOpen(kHiveReadyProbeBox)) return null;
      return await Hive.openBox<dynamic>(boxName);
    } catch (_) {
      return null; // Hive غير مهيّأ (اختبار) أو تالف ⇒ بلا لقطة.
    }
  }

  @override
  Future<DashboardSnapshot?> read(String scope) async {
    try {
      final raw = (await _box())?.get(scope);
      if (raw is! String) return null;
      final decoded = jsonDecode(raw);
      if (decoded is! Map) return null;
      final at = DateTime.tryParse('${decoded['saved_at']}');
      final data = decoded['data'];
      if (at == null || data is! Map) return null;
      return DashboardSnapshot(Map<String, dynamic>.from(data), at);
    } catch (_) {
      return null;
    }
  }

  @override
  Future<void> write(
    String scope,
    Map<String, dynamic> data,
    DateTime at,
  ) async {
    try {
      await (await _box())?.put(
        scope,
        jsonEncode({'saved_at': at.toUtc().toIso8601String(), 'data': data}),
      );
    } catch (_) {
      // الحفظ تحسين لا شرط: فشله لا يُسقط الشاشة.
    }
  }

  @override
  Future<void> clear() async {
    try {
      await (await _box())?.clear();
    } catch (_) {}
  }
}
