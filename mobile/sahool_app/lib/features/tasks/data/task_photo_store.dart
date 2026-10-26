// SAHOOL — features/tasks/data/task_photo_store.dart
// صور المهام المحفوظة على الجهاز فقط.
//
// لا نقطة خادم تخزّن ملفّ صورة: `photo_url` في PATCH /api/v1/tasks/{id} نصّ
// مرجعيّ فقط (api_models.py:121)، ولا موجِّه يقبل UploadFile. إرسال مسار ملفٍّ
// محلّيّ في photo_url كان سيكتب في سجلّ المنصّة مرجعاً لا يفتحه أحد غير هذا
// الجهاز (أثر تدقيق زائف). لذا تُنسَخ الصورة إلى مجلّد التطبيق الدائم (لا مجلّد
// image_picker المؤقّت) مُنطَّقاً بالمستأجر والمستخدم، وتُعرَض مع تنبيه صريح.
import 'dart:io';

import 'package:path_provider/path_provider.dart';

class TaskPhotoStore {
  TaskPhotoStore({
    Future<Directory> Function()? baseDir,
    String? Function()? tenantId,
    String? Function()? userId,
    DateTime Function()? clock,
  }) : _baseDir = baseDir ?? getApplicationDocumentsDirectory,
       _tenantId = tenantId,
       _userId = userId,
       _clock = clock ?? DateTime.now;

  final Future<Directory> Function() _baseDir;
  final String? Function()? _tenantId;
  final String? Function()? _userId;
  final DateTime Function() _clock;

  static const String notice =
      'رفع الصور غير متاح بعد في الخادم — تُحفظ الصورة على هذا الجهاز فقط ولا تظهر لبقيّة الفريق.';

  static String _safe(String? s) {
    final v = (s == null || s.isEmpty) ? '_' : s;
    return v.replaceAll(RegExp(r'[^A-Za-z0-9_.-]'), '_');
  }

  Future<Directory> _dir() async {
    final base = await _baseDir();
    final dir = Directory(
      '${base.path}/task_photos/${_safe(_tenantId?.call())}/${_safe(_userId?.call())}',
    );
    if (!dir.existsSync()) await dir.create(recursive: true);
    return dir;
  }

  /// ينسخ [sourcePath] إلى المجلّد الدائم ويُعيد الملفّ الجديد.
  Future<File> save(String taskId, String sourcePath) async {
    final dir = await _dir();
    final ext = sourcePath.contains('.')
        ? sourcePath.substring(sourcePath.lastIndexOf('.'))
        : '.jpg';
    final name =
        '${_safe(taskId)}__${_clock().millisecondsSinceEpoch}${ext.length <= 5 ? ext : '.jpg'}';
    return File(sourcePath).copy('${dir.path}/$name');
  }

  /// صور المهمّة على هذا الجهاز، الأقدم أوّلاً.
  Future<List<File>> photosFor(String taskId) async {
    final dir = await _dir();
    final prefix = '${_safe(taskId)}__';
    final files =
        dir
            .listSync()
            .whereType<File>()
            .where((f) => f.uri.pathSegments.last.startsWith(prefix))
            .toList()
          ..sort((a, b) => a.path.compareTo(b.path));
    return files;
  }
}
