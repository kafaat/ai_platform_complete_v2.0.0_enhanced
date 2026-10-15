// No carbon sequestration producer exists in /api/v1/indicators/dashboard.
// Never render an invented mass or financial credit value.
import 'package:flutter/material.dart';

const String kCarbonNotMeasuredValue = 'غير مقيس';

class CarbonNotMeasuredCard extends StatelessWidget {
  const CarbonNotMeasuredCard({super.key});

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Icon(Icons.eco, color: Colors.grey, size: 28),
            const SizedBox(height: 12),
            Text(
              kCarbonNotMeasuredValue,
              style: Theme.of(context).textTheme.displayMedium?.copyWith(fontSize: 22),
            ),
            const SizedBox(height: 4),
            Text('الكربون المخزّن', style: Theme.of(context).textTheme.bodyMedium),
            const SizedBox(height: 8),
            const Text('لا يوجد مصدر قياس للكربون المخزّن أو قيمة اعتماده بعد.',
              style: TextStyle(color: Colors.grey, fontSize: 12)),
          ],
        ),
      ),
    );
  }
}
