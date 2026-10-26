// SAHOOL — features/crop_season/presentation/seasons_screen.dart
// شاشة «المواسم والأطوار» لحقل: الطور الحاليّ وماذا أفعل الآن (أعلى الشاشة،
// للموسم النشط)، ثمّ مواسم الحقل مع انتقالات الحالة (تفعيل/إغلاق) والتعديل.
// الكتابة تتطلّب FIELD_EDIT على الخادم (المالك والمدير)، فتظهر أزرارها لهما فقط.
import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:sahool_app/core/permissions/permissions.dart';
import 'package:sahool_app/core/theme/sahool_tokens.dart';
import 'package:sahool_app/core/theme/tokens.dart';
import 'package:sahool_app/core/utils/formatters.dart';
import 'package:sahool_app/core/widgets/widgets.dart';

import '../data/crop_season_api.dart';
import '../data/season_models.dart';
import 'field_picker.dart';
import 'phenology_cards.dart';
import 'season_form_screen.dart';
import 'season_state_screen.dart';
import 'seasons_cubit.dart';

class CropSeasonScreen extends StatefulWidget {
  const CropSeasonScreen({
    super.key,
    this.fieldId,
    this.fieldName,
    this.api,
    this.role,
    this.fieldsLoader,
  });

  /// null ⇒ تُعرَض قائمة الحقول للاختيار أوّلاً.
  final String? fieldId;
  final String? fieldName;
  final CropSeasonApi? api;

  /// الدور (للاختبار)؛ null ⇒ من الجلسة.
  final String? role;
  final FieldsLoader? fieldsLoader;

  @override
  State<CropSeasonScreen> createState() => _CropSeasonScreenState();
}

class _CropSeasonScreenState extends State<CropSeasonScreen> {
  String? _fieldId;
  String? _fieldName;

  @override
  void initState() {
    super.initState();
    _fieldId = widget.fieldId;
    _fieldName = widget.fieldName;
  }

  @override
  Widget build(BuildContext context) {
    final id = _fieldId;
    if (id == null || id.isEmpty) {
      return AppScaffold(
        title: 'المواسم والأطوار',
        body: FieldPickerView(
          loader: widget.fieldsLoader,
          onPicked: (f) => setState(() {
            _fieldId = f.fieldId;
            _fieldName = f.label;
          }),
        ),
      );
    }
    return BlocProvider(
      key: ValueKey(id),
      create: (_) =>
          SeasonsCubit(widget.api ?? CropSeasonApi.instance, id)..load(),
      child: _SeasonsView(
        fieldId: id,
        fieldName: _fieldName,
        api: widget.api,
        canWrite: canManage(widget.role ?? currentRole()),
      ),
    );
  }
}

class _SeasonsView extends StatelessWidget {
  const _SeasonsView({
    required this.fieldId,
    required this.fieldName,
    required this.api,
    required this.canWrite,
  });

  final String fieldId;
  final String? fieldName;
  final CropSeasonApi? api;
  final bool canWrite;

  Future<void> _openForm(
    BuildContext context,
    SeasonsLoaded s, {
    Season? original,
  }) async {
    final cubit = context.read<SeasonsCubit>();
    final messenger = ScaffoldMessenger.of(context);
    final saved = await Navigator.of(context).push<Season>(
      MaterialPageRoute(
        builder: (_) => SeasonFormScreen(
          fieldId: fieldId,
          original: original,
          catalog: s.catalog,
          hasActiveSeason: s.activeSeason != null,
          api: api,
        ),
      ),
    );
    if (saved == null) return;
    final cal = saved.calendarCheck;
    final review = cal != null && cal['requires_review'] == true;
    messenger.showSnackBar(
      SnackBar(
        content: Text(
          review && cal['reason_ar'] != null
              ? 'حُفظ الموسم. تنبيه التقويم: ${cal['reason_ar']}'
              : 'حُفظ الموسم',
        ),
      ),
    );
    await cubit.load();
  }

