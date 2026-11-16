// SAHOOL — features/field_plans/presentation/field_plan_screens.dart
// شاشتا «الوصفة» و«خطّة أخذ العيّنات» لحقل. كلتاهما تقرأ عبر الكاش المشفَّر:
// عند فتح التطبيق دون اتّصال تُعرض آخر نسخة محفوظة لهذا الحساب مع عمرها
// (DataAgeBanner)، لا شاشة فارغة ولا بيانات مختلَقة. بلا field_id تعرض الشاشة
// قائمة الحقول (محفوظة كذلك).
import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:sahool_app/core/offline/cached_loader.dart';
import 'package:sahool_app/core/theme/sahool_tokens.dart';
import 'package:sahool_app/core/theme/tokens.dart';
import 'package:sahool_app/core/utils/formatters.dart';
import 'package:sahool_app/core/widgets/widgets.dart';
import 'package:sahool_app/features/field_plans/data/field_plans_models.dart';
import 'package:sahool_app/features/field_plans/data/field_plans_repository.dart';

import 'cached_read_view.dart';

/// غلاف مشترك: يختار الحقل ثمّ يعرض قراءة [load] له.
class _FieldPlanShell<T> extends StatefulWidget {
  const _FieldPlanShell({
    required this.title,
    required this.fieldId,
    required this.fieldName,
    required this.repository,
    required this.load,
    required this.builder,
    this.now,
  });

  final String title;
  final String? fieldId;
  final String? fieldName;
  final FieldPlansRepository repository;
  final Future<CachedResult<T>> Function(String fieldId) load;
  final List<Widget> Function(BuildContext context, T data) builder;
  final DateTime? now;

  @override
  State<_FieldPlanShell<T>> createState() => _FieldPlanShellState<T>();
}

class _FieldPlanShellState<T> extends State<_FieldPlanShell<T>> {
  String? _fieldId;
  String? _fieldName;

  @override
  void initState() {
    super.initState();
    final id = widget.fieldId?.trim();
    _fieldId = (id == null || id.isEmpty) ? null : id;
    _fieldName = widget.fieldName;
  }

  @override
  Widget build(BuildContext context) {
    final id = _fieldId;
    if (id == null) {
      return AppScaffold(
        title: widget.title,
        body: FieldChooser(
          now: widget.now,
          loader: widget.repository.fields,
          onSelected: (f) => setState(() {
            _fieldId = f.id;
            _fieldName = f.name;
          }),
        ),
      );
    }
    final name = _fieldName;
    return AppScaffold(
      title: name == null || name.isEmpty
          ? widget.title
          : '${widget.title} — $name',
      body: BlocProvider(
        key: ValueKey(id),
        create: (_) => CachedReadCubit<T>(() => widget.load(id))..load(),
        child: CachedReadBody<T>(now: widget.now, builder: widget.builder),
      ),
    );
  }
}

// ── الوصفة ──────────────────────────────────────────────────────────────────

class RecipeScreen extends StatelessWidget {
  const RecipeScreen({
    super.key,
    this.fieldId,
    this.fieldName,
    this.repository,
    this.now,
  });

  final String? fieldId;
  final String? fieldName;
  final FieldPlansRepository? repository;
  final DateTime? now;

  @override
  Widget build(BuildContext context) {
    final repo = repository ?? FieldPlansRepository.instance;
    return _FieldPlanShell<RecipeList>(
      title: 'وصفات الحقل',
      fieldId: fieldId,
      fieldName: fieldName,
      repository: repo,
      load: repo.recipes,
      now: now,
      builder: (context, list) => [
        if (list.recipes.isEmpty)
          Padding(
            padding: const EdgeInsets.all(SahoolSpacing.lg),
            child: EmptyState(
              icon: Icons.science_outlined,
              message: list.noteAr ?? 'لا وصفات محفوظة لهذا الحقل.',
            ),
          )
        else
          for (final r in list.recipes) _RecipeCard(recipe: r),
      ],
    );
  }
}

class _RecipeCard extends StatelessWidget {
  const _RecipeCard({required this.recipe});
  final Recipe recipe;

  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsetsDirectional.fromSTEB(
          SahoolSpacing.lg,
          SahoolSpacing.md,
          SahoolSpacing.lg,
          0,
        ),
        child: SectionCard(
          title: recipe.name,
          icon: Icons.science_outlined,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                '${recipe.productLabelAr} · ${recipe.zones.length} منطقة'
                ' · ${fmtDate(recipe.createdAt)}',
                style: context.textStyles.bodySmall
                    ?.copyWith(color: context.tokens.muted),
              ),
              const SizedBox(height: SahoolSpacing.sm),
              for (var i = 0; i < recipe.zones.length; i++)
                Text(
                  'المنطقة ${i + 1}: '
                  '${fmtNumber(recipe.zones[i].rate)}'
                  '${recipe.zones[i].unit == null ? '' : ' ${recipe.zones[i].unit}'}',
                ),
            ],
          ),
        ),
      );
}

// ── خطّة أخذ العيّنات ────────────────────────────────────────────────────────

class ScanPlanScreen extends StatelessWidget {
  const ScanPlanScreen({
    super.key,
    this.fieldId,
    this.fieldName,
    this.repository,
    this.now,
  });

  final String? fieldId;
  final String? fieldName;
  final FieldPlansRepository? repository;
  final DateTime? now;

  @override
  Widget build(BuildContext context) {
    final repo = repository ?? FieldPlansRepository.instance;
    return _FieldPlanShell<ScanPlan>(
      title: 'خطّة أخذ العيّنات',
      fieldId: fieldId,
      fieldName: fieldName,
      repository: repo,
      load: repo.scanPlan,
      now: now,
      builder: (context, plan) => [
        if (!plan.computed || plan.points.isEmpty)
          Padding(
            padding: const EdgeInsets.all(SahoolSpacing.lg),
            child: EmptyState(
              icon: Icons.place_outlined,
              title: 'لم تُحسَب نقاط عيّنات',
              message: plan.userMessage ??
                  (plan.source == null
                      ? 'لا مصدر بيانات تربة لهذا الحقل.'
                      : 'لا مصدر بيانات تربة لهذا الحقل (${plan.source}).'),
            ),
          )
        else ...[
          ListSectionHeader('${plan.points.length} نقطة عيّنة'),
          for (final p in plan.points) _PointTile(point: p),
        ],
      ],
    );
  }
}

class _PointTile extends StatelessWidget {
  const _PointTile({required this.point});
  final SamplePoint point;

  @override
  Widget build(BuildContext context) {
    final where = point.lat == null || point.lon == null
        ? kNotMeasured
        : '${point.lat!.toStringAsFixed(6)}, ${point.lon!.toStringAsFixed(6)}';
    final details = [
      if (point.zoneId != null) 'المنطقة ${point.zoneId}',
      if (point.depthCm != null) 'العمق ${point.depthCm} سم',
      where,
      if (point.reasonAr != null) point.reasonAr!,
      if (point.tests.isNotEmpty) 'الفحوص: ${point.tests.join('، ')}',
    ].join('\n');
    return AppListTile(
      title: point.pointId,
      subtitle: details,
      icon: Icons.place_outlined,
    );
  }
}
