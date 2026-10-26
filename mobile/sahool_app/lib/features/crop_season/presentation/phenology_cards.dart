// SAHOOL — features/crop_season/presentation/phenology_cards.dart
// بطاقتا الطور الحاليّ وإجراءاته. تعرضان ما يردّه الخادم فقط: اسم المرحلة،
// أيّام ما بعد الزراعة، خطّ الزمن بتواريخ عربيّة، ونصّ الإجراء كما هو. حين
// `available=false` يُعرَض `reason_ar` الخادم صراحةً — لا مرحلة ولا إجراء مُختلَق.
import 'package:flutter/material.dart';
import 'package:sahool_app/core/network/api_exception.dart';
import 'package:sahool_app/core/theme/sahool_tokens.dart';
import 'package:sahool_app/core/theme/tokens.dart';
import 'package:sahool_app/core/utils/formatters.dart';
import 'package:sahool_app/core/widgets/widgets.dart';

import '../data/season_models.dart';

/// «5 مارس 2026 – 20 أبريل 2026».
String fmtDayRange(String? start, String? end) =>
    '${fmtIsoDate(start)} – ${fmtIsoDate(end)}';

StatusChip stageStatusChip(String? status) => switch (status) {
  'current' => const StatusChip(
    label: 'جارية',
    tone: StatusTone.success,
    icon: Icons.play_circle_outline,
  ),
  'past' => const StatusChip(
    label: 'انقضت',
    tone: StatusTone.neutral,
    icon: Icons.check,
  ),
  'upcoming' => const StatusChip(
    label: 'قادمة',
    tone: StatusTone.info,
    icon: Icons.schedule,
  ),
  _ => StatusChip(label: status ?? 'غير معروفة'),
};

class _Unavailable extends StatelessWidget {
  const _Unavailable(this.text);
  final String text;

  @override
  Widget build(BuildContext context) => Row(
    children: [
      Icon(Icons.info_outline, color: context.tokens.muted),
      const SizedBox(width: SahoolSpacing.sm),
      Expanded(child: Text(text, style: context.textStyles.bodyMedium)),
    ],
  );
}

class _ErrorLine extends StatelessWidget {
  const _ErrorLine(this.error);
  final ApiException error;

  @override
  Widget build(BuildContext context) => Row(
    children: [
      Icon(Icons.error_outline, color: context.tokens.danger),
      const SizedBox(width: SahoolSpacing.sm),
      Expanded(
        child: Text(
          error.messageAr,
          style: context.textStyles.bodyMedium?.copyWith(
            color: context.tokens.danger,
          ),
        ),
      ),
    ],
  );
}

class PhenologyCard extends StatelessWidget {
  const PhenologyCard({super.key, this.phenology, this.error, this.cropName});

  final Phenology? phenology;
  final ApiException? error;

  /// اسم المحصول المعروض (من الفهرس) إن عُرف.
  final String? cropName;

  @override
  Widget build(BuildContext context) {
    final p = phenology;
    return SectionCard(
      title: 'الطور الحاليّ',
      icon: Icons.eco_outlined,
      child: error != null
          ? _ErrorLine(error!)
          : p == null
          ? const _Unavailable('غير متاح بعد')
          : !p.available
          ? _Unavailable(p.reasonAr ?? 'مراحل النموّ غير متاحة لهذا الموسم')
          : _body(context, p),
    );
  }

  Widget _body(BuildContext context, Phenology p) {
    final t = context.tokens;
    final current = p.currentStage;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Text(
          current?.nameAr ?? 'خارج دورة المحصول المُعرَّفة',
          style: context.textStyles.titleLarge,
        ),
        const SizedBox(height: SahoolSpacing.xs),
        Text(
          [
            if (cropName != null) cropName!,
            if (p.daysAfterSowing != null)
              'اليوم ${fmtNumber(p.daysAfterSowing, decimals: 0)} بعد الزراعة',
            if (p.sowingDate != null) 'زُرع في ${fmtIsoDate(p.sowingDate)}',
          ].join(' · '),
          style: context.textStyles.bodyMedium?.copyWith(color: t.muted),
        ),
        if (p.timeline.isNotEmpty) ...[
          const SizedBox(height: SahoolSpacing.md),
          for (final st in p.timeline)
            Padding(
              padding: const EdgeInsetsDirectional.only(
                bottom: SahoolSpacing.sm,
              ),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          st.nameAr ?? st.stage,
                          style: context.textStyles.titleSmall,
                        ),
                        Text(
                          fmtDayRange(st.startDate, st.endDate),
                          style: context.textStyles.bodySmall?.copyWith(
                            color: t.muted,
                          ),
                        ),
                      ],
                    ),
                  ),
                  const SizedBox(width: SahoolSpacing.sm),
                  stageStatusChip(st.status),
                ],
              ),
            ),
        ],
      ],
    );
  }
}

class StageActionsCard extends StatelessWidget {
  const StageActionsCard({super.key, this.actions, this.error});

  final StageActions? actions;
  final ApiException? error;

  @override
  Widget build(BuildContext context) {
    final a = actions;
    return SectionCard(
      title: 'ماذا أفعل الآن؟',
      icon: Icons.checklist_rtl,
      child: error != null
          ? _ErrorLine(error!)
          : a == null
          ? const _Unavailable('غير متاح بعد')
          : !a.available
          ? _Unavailable(a.reasonAr ?? 'لا إجراءات متاحة لهذه المرحلة')
          : Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                if (a.currentStageNameAr != null)
                  Text(
                    'المرحلة: ${a.currentStageNameAr}',
                    style: context.textStyles.titleSmall,
                  ),
                if (a.suggestions.isEmpty)
                  const Padding(
                    padding: EdgeInsetsDirectional.only(top: SahoolSpacing.sm),
                    child: _Unavailable(
                      'لا إجراء مقترح لهذه المرحلة من الخادم',
                    ),
                  ),
                for (final s in a.suggestions)
                  Padding(
                    padding: const EdgeInsetsDirectional.only(
                      top: SahoolSpacing.sm,
                    ),
                    child: Row(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Icon(Icons.arrow_left, color: context.colors.primary),
                        const SizedBox(width: SahoolSpacing.xs),
                        Expanded(
                          child: Text(
                            s.actionAr,
                            style: context.textStyles.bodyLarge,
                          ),
                        ),
                      ],
                    ),
                  ),
                if (a.noteAr != null) ...[
                  const SizedBox(height: SahoolSpacing.sm),
                  Text(
                    a.noteAr!,
                    style: context.textStyles.bodySmall?.copyWith(
                      color: context.tokens.muted,
                    ),
                  ),
                ],
              ],
            ),
    );
  }
}
