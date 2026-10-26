// SAHOOL — features/alerts/presentation/alert_detail_screen.dart
// تفاصيل تنبيه: الخطورة والحالة والوقت والحقل، ونصّ الخادم الذي يحمل الإجراء
// الموصى به (alert_rules.py يكتب التوصية داخل message_ar)، والإقرار.
//
// لا نقطة GET لتنبيه مفرد في الخادم؛ الرابط العميق بلا كائن يقرأ أحدث صفحة
// ويبحث فيها، وإلّا يعرض «غير موجود» صادقاً.
import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:sahool_app/core/network/api_exception.dart';
import 'package:sahool_app/core/network/idempotency.dart';
import 'package:sahool_app/core/routing/app_navigator.dart';
import 'package:sahool_app/core/theme/sahool_tokens.dart';
import 'package:sahool_app/core/theme/tokens.dart';
import 'package:sahool_app/core/utils/formatters.dart';
import 'package:sahool_app/core/widgets/widgets.dart';

import '../../weather/weather_paths.dart';
import '../alerts_paths.dart';
import '../data/alert_models.dart';
import '../data/alerts_api.dart';
import '../data/alerts_unread.dart';
import 'alert_visuals.dart';

@immutable
class AlertDetailState {
  const AlertDetailState({
    this.alert,
    this.error,
    this.acking = false,
    this.ackError,
  });
  final AlertItem? alert;
  final ApiException? error;
  final bool acking;
  final String? ackError;
  bool get loading => alert == null && error == null;
}

class AlertDetailCubit extends Cubit<AlertDetailState> {
  AlertDetailCubit(
    this._api,
    this.alertId, {
    AlertItem? initial,
    AlertsUnreadCounter? counter,
  }) : _counter = counter ?? AlertsUnreadCounter.instance,
       super(AlertDetailState(alert: initial));

  final AlertsApi _api;
  final String alertId;
  final AlertsUnreadCounter _counter;
  IdempotencyKey? _ackKey;
  bool changed = false;

  Future<void> load() async {
    if (state.alert != null) return;
    try {
      final list = await _api.listAlerts(limit: AlertsApi.pageSize);
      if (isClosed) return;
      final hit = list.where((a) => a.alertId == alertId);
      emit(
        hit.isEmpty
            ? const AlertDetailState(
                error: ApiException(
                  kind: ApiErrorKind.notFound,
                  statusCode: 404,
                  messageAr: 'العنصر غير موجود.',
                ),
              )
            : AlertDetailState(alert: hit.first),
      );
    } catch (e) {
      if (!isClosed) emit(AlertDetailState(error: ApiException.from(e)));
    }
  }

  Future<void> retry() async {
    emit(const AlertDetailState());
    await load();
  }

  Future<void> acknowledge() async {
    final a = state.alert;
    if (a == null || state.acking || !a.isActive) return;
    final key = _ackKey ??= IdempotencyKey.generate();
    emit(AlertDetailState(alert: a, acking: true));
    try {
      final updated = await _api.acknowledgeAlert(alertId, idempotencyKey: key);
      _ackKey = null;
      changed = true;
      _counter.markAcknowledged(alertId);
      if (!isClosed) emit(AlertDetailState(alert: updated));
    } catch (e) {
      if (!isClosed) {
        emit(
          AlertDetailState(
            alert: a,
            ackError: 'تعذّر الإقرار: ${ApiException.from(e).messageAr}',
          ),
        );
      }
    }
  }
}

class AlertDetailScreen extends StatelessWidget {
  const AlertDetailScreen({
    super.key,
    required this.alertId,
    this.initial,
    this.api,
    this.canAct,
    this.counter,
  });

  final String alertId;
  final AlertItem? initial;
  final AlertsApi? api;

  /// null ⇒ من دور الجلسة.
  final bool? canAct;
  final AlertsUnreadCounter? counter;

  @override
  Widget build(BuildContext context) => BlocProvider(
    create: (_) => AlertDetailCubit(
      api ?? AlertsApi.instance,
      alertId,
      initial: initial,
      counter: counter,
    )..load(),
    child: _DetailView(canAct: canAct ?? canActOnAlerts()),
  );
}

class _DetailView extends StatelessWidget {
  const _DetailView({required this.canAct});
  final bool canAct;

