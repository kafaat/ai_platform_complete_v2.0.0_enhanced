// SAHOOL — features/activities/presentation/farm_activity_feed_screen.dart
// «سجلّ الأنشطة»: موجز أنشطة كلّ الحقول (الأحدث أوّلاً)، ترشيح بالنوع، وتسجيل
// نشاط سريع بعد اختيار الحقل. فشل بعض الحقول يُعلَن بعدده.
import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:sahool_app/core/permissions/permissions.dart';
import 'package:sahool_app/core/theme/sahool_tokens.dart';
import 'package:sahool_app/core/theme/tokens.dart';
import 'package:sahool_app/core/widgets/widgets.dart';
import 'package:sahool_app/features/activities/data/activity_writer.dart';
import 'package:sahool_app/features/activities/data/field_activity.dart';

import 'activity_labels.dart';
import 'activity_log_sheet.dart';
import 'activity_tile.dart';
import 'farm_feed_cubit.dart';
import 'field_activities_screen.dart';

class FarmActivityFeedScreen extends StatelessWidget {
  const FarmActivityFeedScreen({
    super.key,
    this.cubit,
    this.role,
    this.writer,
    this.pending,
  });

  final FarmFeedCubit? cubit;
  final String? role;
  final ActivityWriter? writer;
  final PendingActivities? pending;

  @override
  Widget build(BuildContext context) => BlocProvider<FarmFeedCubit>(
    create: (_) => cubit ?? (FarmFeedCubit()..load()),
    child: _FeedView(
      canEdit: canMutate(role ?? currentRole()),
      role: role,
      writer: writer,
      pending: pending ?? PendingActivities.instance,
    ),
  );
}

class _FeedView extends StatelessWidget {
  const _FeedView({
    required this.canEdit,
    required this.role,
    required this.writer,
    required this.pending,
  });

  final bool canEdit;
  final String? role;
  final ActivityWriter? writer;
  final PendingActivities pending;

  Future<void> _log(BuildContext context, FarmFeedState s) async {
    final cubit = context.read<FarmFeedCubit>();
    final messenger = ScaffoldMessenger.of(context);
    final field = await showAppBottomSheet<FeedField>(
      context,
      builder: (c) => AppSheet(
        title: 'اختر الحقل',
        children: [
          for (final f in s.fields)
            AppListTile(
              title: f.name,
              icon: Icons.grid_view_rounded,
              onTap: () => Navigator.of(c).pop(f),
            ),
        ],
      ),
    );
    if (field == null || !context.mounted) return;
    final r = await showActivityLogSheet(
      context,
      fieldId: field.id,
      fieldName: field.name,
      writer: writer,
    );
    if (r == null) return;
    messenger.showSnackBar(SnackBar(content: Text(activityOutcomeMessage(r))));
    if (r.isSaved) await cubit.load();
  }

  void _openField(BuildContext context, String id, String name) =>
      Navigator.of(context).push(
        MaterialPageRoute<void>(
          builder: (_) => FieldActivitiesScreen(
            fieldId: id,
            fieldName: name,
            role: role,
            writer: writer,
            pending: pending,
          ),
        ),
      );

  @override
  Widget build(BuildContext context) {
    final cubit = context.read<FarmFeedCubit>();
    return BlocBuilder<FarmFeedCubit, FarmFeedState>(
      builder: (context, s) => AppScaffold(
        title: 'سجلّ الأنشطة',
        actions: [
          AppIconButton(
            icon: Icons.refresh_rounded,
            tooltip: 'تحديث',
            onPressed: s.refreshing ? null : cubit.load,
          ),
        ],
        floatingActionButton:
            canEdit && s.load == FeedLoad.loaded && s.fields.isNotEmpty
            ? AppFab(
                heroKey: '/activities',
                label: 'تسجيل نشاط',
                icon: Icons.add_rounded,
                onPressed: () => _log(context, s),
              )
            : null,
        body: switch (s.load) {
          FeedLoad.loading => const LoadingState(
            message: 'جارٍ تحميل الأنشطة…',
          ),
          FeedLoad.failed => ErrorState(error: s.error!, onRetry: cubit.load),
          FeedLoad.loaded => _body(context, s, cubit),
        },
      ),
    );
  }

