// SAHOOL — features/advisor/presentation/recommendations_screen.dart
// توصيات الحقل: ١) العمود الموحَّد (GET /fields/{id}/recommendations) لكلّ الأدوار،
// ٢) طلب توصية من المحرّك (POST /recommendations/for-field) مع قبول/رفض —
// لمالك/مدير/مهندس (recommendation:request). العطل والحجب يُعرَضان بسببهما.
import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:sahool_app/core/network/api_exception.dart';
import 'package:sahool_app/core/permissions/permissions.dart';
import 'package:sahool_app/core/routing/app_navigator.dart';
import 'package:sahool_app/core/theme/sahool_tokens.dart';
import 'package:sahool_app/core/theme/tokens.dart';
import 'package:sahool_app/core/widgets/widgets.dart';
import 'package:sahool_app/features/advisor/advisor_paths.dart';
import 'package:sahool_app/features/advisor/advisor_permissions.dart';
import 'package:sahool_app/features/advisor/data/advisor_api.dart';
import 'package:sahool_app/features/advisor/data/advisor_models.dart';
import 'package:sahool_app/features/advisor/presentation/recommendations_cubit.dart';
import 'package:sahool_app/features/advisor/presentation/widgets/field_picker.dart';
import 'package:sahool_app/features/advisor/presentation/widgets/recommendation_widgets.dart';
import 'package:sahool_app/features/fields/data/fields_api.dart';

/// محاصيل شائعة (مرآة CROPS في RecommendationPage.tsx) حين لا يحمل الحقل محصولاً.
const List<String> kEngineCrops = [
  'قمح صلب',
  'شعير',
  'ذرة صفراء',
  'طماطم',
  'بطاطس',
  'خضروات',
  'برسيم',
  'سورغم',
];

class RecommendationsScreen extends StatelessWidget {
  const RecommendationsScreen({
    super.key,
    this.fieldId,
    this.api,
    this.fieldLoader,
    this.role,
  });

  final String? fieldId;
  final AdvisorApi? api;
  final FieldLoader? fieldLoader;

  /// للاختبار؛ الافتراضيّ دور الجلسة.
  final String? role;

  @override
  Widget build(BuildContext context) {
    final a = api ?? AdvisorApi.instance;
    final loader = fieldLoader ?? FieldsApi.instance.listFields;
    return BlocProvider(
      create: (_) {
        final c = RecommendationsCubit(a, fieldLoader: loader);
        final id = fieldId;
        if (id != null && id.isNotEmpty) c.openWithFieldId(id);
        return c;
      },
      child: _RecommendationsView(
        api: a,
        fieldLoader: loader,
        role: role ?? currentRole(),
      ),
    );
  }
}

class _RecommendationsView extends StatelessWidget {
  const _RecommendationsView({
    required this.api,
    required this.fieldLoader,
    required this.role,
  });

  final AdvisorApi api;
  final FieldLoader fieldLoader;
  final String? role;

  Future<void> _pick(BuildContext context) async {
    final cubit = context.read<RecommendationsCubit>();
    final picked = await pickField(context, loader: fieldLoader);
    if (picked != null) await cubit.selectField(picked);
  }

  @override
  Widget build(BuildContext context) {
    return BlocBuilder<RecommendationsCubit, RecommendationsState>(
      builder: (context, state) {
        final cubit = context.read<RecommendationsCubit>();
        final field = state.field;
        return AppScaffold(
          title: 'توصيات الحقل',
          onRefresh: field == null ? null : cubit.load,
          body: ListView(
            padding: const EdgeInsets.all(SahoolSpacing.lg),
            children: [
              SectionCard(
                title: 'الحقل',
                icon: Icons.grass_outlined,
                child: Row(
                  children: [
                    Expanded(
                      child: Text(
                        field == null ? 'لم يُختَر حقل بعد' : field.name,
                        style: context.textStyles.titleMedium,
                      ),
                    ),
                    TextButton(
                      onPressed: state.requesting ? null : () => _pick(context),
                      child: Text(field == null ? 'اختر حقلاً' : 'غيّر'),
                    ),
                  ],
                ),
              ),
              if (field == null)
                const Padding(
                  padding: EdgeInsets.only(top: SahoolSpacing.xl),
                  child: EmptyState(
                    message: 'اختر حقلاً لعرض توصياته.',
                    icon: Icons.fact_check_outlined,
                  ),
                )
              else ...[
                const SizedBox(height: SahoolSpacing.lg),
                ListSectionHeader('العمود الموحَّد للحقل'),
                _Column(state: state, onRetry: cubit.load),
                const SizedBox(height: SahoolSpacing.lg),
                if (canRequestRecommendation(role))
                  _EngineSection(api: api, state: state, field: field)
                else
                  Text(
                    'طلب توصية من المحرّك وتسجيل القبول/الرفض متاحان للمالك والمدير والمهندس.',
                    style: context.textStyles.bodySmall?.copyWith(
                      color: context.tokens.muted,
                    ),
                  ),
                const SizedBox(height: SahoolSpacing.md),
                AppListTile(
                  icon: Icons.forum_outlined,
                  title: 'اسأل المستشار عن هذا الحقل',
                  onTap: () => context.openRoute(
                    AdvisorPaths.chatFor(field.id, fieldName: field.name),
                  ),
                ),
                if (canRunPestEscalation(role))
                  AppListTile(
                    icon: Icons.bug_report_outlined,
                    title: 'تصعيد آفة لهذا الحقل',
                    onTap: () => context.openRoute(
                      AdvisorPaths.pestEscalationFor(field.id),
                    ),
                  ),
              ],
            ],
          ),
        );
      },
    );
  }
}

