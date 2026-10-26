// SAHOOL — features/lab_sampling/presentation/gps_reader.dart
// قراءة موقع العيّنة من GPS الجهاز مع أذوناته. كلّ فشل يُرمى [GpsFailure] برسالة
// عربيّة صريحة (خدمة مطفأة، إذن مرفوض) — لا إحداثيّات افتراضيّة.
import 'package:geolocator/geolocator.dart';

import 'sample_create_cubit.dart';

class GpsFailure implements Exception {
  const GpsFailure(this.messageAr);
  final String messageAr;
  @override
  String toString() => messageAr;
}

typedef GpsReader = Future<GpsFix> Function();

Future<GpsFix> readDeviceGps() async {
  if (!await Geolocator.isLocationServiceEnabled()) {
    throw const GpsFailure(
      'خدمة الموقع غير مُفعَّلة على الجهاز — فعّلها ثمّ أعد المحاولة.',
    );
  }
  var perm = await Geolocator.checkPermission();
  if (perm == LocationPermission.denied) {
    perm = await Geolocator.requestPermission();
  }
  if (perm == LocationPermission.denied) {
    throw const GpsFailure('إذن الموقع مرفوض — تعذّر التقاط موقع العيّنة.');
  }
  if (perm == LocationPermission.deniedForever) {
    throw const GpsFailure(
      'إذن الموقع مرفوض دائماً — فعّله من إعدادات الجهاز أو أدخل الإحداثيّات يدويّاً.',
    );
  }
  final pos = await Geolocator.getCurrentPosition(
    desiredAccuracy: LocationAccuracy.best,
    timeLimit: const Duration(seconds: 30),
  );
  return GpsFix(pos.latitude, pos.longitude, accuracyM: pos.accuracy);
}
