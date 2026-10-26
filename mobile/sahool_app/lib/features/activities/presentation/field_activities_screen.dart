// SAHOOL — features/activities/presentation/field_activities_screen.dart
// أنشطة حقل واحد: «السجلّ» (أنشطة مسجَّلة + المنتظرة للمزامنة) و«الخطّ الزمنيّ»
// الموحّد (أحداث حقيقيّة من الخادم بالتوقيت المحلّيّ). زرّ «تسجيل نشاط» للمحرّرين.
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
import 'field_activities_cubit.dart';

class FieldActivitiesScreen extends StatelessWidget {
  const FieldActivitiesScreen({
    super.key,
    required this.fieldId,
    this.fieldName,
    this.cubit,
    this.role,
    this.writer,
    this.pending,
  });

  final String fieldId;
  final String? fieldName;
  final FieldActivitiesCubit? cubit;
  final String? role;
  final ActivityWriter? writer;
  final PendingActivities? pending;

  @override
  Widget build(BuildContext context) => BlocProvider<FieldActivitiesCubit>(
    create: (_) => cubit ?? (FieldActivitiesCubit(fieldId)..load()),
    child: _FieldActivitiesView(
      fieldId: fieldId,
      fieldName: fieldName,
      canEdit: canMutate(role ?? currentRole()),
      writer: writer,
      pending: pending ?? PendingActivities.instance,
    ),
  );
}

class _FieldActivitiesView extends StatelessWidget {
  const _FieldActivitiesView({
    required this.fieldId,
    required this.fieldName,
    required this.canEdit,
    required this.writer,
    required this.pending,
  });

  final String fieldId;
  final String? fieldName;
  final bool canEdit;
  final ActivityWriter? writer;
  final PendingActivities pending;

  Future<void> _log(BuildContext context) async {
    final cubit = context.read<FieldActivitiesCubit>();
    final messenger = ScaffoldMessenger.of(context);
    final r = await showActivityLogSheet(
      context,
      fieldId: fieldId,
      fieldName: fieldName,
      writer: writer,
    );
    if (r == null) return;
    messenger.showSnackBar(SnackBar(content: Text(activityOutcomeMessage(r))));
    if (r.isSaved) await cubit.load();
  }

  @override
  Widget build(BuildContext context) {
    final cubit = context.read<FieldActivitiesCubit>();
    return DefaultTabController(
      length: 2,
      child: AppScaffold(
        title: fieldName ?? 'أنشطة الحقل',
        actions: [
          AppIconButton(
            icon: Icons.refresh_rounded,
            tooltip: 'تحديث',
            onPressed: cubit.load,
          ),
        ],
        bottom: const TabBar(
          tabs: [
            Tab(text: 'السجلّ'),
            Tab(text: 'الخطّ الزمنيّ'),
          ],
        ),
        floatingActionButton: canEdit
            ? AppFab(
                heroKey: '/activities/field',
                label: 'تسجيل نشاط',
                icon: Icons.add_rounded,
                onPressed: () => _log(context),
              )
            : null,
        body: BlocBuilder<FieldActivitiesCubit, FieldActivitiesState>(
          builder: (context, s) => TabBarView(
            children: [
              _ActivitiesTab(state: s, pending: pending, fieldId: fieldId),
              _TimelineTab(state: s),
            ],
          ),
        ),
      ),
    );
  }
}

class _ActivitiesTab extends StatelessWidget {
  const _ActivitiesTab({
    required this.state,
    required this.pending,
    required this.fieldId,
  });
  final FieldActivitiesState state;
  final PendingActivities pending;
  final String fieldId;

