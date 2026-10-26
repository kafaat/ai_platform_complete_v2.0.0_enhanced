// SAHOOL — features/irrigation/presentation/today/recommendation_card.dart
// عرض مرشَّح «هل أروي اليوم؟» كما أعاده الخادم بالضبط. لا كمّيّة يعرضها الكرت ما
// لم يُعطها الخادم: insufficient_data / inconsistent_state / dependency_unavailable
// تحمل recommendation=null فلا يظهر رقم ريّ أبداً، والحدّ الأعلى للاستنزاف يُسمّى
// «حدّاً أعلى» لا «استنزافاً» ولا «كمّيّة ريّ».
import 'package:flutter/material.dart';
import 'package:sahool_app/core/theme/sahool_tokens.dart';
import 'package:sahool_app/core/theme/tokens.dart';
import 'package:sahool_app/core/widgets/widgets.dart';
import 'package:sahool_app/features/irrigation/data/irrigation_models.dart';
import 'package:sahool_app/features/irrigation/presentation/irrigation_format.dart';

class RecommendationCard extends StatelessWidget {
  const RecommendationCard({
    super.key,
    required this.recommendation,
    this.areaHa,
    this.onLogWater,
    this.onRetry,
  });

  final IrrigationRecommendation recommendation;

  /// مساحة الحقل بالهكتار — لتحويل مم إلى م³ فقط (null ⇒ لا تحويل).
  final num? areaHa;

  /// null ⇒ لا صلاحيّة لتسجيل الريّ.
  final VoidCallback? onLogWater;
  final VoidCallback? onRetry;

  @override
  Widget build(BuildContext context) {
    final r = recommendation;
    final body = switch (r.status) {
      RecommendationStatus.ready when r.isReady => _Ready(r, areaHa),
      RecommendationStatus.insufficient => _Insufficient(r),
      RecommendationStatus.inconsistent => const _Headline(
        icon: Icons.report_gmailerrorred_rounded,
        tone: StatusTone.danger,
        text: 'حالة ماء الحقل غير متّسقة — لا توصية',
      ),
      RecommendationStatus.dependencyUnavailable => const _Headline(
        icon: Icons.cloud_off_rounded,
        tone: StatusTone.warning,
        text: 'تعذّر الحصول على الطقس أو ET₀ — لا توصية الآن',
      ),
      _ => _Headline(
        icon: Icons.help_outline_rounded,
        tone: StatusTone.neutral,
        text: 'حالة غير معروفة من الخادم: ${r.status}',
      ),
    };
    final askToLog = onLogWater != null && r.irrigationKnown != true;
    return SectionCard(
      title: 'هل أروي اليوم؟',
      icon: Icons.water_drop_outlined,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          body,
          const SizedBox(height: SahoolSpacing.md),
          _AppliedWater(r),
          if (r.limitations.isNotEmpty) ...[
            const SizedBox(height: SahoolSpacing.md),
            _Limitations(r.limitations),
          ],
          const SizedBox(height: SahoolSpacing.md),
          Wrap(
            spacing: SahoolSpacing.sm,
            runSpacing: SahoolSpacing.sm,
            children: [
              StatusChip(
                label: approvalStateAr(r.approvalState),
                tone: StatusTone.info,
                icon: Icons.gavel_rounded,
              ),
              if (!r.calibrated)
                const StatusChip(
                  label: 'غير معايَر ميدانيّاً',
                  tone: StatusTone.neutral,
                ),
            ],
          ),
          if (askToLog) ...[
            const SizedBox(height: SahoolSpacing.md),
            SecondaryButton(
              label: 'سجّل ماء الريّ المضاف',
              icon: Icons.edit_note_rounded,
              onPressed: onLogWater,
            ),
          ],
          if (onRetry != null &&
              r.status == RecommendationStatus.dependencyUnavailable) ...[
            const SizedBox(height: SahoolSpacing.sm),
            SecondaryButton(
              label: 'إعادة المحاولة',
              icon: Icons.refresh_rounded,
              onPressed: onRetry,
            ),
          ],
        ],
      ),
    );
  }
}

class _Headline extends StatelessWidget {
  const _Headline({required this.icon, required this.tone, required this.text});
  final IconData icon;
  final StatusTone tone;
  final String text;

  @override
  Widget build(BuildContext context) {
    final t = context.tokens;
    final color = switch (tone) {
      StatusTone.success => t.success,
      StatusTone.warning => t.warning,
      StatusTone.danger => t.danger,
      StatusTone.info => t.info,
      StatusTone.neutral => t.muted,
    };
    return Row(
      children: [
        Icon(icon, color: color, size: SahoolSizes.iconLg),
        const SizedBox(width: SahoolSpacing.md),
        Expanded(
          child: Semantics(
            header: true,
            child: Text(text, style: context.textStyles.titleLarge),
          ),
        ),
      ],
    );
  }
}

class _Ready extends StatelessWidget {
  const _Ready(this.r, this.areaHa);
  final IrrigationRecommendation r;
  final num? areaHa;

