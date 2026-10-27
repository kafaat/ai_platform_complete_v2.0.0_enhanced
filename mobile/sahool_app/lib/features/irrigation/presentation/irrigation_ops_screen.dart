// SAHOOL — features/irrigation/presentation/irrigation_ops_screen.dart
// الريّ التشغيليّ: صمّامات + جداول الريّ عبر /api/v1/irrigation/*. العرض للجميع
// (irrigation:view)؛ الطلبات والإضافة والحذف للمالك والمدير والمهندس الزراعيّ
// (irrigation:manage) كما يفرض الخادم — كانت الأزرار تظهر للعامل فيردّ 403.
//
// صدق: طلب فتح/إغلاق الصمّام يسجّل النيّة فقط — التشغيل الفيزيائيّ يمرّ عبر
// موافقة بشريّة (HIL)، وأوامر المشغِّلات مجمَّدة بقرار المالك على الخادم. المفتاح
// يعرض حالة الخادم لا تمنّي المستخدم: لا يتحرّك قبل ردّ الخادم، يُعطَّل أثناء
// الطلب، يطلب تأكيداً، ويحمل مفتاح Idempotency-Key ثابتاً للنيّة. رفض الخادم
// يُعرَض بنصّه. لا fallback وهميّ. تطابق IrrigationOpsPage في الويب.
import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:sahool_app/core/network/api_exception.dart';
import 'package:sahool_app/core/network/idempotency.dart';
import 'package:sahool_app/core/permissions/permissions.dart';
import 'package:sahool_app/core/theme/sahool_tokens.dart';
import 'package:sahool_app/core/theme/tokens.dart';
import 'package:sahool_app/core/utils/formatters.dart';
import 'package:sahool_app/core/widgets/widgets.dart';
import 'package:sahool_app/features/irrigation/data/irrigation_api.dart';
import 'package:sahool_app/features/irrigation/data/irrigation_models.dart';
import 'package:sahool_app/features/irrigation/presentation/irrigation_format.dart';
import 'package:sahool_app/features/irrigation/presentation/irrigation_ops_cubit.dart';

const String kValveIntentBanner =
    'طلب فتح/إغلاق الصمّام يُسجَّل على الخادم كنيّة فقط — التشغيل الفعليّ للعتاد '
    'يتطلّب موافقة بشريّة (HIL)، وقد يرفض الخادم الطلب.';

class IrrigationOpsScreen extends StatelessWidget {
  const IrrigationOpsScreen({super.key, this.api, this.role});

  final IrrigationApi? api;

  /// للاختبار؛ null ⇒ دور الجلسة.
  final String? role;

  @override
  Widget build(BuildContext context) => BlocProvider(
    create: (_) => IrrigationOpsCubit(api ?? IrrigationApi.instance)..load(),
    child: _OpsView(canManage: canManageIrrigation(role ?? currentRole())),
  );
}

class _OpsView extends StatefulWidget {
  const _OpsView({required this.canManage});
  final bool canManage;

  @override
  State<_OpsView> createState() => _OpsViewState();
}

