// SAHOOL — features/scouting/presentation/scouting_deps.dart
// تبعيّات شاشات الاستكشاف في مكان واحد: الإنتاج يستعمل [ScoutingDeps.device]،
// والاختبارات تمرّر عميلاً مزيّفاً وموقعاً/كاميرا/صندوق إرسال مزيّفة.
import 'package:flutter/foundation.dart';
import 'package:sahool_app/core/network/connectivity_status.dart';
import 'package:sahool_app/core/permissions/permissions.dart';
import 'package:sahool_app/features/fields/data/fields_api.dart';
import 'package:sahool_app/features/offline_sync/offline_outbox.dart';

import '../data/device_sources.dart';
import '../data/scouting_api.dart';
import 'scouting_fields_cubit.dart';

@immutable
class ScoutingDeps {
  const ScoutingDeps({
    required this.api,
    required this.fieldsLoader,
    required this.location,
    required this.photos,
    required this.photoStore,
    this.outbox,
    this.connectivity,
    this.role = currentRole,
    this.showMapTiles = true,
  });

  factory ScoutingDeps.device() => ScoutingDeps(
    api: ScoutingApi.instance,
    fieldsLoader: FieldsApi.instance.listFields,
    location: const GeolocatorLocationSource(),
    photos: ImagePickerCapturer(),
    photoStore: const DeviceLocalPhotoStore(),
  );

  final ScoutingApi api;
  final FieldsLoader fieldsLoader;
  final LocationSource location;
  final PhotoCapturer photos;
  final LocalPhotoStore photoStore;

  /// null ⇒ OfflineOutbox.instance وقت الإيداع (يستبدله وكيل offline_sync).
  final OfflineOutbox? outbox;
  final ConnectivityStatus? connectivity;
  final String? Function() role;

  /// false في الاختبارات: لا بلاطات شبكة.
  final bool showMapTiles;

  bool get canRecord => canMutate(role());
}
