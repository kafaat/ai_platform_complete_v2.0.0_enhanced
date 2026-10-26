// SAHOOL — features/scouting/data/device_sources.dart
// مصادر الجهاز للاستكشاف: الموقع (geolocator) والكاميرا (image_picker) وحفظ الصور
// محلّيّاً. خلف واجهات صغيرة كي تُختبر الشاشات بلا منصّة حقيقيّة.
//
// صدق: لا إحداثيّات وهميّة عند رفض الإذن أو تعطّل الخدمة — يُعاد سبب الفشل كما
// هو، والبديل الوحيد «مركز الحقل» المسجَّل على الخادم ويُعلَن أنّه مركز لا قياس.
// الصور: لا نقطة تخزين في المنصّة، فتُنسخ إلى مجلّد التطبيق وتبقى على الجهاز.
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
}

/// `documents/scouting_photos/<tenant>/<pin_id>.<ext>` — مُنطَّق بالمستأجِر كي لا
/// يرى حساب آخر على الجهاز نفسه صور حساب سابق في قائمته.
class DeviceLocalPhotoStore implements LocalPhotoStore {
  const DeviceLocalPhotoStore();

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
    final dir = await _dir();
    final target = File('${dir.path}/$pinId.${_ext(photo.filename)}');
    await target.writeAsBytes(await photo.readBytes(), flush: true);
    return target.path;
  }

  @override
  Future<void> discard(String path) async {
    try {
      final f = File(path);
      if (f.existsSync()) await f.delete();
    } catch (_) {}
  }

  @override
  Future<String?> find(String pinId) async {
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
