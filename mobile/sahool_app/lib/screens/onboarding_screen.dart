// SAHOOL — lib/screens/onboarding_screen.dart
// بوّابة الترحيب: تُعرَض للمستخدم المُصادَق عليه حين لا يملك أيّ حقل بعد. تشرح
// الخطوات الثلاث (أنشئ مزرعة ← ارسم الحقل ← المحصول/الموسم) وتقدّم زرّاً رئيسيّاً
// ينقل إلى تبويب «الحقول» لبدء إنشاء أوّل حقل (شاشة الإنشاء يبنيها وكيل آخر؛
// هنا نكتفي بالتنقّل عبر الـcallback إلى فهرس تبويب الحقول). RTL عربيّ، نفس الثيم.
import 'package:flutter/material.dart';

class _Step {
  final IconData icon;
  final String title;
  final String body;
  const _Step(this.icon, this.title, this.body);
}

class OnboardingScreen extends StatelessWidget {
  // يُستدعى عند الضغط على الزرّ الرئيسيّ: ينقل إلى تبويب الحقول لبدء الإنشاء.
  final VoidCallback onStart;
  const OnboardingScreen({super.key, required this.onStart});

  static const List<_Step> _steps = [
    _Step(Icons.home_work_outlined, 'أنشئ مزرعتك',
        'ابدأ بإضافة مزرعتك الأولى لتجميع حقولك تحتها.'),
    _Step(Icons.draw_outlined, 'ارسم حدود الحقل',
        'حدّد حدود الحقل على الخريطة أو أدخل مساحته وموقعه.'),
    _Step(Icons.eco_outlined, 'اختر المحصول والموسم',
        'اربط الحقل بمحصوله وموسمه لتبدأ المؤشّرات والتنبيهات.'),
  ];

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFF0F1117),
      body: SafeArea(
        child: ListView(
          padding: const EdgeInsets.all(24),
          children: [
            const SizedBox(height: 24),
            const Center(child: Text('🌿', style: TextStyle(fontSize: 56))),
            const SizedBox(height: 16),
            const Center(
              child: Text(
                'أهلاً بك في سهول',
                style: TextStyle(
                    color: Colors.white,
                    fontSize: 24,
                    fontWeight: FontWeight.bold),
              ),
            ),
            const SizedBox(height: 8),
            const Center(
              child: Text(
                'لنبدأ بإعداد أوّل حقل لك في ثلاث خطوات بسيطة.',
                textAlign: TextAlign.center,
                style: TextStyle(color: Colors.grey, fontSize: 14),
              ),
            ),
            const SizedBox(height: 32),
            for (var i = 0; i < _steps.length; i++)
              _StepTile(index: i + 1, step: _steps[i]),
            const SizedBox(height: 24),
            ElevatedButton.icon(
              onPressed: onStart,
              icon: const Icon(Icons.add_location_alt_outlined,
                  color: Colors.white),
              label: const Text('إنشاء أوّل حقل',
                  style: TextStyle(color: Colors.white, fontSize: 16)),
              style: ElevatedButton.styleFrom(
                backgroundColor: const Color(0xFF10B981),
                padding: const EdgeInsets.symmetric(vertical: 16),
                shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(12)),
              ),
            ),
            const SizedBox(height: 12),
            Center(
              child: TextButton(
                onPressed: onStart,
                child: const Text('تخطّي إلى الحقول',
                    style: TextStyle(color: Colors.grey)),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _StepTile extends StatelessWidget {
  final int index;
  final _Step step;
  const _StepTile({required this.index, required this.step});

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.only(bottom: 14),
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: const Color(0xFF1A1D29),
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: Colors.white10),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Container(
            width: 40,
            height: 40,
            decoration: BoxDecoration(
              color: const Color(0xFF10B981).withOpacity(0.15),
              borderRadius: BorderRadius.circular(10),
            ),
            child: Center(
              child: Text('$index',
                  style: const TextStyle(
                      color: Color(0xFF10B981),
                      fontWeight: FontWeight.bold,
                      fontSize: 18)),
            ),
          ),
          const SizedBox(width: 14),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Icon(step.icon,
                        color: const Color(0xFF10B981), size: 18),
                    const SizedBox(width: 8),
                    Expanded(
                      child: Text(step.title,
                          style: const TextStyle(
                              color: Colors.white,
                              fontWeight: FontWeight.bold)),
                    ),
                  ],
                ),
                const SizedBox(height: 6),
                Text(step.body,
                    style: const TextStyle(color: Colors.grey, fontSize: 13)),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