class _OpsViewState extends State<_OpsView>
    with SingleTickerProviderStateMixin {
  late final TabController _tabs = TabController(length: 2, vsync: this);

  @override
  void dispose() {
    _tabs.dispose();
    super.dispose();
  }

  void _snack(String text, {bool error = false}) {
    if (!mounted) return;
    final t = context.tokens;
    ScaffoldMessenger.of(context)
      ..hideCurrentSnackBar()
      ..showSnackBar(
        SnackBar(content: Text(text), backgroundColor: error ? t.danger : null),
      );
  }

  void _report(OpsOutcome o) {
    if (o.ignored) return;
    if (o.ok) {
      _snack(o.messageAr!);
    } else {
      _snack(refusalText(o.error!), error: true);
    }
  }

  Future<void> _requestValve(Valve v, bool open) async {
    final cubit = context.read<IrrigationOpsCubit>();
    if (cubit.state.isValvePending(v.id)) return;
    final target = open ? 'open' : 'closed';
    final confirmed = await showConfirmDialog(
      context,
      title: open ? 'طلب فتح الصمّام' : 'طلب إغلاق الصمّام',
      message:
          '${open ? 'فتح' : 'إغلاق'} «${v.name}»؟\n'
          'يُسجَّل الطلب على الخادم؛ التشغيل الفعليّ يتطلّب موافقة بشريّة.',
      confirmLabel: open ? 'اطلب الفتح' : 'اطلب الإغلاق',
    );
    if (!confirmed || !mounted) return;
    _report(await cubit.requestValveState(v.id, target));
  }

  Future<void> _deleteSchedule(IrrigationSchedule s) async {
    final cubit = context.read<IrrigationOpsCubit>();
    final confirmed = await showConfirmDialog(
      context,
      title: 'حذف الجدول',
      message: 'حذف «${s.name}» نهائيّاً؟',
      confirmLabel: 'حذف',
      destructive: true,
    );
    if (!confirmed || !mounted) return;
    _report(await cubit.deleteSchedule(s.id));
  }

  Future<void> _add() async {
    final cubit = context.read<IrrigationOpsCubit>();
    final valveTab = _tabs.index == 0;
    final created = await showAppBottomSheet<bool>(
      context,
      builder: (_) => valveTab
          ? _AddValveSheet(api: cubit.api)
          : _AddScheduleSheet(api: cubit.api, valves: cubit.state.valves),
    );
    if (created == true && mounted) {
      _snack(valveTab ? 'سُجّل الصمّام.' : 'أُنشئ جدول الريّ.');
      await cubit.refresh();
    }
  }

  @override
  Widget build(BuildContext context) {
    final cubit = context.read<IrrigationOpsCubit>();
    return AppScaffold(
      title: 'الريّ التشغيليّ',
      actions: [
        AppIconButton(
          icon: Icons.refresh_rounded,
          tooltip: 'تحديث',
          onPressed: cubit.load,
        ),
      ],
      bottom: TabBar(
        controller: _tabs,
        tabs: const [
          Tab(text: 'الصمّامات'),
          Tab(text: 'الجداول'),
        ],
      ),
      floatingActionButton: widget.canManage
          ? AnimatedBuilder(
              animation: _tabs,
              builder: (_, _) => AppFab(
                heroKey: 'irrigation-ops',
                label: _tabs.index == 0 ? 'صمّام' : 'جدول',
                icon: Icons.add_rounded,
                onPressed: _add,
              ),
            )
          : null,
      body: BlocBuilder<IrrigationOpsCubit, IrrigationOpsState>(
        builder: (context, s) {
          if (s.loading && s.valves.isEmpty && s.schedules.isEmpty) {
            return const LoadingState(
              message: 'جارٍ تحميل الصمّامات والجداول…',
            );
          }
          if (s.error != null && s.valves.isEmpty && s.schedules.isEmpty) {
            return ErrorState(error: s.error!, onRetry: cubit.load);
          }
          return Column(
            children: [
              const _Banner(kValveIntentBanner),
              if (!widget.canManage)
                const _Banner(
                  'عرض فقط: طلبات الصمّام والجداول للمالك والمدير والمهندس الزراعيّ.',
                ),
              Expanded(
                child: TabBarView(
                  controller: _tabs,
                  children: [_valves(s), _schedules(s)],
                ),
              ),
            ],
          );
        },
      ),
    );
  }

  Widget _valves(IrrigationOpsState s) {
    final cubit = context.read<IrrigationOpsCubit>();
    if (s.valves.isEmpty) {
      return const EmptyState(
        message: 'لا صمّامات مسجّلة بعد',
        icon: Icons.water_drop_outlined,
      );
    }
    return RefreshIndicator(
      onRefresh: cubit.refresh,
      child: ListView.builder(
        padding: const EdgeInsetsDirectional.fromSTEB(
          SahoolSpacing.page,
          SahoolSpacing.sm,
          SahoolSpacing.page,
          SahoolSpacing.xxl * 3,
        ),
        itemCount: s.valves.length,
        itemBuilder: (_, i) {
          final v = s.valves[i];
          return _ValveCard(
            valve: v,
            pending: s.isValvePending(v.id),
            canManage: widget.canManage,
            onRequest: (open) => _requestValve(v, open),
          );
        },
      ),
    );
  }

  Widget _schedules(IrrigationOpsState s) {
    final cubit = context.read<IrrigationOpsCubit>();
    if (s.schedules.isEmpty) {
      return const EmptyState(
        message: 'لا جداول ريّ بعد',
        icon: Icons.schedule_rounded,
      );
    }
    return RefreshIndicator(
      onRefresh: cubit.refresh,
      child: ListView.builder(
        padding: const EdgeInsetsDirectional.fromSTEB(
          SahoolSpacing.page,
          SahoolSpacing.sm,
          SahoolSpacing.page,
          SahoolSpacing.xxl * 3,
        ),
        itemCount: s.schedules.length,
        itemBuilder: (_, i) {
          final sc = s.schedules[i];
          final pending = s.pendingSchedules.contains(sc.id);
          return _ScheduleCard(
            schedule: sc,
            trailing: !widget.canManage
                ? null
                : pending
                ? const _Spinner()
                : AppIconButton(
                    icon: Icons.delete_outline_rounded,
                    tooltip: 'حذف الجدول',
                    onPressed: () => _deleteSchedule(sc),
                  ),
          );
        },
      ),
    );
  }
}

