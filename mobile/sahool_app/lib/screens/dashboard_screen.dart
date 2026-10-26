// SAHOOL — lib/screens/dashboard_screen.dart (مسار مُثبَّت: تقرؤه اختبارات CI)
// شاشة «اليوم» — الرئيسية. ما يحتاج المزارع أوّلاً: التنبيهات، مهامّ اليوم،
// الطقس الآن، ثمّ حقوله مرتّبةً بالأولويّة، ثمّ ما لم يُقَس بعد.
//
// المصدر الحقيقيّ فقط: GET /api/v1/indicators/dashboard {kpis, alerts,
// fields_summary, note_ar} + GET /api/v1/tasks + GET /api/v1/farms، وبحسب المزرعة
// المختارة حقولها وطابور أولويّاتها وطقس مركزها. لا NDVI ولا إنتاجيّة ولا أسعار
// سوق ولا «صحّة جيدة» ثابتة: لا مُنتِج لها في هذه الحمولات.
// المنطق في DashboardCubit (features/dashboard/presentation)؛ هنا العرض فقط.
import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:sahool_app/core/permissions/permissions.dart';
import 'package:sahool_app/core/routing/app_navigator.dart';
import 'package:sahool_app/core/routing/app_router.dart';
import 'package:sahool_app/core/routing/shell_scope.dart';
import 'package:sahool_app/core/theme/sahool_tokens.dart';
import 'package:sahool_app/core/theme/tokens.dart';
import 'package:sahool_app/core/widgets/widgets.dart';
import 'package:sahool_app/features/dashboard/data/dashboard_api.dart';
import 'package:sahool_app/features/dashboard/data/dashboard_snapshot_store.dart';
import 'package:sahool_app/features/dashboard/data/today_models.dart';
import 'package:sahool_app/features/dashboard/presentation/dashboard_cubit.dart';
import 'package:sahool_app/features/dashboard/presentation/dashboard_state.dart';
import 'package:sahool_app/features/dashboard/presentation/widgets/today_sections.dart';
import 'package:sahool_app/features/farms/data/farms_api.dart';
import 'package:sahool_app/features/tasks/data/tasks_api.dart';
import 'package:sahool_app/services/auth_service.dart';
import 'package:sahool_app/services/websocket_service.dart';

import '../widgets/carbon_not_measured_card.dart';
import '../widgets/water_usage_card.dart';

class DashboardScreen extends StatelessWidget {
  const DashboardScreen({
    super.key,
    this.onCreateField,
    this.createCubit,
    this.clock,
    this.role,
    this.userName,
    this.routeExists,
  });

  /// «أنشئ أوّل حقل» في حالة صفر حقول. إن لم يُمرَّر يُخفى الزرّ.
  final VoidCallback? onCreateField;

  /// للاختبارات: cubit بواجهات مزيّفة. الافتراضيّ الواجهات الحقيقيّة.
  final DashboardCubit Function()? createCubit;
  final DateTime Function()? clock;

  /// الدور (الافتراضيّ من الجلسة). viewer لا يرى «تمّ الاطّلاع» ولا «إنشاء حقل».
  final String? role;
  final String? userName;

  /// هل يوجد مسار مسجَّل (مثل '/alerts')؟ الافتراضيّ AppRouter.
  final bool Function(String path)? routeExists;

  static DashboardCubit _defaultCubit() => DashboardCubit(
    api: DashboardApi.instance,
    tasksApi: TasksApi.instance,
    farmsApi: FarmsApi.instance,
    snapshots: HiveDashboardSnapshotStore.instance,
    alertEvents: WebSocketService.instance.on('alert'),
  );

  @override
  Widget build(BuildContext context) => BlocProvider<DashboardCubit>(
    create: (_) => (createCubit ?? _defaultCubit)()..load(),
    child: _TodayView(
      onCreateField: onCreateField,
      clock: clock ?? DateTime.now,
      role: role ?? currentRole(),
      userName:
          userName ??
          AuthService.instance.userProfile?['full_name']?.toString(),
      routeExists: routeExists ?? (p) => AppRouter.instance.match(p) != null,
    ),
  );
}

class _TodayView extends StatelessWidget {
  const _TodayView({
    required this.onCreateField,
    required this.clock,
    required this.role,
    required this.userName,
    required this.routeExists,
  });

  final VoidCallback? onCreateField;
  final DateTime Function() clock;
  final String? role;
  final String? userName;
  final bool Function(String path) routeExists;

  void _openField(BuildContext context, String fieldId) =>
      context.openRoute<void>(
        '/fields/workspace?field_id=${Uri.encodeQueryComponent(fieldId)}',
      );

  void _openTab(BuildContext context, String tab, String path) {
    final shell = ShellScope.maybeOf(context);
    if (shell == null || !shell.select(tab)) context.openRoute<void>(path);
  }

  /// وجهة التنبيه: ميزة التنبيهات إن سُجِّلت، وإلّا حقل التنبيه، وإلّا لا شيء.
  VoidCallback? _alertTarget(BuildContext context, TodayAlert a) {
    if (routeExists('/alerts')) {
      return () => context.openRoute<void>(
        '/alerts?alert_id=${Uri.encodeQueryComponent(a.id)}',
      );
    }
    final fid = a.fieldId;
    if (fid != null) return () => _openField(context, fid);
    return null;
  }

  Future<void> _acknowledge(BuildContext context, TodayAlert a) async {
    final messenger = ScaffoldMessenger.maybeOf(context);
    final err = await context.read<DashboardCubit>().acknowledge(a.id);
    messenger?.showSnackBar(
      SnackBar(content: Text(err?.messageAr ?? 'سُجِّل الاطّلاع على التنبيه')),
    );
  }

