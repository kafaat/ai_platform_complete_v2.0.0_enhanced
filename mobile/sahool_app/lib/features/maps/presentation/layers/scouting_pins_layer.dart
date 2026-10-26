// SAHOOL — features/maps/presentation/layers/scouting_pins_layer.dart
// دبابيس الكشف الحقليّ. البيانات يمرّرها المستدعي (ميزة الكشّافة تملك جلبها)؛
// هذه الطبقة عرض ونقر فقط. هدف لمس 48dp، والشدّة تُميَّز بأيقونة ولون معاً.
import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:latlong2/latlong.dart';
import 'package:sahool_app/core/theme/sahool_tokens.dart';
import 'package:sahool_app/core/theme/tokens.dart';

enum PinSeverity {
  low('منخفضة', Icons.circle_outlined),
  medium('متوسّطة', Icons.error_outline),
  high('عالية', Icons.warning_amber_rounded),
  critical('حرجة', Icons.dangerous_outlined),
  unknown('غير محدّدة', Icons.place_outlined);

  const PinSeverity(this.labelAr, this.icon);
  final String labelAr;
  final IconData icon;

  static PinSeverity parse(Object? v) => PinSeverity.values.firstWhere(
    (s) => s.name == v?.toString().toLowerCase(),
    orElse: () => PinSeverity.unknown,
  );

  Color color(SahoolTokens t) => switch (this) {
    low => t.success,
    medium => t.warning,
    high => SahoolColors.statusPoor,
    critical => t.danger,
    unknown => t.info,
  };
}

@immutable
class ScoutingPin {
  const ScoutingPin({
    required this.id,
    required this.point,
    this.severity = PinSeverity.unknown,
    this.label,
  });

  final String id;
  final LatLng point;
  final PinSeverity severity;
  final String? label;
}

class ScoutingPinsLayer extends StatelessWidget {
  const ScoutingPinsLayer({
    super.key,
    required this.pins,
    this.onTap,
    this.selectedId,
  });

  final List<ScoutingPin> pins;
  final ValueChanged<ScoutingPin>? onTap;
  final String? selectedId;

  @override
  Widget build(BuildContext context) {
    final t = context.tokens;
    final surface = Theme.of(context).colorScheme.surface;
    return MarkerLayer(
      alignment: Alignment.topCenter, // سنّ الدبوس على النقطة
      markers: [
        for (final p in pins)
          Marker(
            key: ValueKey('scout-pin-${p.id}'),
            point: p.point,
            width: SahoolSizes.minTouchTarget,
            height: SahoolSizes.minTouchTarget,
            child: Semantics(
              button: onTap != null,
              label:
                  'ملاحظة كشف — شدّة ${p.severity.labelAr}'
                  '${p.label == null ? '' : ': ${p.label}'}',
              child: GestureDetector(
                behavior: HitTestBehavior.opaque,
                onTap: onTap == null ? null : () => onTap!(p),
                child: Stack(
                  alignment: Alignment.center,
                  children: [
                    Icon(
                      Icons.location_on,
                      size: SahoolSizes.minTouchTarget,
                      color: p.severity.color(t),
                      shadows: const [Shadow(blurRadius: 3)],
                    ),
                    Padding(
                      padding: const EdgeInsetsDirectional.only(bottom: 10),
                      child: Icon(
                        p.severity.icon,
                        size: SahoolSizes.iconSm,
                        color: p.id == selectedId ? t.accent : surface,
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ),
      ],
    );
  }
}