  Future<void> _transition(
    BuildContext context,
    Season season,
    SeasonStatus target,
  ) async {
    final cubit = context.read<SeasonsCubit>();
    final messenger = ScaffoldMessenger.of(context);
    if (target == SeasonStatus.closed) {
      final ok = await showConfirmDialog(
        context,
        title: 'إغلاق الموسم',
        message: 'إغلاق الموسم نهائيّ ولا يمكن إعادة فتحه. هل تريد المتابعة؟',
        confirmLabel: 'إغلاق الموسم',
        destructive: true,
      );
      if (!ok) return;
    }
    final err = await cubit.transition(season, target);
    messenger.showSnackBar(
      SnackBar(
        content: Text(
          err ??
              (target == SeasonStatus.closed
                  ? 'أُغلق الموسم'
                  : 'فُعِّل الموسم'),
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return BlocBuilder<SeasonsCubit, SeasonsState>(
      builder: (context, state) {
        final cubit = context.read<SeasonsCubit>();
        return AppScaffold(
          title: fieldName == null ? 'المواسم والأطوار' : 'مواسم $fieldName',
          onRefresh: cubit.load,
          floatingActionButton: canWrite && state is SeasonsLoaded
              ? AppFab(
                  heroKey: '/seasons',
                  label: 'موسم جديد',
                  icon: Icons.add,
                  onPressed: () => _openForm(context, state),
                )
              : null,
          body: switch (state) {
            SeasonsLoading() => const LoadingState(
              message: 'جارٍ تحميل المواسم…',
            ),
            SeasonsFailed(:final error) => ErrorState(
              error: error,
              onRetry: cubit.load,
            ),
            SeasonsLoaded() => _loaded(context, state),
          },
        );
      },
    );
  }

  Widget _loaded(BuildContext context, SeasonsLoaded s) {
    final active = s.activeSeason;
    return ListView(
      padding: const EdgeInsetsDirectional.fromSTEB(
        SahoolSpacing.page,
        SahoolSpacing.md,
        SahoolSpacing.page,
        96,
      ),
      children: [
        PhenologyCard(
          phenology: s.phenology,
          error: s.phenologyError,
          cropName: active == null
              ? null
              : cropLabel(active.primaryCrop, s.catalog),
        ),
        const SizedBox(height: SahoolSpacing.md),
        StageActionsCard(actions: s.stageActions, error: s.stageActionsError),
        const ListSectionHeader('مواسم الحقل'),
        if (s.seasons.isEmpty)
          EmptyState(
            title: 'لا مواسم بعد',
            message: 'لم يُسجَّل أيّ موسم لهذا الحقل.',
            icon: Icons.calendar_month_outlined,
            actionLabel: canWrite ? 'إضافة موسم' : null,
            onAction: canWrite ? () => _openForm(context, s) : null,
          ),
        for (final season in s.seasons)
          Padding(
            padding: const EdgeInsetsDirectional.only(bottom: SahoolSpacing.md),
            child: _SeasonCard(
              season: season,
              cropName: cropLabel(season.primaryCrop, s.catalog),
              busy: s.busySeasonIds.contains(season.seasonId),
              canWrite: canWrite,
              onOpen: () => Navigator.of(context).push(
                MaterialPageRoute<void>(
                  builder: (_) => SeasonStateScreen(
                    fieldId: fieldId,
                    season: season,
                    cropName: cropLabel(season.primaryCrop, s.catalog),
                    api: api,
                  ),
                ),
              ),
              onEdit: () => _openForm(context, s, original: season),
              onTransition: (t) => _transition(context, season, t),
            ),
          ),
      ],
    );
  }
}

StatusChip seasonStatusChip(Season s) => switch (s.status) {
  SeasonStatus.active => const StatusChip(
    label: 'نشط',
    tone: StatusTone.success,
    icon: Icons.play_circle_outline,
  ),
  SeasonStatus.planned => const StatusChip(
    label: 'مُخطَّط',
    tone: StatusTone.info,
    icon: Icons.schedule,
  ),
  SeasonStatus.closed => const StatusChip(
    label: 'مُغلَق',
    tone: StatusTone.neutral,
    icon: Icons.lock_outline,
  ),
  null => StatusChip(label: s.statusRaw.isEmpty ? 'غير معروفة' : s.statusRaw),
};

class _SeasonCard extends StatelessWidget {
  const _SeasonCard({
    required this.season,
    required this.cropName,
    required this.busy,
    required this.canWrite,
    required this.onOpen,
    required this.onEdit,
    required this.onTransition,
  });

  final Season season;
  final String cropName;
  final bool busy;
  final bool canWrite;
  final VoidCallback onOpen;
  final VoidCallback onEdit;
  final ValueChanged<SeasonStatus> onTransition;

  @override
  Widget build(BuildContext context) {
    final t = context.tokens;
    final status = season.status;
    final targets = status?.allowedTargets ?? const <SeasonStatus>{};
    Widget row(String label, String value) => Padding(
      padding: const EdgeInsetsDirectional.only(top: SahoolSpacing.xs),
      child: Row(
        children: [
          Expanded(
            child: Text(
              label,
              style: context.textStyles.bodyMedium?.copyWith(color: t.muted),
            ),
          ),
          Text(value, style: context.textStyles.bodyMedium),
        ],
      ),
    );
    return SectionCard(
      title: cropName,
      icon: Icons.grass_outlined,
      trailing: seasonStatusChip(season),
      onTap: onOpen,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          row('الصنف', season.cultivar ?? '—'),
          row('تاريخ الزراعة', fmtIsoDate(season.sowingDate)),
          row('الحصاد المتوقّع', fmtIsoDate(season.seasonEnd)),
          if (season.irrigationType != null)
            row(
              'الريّ',
              kIrrigationTypesAr[season.irrigationType] ??
                  season.irrigationType!,
            ),
          row('الإنتاجيّة المستهدفة', fmtYieldKgHa(season.targetYieldKgHa)),
          if (canWrite && status != SeasonStatus.closed) ...[
            const SizedBox(height: SahoolSpacing.md),
            if (busy)
              const LinearProgressIndicator()
            else
              Wrap(
                spacing: SahoolSpacing.sm,
                runSpacing: SahoolSpacing.sm,
                children: [
                  SecondaryButton(
                    label: 'تعديل',
                    icon: Icons.edit_outlined,
                    expand: false,
                    onPressed: onEdit,
                  ),
                  if (targets.contains(SeasonStatus.active))
                    SecondaryButton(
                      label: 'تفعيل الموسم',
                      icon: Icons.play_arrow_rounded,
                      expand: false,
                      onPressed: () => onTransition(SeasonStatus.active),
                    ),
                  if (targets.contains(SeasonStatus.closed))
                    SecondaryButton(
                      label: 'إغلاق الموسم',
                      icon: Icons.lock_outline,
                      expand: false,
                      onPressed: () => onTransition(SeasonStatus.closed),
                    ),
                ],
              ),
          ],
        ],
      ),
    );
  }
}
