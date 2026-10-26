// SAHOOL — features/operations_hub/presentation/widgets/ops_refresh_banner.dart
// لافتة «تعذّر التحديث» فوق بيانات سابقة: لا تُعرض بيانات قديمة كأنّها حاليّة،
// ولا تُمسح بشاشة خطأ كاملة لمجرّد فشل تحديث. مشتركة بين وحدات العمليّات.
import 'package:flutter/material.dart';
import 'package:sahool_app/core/network/api_exception.dart';
import 'package:sahool_app/core/theme/sahool_tokens.dart';
import 'package:sahool_app/core/theme/tokens.dart';
import 'package:sahool_app/core/utils/formatters.dart';

class OpsRefreshBanner extends StatelessWidget {
  const OpsRefreshBanner({
    super.key,
    required this.error,
    this.fetchedAt,
    this.now,
  });

  final ApiException error;

  /// وقت آخر تحميل ناجح (يُعرض عمره).
  final DateTime? fetchedAt;
  final DateTime? now;

  @override
  Widget build(BuildContext context) {
    final t = context.tokens;
    final age = fetchedAt == null
        ? ''
        : ' (${fmtAge(fetchedAt, now: now ?? DateTime.now())})';
    return Padding(
      padding: const EdgeInsetsDirectional.fromSTEB(
        SahoolSpacing.lg,
        SahoolSpacing.md,
        SahoolSpacing.lg,
        0,
      ),
      child: Semantics(
        liveRegion: true,
        child: Container(
          padding: const EdgeInsets.all(SahoolSpacing.md),
          decoration: BoxDecoration(
            color: t.warning.withValues(alpha: 0.12),
            borderRadius: SahoolRadius.mdAll,
            border: Border.all(color: t.warning.withValues(alpha: 0.45)),
          ),
          child: Row(
            children: [
              Icon(Icons.sync_problem_rounded, color: t.warning),
              const SizedBox(width: SahoolSpacing.sm),
              Expanded(
                child: Text(
                  'تعذّر التحديث: ${error.messageAr}\n'
                  'المعروض من آخر تحميل ناجح$age.',
                  style: context.textStyles.bodySmall,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
