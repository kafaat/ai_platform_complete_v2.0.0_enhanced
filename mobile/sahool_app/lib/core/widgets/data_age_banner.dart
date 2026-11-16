// SAHOOL — lib/core/widgets/data_age_banner.dart
// مؤشّر «عمر البيانات» الظاهر دائماً فوق بيانات قابلة للحفظ دون اتّصال: حاليّة ⇒
// سطر هادئ «آخر تحديث …»؛ من الكاش ⇒ لافتة تحذير تقول إنّها محفوظة على الجهاز،
// ومتى جُلِبت، ولماذا تعذّر التحديث. لا تُعرض بيانات قديمة كأنّها حاليّة.
import 'package:flutter/material.dart';
import 'package:sahool_app/core/network/api_exception.dart';
import 'package:sahool_app/core/theme/sahool_tokens.dart';
import 'package:sahool_app/core/theme/tokens.dart';
import 'package:sahool_app/core/utils/formatters.dart';

class DataAgeBanner extends StatelessWidget {
  const DataAgeBanner({
    super.key,
    required this.fetchedAt,
    this.fromCache = false,
    this.refreshError,
    this.now,
  });

  /// وقت جلب البيانات من الخادم.
  final DateTime fetchedAt;
  final bool fromCache;
  final ApiException? refreshError;
  final DateTime? now;

  /// نصّ العمر وحده (للاختبارات ولقارئ الشاشة).
  static String ageText(DateTime fetchedAt, {DateTime? now}) =>
      'عمر البيانات: ${fmtAge(fetchedAt, now: now ?? DateTime.now())}'
      ' (${fmtDateTime(fetchedAt)})';

  @override
  Widget build(BuildContext context) {
    final t = context.tokens;
    final age = ageText(fetchedAt, now: now);
    final color = fromCache ? t.warning : t.muted;
    final reason = refreshError == null ? '' : '\n${refreshError!.messageAr}';
    final text = fromCache
        ? 'غير متّصل — المعروض آخر نسخة محفوظة على الجهاز.\n$age$reason'
        : age;
    return Padding(
      padding: const EdgeInsetsDirectional.fromSTEB(
        SahoolSpacing.lg,
        SahoolSpacing.md,
        SahoolSpacing.lg,
        0,
      ),
      child: Semantics(
        liveRegion: fromCache,
        child: Container(
          key: const ValueKey('data-age-banner'),
          padding: const EdgeInsets.all(SahoolSpacing.md),
          decoration: BoxDecoration(
            color: color.withValues(alpha: fromCache ? 0.12 : 0.06),
            borderRadius: SahoolRadius.mdAll,
            border: Border.all(color: color.withValues(alpha: 0.45)),
          ),
          child: Row(
            children: [
              Icon(
                fromCache ? Icons.cloud_off_rounded : Icons.schedule_rounded,
                color: color,
              ),
              const SizedBox(width: SahoolSpacing.sm),
              Expanded(
                child: Text(text, style: context.textStyles.bodySmall),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
