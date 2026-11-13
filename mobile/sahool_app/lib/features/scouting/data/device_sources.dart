// SAHOOL — features/scouting/data/device_sources.dart
// مصادر الجهاز للاستكشاف: الموقع (geolocator) والكاميرا (image_picker) وحفظ الصور
// محلّيّاً. خلف واجهات صغيرة كي تُختبر الشاشات بلا منصّة حقيقيّة.
//
// صدق: لا إحداثيّات وهميّة عند رفض الإذن أو تعطّل الخدمة — يُعاد سبب الفشل كما
// هو، والبديل الوحيد «مركز الحقل» المسجَّل على الخادم ويُعلَن أنّه مركز لا قياس.
// الصور: تُنسخ إلى مجلّد التطبيق فوراً (تبقى إن أُغلق التطبيق قبل الإرسال)، ثمّ تُرفع
// بعد التزام الدبّوس دليلاً إلى scout-ingest (v260؛ new_observation_cubit.dart). القراءة
// والاستبدال والحذف محصورة في مجلّد المستأجِر الحاليّ (لا روابط رمزيّة ولا '..').
import 'dart:async';
import 'dart:io';
import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:geolocator/geolocator.dart';
import 'package:image_picker/image_picker.dart';
import 'package:path_provider/path_provider.dart';
import 'package:sahool_app/services/auth_service.dart';

// ── الموقع ───────────────────────────────────────────────────────────

enum GpsFailureReason { serviceDisabled, denied, deniedForever, timeout, error }

sealed class GpsResult {
  const GpsResult();
}

@immutable
class GpsFix extends GpsResult {
  const GpsFix({required this.lat, required this.lng, this.accuracyM});
  final double lat;
  final double lng;

  /// نصف قطر الدقّة بالأمتار كما يبلّغه الجهاز؛ null ⇒ غير معروف.
  final double? accuracyM;
}

@immutable
class GpsFailure extends GpsResult {
  const GpsFailure(this.reason);
  final GpsFailureReason reason;

  String get messageAr => switch (reason) {
    GpsFailureReason.serviceDisabled => 'خدمة الموقع مُعطَّلة على الجهاز.',
    GpsFailureReason.denied => 'إذن الموقع مرفوض — لم يُحدَّد موقعك.',
    GpsFailureReason.deniedForever =>
      'إذن الموقع مرفوض نهائيّاً — فعّله من إعدادات التطبيق.',
    GpsFailureReason.timeout =>
      'لم يُلتقط إشارة GPS في الوقت المحدّد — جرّب في مكان مكشوف.',
    GpsFailureReason.error => 'تعذّر قراءة الموقع من الجهاز.',
  };
}

abstract class LocationSource {
  Future<GpsResult> current();

  /// يفتح إعدادات التطبيق (بعد رفض نهائيّ) أو الموقع (خدمة معطّلة).
  Future<void> openSettings(GpsFailureReason reason);
}

class GeolocatorLocationSource implements LocationSource {
  const GeolocatorLocationSource({
    this.timeLimit = const Duration(seconds: 25),
  });
  final Duration timeLimit;

  @override
  Future<GpsResult> current() async {
    try {
      if (!await Geolocator.isLocationServiceEnabled()) {
        return const GpsFailure(GpsFailureReason.serviceDisabled);
      }
      var perm = await Geolocator.checkPermission();
      if (perm == LocationPermission.denied) {
        perm = await Geolocator.requestPermission();
      }
      if (perm == LocationPermission.deniedForever) {
        return const GpsFailure(GpsFailureReason.deniedForever);
      }
      if (perm == LocationPermission.denied ||
          perm == LocationPermission.unableToDetermine) {
        return const GpsFailure(GpsFailureReason.denied);
      }
      final pos = await Geolocator.getCurrentPosition(
        desiredAccuracy: LocationAccuracy.best,
        timeLimit: timeLimit,
      );
      return GpsFix(
        lat: pos.latitude,
        lng: pos.longitude,
        accuracyM: pos.accuracy > 0 ? pos.accuracy : null,
      );
    } on TimeoutException {
      return const GpsFailure(GpsFailureReason.timeout);
    } on PermissionDeniedException {
      return const GpsFailure(GpsFailureReason.denied);
    } on LocationServiceDisabledException {
      return const GpsFailure(GpsFailureReason.serviceDisabled);
    } catch (_) {
      return const GpsFailure(GpsFailureReason.error);
    }
  }

