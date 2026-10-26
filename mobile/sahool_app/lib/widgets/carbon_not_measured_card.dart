// SAHOOL — lib/widgets/carbon_not_measured_card.dart
// No carbon sequestration producer exists in /api/v1/indicators/dashboard.
// Never render an invented mass or financial credit value.
import 'package:flutter/material.dart';
import 'package:sahool_app/core/theme/sahool_tokens.dart';
import 'package:sahool_app/core/theme/tokens.dart';

const String kCarbonNotMeasuredValue = 'غير مقيس';

class CarbonNotMeasuredCard extends StatelessWidget {
  const CarbonNotMeasuredCard({super.key});

  @override
  Widget build(BuildContext context) {
    final muted = context.tokens.muted;
    return Card(
      child: Padding(
        padding: const EdgeInsetsDirectional.all(SahoolSpacing.lg),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Icon(Icons.eco, color: muted, size: SahoolSizes.iconLg),
            const SizedBox(height: SahoolSpacing.md),
            Text(
              kCarbonNotMeasuredValue,
              style: context.textStyles.titleLarge?.copyWith(color: muted),
            ),
            const SizedBox(height: SahoolSpacing.xs),
            Text('الكربون المخزّن', style: context.textStyles.bodyMedium),
            const SizedBox(height: SahoolSpacing.sm),
            Text(
              'لا يوجد مصدر قياس للكربون المخزّن أو قيمة اعتماده بعد.',
              style: context.textStyles.bodySmall?.copyWith(color: muted),
            ),
          ],
        ),
      ),
    );
  }
}
