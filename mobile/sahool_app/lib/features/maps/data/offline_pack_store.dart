// SAHOOL — features/maps/data/offline_pack_store.dart
// حزم الخرائط بلا اتّصال على الجهاز: السرد والتفعيل والحذف.
//
// أين توضع الحزم: مجلّد `maps/` داخل مستندات التطبيق، وعلى أندرويد أيضاً مجلّد
// `maps/` في تخزين التطبيق الخارجيّ (Android/data/<pkg>/files/maps) الذي يمكن
// النسخ إليه عبر USB أو مدير الملفّات. لا مُنتقي ملفّات في الاعتماديّات اليوم
// (image_picker لا يفتح ‎.mbtiles) — الاستيراد من داخل التطبيق مطلوب كاعتماديّة.
// تنزيل الحزم من الخادم غير متاح: GET /api/raster/v1/offline/packs يتطلّب رمز
// خدمة (X-Agent-Token) لا جلسة مستخدم.
//
// الحزمة المفعّلة تُحفظ كمسار في SharedPreferences (تفضيل محلّيّ لكلّ جهاز).
import 'dart:io';

import 'package:path_provider/path_provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'offline_tiles.dart';

/// حزمة معروفة على القرص (قبل فتحها).
class OfflinePackFile {
  const OfflinePackFile({
    required this.path,
    required this.name,
    required this.format,
    required this.sizeBytes,
    required this.modified,
  });

  final String path;
  final String name;
  final OfflinePackFormat format;
  final int sizeBytes;
  final DateTime modified;
}

typedef DirectoryResolver = Future<List<Directory>> Function();

class OfflinePackStore {
  OfflinePackStore({
    DirectoryResolver? roots,
    Future<SharedPreferences> Function()? prefs,
  }) : _roots = roots ?? defaultPackRoots,
       _prefs = prefs ?? SharedPreferences.getInstance;

  static final OfflinePackStore instance = OfflinePackStore();

  static const activePackKey = 'maps.active_offline_pack';
  static const folderName = 'maps';

  final DirectoryResolver _roots;
  final Future<SharedPreferences> Function() _prefs;

  /// المجلّدات التي تُفحص (تُنشأ إن غابت كي يجد المستخدم مكانها).
  static Future<List<Directory>> defaultPackRoots() async {
    final dirs = <Directory>[];
    final docs = await getApplicationDocumentsDirectory();
    dirs.add(Directory('${docs.path}/$folderName'));
    if (Platform.isAndroid) {
      final ext = await getExternalStorageDirectory();
      if (ext != null) dirs.add(Directory('${ext.path}/$folderName'));
    }
    return dirs;
  }

  /// مسارات المجلّدات المفحوصة (لعرضها للمستخدم).
  Future<List<String>> folders() async => [
    for (final d in await _roots()) d.path,
  ];

  /// كلّ الحزم (‎.pmtiles/‎.mbtiles) في المجلّدات، الأحدث أوّلاً.
  Future<List<OfflinePackFile>> list() async {
    final out = <OfflinePackFile>[];
    for (final dir in await _roots()) {
      try {
        if (!await dir.exists()) await dir.create(recursive: true);
        await for (final e in dir.list(followLinks: false)) {
          if (e is! File) continue;
          final format = offlinePackFormatOf(e.path);
          if (format == null) continue;
          final stat = await e.stat();
          out.add(
            OfflinePackFile(
              path: e.path,
              name: e.uri.pathSegments.last,
              format: format,
              sizeBytes: stat.size,
              modified: stat.modified,
            ),
          );
        }
      } on FileSystemException {
        // مجلّد غير مقروء (صلاحيّات) ⇒ نتجاوزه، لا نُسقط القائمة كلّها.
      }
    }
    out.sort((a, b) => b.modified.compareTo(a.modified));
    return out;
  }

  /// مسار الحزمة المفعّلة إن كانت ما تزال موجودة.
  Future<String?> activePath() async {
    final p = (await _prefs()).getString(activePackKey);
    if (p == null) return null;
    return await File(p).exists() ? p : null;
  }

  Future<void> setActive(String? path) async {
    final prefs = await _prefs();
    if (path == null) {
      await prefs.remove(activePackKey);
    } else {
      await prefs.setString(activePackKey, path);
    }
  }

  /// يحذف ملفّ الحزمة (ويُلغي تفعيلها إن كانت المفعّلة).
  Future<void> delete(OfflinePackFile pack) async {
    if (await activePath() == pack.path) await setActive(null);
    final f = File(pack.path);
    if (await f.exists()) await f.delete();
  }
}
