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

const String kWaterNotMeasuredValue = 'غير مقيس';
const String kWaterNotMeasuredNote = 'لا يوجد مصدر قياس لاستهلاك المياه بعد.';

class WaterUsageNotMeasuredCard extends StatelessWidget {
  const WaterUsageNotMeasuredCard({super.key});

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Icon(Icons.water_drop, color: Colors.grey, size: 28),
            const SizedBox(height: 12),
            Text(
              kWaterNotMeasuredValue,
              style: Theme.of(context)
                  .textTheme
                  .displayMedium
                  ?.copyWith(fontSize: 22),
            ),
            const SizedBox(height: 4),
            Text(
              'استهلاك المياه',
              style: Theme.of(context).textTheme.bodyMedium,
            ),
            const SizedBox(height: 8),
            const Text(
              kWaterNotMeasuredNote,
              style: TextStyle(color: Colors.grey, fontSize: 12),
            ),
          ],
        ),
      ),
    );
  }
}