  @override
  Widget build(BuildContext context) {
    final cubit = context.read<FieldActivitiesCubit>();
    final slice = state.activities;
    return ValueListenableBuilder<List<FieldActivity>>(
      valueListenable: pending,
      builder: (context, _, _) {
        final local = pending.forField(fieldId);
        if (slice.loading && local.isEmpty) {
          return const LoadingState(message: 'جارٍ تحميل الأنشطة…');
        }
        final server = slice.data ?? const <FieldActivity>[];
        final items = <Widget>[
          if (slice.error != null)
            Padding(
              padding: const EdgeInsetsDirectional.all(SahoolSpacing.page),
              child: ErrorState(
                error: slice.error!,
                onRetry: cubit.loadActivities,
              ),
            ),
          for (final a in local) ActivityTile(activity: a),
          for (final a in server) ActivityTile(activity: a),
        ];
        if (slice.error == null && local.isEmpty && server.isEmpty) {
          items.add(
            const EmptyState(
              title: 'لا أنشطة مسجَّلة بعد',
              message:
                  'سجّل الرشّ والتسميد والريّ والحصاد من زرّ «تسجيل نشاط».',
              icon: Icons.event_note_outlined,
            ),
          );
        }
        items.add(const SizedBox(height: 96));
        return RefreshIndicator(
          onRefresh: cubit.loadActivities,
          child: ListView(
            physics: const AlwaysScrollableScrollPhysics(),
            padding: const EdgeInsetsDirectional.only(top: SahoolSpacing.sm),
            children: items,
          ),
        );
      },
    );
  }
}

class _TimelineTab extends StatelessWidget {
  const _TimelineTab({required this.state});
  final FieldActivitiesState state;

  @override
  Widget build(BuildContext context) {
    final cubit = context.read<FieldActivitiesCubit>();
    final slice = state.timeline;
    if (slice.loading) {
      return const LoadingState(message: 'جارٍ تحميل الخطّ الزمنيّ…');
    }
    if (slice.error != null) {
      return ErrorState(error: slice.error!, onRetry: cubit.loadTimeline);
    }
    final data = slice.data!;
    final t = context.tokens;
    final events = state.visibleEvents;
    final items = <Widget>[];
    if (data.degraded) {
      items.add(
        Padding(
          padding: const EdgeInsetsDirectional.all(SahoolSpacing.page),
          child: EmptyState(
            title: 'الخطّ الزمنيّ غير متاح الآن',
            message:
                data.degradedReasonAr ??
                'تعذّر على الخادم قراءة أحداث الحقل — هذا ليس «لا أحداث».',
            icon: Icons.cloud_off_outlined,
            actionLabel: 'إعادة المحاولة',
            onAction: cubit.loadTimeline,
          ),
        ),
      );
    } else {
      if (data.categoryCounts.isNotEmpty) {
        items.add(
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
                    label: Text('الكلّ (${data.events.length})'),
                    selected: state.category == null,
                    onSelected: (_) => cubit.setCategory(null),
                  ),
                ),
                for (final e in data.categoryCounts.entries)
                  Padding(
                    padding: const EdgeInsetsDirectional.only(
                      end: SahoolSpacing.sm,
                    ),
                    child: ChoiceChip(
                      avatar: Icon(
                        timelineCategoryIcon(e.key),
                        size: SahoolSizes.iconSm,
                      ),
                      label: Text('${timelineCategoryAr(e.key)} (${e.value})'),
                      selected: state.category == e.key,
                      onSelected: (_) => cubit.setCategory(e.key),
                    ),
                  ),
              ],
            ),
          ),
        );
      }
      if (events.isEmpty) {
        items.add(
          const EmptyState(
            title: 'لا أحداث بعد',
            message:
                'تظهر هنا العمليّات والمشاهدات وانتقالات المراحل عند تسجيلها.',
            icon: Icons.timeline_outlined,
          ),
        );
      }
      for (final e in events) {
        items.add(
          ListTile(
            minTileHeight: SahoolSizes.minTouchTarget,
            leading: Icon(timelineCategoryIcon(e.category)),
            title: Text(e.summaryAr),
            subtitle: Text(
              '${timelineCategoryAr(e.category)} · ${timelineTimeLabel(e)}',
              style: context.textStyles.bodySmall?.copyWith(color: t.muted),
            ),
          ),
        );
      }
    }
    items.add(const SizedBox(height: 96));
    return RefreshIndicator(
      onRefresh: cubit.loadTimeline,
      child: ListView(
        physics: const AlwaysScrollableScrollPhysics(),
        children: items,
      ),
    );
  }
}
