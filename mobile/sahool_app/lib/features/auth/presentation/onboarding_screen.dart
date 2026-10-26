// SAHOOL — features/auth/presentation/onboarding_screen.dart
// بوّابة الترحيب: تُعرَض للمستخدم المُصادَق عليه حين لا يملك أيّ حقل بعد. ثلاث
// شاشات قصيرة كحدّ أقصى (أنشئ مزرعة ← ارسم الحقل ← المحصول/الموسم)، قابلة للتخطّي
// من أيّ شاشة. الزرّ الأخير يبدأ إنشاء أوّل حقل عبر الـcallback (الغلاف ينقل إلى
// تبويب الحقول؛ المسار /onboarding يفتح معالج الإنشاء). RTL عربيّ ورموز السمة.
import 'package:flutter/material.dart';
import 'package:sahool_app/core/theme/sahool_tokens.dart';
import 'package:sahool_app/core/theme/tokens.dart';
import 'package:sahool_app/core/widgets/widgets.dart';

class _Step {
  final IconData icon;
  final String title;
  final String body;
  const _Step(this.icon, this.title, this.body);
}

class OnboardingScreen extends StatefulWidget {
  // يُستدعى عند إنهاء الترحيب: ينقل إلى الحقول لبدء الإنشاء.
  final VoidCallback onStart;

  /// التخطّي؛ null ⇒ نفس [onStart] (لا طريق مسدود: التخطّي يفتح التطبيق).
  final VoidCallback? onSkip;

  const OnboardingScreen({super.key, required this.onStart, this.onSkip});

  /// عدد الشاشات (حدّ أقصى ثلاث).
  static const int pageCount = 3;

  @override
  State<OnboardingScreen> createState() => _OnboardingScreenState();
}

class _OnboardingScreenState extends State<OnboardingScreen> {
  static const List<_Step> _steps = [
    _Step(
      Icons.home_work_outlined,
      'أنشئ مزرعتك',
      'أضف مزرعتك الأولى لتجمع حقولك تحتها.',
    ),
    _Step(
      Icons.draw_outlined,
      'ارسم حدود الحقل',
      'امشِ حول الحقل بالهاتف أو ارسمه على الخريطة.',
    ),
    _Step(
      Icons.eco_outlined,
      'اختر المحصول والموسم',
      'اربط الحقل بمحصوله وموسمه لتبدأ المؤشّرات والتنبيهات.',
    ),
  ];

  final _pages = PageController();
  int _index = 0;

  @override
  void dispose() {
    _pages.dispose();
    super.dispose();
  }

  bool get _last => _index == _steps.length - 1;

  void _next() {
    if (_last) {
      widget.onStart();
      return;
    }
    _pages.nextPage(duration: SahoolMotion.normal, curve: Curves.easeOut);
  }

  @override
  Widget build(BuildContext context) {
    final t = context.tokens;
    final styles = context.textStyles;
    return Scaffold(
      body: SafeArea(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Align(
              alignment: AlignmentDirectional.centerEnd,
              child: Padding(
                padding: const EdgeInsets.all(SahoolSpacing.sm),
                child: TextButton(
                  key: const ValueKey('onboarding_skip'),
                  onPressed: widget.onSkip ?? widget.onStart,
                  child: const Text('تخطّي'),
                ),
              ),
            ),
            Expanded(
              child: PageView.builder(
                controller: _pages,
                itemCount: _steps.length,
                onPageChanged: (i) => setState(() => _index = i),
                itemBuilder: (context, i) {
                  final step = _steps[i];
                  return SingleChildScrollView(
                    padding: const EdgeInsets.all(SahoolSpacing.xl),
                    child: Column(
                      children: [
                        const SizedBox(height: SahoolSpacing.xxl),
                        Container(
                          width: 120,
                          height: 120,
                          decoration: BoxDecoration(
                            color: context.colors.primary.withValues(
                              alpha: 0.12,
                            ),
                            shape: BoxShape.circle,
                          ),
                          child: Icon(
                            step.icon,
                            size: 56,
                            color: context.colors.primary,
                          ),
                        ),
                        const SizedBox(height: SahoolSpacing.xl),
                        Text(
                          step.title,
                          textAlign: TextAlign.center,
                          style: styles.headlineSmall?.copyWith(
                            fontWeight: SahoolType.bold,
                          ),
                        ),
                        const SizedBox(height: SahoolSpacing.md),
                        Text(
                          step.body,
                          textAlign: TextAlign.center,
                          style: styles.bodyLarge?.copyWith(color: t.muted),
                        ),
                      ],
                    ),
                  );
                },
              ),
            ),
            Semantics(
              label: 'الخطوة ${_index + 1} من ${_steps.length}',
              child: Row(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  for (var i = 0; i < _steps.length; i++)
                    AnimatedContainer(
                      duration: SahoolMotion.fast,
                      margin: const EdgeInsets.symmetric(
                        horizontal: SahoolSpacing.xs,
                      ),
                      width: i == _index ? SahoolSpacing.xl : SahoolSpacing.sm,
                      height: SahoolSpacing.sm,
                      decoration: BoxDecoration(
                        color: i == _index ? context.colors.primary : t.line,
                        borderRadius: BorderRadius.circular(SahoolRadius.pill),
                      ),
                    ),
                ],
              ),
            ),
            Padding(
              padding: const EdgeInsets.all(SahoolSpacing.xl),
              child: PrimaryButton(
                key: const ValueKey('onboarding_next'),
                label: _last ? 'إنشاء أوّل حقل' : 'التالي',
                icon: _last
                    ? Icons.add_location_alt_outlined
                    : Icons.arrow_forward_rounded,
                onPressed: _next,
              ),
            ),
          ],
        ),
      ),
    );
  }
}
