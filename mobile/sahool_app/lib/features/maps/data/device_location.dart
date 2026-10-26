// SAHOOL — features/maps/data/device_location.dart
// موقع الجهاز لزرّ «موقعي» (geolocator). يردّ الدقّة مع النقطة لأنّ المزارع يجب
// أن يرى دائرة عدم اليقين لا نقطة توحي بدقّة غير موجودة. لا موقع مُختلَق: كلّ
// فشل يُرمى [LocationUnavailable] بسبب عربيّ يعرضه المستدعي كما هو.
import 'package:geolocator/geolocator.dart';
import 'package:latlong2/latlong.dart';

class LocationFix {
  const LocationFix(this.point, {this.accuracyM});
  final LatLng point;

  /// نصف قطر عدم اليقين بالمتر (null ⇒ غير معروف).
  final double? accuracyM;
}

class LocationUnavailable implements Exception {
  const LocationUnavailable(this.messageAr);
  final String messageAr;
  @override
  String toString() => messageAr;
}

typedef LocateFn = Future<LocationFix> Function();

/// قراءة موقع واحدة بدقّة عالية، بعد التحقّق من الخدمة والإذن.
Future<LocationFix> locateDevice() async {
  if (!await Geolocator.isLocationServiceEnabled()) {
    throw const LocationUnavailable('خدمة الموقع غير مُفعَّلة على الجهاز');
  }
  var perm = await Geolocator.checkPermission();
  if (perm == LocationPermission.denied) {
    perm = await Geolocator.requestPermission();
  }
  if (perm == LocationPermission.deniedForever) {
    throw const LocationUnavailable(
      'إذن الموقع مرفوض نهائيّاً — فعّله من إعدادات الجهاز',
    );
  }
  if (perm == LocationPermission.denied) {
    throw const LocationUnavailable('إذن الموقع مرفوض');
  }
  try {
    final pos = await Geolocator.getCurrentPosition(
      desiredAccuracy: LocationAccuracy.high,
      timeLimit: const Duration(seconds: 30),
    );
    return LocationFix(
      LatLng(pos.latitude, pos.longitude),
      accuracyM: pos.accuracy > 0 ? pos.accuracy : null,
    );
  } catch (_) {
    throw const LocationUnavailable(
      'تعذّر تحديد الموقع — جرّب في مكان مكشوف للسماء',
    );
  }
}