  @override
  Widget build(BuildContext context) {
    final cubit = context.read<AlertDetailCubit>();
    return PopScope<Object?>(
      canPop: false,
      onPopInvokedWithResult: (didPop, _) {
        if (!didPop) Navigator.of(context).pop(cubit.changed);
      },
      child: AppScaffold(
        title: 'تفاصيل التنبيه',
        body: BlocBuilder<AlertDetailCubit, AlertDetailState>(
          builder: (context, s) {
            if (s.loading) return const LoadingState();
            if (s.alert == null) {
              return ErrorState(error: s.error!, onRetry: cubit.retry);
            }
            return _body(context, s, s.alert!);
          },
        ),
      ),
    );
  }

  Widget _body(BuildContext context, AlertDetailState s, AlertItem a) {
    final t = context.tokens;
    final cubit = context.read<AlertDetailCubit>();
    final fieldId = a.fieldId;
    return ListView(
      padding: const EdgeInsets.all(SahoolSpacing.lg),
      children: [
        Wrap(
          spacing: SahoolSpacing.sm,
          runSpacing: SahoolSpacing.xs,
          children: [severityChip(a.severity), alertStatusChip(a)],
        ),
        const SizedBox(height: SahoolSpacing.md),
        Text(a.displayTitle, style: context.textStyles.headlineSmall),
        const SizedBox(height: SahoolSpacing.xs),
        Text(
          [
            alertTypeLabelAr(a.alertType),
            if (a.createdAt != null) fmtDateTime(a.createdAt),
          ].join(' · '),
          style: context.textStyles.bodySmall?.copyWith(color: t.muted),
        ),
        const SizedBox(height: SahoolSpacing.lg),
        SectionCard(
          title: 'التفاصيل والإجراء الموصى به',
          icon: Icons.assignment_turned_in_outlined,
          child: Text(
            a.messageAr ??
                'لم يُرسل الخادم نصّاً أو إجراءً موصى به لهذا التنبيه.',
            style: a.messageAr == null
                ? context.textStyles.bodyLarge?.copyWith(color: t.muted)
                : context.textStyles.bodyLarge,
          ),
        ),
        const SizedBox(height: SahoolSpacing.md),
        if (fieldId != null)
          SectionCard(
            title: 'الحقل',
            icon: Icons.layers_outlined,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Text(fieldId, style: context.textStyles.bodyMedium),
                const SizedBox(height: SahoolSpacing.sm),
                SecondaryButton(
                  label: 'فتح مساحة عمل الحقل',
                  icon: Icons.open_in_new_rounded,
                  onPressed: () => context.openRoute<void>(
                    '/fields/workspace?field_id=${Uri.encodeQueryComponent(fieldId)}',
                  ),
                ),
                const SizedBox(height: SahoolSpacing.sm),
                SecondaryButton(
                  label: 'طقس الحقل',
                  icon: Icons.cloud_outlined,
                  onPressed: () =>
                      context.openRoute<void>(WeatherPaths.field(fieldId)),
                ),
                const SizedBox(height: SahoolSpacing.sm),
                SecondaryButton(
                  label: 'كلّ تنبيهات الحقل',
                  icon: Icons.notifications_outlined,
                  onPressed: () =>
                      context.openRoute<void>(AlertsPaths.field(fieldId)),
                ),
              ],
            ),
          )
        else
          Text(
            'تنبيه عامّ غير مرتبط بحقل.',
            style: context.textStyles.bodyMedium?.copyWith(color: t.muted),
          ),
        const SizedBox(height: SahoolSpacing.xl),
        if (s.ackError != null) ...[
          Text(
            s.ackError!,
            style: context.textStyles.bodyMedium?.copyWith(color: t.danger),
          ),
          const SizedBox(height: SahoolSpacing.sm),
        ],
        if (a.isActive && canAct)
          PrimaryButton(
            label: 'إقرار التنبيه',
            icon: Icons.done_all_rounded,
            loading: s.acking,
            onPressed: cubit.acknowledge,
          )
        else if (a.isActive)
          Text(
            'الإقرار متاح للمالك والمدير فقط.',
            style: context.textStyles.bodySmall?.copyWith(color: t.muted),
          ),
      ],
    );
  }
}