  @override
  Widget build(BuildContext context) =>
      BlocBuilder<DashboardCubit, DashboardState>(
        builder: (context, s) {
          final cubit = context.read<DashboardCubit>();
          final now = clock();
          final children = <Widget>[
            TodayHeader(
              now: now,
              userName: userName,
              fetchedAt: s.fetchedAt,
              refreshing: s.refreshing,
            ),
            const SizedBox(height: SahoolSpacing.md),
          ];

          if (!s.hasData && s.status != DashboardStatus.failed) {
            children.add(const TodaySkeleton());
          } else if (!s.hasData) {
            children.add(
              ErrorState(
                error: s.error!,
                title: 'تعذّر تحميل اليوم',
                onRetry: cubit.refresh,
              ),
            );
          } else if (s.fields.isEmpty) {
            if (s.isStale) children.add(_stale(s, now, cubit));
            children.add(
              EmptyState(
                icon: Icons.terrain,
                title: 'لا توجد حقول بعد',
                message:
                    'أنشئ أوّل حقل لتبدأ بمتابعة التنبيهات والمهامّ والطقس.',
                actionLabel: (onCreateField != null && canMutate(role))
                    ? 'إنشاء أوّل حقل'
                    : null,
                onAction: onCreateField,
              ),
            );
          } else {
            children.addAll(_sections(context, s, now, cubit));
          }

          return SafeArea(
            child: RefreshIndicator(
              onRefresh: cubit.refresh,
              child: ListView(
                key: const ValueKey('today-list'),
                physics: const AlwaysScrollableScrollPhysics(),
                padding: const EdgeInsetsDirectional.all(SahoolSpacing.page),
                children: children,
              ),
            ),
          );
        },
      );

  Widget _stale(DashboardState s, DateTime now, DashboardCubit cubit) =>
      Padding(
        padding: const EdgeInsetsDirectional.only(bottom: SahoolSpacing.md),
        child: StaleBanner(
          fetchedAt: s.fetchedAt!,
          now: now,
          error: s.refreshError,
          fromSnapshot: s.fromSnapshot,
          onRetry: cubit.refresh,
        ),
      );

  List<Widget> _sections(
    BuildContext context,
    DashboardState s,
    DateTime now,
    DashboardCubit cubit,
  ) {
    const gap = SizedBox(height: SahoolSpacing.md);
    return [
      if (s.isStale) _stale(s, now, cubit),
      FarmSelector(
        farms: s.farms,
        selectedId: s.selectedFarmId,
        onSelect: cubit.selectFarm,
      ),
      gap,
      KpiGrid(kpis: s.kpis),
      gap,
      AlertsSection(
        alerts: s.visibleAlerts,
        now: now,
        fieldName: s.fieldName,
        canAcknowledge: canMutate(role) && !s.fromSnapshot,
        busy: s.ackBusy,
        onOpen: (a) => _alertTarget(context, a),
        onAcknowledge: (a) => _acknowledge(context, a),
        onSeeAll: routeExists('/alerts')
            ? () => context.openRoute<void>('/alerts')
            : null,
      ),
      gap,
      TasksSection(
        tasks: s.tasks,
        today: s.todayTasks(now),
        now: now,
        fieldName: s.fieldName,
        onSeeAll: () => _openTab(context, 'tasks', '/tasks'),
        onRetry: cubit.refresh,
      ),
      gap,
      WeatherStrip(weather: s.weather, onRetry: cubit.refresh),
      gap,
      FieldPrioritySection(
        rows: s.fieldsByPriority,
        priority: s.priority,
        onOpenField: (id) => _openField(context, id),
        onSeeAll: () => _openTab(context, 'fields', '/fields'),
      ),
      if (s.noteAr != null) ...[
        const SizedBox(height: SahoolSpacing.sm),
        Text(s.noteAr!, style: context.textStyles.bodySmall),
      ],
      gap,
      const _NotMeasuredSection(),
    ];
  }
}

/// ما لا يحسبه الخادم بعد. يُعرض صراحةً «غير مقيس» بدل أن يختفي أو يُخترَع.
class _NotMeasuredSection extends StatelessWidget {
  const _NotMeasuredSection();

  @override
  // ليس بطاقةً حاوية: البطاقتان تُعرضان مباشرةً (لا Card داخل Card).
  Widget build(BuildContext context) => Semantics(
    container: true,
    child: Column(
      key: const ValueKey('today-not-measured'),
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Row(
          children: [
            Icon(Icons.help_outline_rounded, color: context.tokens.muted),
            const SizedBox(width: SahoolSpacing.sm),
            Expanded(
              child: Semantics(
                header: true,
                child: Text(
                  'لم يُقَس بعد',
                  style: context.textStyles.titleMedium,
                ),
              ),
            ),
          ],
        ),
        const SizedBox(height: SahoolSpacing.sm),
        const Wrap(
          spacing: SahoolSpacing.sm,
          runSpacing: SahoolSpacing.xs,
          children: [
            StatusChip(
              label: 'المياه غير مقيسة',
              icon: Icons.water_drop_outlined,
            ),
            StatusChip(label: 'الكربون غير مقيس', icon: Icons.eco_outlined),
          ],
        ),
        const SizedBox(height: SahoolSpacing.sm),
        Text(
          'لا يُصدر الخادم هذه القياسات بعد، فلا نعرض لها أرقاماً.',
          style: context.textStyles.bodySmall?.copyWith(
            color: context.tokens.muted,
          ),
        ),
        const SizedBox(height: SahoolSpacing.sm),
        const WaterUsageNotMeasuredCard(),
        const CarbonNotMeasuredCard(),
      ],
    ),
  );
}