  Widget _body(BuildContext context, FarmFeedState s, FarmFeedCubit cubit) {
    if (s.fields.isEmpty) {
      return const EmptyState(
        title: 'لا حقول بعد',
        message: 'أضف حقلاً أوّلاً من تبويب «الحقول» ثمّ سجّل أنشطته هنا.',
        icon: Icons.grid_view_rounded,
      );
    }
    final t = context.tokens;
    return ValueListenableBuilder<List<FieldActivity>>(
      valueListenable: pending,
      builder: (context, local, _) {
        final all = [...local, ...s.items];
        final visible = s.typeFilter == null
            ? all
            : all.where((a) => a.type == s.typeFilter).toList();
        final items = <Widget>[
          if (s.failedFields > 0)
            Container(
              margin: const EdgeInsetsDirectional.fromSTEB(
                SahoolSpacing.page,
                SahoolSpacing.sm,
                SahoolSpacing.page,
                0,
              ),
              padding: const EdgeInsetsDirectional.all(SahoolSpacing.md),
              decoration: BoxDecoration(
                color: t.warning.withValues(alpha: 0.12),
                borderRadius: const BorderRadius.all(
                  Radius.circular(SahoolRadius.md),
                ),
              ),
              child: Text(
                'تعذّر تحميل أنشطة ${s.failedFields} من ${s.fields.length} حقل — '
                'الموجز ناقص. ${s.error?.messageAr ?? ''}',
                style: context.textStyles.bodyMedium,
              ),
            ),
          SingleChildScrollView(
            scrollDirection: Axis.horizontal,
            padding: const EdgeInsetsDirectional.symmetric(
              horizontal: SahoolSpacing.page,
              vertical: SahoolSpacing.sm,
            ),
            child: Row(
              children: [
                Padding(
                  padding: const EdgeInsetsDirectional.only(
                    end: SahoolSpacing.sm,
                  ),
                  child: ChoiceChip(
                    label: const Text('كلّ الأنواع'),
                    selected: s.typeFilter == null,
                    onSelected: (_) => cubit.setTypeFilter(null),
                  ),
                ),
                for (final type in kActivityTypes)
                  Padding(
                    padding: const EdgeInsetsDirectional.only(
                      end: SahoolSpacing.sm,
                    ),
                    child: ChoiceChip(
                      avatar: Icon(
                        activityTypeIcon(type),
                        size: SahoolSizes.iconSm,
                      ),
                      label: Text(activityTypeAr(type)),
                      selected: s.typeFilter == type,
                      onSelected: (_) => cubit.setTypeFilter(type),
                    ),
                  ),
              ],
            ),
          ),
          if (all.isEmpty)
            EmptyState(
              title: 'لا أنشطة مسجَّلة بعد',
              message: 'سجّل أوّل نشاط (رشّ، تسميد، ريّ، حصاد…) لأحد حقولك.',
              icon: Icons.event_note_outlined,
              actionLabel: canEdit ? 'تسجيل نشاط' : null,
              onAction: canEdit ? () => _log(context, s) : null,
            )
          else if (visible.isEmpty)
            EmptyState(
              title: 'لا أنشطة من هذا النوع',
              message: 'اختر «كلّ الأنواع» لعرض الكلّ.',
              icon: Icons.filter_alt_off_outlined,
              actionLabel: 'كلّ الأنواع',
              onAction: () => cubit.setTypeFilter(null),
            ),
          for (final a in visible)
            ActivityTile(
              activity: a,
              fieldName: s.fieldName(a.fieldId),
              onTap: () =>
                  _openField(context, a.fieldId, s.fieldName(a.fieldId)),
            ),
          const SizedBox(height: 96),
        ];
        return RefreshIndicator(
          onRefresh: cubit.load,
          child: ListView(
            physics: const AlwaysScrollableScrollPhysics(),
            children: items,
          ),
        );
      },
    );
  }
}
