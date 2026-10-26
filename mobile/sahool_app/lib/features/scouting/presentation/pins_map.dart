// SAHOOL — features/scouting/presentation/pins_map.dart
// خريطة قراءة فقط لدبابيس الحقل. صغيرة ومحلّيّة لهذه الميزة: أدوات الخرائط والرسم
// يملكها وكيل maps. نفس مصدر البلاطات الافتراضيّ لـOfflineFieldMap (صور ArcGIS
// World Imagery، userAgentPackageName = ye.sahool.app).
import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:latlong2/latlong.dart';
import 'package:sahool_app/core/theme/sahool_tokens.dart';
import 'package:sahool_app/core/theme/tokens.dart';
import 'package:sahool_app/core/widgets/widgets.dart';

import '../data/scouting_models.dart';

const String kScoutingTileUrl =
    'https://server.arcgisonline.com/ArcGIS/rest/services/'
    'World_Imagery/MapServer/tile/{z}/{y}/{x}';

Color severityColor(BuildContext context, PinSeverity? s) {
  final t = context.tokens;
  return switch (s) {
    PinSeverity.low => t.info,
    PinSeverity.medium => t.warning,
    PinSeverity.high => t.danger,
    null => t.muted,
  };
}

class ScoutingPinsMap extends StatelessWidget {
  const ScoutingPinsMap({
    super.key,
    required this.pins,
    required this.field,
    required this.onPinTap,
    this.showTiles = true,
  });

  final List<ScoutingPin> pins;
  final ScoutingField field;
  final ValueChanged<ScoutingPin> onPinTap;
  final bool showTiles;

  @override
  Widget build(BuildContext context) {
    if (pins.isEmpty && !field.hasCenter) {
      return const EmptyState(
        icon: Icons.map_outlined,
        message: 'لا دبابيس لعرضها ولا مركز مسجَّل لهذا الحقل.',
      );
    }
    final points = [for (final p in pins) LatLng(p.lat, p.lng)];
    final centre = field.hasCenter
        ? LatLng(field.centerLat!, field.centerLng!)
        : points.first;
    final options = points.length >= 2
        ? MapOptions(
            initialCenter: centre,
            initialZoom: 15,
            maxZoom: 19,
            initialCameraFit: CameraFit.coordinates(
              coordinates: points,
              padding: const EdgeInsets.all(SahoolSpacing.xxl),
              maxZoom: 18,
            ),
          )
        : MapOptions(initialCenter: centre, initialZoom: 16, maxZoom: 19);
    return Semantics(
      label: 'خريطة دبابيس الحقل (${pins.length})',
      child: FlutterMap(
        options: options,
        children: [
          if (showTiles)
            TileLayer(
              urlTemplate: kScoutingTileUrl,
              userAgentPackageName: 'ye.sahool.app',
            ),
          MarkerLayer(
            markers: [
              for (final p in pins)
                Marker(
                  point: LatLng(p.lat, p.lng),
                  width: SahoolSizes.minTouchTarget,
                  height: SahoolSizes.minTouchTarget,
                  child: _PinMarker(pin: p, onTap: () => onPinTap(p)),
                ),
            ],
          ),
        ],
      ),
    );
  }
}

class _PinMarker extends StatelessWidget {
  const _PinMarker({required this.pin, required this.onTap});
  final ScoutingPin pin;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final color = severityColor(context, pin.severity);
    final scheme = Theme.of(context).colorScheme;
    final label =
        '${pin.category?.labelAr ?? pin.categoryWire} — '
        '${pin.severity?.labelAr ?? pin.severityWire}';
    return Semantics(
      button: true,
      label: label,
      child: Tooltip(
        message: label,
        child: InkResponse(
          onTap: onTap,
          child: Container(
            margin: const EdgeInsets.all(SahoolSpacing.xs),
            decoration: BoxDecoration(
              color: color,
              shape: BoxShape.circle,
              border: Border.all(color: scheme.surface, width: 2),
            ),
            child: Icon(
              pin.category?.icon ?? Icons.place_outlined,
              size: SahoolSizes.iconSm,
              color: scheme.surface,
            ),
          ),
        ),
      ),
    );
  }
}