class _Banner extends StatelessWidget {
  const _Banner(this.text);
  final String text;

  @override
  Widget build(BuildContext context) {
    final t = context.tokens;
    return Container(
      width: double.infinity,
      margin: const EdgeInsetsDirectional.fromSTEB(
        SahoolSpacing.page,
        SahoolSpacing.sm,
        SahoolSpacing.page,
        0,
      ),
      padding: const EdgeInsets.all(SahoolSpacing.md),
      decoration: BoxDecoration(
        color: t.info.withValues(alpha: 0.10),
        borderRadius: SahoolRadius.mdAll,
        border: Border.all(color: t.info.withValues(alpha: 0.4)),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(
            Icons.info_outline_rounded,
            color: t.info,
            size: SahoolSizes.iconSm,
          ),
          const SizedBox(width: SahoolSpacing.sm),
          Expanded(child: Text(text, style: context.textStyles.bodySmall)),
        ],
      ),
    );
  }
}

class _Spinner extends StatelessWidget {
  const _Spinner();

  @override
  Widget build(BuildContext context) => const SizedBox(
    width: SahoolSizes.minTouchTarget,
    height: SahoolSizes.minTouchTarget,
    child: Center(
      child: SizedBox(
        width: 22,
        height: 22,
        child: CircularProgressIndicator(strokeWidth: 2.4),
      ),
    ),
  );
}

class _ValveCard extends StatelessWidget {
  const _ValveCard({
    required this.valve,
    required this.pending,
    required this.canManage,
    required this.onRequest,
  });

  final Valve valve;
  final bool pending;
  final bool canManage;
  final ValueChanged<bool> onRequest;

  @override
  Widget build(BuildContext context) {
    final v = valve;
    final (label, tone) = v.isOpen
        ? ('مفتوح', StatusTone.success)
        : v.isClosed
        ? ('مغلق', StatusTone.neutral)
        : ('غير معروف', StatusTone.warning);
    final details = [
      if (v.valveType != null) kValveTypesAr[v.valveType] ?? v.valveType!,
      if (v.flowRateLpm != null) '${fmtNumber(v.flowRateLpm)} لتر/دقيقة',
      if (v.lastChangedAt != null) 'آخر تغيير ${fmtDateTime(v.lastChangedAt)}',
    ].join(' · ');
    return Card(
      child: Padding(
        padding: const EdgeInsetsDirectional.fromSTEB(
          SahoolSpacing.md,
          SahoolSpacing.md,
          SahoolSpacing.sm,
          SahoolSpacing.md,
        ),
        child: Row(
          children: [
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    v.name.isEmpty ? '—' : v.name,
                    style: context.textStyles.titleSmall,
                  ),
                  const SizedBox(height: SahoolSpacing.xs),
                  Wrap(
                    spacing: SahoolSpacing.sm,
                    runSpacing: SahoolSpacing.xs,
                    children: [
                      StatusChip(label: label, tone: tone),
                      if (pending)
                        const StatusChip(
                          label: 'جارٍ إرسال الطلب…',
                          tone: StatusTone.info,
                          icon: Icons.sync_rounded,
                        ),
                    ],
                  ),
                  if (details.isNotEmpty) ...[
                    const SizedBox(height: SahoolSpacing.xs),
                    Text(details, style: context.textStyles.bodySmall),
                  ],
                ],
              ),
            ),
            if (canManage)
              SizedBox(
                width: SahoolSizes.minTouchTarget + SahoolSpacing.md,
                height: SahoolSizes.minTouchTarget,
                child: Semantics(
                  label: v.isOpen ? 'طلب إغلاق ${v.name}' : 'طلب فتح ${v.name}',
                  child: Switch(
                    key: ValueKey('valve-switch-${v.id}'),
                    // حالة الخادم فقط — لا يتحرّك قبل ردّه، ومعطَّل أثناء الطلب.
                    value: v.isOpen,
                    onChanged: pending ? null : onRequest,
                  ),
                ),
              ),
          ],
        ),
      ),
    );
  }
}