  @override
  Widget build(BuildContext context) {
    final should = r.shouldIrrigate;
    final headline = switch (should) {
      true => const _Headline(
        icon: Icons.water_drop_rounded,
        tone: StatusTone.warning,
        text: 'نعم — يُقترَح الريّ اليوم',
      ),
      false => const _Headline(
        icon: Icons.check_circle_outline_rounded,
        tone: StatusTone.success,
        text: 'لا حاجة للريّ الآن',
      ),
      null when r.forecastHold => const _Headline(
        icon: Icons.umbrella_rounded,
        tone: StatusTone.info,
        text: 'مؤجَّل — مطر متوقَّع، أعِد التقييم بعده',
      ),
      null => const _Headline(
        icon: Icons.help_outline_rounded,
        tone: StatusTone.neutral,
        text: 'لا قرار ريّ اليوم',
      ),
    };
    final target = r.targetRefillMm;
    final net = r.netIrrigationMm;
    final tiles = <Widget>[
      if (target != null)
        MetricTile(
          label: 'كمّيّة الملء المقترحة',
          value: target,
          unit: 'مم',
          icon: Icons.opacity_rounded,
          caption: _m3Caption(target),
        ),
      if (net != null)
        MetricTile(
          label: 'الاحتياج الصافي (حسابيّ، ليس أمراً)',
          value: net,
          unit: 'مم',
          caption: _m3Caption(net),
        ),
      MetricTile(
        label: 'استنزاف منطقة الجذور',
        value: r.depletionMm,
        unit: 'مم',
      ),
    ];
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        headline,
        if (r.urgency != null && should == true) ...[
          const SizedBox(height: SahoolSpacing.sm),
          Align(
            alignment: AlignmentDirectional.centerStart,
            child: StatusChip(
              label: 'الإلحاح: ${urgencyAr(r.urgency)}',
              tone: r.urgency == 'high'
                  ? StatusTone.danger
                  : StatusTone.warning,
            ),
          ),
        ],
        const SizedBox(height: SahoolSpacing.md),
        LayoutBuilder(
          builder: (context, c) {
            final w = c.maxWidth >= 360
                ? (c.maxWidth - SahoolSpacing.sm) / 2
                : c.maxWidth;
            return Wrap(
              spacing: SahoolSpacing.sm,
              runSpacing: SahoolSpacing.sm,
              children: [for (final t in tiles) SizedBox(width: w, child: t)],
            );
          },
        ),
        if ((r.timingAr ?? '').isNotEmpty) ...[
          const SizedBox(height: SahoolSpacing.md),
          Text(r.timingAr!, style: context.textStyles.bodyLarge),
        ],
        if ((r.rationaleAr ?? '').isNotEmpty) ...[
          const SizedBox(height: SahoolSpacing.sm),
          Text(r.rationaleAr!, style: context.textStyles.bodyMedium),
        ],
        const SizedBox(height: SahoolSpacing.sm),
        Text(
          'الثقة: ${r.confidence == null ? kNotMeasured : fmtPct(r.confidence, fraction: true)}'
          '${r.generatedOn != null ? ' · ${r.generatedOn}' : ''}',
          style: context.textStyles.bodySmall,
        ),
      ],
    );
  }

  String? _m3Caption(num mm) {
    final m3 = mmToM3(mm, areaHa);
    return m3 == null ? null : '≈ ${fmtM3(m3, decimals: 0)} لمساحة الحقل';
  }
}

class _Insufficient extends StatelessWidget {
  const _Insufficient(this.r);
  final IrrigationRecommendation r;

  @override
  Widget build(BuildContext context) {
    final upper = r.depletionUpperBoundMm;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        const _Headline(
          icon: Icons.hourglass_empty_rounded,
          tone: StatusTone.warning,
          text: 'لا تكفي البيانات لقرار ريّ اليوم',
        ),
        const SizedBox(height: SahoolSpacing.sm),
        Text(
          'لا يُعرض رقم ريّ لأنّ الخادم لم يُصدر توصية.',
          style: context.textStyles.bodyMedium,
        ),
        if (upper != null) ...[
          const SizedBox(height: SahoolSpacing.md),
          MetricTile(
            label: 'حدّ أعلى للاستنزاف (ليس قياساً ولا كمّيّة ريّ)',
            value: upper,
            unit: 'مم',
            icon: Icons.vertical_align_top_rounded,
            caption: 'الريّ المضاف مجهول، فالاستنزاف الحقيقيّ قد يكون أقلّ.',
          ),
        ],
      ],
    );
  }
}

class _AppliedWater extends StatelessWidget {
  const _AppliedWater(this.r);
  final IrrigationRecommendation r;

  @override
  Widget build(BuildContext context) {
    final known = r.irrigationKnown;
    return Row(
      children: [
        Text('الريّ المضاف في الدفتر:', style: context.textStyles.bodyMedium),
        const SizedBox(width: SahoolSpacing.sm),
        StatusChip(
          label: appliedWaterAr(known),
          tone: switch (known) {
            true => StatusTone.success,
            false => StatusTone.warning,
            null => StatusTone.neutral,
          },
        ),
      ],
    );
  }
}

class _Limitations extends StatelessWidget {
  const _Limitations(this.items);
  final List<String> items;

  @override
  Widget build(BuildContext context) {
    final t = context.tokens;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Text('حدود هذه القراءة', style: context.textStyles.titleSmall),
        const SizedBox(height: SahoolSpacing.xs),
        for (final l in items)
          Padding(
            padding: const EdgeInsetsDirectional.only(top: SahoolSpacing.xs),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Icon(
                  Icons.info_outline_rounded,
                  size: SahoolSizes.iconSm,
                  color: t.muted,
                ),
                const SizedBox(width: SahoolSpacing.sm),
                Expanded(
                  child: Text(
                    limitationAr(l),
                    style: context.textStyles.bodySmall,
                  ),
                ),
              ],
            ),
          ),
      ],
    );
  }
}