/// نصّ خطأ التوصيات: عقد الرسالة + سبب الخادم إن أرسله (503 هنا يعني «لا توصية
/// أمكن توليدها» ويقول الخادم لماذا).
String recommendationsErrorText(ApiException e) {
  final d = e.detail;
  if (d is String && d.trim().isNotEmpty && d.trim() != e.messageAr) {
    return '${e.messageAr}\n${d.trim()}';
  }
  return e.messageAr;
}

class _Column extends StatelessWidget {
  const _Column({required this.state, required this.onRetry});
  final RecommendationsState state;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    switch (state.columnPhase) {
      case LoadPhase.idle:
      case LoadPhase.loading:
        return const SizedBox(
          height: 120,
          child: LoadingState(message: 'جارٍ تحميل التوصيات…'),
        );
      case LoadPhase.failed:
        final e = state.columnError!;
        return SectionCard(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Text(
                recommendationsErrorText(e),
                style: context.textStyles.bodyMedium,
              ),
              if (!e.isForbidden && !e.isUnauthorized) ...[
                const SizedBox(height: SahoolSpacing.sm),
                SecondaryButton(
                  label: 'أعد المحاولة',
                  icon: Icons.refresh_rounded,
                  onPressed: onRetry,
                ),
              ],
            ],
          ),
        );
      case LoadPhase.loaded:
        return _ColumnBody(set: state.column!);
    }
  }
}

class _ColumnBody extends StatelessWidget {
  const _ColumnBody({required this.set});
  final FieldRecommendationSet set;

  @override
  Widget build(BuildContext context) {
    final t = context.tokens;
    final small = context.textStyles.bodySmall?.copyWith(color: t.muted);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Wrap(
          spacing: SahoolSpacing.xs,
          runSpacing: SahoolSpacing.xs,
          children: [
            if (set.requiresReview == true)
              const StatusChip(
                label: 'تحتاج مراجعة قبل التنفيذ',
                tone: StatusTone.warning,
                icon: Icons.person_search_outlined,
              ),
            if (set.confidenceLevel != null)
              StatusChip(
                label: 'مستوى الثقة: ${set.confidenceLevel}',
                icon: Icons.speed_outlined,
              ),
            if (set.weatherAvailable == false)
              const StatusChip(
                label: 'الطقس غير متاح',
                tone: StatusTone.warning,
                icon: Icons.cloud_off_outlined,
              ),
          ],
        ),
        if (set.weatherAvailable == false)
          Padding(
            padding: const EdgeInsets.only(top: SahoolSpacing.xs),
            child: Text(
              'تُعرض فقط التوصيات التي لا تحتاج الطقس — لا قيم طقس مُفترَضة.',
              style: small,
            ),
          ),
        for (final r in set.reasonsAr.take(3)) Text('• $r', style: small),
        const SizedBox(height: SahoolSpacing.sm),
        if (set.items.isEmpty)
          const EmptyState(
            message: 'لا توصيات لهذا الحقل الآن.',
            icon: Icons.fact_check_outlined,
          ),
        for (final r in set.items)
          Padding(
            padding: const EdgeInsets.only(bottom: SahoolSpacing.sm),
            child: SectionCard(
              title: r.titleAr,
              icon: r.safety ? Icons.health_and_safety_outlined : null,
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Wrap(
                    spacing: SahoolSpacing.xs,
                    runSpacing: SahoolSpacing.xs,
                    children: [
                      if (r.category.isNotEmpty)
                        StatusChip(
                          label:
                              kRecommendationCategoryAr[r.category] ??
                              r.category,
                        ),
                      if (r.priority.isNotEmpty)
                        StatusChip(
                          label: kPriorityAr[r.priority] ?? r.priority,
                          tone: r.priority == 'high'
                              ? StatusTone.danger
                              : r.priority == 'medium'
                              ? StatusTone.warning
                              : StatusTone.success,
                          icon: Icons.flag_outlined,
                        ),
                      if (r.safety)
                        const StatusChip(
                          label: 'تنبيه سلامة',
                          tone: StatusTone.danger,
                          icon: Icons.warning_amber_rounded,
                        ),
                    ],
                  ),
                  if (r.detailAr.isNotEmpty) ...[
                    const SizedBox(height: SahoolSpacing.sm),
                    Text(r.detailAr, style: context.textStyles.bodyMedium),
                  ],
                  if (r.source != null)
                    Text('المصدر: ${r.source}', style: small),
                ],
              ),
            ),
          ),
      ],
    );
  }
}