  @override
  Future<void> openSettings(GpsFailureReason reason) async {
    try {
      if (reason == GpsFailureReason.serviceDisabled) {
        await Geolocator.openLocationSettings();
      } else {
        await Geolocator.openAppSettings();
      }
    } catch (_) {
      // لا منصّة تفتح الإعدادات — لا شيء آخر يُفعل بصدق.
    }
  }
}

// ── الكاميرا ─────────────────────────────────────────────────────────

/// صورة التُقطت للتوّ (ملفّ مؤقّت من image_picker).
@immutable
class CapturedPhoto {
  const CapturedPhoto({
    required this.path,
    required this.filename,
    required this.readBytes,
  });
  final String path;
  final String filename;
  final Future<Uint8List> Function() readBytes;
}

class PhotoCaptureException implements Exception {
  const PhotoCaptureException(this.messageAr);
  final String messageAr;
  @override
  String toString() => messageAr;
}

abstract class PhotoCapturer {
  /// null ⇒ ألغى المستخدم. يرمي [PhotoCaptureException] عند رفض الكاميرا.
  Future<CapturedPhoto?> capture({bool fromCamera = true});
}

class ImagePickerCapturer implements PhotoCapturer {
  ImagePickerCapturer([ImagePicker? picker])
    : _picker = picker ?? ImagePicker();
  final ImagePicker _picker;

  @override
  Future<CapturedPhoto?> capture({bool fromCamera = true}) async {
    try {
      final x = await _picker.pickImage(
        source: fromCamera ? ImageSource.camera : ImageSource.gallery,
        imageQuality: 80,
        maxWidth: 1920,
      );
      if (x == null) return null;
      return CapturedPhoto(
        path: x.path,
        filename: x.name,
        readBytes: x.readAsBytes,
      );
    } on PlatformException catch (e) {
      throw PhotoCaptureException(
        e.code.contains('denied')
            ? 'إذن الكاميرا مرفوض — فعّله من إعدادات التطبيق.'
            : 'تعذّر فتح الكاميرا على هذا الجهاز.',
      );
    }
  }
}

// ── حفظ الصور محلّيّاً ───────────────────────────────────────────────

abstract class LocalPhotoStore {
  /// ينسخ الصورة إلى مجلّد التطبيق باسم [pinId] ويردّ المسار الدائم.
  Future<String> keep(String pinId, CapturedPhoto photo);

  Future<void> discard(String path);

  /// مسار صورة الدبّوس على هذا الجهاز إن وُجدت.
  Future<String?> find(String pinId);

  /// بايتات نسخة الجهاز المحفوظة (لا ملفّ الالتقاط المؤقّت) للرفع. يرمي إن لم يوجد
  /// الملفّ أو كان خارج مجلّد المستأجِر الحاليّ.
  Future<Uint8List> read(String path);
}

/// `documents/scouting_photos/<tenant>/<pin_id>.<ext>` — مُنطَّق بالمستأجِر كي لا
/// يرى حساب آخر على الجهاز نفسه صور حساب سابق في قائمته.
class DeviceLocalPhotoStore implements LocalPhotoStore {
  const DeviceLocalPhotoStore();

  /// معرّف الدبّوس يصير جزءاً من مسار ملفّ: الأبجديّة والطول نفسهما في مفتاح الخادم
  /// (shared/security/scout_photo.py:_SAFE_PIN)؛ لا '/' ولا '..'.
  static final RegExp _validPinId = RegExp(r'^[A-Za-z0-9_-]{1,100}$');
  static bool isValidPinId(String pinId) => _validPinId.hasMatch(pinId);

