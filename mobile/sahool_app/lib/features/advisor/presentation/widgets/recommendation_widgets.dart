// SAHOOL — features/advisor/presentation/widgets/recommendation_widgets.dart
// بطاقة توصية المحرّك + ورقة التغذية الراجعة (قبول/رفض). النصوص من الخادم حرفيّاً؛
// الإنتاج المتوقّع الغائب «غير معايَر بعد» لا رقم.
import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:sahool_app/core/theme/sahool_tokens.dart';
import 'package:sahool_app/core/theme/tokens.dart';
import 'package:sahool_app/core/utils/formatters.dart';
import 'package:sahool_app/core/widgets/widgets.dart';
import 'package:sahool_app/features/advisor/data/advisor_api.dart';
import 'package:sahool_app/features/advisor/data/advisor_models.dart';
import 'package:sahool_app/features/advisor/presentation/recommendations_cubit.dart';

/// الإنتاج المتوقّع حين لا يرسله المحرّك.
const String kYieldNotCalibrated = 'غير معايَر بعد';

class EngineRecommendationCard extends StatelessWidget {
  const EngineRecommendationCard({
    super.key,
    required this.rec,
    this.onAccept,
    this.onReject,
    this.onDetails,
  });

  final EngineRecommendation rec;
  final VoidCallback? onAccept;
  final VoidCallback? onReject;
  final VoidCallback? onDetails;

  @override
  Widget build(BuildContext context) {
    final t = context.tokens;
    final small = context.textStyles.bodySmall?.copyWith(color: t.muted);
    final yieldText = rec.predictedYieldTHa == null
        ? kYieldNotCalibrated
        : '${fmtNumber(rec.predictedYieldTHa, decimals: 2)} طن/هـ';
    return SectionCard(
      title: rec.delivered ? 'توصية المحرّك' : 'توصية محجوبة',
      icon: rec.delivered ? Icons.auto_awesome_outlined : Icons.block_outlined,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Wrap(
            spacing: SahoolSpacing.xs,
            runSpacing: SahoolSpacing.xs,
            children: [
              if (rec.qualityGrade != null)
                StatusChip(
                  label: 'جودة البيانات: ${rec.qualityGrade}',
                  tone: rec.qualityGrade == 'BLOCKED'
                      ? StatusTone.danger
                      : StatusTone.info,
                  icon: Icons.verified_outlined,
                ),
              if (rec.confidence != null)
                StatusChip(
                  label:
                      kEngineConfidenceAr[rec.confidence] ??
                      'الثقة: ${rec.confidence}',
                  tone: StatusTone.neutral,
                  icon: Icons.speed_outlined,
                ),
            ],
          ),
          if (rec.headline != null) ...[
            const SizedBox(height: SahoolSpacing.sm),
            SelectableText(
              rec.headline!,
              style: context.textStyles.titleMedium,
            ),
          ],
          if (!rec.delivered && rec.reasonAr != null) ...[
            const SizedBox(height: SahoolSpacing.sm),
            Text(
              rec.reasonAr!,
              style: context.textStyles.bodyMedium?.copyWith(color: t.warning),
            ),
          ],
          if (rec.nextActionAr != null) ...[
            const SizedBox(height: SahoolSpacing.sm),
            Text(
              'الخطوة التالية: ${rec.nextActionAr}',
              style: context.textStyles.bodyMedium,
            ),
          ],
          if (rec.delivered) ...[
            const SizedBox(height: SahoolSpacing.sm),
            Text('الإنتاج المتوقّع: $yieldText', style: small),
          ],
          if (rec.crossReferenceNoteAr != null)
            Text(rec.crossReferenceNoteAr!, style: small),
          if (rec.recId != null)
            Text('معرّف التوصية: ${rec.recId}', style: small),
          if (rec.issuedAt != null)
            Text('صدرت: ${fmtDateTime(rec.issuedAt)}', style: small),
          if (onAccept != null || onReject != null) ...[
            const SizedBox(height: SahoolSpacing.md),
            Row(
              children: [
                if (onAccept != null)
                  Expanded(
                    child: PrimaryButton(
                      label: 'قبول',
                      icon: Icons.thumb_up_alt_outlined,
                      onPressed: onAccept,
                    ),
                  ),
                if (onAccept != null && onReject != null)
                  const SizedBox(width: SahoolSpacing.sm),
                if (onReject != null)
                  Expanded(
                    child: SecondaryButton(
                      label: 'رفض',
                      icon: Icons.thumb_down_alt_outlined,
                      onPressed: onReject,
                    ),
                  ),
              ],
            ),
          ],
          if (onDetails != null) ...[
            const SizedBox(height: SahoolSpacing.sm),
            TextButton.icon(
              onPressed: onDetails,
              icon: const Icon(Icons.info_outline),
              label: const Text('التفاصيل والشرح'),
            ),
          ],
        ],
      ),
    );
  }
}

/// يفتح ورقة تأكيد القبول/الرفض. يُرجع true إن سُجّلت التغذية.
Future<bool> showOutcomeFeedbackSheet(
  BuildContext context, {
  required AdvisorApi api,
  required bool accepted,
  required String crop,
  required String fieldId,
  String? farmId,
  String? recommendationId,
  double? predictedYieldTHa,
}) async {
  final recorded = await showAppBottomSheet<bool>(
    context,
    builder: (_) => BlocProvider(
      // فتح الورقة = نيّة واحدة ⇒ مفتاح واحد لكلّ محاولاتها.
      create: (_) => OutcomeFeedbackCubit(
        api,
        accepted: accepted,
        crop: crop,
        fieldId: fieldId,
        farmId: farmId,
        recommendationId: recommendationId,
        predictedYieldTHa: predictedYieldTHa,
      ),
      child: const OutcomeFeedbackSheet(),
    ),
  );
  return recorded == true;
}

class OutcomeFeedbackSheet extends StatelessWidget {
  const OutcomeFeedbackSheet({super.key});

  @override
  Widget build(BuildContext context) {
    return BlocConsumer<OutcomeFeedbackCubit, OutcomeFeedbackState>(
      listener: (context, state) {
        if (state.phase == FeedbackPhase.recorded) {
          Navigator.of(context).pop(true);
        }
      },
      builder: (context, state) {
        final cubit = context.read<OutcomeFeedbackCubit>();
        final t = context.tokens;
        return AppSheet(
          title: cubit.accepted ? 'تأكيد قبول التوصية' : 'تأكيد رفض التوصية',
          submitLabel: cubit.accepted ? 'سجّل القبول' : 'سجّل الرفض',
          submitting: state.phase == FeedbackPhase.submitting,
          onSubmit: state.phase == FeedbackPhase.submitting
              ? null
              : cubit.submit,
          errorText: state.error?.messageAr,
          children: [
            const SizedBox(height: SahoolSpacing.sm),
            Text(
              cubit.accepted
                  ? 'سيُسجَّل أنّك قبلت هذه التوصية للحقل. يغذّي ذلك معايرة التنبّؤ؛ '
                        'لا يُنفّذ أيّ إجراء تلقائيّاً.'
                  : 'سيُسجَّل أنّك رفضت هذه التوصية للحقل.',
              style: context.textStyles.bodyMedium,
            ),
            const SizedBox(height: SahoolSpacing.sm),
            Text(
              'سبب القبول/الرفض لا يستقبله الخادم بعد؛ يُسجَّل القرار وحده.',
              style: context.textStyles.bodySmall?.copyWith(color: t.muted),
            ),
          ],
        );
      },
    );
  }
}
