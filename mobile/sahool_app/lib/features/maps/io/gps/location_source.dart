// SAHOOL — features/maps/io/gps/location_source.dart
// مصدر الموقع خلف واجهة صغيرة كي يُختبَر مشي الحدود بتيّار مواقع مزيّف بلا جهاز.
import 'package:geolocator/geolocator.dart';

abstract class LocationSource {
  Future<bool> serviceEnabled();
  Future<LocationPermission> checkPermission();
  Future<LocationPermission> requestPermission();
  Stream<Position> positions();

  /// يفتح إعدادات التطبيق (إذن مرفوض نهائيّاً) أو الموقع (خدمة مُطفأة).
  Future<bool> openSettings({bool locationService = false});
}

/// المصدر الحقيقيّ: تيّار geolocator مستمرّ بأعلى دقّة. distanceFilter=1 م
/// يترك الترشيح الفعليّ لـ[GpsFixFilter] (حيث تُقاس الدقّة وتُرفض القفزات).
class GeolocatorLocationSource implements LocationSource {
  const GeolocatorLocationSource();

  @override
  Future<bool> serviceEnabled() => Geolocator.isLocationServiceEnabled();
  @override
  Future<LocationPermission> checkPermission() => Geolocator.checkPermission();
  @override
  Future<LocationPermission> requestPermission() =>
      Geolocator.requestPermission();
  @override
  Stream<Position> positions() => Geolocator.getPositionStream(
    locationSettings: const LocationSettings(
      accuracy: LocationAccuracy.best,
      distanceFilter: 1,
    ),
  );
  @override
  Future<bool> openSettings({bool locationService = false}) => locationService
      ? Geolocator.openLocationSettings()
      : Geolocator.openAppSettings();
}