class _ScheduleCard extends StatelessWidget {
  const _ScheduleCard({required this.schedule, this.trailing});
  final IrrigationSchedule schedule;
  final Widget? trailing;

  @override
  Widget build(BuildContext context) {
    final s = schedule;
    final days = s.daysOfWeek == null || s.daysOfWeek!.isEmpty
        ? 'كلّ الأيّام'
        : s.daysOfWeek!
              .map((d) => (d >= 0 && d < 7) ? kDaysAr[d] : '$d')
              .join('، ');
    return Card(
      child: Padding(
        padding: const EdgeInsetsDirectional.fromSTEB(
          SahoolSpacing.md,
          SahoolSpacing.md,
          SahoolSpacing.sm,
          SahoolSpacing.md,
        ),
        child: Row(
          children: [
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    s.name.isEmpty ? '—' : s.name,
                    style: context.textStyles.titleSmall,
                  ),
                  const SizedBox(height: SahoolSpacing.xs),
                  StatusChip(
                    label: switch (s.enabled) {
                      true => 'مفعَّل',
                      false => 'معطَّل',
                      null => 'غير معروف',
                    },
                    tone: s.enabled == true
                        ? StatusTone.success
                        : StatusTone.neutral,
                  ),
                  const SizedBox(height: SahoolSpacing.xs),
                  Text(
                    '${fmtClock(s.startTime)} · ${fmtMinutes(s.durationMin)} · $days',
                    style: context.textStyles.bodyMedium,
                  ),
                  if (s.waterTargetMm != null)
                    Text(
                      'الهدف: ${fmtMm(s.waterTargetMm)}',
                      style: context.textStyles.bodySmall,
                    ),
                  if (s.lastRunAt != null)
                    Text(
                      'آخر تشغيل: ${fmtDateTime(s.lastRunAt)}',
                      style: context.textStyles.bodySmall,
                    ),
                ],
              ),
            ),
            ?trailing,
          ],
        ),
      ),
    );
  }
}

// ── أوراق الإضافة (مسارات قائمة؛ لا أوامر عتاد) ───────────────────────────

class _AddValveSheet extends StatefulWidget {
  const _AddValveSheet({required this.api});
  final IrrigationApi api;

  @override
  State<_AddValveSheet> createState() => _AddValveSheetState();
}

class _AddValveSheetState extends State<_AddValveSheet> {
  final _name = TextEditingController();
  final _flow = TextEditingController();
  late final IdempotencyKey _key = IdempotencyKey.generate();
  String _type = 'solenoid';
  bool _saving = false;
  String? _error;

