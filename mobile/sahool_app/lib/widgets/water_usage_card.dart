// SAHOOL — lib/widgets/water_usage_card.dart
// بطاقة «استهلاك المياه» في لوحة النظرة العامّة — حالة «غير مقيس» صريحة.
//
// صدق (MOBILE-DASHBOARD-SAVINGS-PCT-HAS-NO-PRODUCER-01): المُنتِج الوحيد للوحة،
// GET /api/v1/indicators/dashboard، لا يُصدِر `water_usage` (لا `this_month_m3`
// ولا `savings_pct`). كانت الشاشة تقرأ `data['water_usage']['savings_pct']` بلا
// حارس (ينهار البناء) وتعرض «توفير X% عن الشهر الماضي» بلا أساس مقيس. هذه البطاقة
// لا تأخذ حمولةً أصلاً، فلا تقرأ مفتاحاً غائباً ولا تعرض نسبةَ توفيرٍ أو حجماً.
// تُستبدَل بعرضٍ مقيس فقط حين يوجد مُنتِجٌ خلفيّ يحسب الحجمَ بوحداته وأساسه.
import 'package:flutter/material.dart';
import 'package:sahool_app/core/theme/sahool_tokens.dart';
import 'package:sahool_app/core/theme/tokens.dart';

const String kWaterNotMeasuredValue = 'غير مقيس';
const String kWaterNotMeasuredNote = 'لا يوجد مصدر قياس لاستهلاك المياه بعد.';

class WaterUsageNotMeasuredCard extends StatelessWidget {
  const WaterUsageNotMeasuredCard({super.key});

  @override
  Widget build(BuildContext context) {
    final muted = context.tokens.muted;
    return Card(
      child: Padding(
        padding: const EdgeInsetsDirectional.all(SahoolSpacing.lg),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Icon(Icons.water_drop, color: muted, size: SahoolSizes.iconLg),
            const SizedBox(height: SahoolSpacing.md),
            Text(
              kWaterNotMeasuredValue,
              style: context.textStyles.titleLarge?.copyWith(color: muted),
            ),
            const SizedBox(height: SahoolSpacing.xs),
            Text('استهلاك المياه', style: context.textStyles.bodyMedium),
            const SizedBox(height: SahoolSpacing.sm),
            Text(
              kWaterNotMeasuredNote,
              style: context.textStyles.bodySmall?.copyWith(color: muted),
            ),
          ],
        ),
      ),
    );
  }
}