  /// الحدّ نفسه في الخادم (MAX_PHOTO_BYTES).
  static const int maxPhotoBytes = 8 * 1024 * 1024;

  Future<Directory> _dir() async {
    final docs = await getApplicationDocumentsDirectory();
    final tenant = (AuthService.instance.tenantId ?? '_').replaceAll(
      RegExp('[^A-Za-z0-9_-]'),
      '_',
    );
    final dir = Directory('${docs.path}/scouting_photos/$tenant');
    if (!dir.existsSync()) await dir.create(recursive: true);
    return dir;
  }

  static String _ext(String filename) {
    final dot = filename.lastIndexOf('.');
    final ext = dot < 0 ? '' : filename.substring(dot + 1).toLowerCase();
    return RegExp(r'^[a-z0-9]{2,5}$').hasMatch(ext) ? ext : 'jpg';
  }

  @override
  Future<String> keep(String pinId, CapturedPhoto photo) async {
    if (!isValidPinId(pinId)) {
      throw const FormatException('معرّف الصورة غير صالح للتخزين المحلي.');
    }
    final lowerName = photo.filename.toLowerCase();
    if (!lowerName.endsWith('.jpg') &&
        !lowerName.endsWith('.jpeg') &&
        !lowerName.endsWith('.png') &&
        !lowerName.endsWith('.webp')) {
      throw const PhotoCaptureException(
        'صيغة الصورة غير مدعومة؛ اختر JPG أو PNG أو WebP.',
      );
    }
    final bytes = await photo.readBytes();
    if (bytes.isEmpty || bytes.length > maxPhotoBytes) {
      throw const PhotoCaptureException(
        'حجم الصورة غير مناسب؛ الحد الأقصى 8 ميغابايت.',
      );
    }
    final dir = await _dir();
    final target = File('${dir.path}/$pinId.${_ext(photo.filename)}');
    // لا كتابة فوق رابط رمزيّ يشير خارج مجلّد المستأجِر.
    if (await FileSystemEntity.type(target.path, followLinks: false) ==
        FileSystemEntityType.link) {
      throw const FileSystemException('Symlink is not a valid scouting photo');
    }
    if (await target.exists()) {
      await _ownedPhotoFile(target.path);
    }
    await target.writeAsBytes(bytes, flush: true);
    return target.path;
  }

  /// [path] بعد حلّ '..' والروابط، بشرط أن يقع داخل مجلّد المستأجِر الحاليّ.
  Future<File> _ownedPhotoFile(String path) async {
    if (await FileSystemEntity.type(path, followLinks: false) ==
        FileSystemEntityType.link) {
      throw const FileSystemException('Symlink is not an owned scouting photo');
    }
    final dir = await _dir();
    final canonicalDir = await dir.resolveSymbolicLinks();
    final canonical = await File(path).resolveSymbolicLinks();
    if (!canonical.startsWith('$canonicalDir/')) {
      throw const FileSystemException('Photo is outside current tenant scope');
    }
    return File(canonical);
  }

  @override
  Future<void> discard(String path) async {
    try {
      // الحذف يخضع لحدّ القراءة نفسه: تنظيفٌ متأخّر لحساب سابق لا يحذف دليل حساب آخر.
      final f = await _ownedPhotoFile(path);
      if (await f.exists()) await f.delete();
    } catch (_) {
      // مسار غريب أو مفقود ⇒ لا حذف «بأفضل جهد» عابر للمستأجِرين.
    }
  }

  @override
  Future<Uint8List> read(String path) async =>
      (await _ownedPhotoFile(path)).readAsBytes();

  @override
  Future<String?> find(String pinId) async {
    if (!isValidPinId(pinId)) return null;
    try {
      final dir = await _dir();
      for (final e in dir.listSync()) {
        if (e is File && e.uri.pathSegments.last.startsWith('$pinId.')) {
          return e.path;
        }
      }
    } catch (_) {}
    return null;
  }
}
