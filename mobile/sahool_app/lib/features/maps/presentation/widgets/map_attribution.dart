// SAHOOL — features/maps/presentation/widgets/map_attribution.dart
// نسبة المصادر **ظاهرة دائماً** فوق الخريطة (شروط Esri/OSM-ODbL/CARTO تشترط عرضها).
// الودجت القديم عرض صور Esri بلا أيّ نسبة. لا نستعمل RichAttributionWidget لأنّه
// يطوي النصّ خلف زرّ «i» فلا يظهر للمزارع.
import 'package:flutter/material.dart';
import 'package:sahool_app/core/theme/sahool_tokens.dart';
import 'package:sahool_app/core/theme/tokens.dart';

class MapAttribution extends StatelessWidget {
  const MapAttribution({super.key, required this.sources});

  /// نصوص النسبة (بلا تكرار).
  final List<String> sources;

  @override
  Widget build(BuildContext context) {
    final unique = <String>{
      ...sources.where((s) => s.trim().isNotEmpty),
    }.toList();
    if (unique.isEmpty) return const SizedBox.shrink();
    final text = unique.join(' · ');
    final scheme = Theme.of(context).colorScheme;
    return Semantics(
      label: 'مصادر الخريطة: $text',
      button: true,
      child: Material(
        color: scheme.surface.withValues(alpha: 0.85),
        borderRadius: SahoolRadius.smAll,
        child: InkWell(
          borderRadius: SahoolRadius.smAll,
          onTap: () => showDialog<void>(
            context: context,
            builder: (ctx) => AlertDialog(
              title: const Text('مصادر الخريطة'),
              content: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  for (final s in unique)
                    Padding(
                      padding: const EdgeInsetsDirectional.only(
                        bottom: SahoolSpacing.xs,
                      ),
                      // النسب لاتينيّة: اتّجاهها LTR حتى داخل واجهة عربيّة.
                      child: Text(s, textDirection: TextDirection.ltr),
                    ),
                ],
              ),
              actions: [
                TextButton(
                  onPressed: () => Navigator.of(ctx).pop(),
                  child: const Text('إغلاق'),
                ),
              ],
            ),
          ),
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 260),
            child: Padding(
              padding: const EdgeInsetsDirectional.symmetric(
                horizontal: SahoolSpacing.sm,
                vertical: SahoolSpacing.xxs,
              ),
              child: Text(
                text,
                key: const ValueKey('map-attribution'),
                textDirection: TextDirection.ltr,
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
                style: TextStyle(
                  fontSize: SahoolType.caption,
                  color: context.tokens.ink,
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}