class _EngineSection extends StatefulWidget {
  const _EngineSection({
    required this.api,
    required this.state,
    required this.field,
  });
  final AdvisorApi api;
  final RecommendationsState state;
  final FieldChoice field;

  @override
  State<_EngineSection> createState() => _EngineSectionState();
}

class _EngineSectionState extends State<_EngineSection> {
  final _stage = TextEditingController();
  String? _crop;

  @override
  void dispose() {
    _stage.dispose();
    super.dispose();
  }

  List<String> get _crops {
    final c = widget.field.crop;
    return [if (c != null && !kEngineCrops.contains(c)) c, ...kEngineCrops];
  }

  Future<void> _feedback(bool accepted, EngineRecommendation rec) async {
    final crop = _crop ?? widget.field.crop;
    if (crop == null) return;
    final ok = await showOutcomeFeedbackSheet(
      context,
      api: widget.api,
      accepted: accepted,
      crop: crop,
      fieldId: widget.field.id,
      farmId: widget.field.farmId,
      recommendationId: rec.recId,
      predictedYieldTHa: rec.predictedYieldTHa,
    );
    if (!mounted || !ok) return;
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
    final state = widget.state;
    final cubit = context.read<RecommendationsCubit>();
    final crop = _crop ?? widget.field.crop;
    final rec = state.engine;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        ListSectionHeader('توصية من المحرّك'),
        SectionCard(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Text(
                'يبني الخادم «شهادة الجودة» من ملاحظات حقلك ثمّ يشغّل المحرّك. عند '
                'نقص البيانات تظهر توصية محجوبة تُبيّن ما يلزم قياسه.',
                style: context.textStyles.bodySmall?.copyWith(
                  color: context.tokens.muted,
                ),
              ),
              AppDropdown<String>(
                label: 'المحصول',
                items: {for (final c in _crops) c: c},
                value: crop,
                onChanged: state.requesting
                    ? null
                    : (v) => setState(() => _crop = v),
              ),
              AppTextField(
                label: 'مرحلة النموّ (اختياريّ)',
                controller: _stage,
                enabled: !state.requesting,
              ),
              const SizedBox(height: SahoolSpacing.md),
              PrimaryButton(
                label: 'اطلب توصية',
                icon: Icons.auto_awesome_outlined,
                loading: state.requesting,
                onPressed: crop == null
                    ? null
                    : () => cubit.requestEngine(
                        crop: crop,
                        growthStage: _stage.text.trim(),
                      ),
              ),
              if (crop == null)
                Padding(
                  padding: const EdgeInsets.only(top: SahoolSpacing.xs),
                  child: Text(
                    'اختر المحصول أوّلاً.',
                    style: context.textStyles.bodySmall,
                  ),
                ),
            ],
          ),
        ),
        if (state.engineError != null)
          Padding(
            padding: const EdgeInsets.only(top: SahoolSpacing.sm),
            child: Semantics(
              liveRegion: true,
              child: Text(
                recommendationsErrorText(state.engineError!),
                style: context.textStyles.bodyMedium?.copyWith(
                  color: context.tokens.danger,
                ),
              ),
            ),
          ),
        if (rec != null)
          Padding(
            padding: const EdgeInsets.only(top: SahoolSpacing.sm),
            child: EngineRecommendationCard(
              rec: rec,
              onAccept: rec.delivered ? () => _feedback(true, rec) : null,
              onReject: rec.delivered ? () => _feedback(false, rec) : null,
              onDetails: rec.recId == null || !rec.delivered
                  ? null
                  : () => context.openRoute(
                      AdvisorPaths.recommendationDetail(rec.recId!),
                    ),
            ),
          ),
      ],
    );
  }
}
