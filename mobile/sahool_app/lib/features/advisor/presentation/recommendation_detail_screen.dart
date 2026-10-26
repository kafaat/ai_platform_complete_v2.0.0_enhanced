// SAHOOL — features/advisor/presentation/recommendation_detail_screen.dart
// توصية مُخزَّنة وشرحها (GET /api/v1/recommendations/{rec_id}) + قبول/رفض.
import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:sahool_app/core/theme/sahool_tokens.dart';
import 'package:sahool_app/core/theme/tokens.dart';
import 'package:sahool_app/core/widgets/widgets.dart';
import 'package:sahool_app/features/advisor/data/advisor_api.dart';
import 'package:sahool_app/features/advisor/presentation/recommendations_cubit.dart';
import 'package:sahool_app/features/advisor/presentation/widgets/recommendation_widgets.dart';

class RecommendationDetailScreen extends StatelessWidget {
  const RecommendationDetailScreen({super.key, required this.recId, this.api});
  final String? recId;
  final AdvisorApi? api;

  @override
  Widget build(BuildContext context) {
    final id = recId;
    if (id == null || id.isEmpty) {
      return const AppScaffold(
        title: 'تفاصيل التوصية',
        body: EmptyState(
          message: 'لم يُحدَّد معرّف التوصية (rec_id).',
          icon: Icons.link_off_rounded,
        ),
      );
    }
    final a = api ?? AdvisorApi.instance;
    return BlocProvider(
      create: (_) => RecommendationDetailCubit(a, id)..load(),
      child: _DetailView(api: a),
    );
  }
}

class _DetailView extends StatelessWidget {
  const _DetailView({required this.api});
  final AdvisorApi api;

  Future<void> _feedback(
    BuildContext context,
    bool accepted,
    String crop,
    String fieldId,
    RecommendationDetailState s,
  ) async {
    final rec = s.recommendation!;
    final ok = await showOutcomeFeedbackSheet(
      context,
      api: api,
      accepted: accepted,
      crop: crop,
      fieldId: fieldId,
      farmId: rec.farmId,
      recommendationId: rec.recId,
      predictedYieldTHa: rec.predictedYieldTHa,
    );
    if (!context.mounted || !ok) return;
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(
          accepted ? 'سُجِّل قبول التوصية.' : 'سُجِّل رفض التوصية.',
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return BlocBuilder<RecommendationDetailCubit, RecommendationDetailState>(
      builder: (context, s) {
        final cubit = context.read<RecommendationDetailCubit>();
        Widget body;
        switch (s.phase) {
          case LoadPhase.idle:
          case LoadPhase.loading:
            body = const LoadingState(message: 'جارٍ تحميل التوصية…');
          case LoadPhase.failed:
            body = ErrorState(error: s.error!, onRetry: cubit.load);
          case LoadPhase.loaded:
            final rec = s.recommendation!;
            final crop = rec.crop;
            final fieldId = rec.fieldId;
            final canFeedback =
                rec.delivered && crop != null && fieldId != null;
            final explanation = s.raw['explanation'];
            final xref = explanation is Map
                ? explanation['cross_reference']
                : null;
            final xrefNote = xref is Map ? xref['note_ar'] : null;
            body = ListView(
              padding: const EdgeInsets.all(SahoolSpacing.lg),
              children: [
                EngineRecommendationCard(
                  rec: rec,
                  onAccept: canFeedback
                      ? () => _feedback(context, true, crop, fieldId, s)
                      : null,
                  onReject: canFeedback
                      ? () => _feedback(context, false, crop, fieldId, s)
                      : null,
                ),
                if (xrefNote is String && xrefNote.trim().isNotEmpty) ...[
                  const SizedBox(height: SahoolSpacing.md),
                  SectionCard(
                    title: 'حالات مشابهة',
                    icon: Icons.compare_arrows_rounded,
                    child: Text(xrefNote, style: context.textStyles.bodyMedium),
                  ),
                ],
                if (rec.delivered && !canFeedback)
                  Padding(
                    padding: const EdgeInsets.only(top: SahoolSpacing.md),
                    child: Text(
                      'لا يمكن تسجيل القبول/الرفض: التوصية بلا حقل أو محصول مُسجَّل.',
                      style: context.textStyles.bodySmall?.copyWith(
                        color: context.tokens.muted,
                      ),
                    ),
                  ),
              ],
            );
        }
        return AppScaffold(
          title: 'تفاصيل التوصية',
          onRefresh: s.phase == LoadPhase.loaded ? cubit.load : null,
          body: body,
        );
      },
    );
  }
}
