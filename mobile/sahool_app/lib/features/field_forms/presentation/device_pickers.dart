/// ملتقطا الجهاز الافتراضيّان لحقول الصورة والموقع. كانت شاشة النموذج تُفتح بلا
/// ملتقط صور، فزرّ «التقاط صورة» معطَّل دائماً. لا قيم مختلَقة: فشلٌ أو رفض إذن
/// ⇒ null وتُعرض رسالة، لا إحداثيّات ولا مسار وهميّ.
library;

import 'package:geolocator/geolocator.dart';
import 'package:image_picker/image_picker.dart';

/// يلتقط صورة بالكاميرا ويعيد مسارها على الجهاز (يبقى محلّيّاً).
Future<String?> pickFieldPhoto() async {
  final file = await ImagePicker().pickImage(
    source: ImageSource.camera,
    imageQuality: 70,
    maxWidth: 1920,
  );
  return file?.path;
}

/// موقع الجهاز الحاليّ بعد طلب الإذن. أيّ تعذّر ⇒ null.
Future<({double lat, double lng})?> currentDeviceLocation() async {
  if (!await Geolocator.isLocationServiceEnabled()) return null;
  var perm = await Geolocator.checkPermission();
  if (perm == LocationPermission.denied) {
    perm = await Geolocator.requestPermission();
  }
  if (perm == LocationPermission.denied ||
      perm == LocationPermission.deniedForever) {
    return null;
  }
  final pos = await Geolocator.getCurrentPosition(
    desiredAccuracy: LocationAccuracy.high,
  );
  return (lat: pos.latitude, lng: pos.longitude);
}