  @override
  void dispose() {
    _name.dispose();
    _flow.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (_saving) return;
    final name = _name.text.trim();
    final flowText = _flow.text.trim();
    final flow = parseLocalizedNum(flowText);
    if (name.isEmpty) {
      setState(() => _error = 'الاسم مطلوب');
      return;
    }
    if (flowText.isNotEmpty && (flow == null || flow < 0)) {
      setState(() => _error = 'معدّل التدفّق رقم موجب أو اتركه فارغاً');
      return;
    }
    setState(() {
      _saving = true;
      _error = null;
    });
    try {
      await widget.api.createValve({
        'name': name,
        'valve_type': _type,
        'flow_rate_lpm': ?flow,
      }, idempotencyKey: _key);
      if (mounted) Navigator.of(context).pop(true);
    } catch (e) {
      if (mounted) {
        setState(() {
          _saving = false;
          _error = ApiException.from(e).messageAr;
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) => AppSheet(
    title: 'صمّام جديد',
    submitLabel: 'تسجيل الصمّام',
    onSubmit: _submit,
    submitting: _saving,
    errorText: _error,
    children: [
      AppDropdown<String>(
        label: 'النوع',
        items: kValveTypesAr,
        value: _type,
        onChanged: (v) => setState(() => _type = v ?? 'solenoid'),
      ),
      AppTextField(label: 'الاسم', controller: _name, enabled: !_saving),
      AppNumberField(
        label: 'معدّل التدفّق (اختياريّ)',
        controller: _flow,
        unit: 'لتر/دقيقة',
      ),
    ],
  );
}

class _AddScheduleSheet extends StatefulWidget {
  const _AddScheduleSheet({required this.api, required this.valves});
  final IrrigationApi api;
  final List<Valve> valves;

  @override
  State<_AddScheduleSheet> createState() => _AddScheduleSheetState();
}

class _AddScheduleSheetState extends State<_AddScheduleSheet> {
  final _name = TextEditingController();
  final _start = TextEditingController();
  final _duration = TextEditingController();
  final _target = TextEditingController();
  late final IdempotencyKey _key = IdempotencyKey.generate();
  String? _valveId;
  bool _saving = false;
  String? _error;

  static final _clock = RegExp(r'^([01]?\d|2[0-3]):([0-5]\d)$');

  @override
  void dispose() {
    _name.dispose();
    _start.dispose();
    _duration.dispose();
    _target.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (_saving) return;
    final name = _name.text.trim();
    final start = normalizeDigits(_start.text.trim());
    final duration = parseLocalizedInt(_duration.text);
    final targetText = _target.text.trim();
    final target = parseLocalizedNum(targetText);
    String? error;
    if (name.isEmpty) {
      error = 'الاسم مطلوب';
    } else if (!_clock.hasMatch(start)) {
      error = 'وقت البدء بصيغة HH:MM (مثل 06:30)';
    } else if (duration == null || duration < 1 || duration > 1440) {
      error = 'المدّة بالدقائق بين 1 و1440';
    } else if (targetText.isNotEmpty && (target == null || target < 0)) {
      error = 'هدف الماء رقم موجب أو اتركه فارغاً';
    }
    if (error != null) {
      setState(() => _error = error);
      return;
    }
    setState(() {
      _saving = true;
      _error = null;
    });
    // حقل الصمّام المختار (UI-M1): بلا field_id كان الجدول يُحفظ غير مربوط فلا يظهر
    // في جداول الحقل. الخادم يشتقّه من الصمّام ويرفض التعارض أيضاً؛ بلا صمّام لا حقل.
    String? fieldId;
    for (final v in widget.valves) {
      if (v.id == _valveId) fieldId = v.fieldId;
    }
    try {
      await widget.api.createSchedule({
        'name': name,
        'start_time': start,
        'duration_min': duration,
        'valve_id': ?_valveId,
        'field_id': ?fieldId,
        'water_target_mm': ?target,
        'enabled': true,
      }, idempotencyKey: _key);
      if (mounted) Navigator.of(context).pop(true);
    } catch (e) {
      if (mounted) {
        setState(() {
          _saving = false;
          _error = ApiException.from(e).messageAr;
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) => AppSheet(
    title: 'جدول ريّ جديد',
    submitLabel: 'إنشاء الجدول',
    onSubmit: _submit,
    submitting: _saving,
    errorText: _error,
    children: [
      AppTextField(label: 'الاسم', controller: _name, enabled: !_saving),
      AppTextField(
        label: 'وقت البدء (HH:MM)',
        controller: _start,
        hint: '06:30',
        keyboardType: TextInputType.datetime,
        inputFormatters: const [LocalizedDigitsFormatter()],
        enabled: !_saving,
      ),
      AppNumberField(
        label: 'المدّة',
        controller: _duration,
        unit: 'دقيقة',
        decimal: false,
        required: true,
        min: 1,
        max: 1440,
      ),
      AppNumberField(
        label: 'هدف الماء (اختياريّ)',
        controller: _target,
        unit: 'مم',
      ),
      if (widget.valves.isNotEmpty)
        AppDropdown<String>(
          label: 'الصمّام (اختياريّ — يفحص الخادم التعارض)',
          items: {for (final v in widget.valves) v.id: v.name},
          value: _valveId,
          onChanged: (v) => setState(() => _valveId = v),
        ),
    ],
  );
}
