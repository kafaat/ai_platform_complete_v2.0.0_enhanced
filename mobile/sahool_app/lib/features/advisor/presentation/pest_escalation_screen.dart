// SAHOOL — features/advisor/presentation/pest_escalation_screen.dart
// تصعيد الآفة (POST /api/v1/pest-escalation/run، pesticide:approve): رصد ← تأكيد ←
// توصية ← تعليق بانتظار موافقة الخبير ← تنفيذ يحكمه الخادم.
// W0-01 نقل فحص السلامة الكيميائيّة إلى الخادم (داخل نقطة التصعيد)، فصارت الموافقة ممكنة
// من التطبيق: الخادم يفحص ولا ينفّذ إلّا إذا سمح الفحص.
// W3-07: التصعيد يبدأ من دبّوس استطلاع أعاده الخادم (GET /api/v1/scouting/pins) وسياق
// دليل صورته (…/photo/context)، لا من قائمة آفات حرّة؛ الموافقة معطَّلة ومشروحة ما لم يُثبت
// الخادم السلسلة (context.chemical_lineage_audit)؛ ونتيجة التنفيذ تُعرَض كما أعادها الخادم.
import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:sahool_app/core/network/api_exception.dart';
import 'package:sahool_app/core/theme/sahool_tokens.dart';
import 'package:sahool_app/core/theme/tokens.dart';
import 'package:sahool_app/core/utils/formatters.dart';
import 'package:sahool_app/core/widgets/widgets.dart';
import 'package:sahool_app/features/advisor/data/advisor_api.dart';
import 'package:sahool_app/features/advisor/data/advisor_models.dart';
import 'package:sahool_app/features/advisor/data/pest_escalation_lineage.dart';
import 'package:sahool_app/features/advisor/presentation/pest_escalation_cubit.dart';
import 'package:sahool_app/features/advisor/presentation/widgets/field_picker.dart';
import 'package:sahool_app/features/scouting/data/scouting_api.dart';
import 'package:sahool_app/features/scouting/data/scouting_models.dart';

String pestEscalationErrorText(ApiException e) {
  final d = e.detail;
  if (d is Map && d['code'] == 'CHEMICAL_LINEAGE_REQUIRED') {
    final v = d['violations'];
    final list = v is List ? v.whereType<String>().join('، ') : '';
    return 'رفض الخادم التصعيد: يلزم ربط تشخيص ودليل للحقل والموسم قبل أيّ '
        'مسار مبيدات (CHEMICAL_LINEAGE_REQUIRED${list.isEmpty ? '' : ': $list'}).';
  }
  return e.messageAr;
}

/// نصّ تعذّر سياق دليل الصورة: الخطأ يُعرَض ولا يُستبدَل بمراجع.
String photoContextErrorText(Object e) {
  if (e is ApiException) {
    if (e.statusCode == 404) {
      return 'لا دليل صورة لهذا الدبّوس على الخادم (أو خدمة الوسائط غير مفعّلة).';
    }
    if (e.statusCode == 403) {
      return 'دورك أو منحتك على الحقل لا تسمح بقراءة سياق دليل الصورة.';
    }
    return e.messageAr;
  }
  if (e is FormatException) return e.message;
  return 'تعذّر جلب سياق دليل الصورة من الخادم.';
}

class PestEscalationScreen extends StatelessWidget {
  const PestEscalationScreen({
    super.key,
    this.fieldId,
    this.api,
    this.scoutingApi,
    this.fieldLoader,
  });
  final String? fieldId;
  final AdvisorApi? api;
  final ScoutingApi? scoutingApi;
  final FieldLoader? fieldLoader;

  @override
  Widget build(BuildContext context) => BlocProvider(
    create: (_) => PestEscalationCubit(api ?? AdvisorApi.instance),
    child: _PestView(
      initialFieldId: fieldId,
      fieldLoader: fieldLoader,
      scoutingApi: scoutingApi ?? ScoutingApi.instance,
    ),
  );
}

class _PestView extends StatefulWidget {
  const _PestView({
    this.initialFieldId,
    this.fieldLoader,
    required this.scoutingApi,
  });
  final String? initialFieldId;
  final FieldLoader? fieldLoader;
  final ScoutingApi scoutingApi;

  @override
  State<_PestView> createState() => _PestViewState();
}

class _PestViewState extends State<_PestView> {
  late String? _fieldId = widget.initialFieldId;
  String? _fieldName;
  double _severity = 0.7;

  bool _pinsLoading = false;
  String? _pinsError;
  List<ScoutingPin> _pins = const [];
  String? _pinsNote;

  ScoutingPin? _pin;
  bool _photoLoading = false;
  String? _photoError;
  Map<String, dynamic>? _photoContext;

  @override
  void initState() {
    super.initState();
    final id = _fieldId;
    // بعد أوّل إطار: _loadPins يستدعي setState.
    if (id != null) {
      WidgetsBinding.instance.addPostFrameCallback((_) => _loadPins(id));
    }
  }

  Future<void> _pickField() async {
    final picked = await pickField(context, loader: widget.fieldLoader);
    if (!mounted || picked == null) return;
    setState(() {
      _fieldId = picked.id;
      _fieldName = picked.name;
    });
    await _loadPins(picked.id);
  }

  Future<void> _loadPins(String fieldId) async {
    setState(() {
      _pinsLoading = true;
      _pinsError = null;
      _pins = const [];
      _pinsNote = null;
      _pin = null;
      _photoContext = null;
      _photoError = null;
    });
    try {
      final page = await widget.scoutingApi.listPins(fieldId);
      if (!mounted || _fieldId != fieldId) return;
      setState(() {
        _pins = page.pins;
        _pinsNote = page.noteAr;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() => _pinsError = ApiException.from(e).messageAr);
    } finally {
      if (mounted) setState(() => _pinsLoading = false);
    }
  }

  Future<void> _selectPin(String? pinId) async {
    final pin = _pins.where((p) => p.pinId == pinId).firstOrNull;
    setState(() {
      _pin = pin;
      _photoContext = null;
      _photoError = null;
      _photoLoading = pin != null;
    });
    if (pin == null) return;
    try {
      final ctx = await widget.scoutingApi.photoEvidenceContext(
        pin.fieldId,
        pin.pinId,
      );
      if (!mounted || _pin?.pinId != pin.pinId) return;
      setState(() => _photoContext = ctx);
    } catch (e) {
      if (!mounted || _pin?.pinId != pin.pinId) return;
      setState(() => _photoError = photoContextErrorText(e));
    } finally {
      if (mounted && _pin?.pinId == pin.pinId) {
        setState(() => _photoLoading = false);
      }
    }
  }

  Future<void> _reject(PestEscalationCubit cubit) async {
    final ok = await showConfirmDialog(
      context,
      title: 'رفض التنفيذ؟',
      message: 'سيُستأنف التدفّق برفض الخبير ولن يُنفَّذ أيّ إجراء مكافحة.',
      confirmLabel: 'رفض',
      destructive: true,
    );
    if (ok && mounted) await cubit.reject();
  }

  Future<void> _approve(PestEscalationCubit cubit) async {
    final ok = await showConfirmDialog(
      context,
      title: 'الموافقة على التنفيذ؟',
      message:
          'سيفحص الخادم السلامة الكيميائيّة، ولا يُنفَّذ الإجراء إلّا إذا سمح الفحص.',
      confirmLabel: 'موافقة',
    );
    if (ok && mounted) await cubit.approve();
  }

  @override
  Widget build(BuildContext context) {
    return BlocBuilder<PestEscalationCubit, PestEscalationState>(
      builder: (context, state) {
        final cubit = context.read<PestEscalationCubit>();
        final wf = state.workflow;
        final fieldId = _fieldId;
        final pin = _pin;
        final refs = pin == null ? null : refsFromPin(pin, _photoContext);
        final muted = context.textStyles.bodySmall?.copyWith(
          color: context.tokens.muted,
        );
        return AppScaffold(
          title: 'تصعيد الآفة',
          body: ListView(
            padding: const EdgeInsets.all(SahoolSpacing.lg),
            children: [
              Text(
                'يبدأ التصعيد من مشاهدة استطلاع محفوظة على الخادم ودليل صورتها، ثمّ '
                'يُعلَّق بانتظار موافقة الخبير. لا موافقة ما لم يُثبت الخادم سلسلة '
                'التشخيص والدليل.',
                style: context.textStyles.bodyMedium?.copyWith(
                  color: context.tokens.muted,
                ),
              ),
              const SizedBox(height: SahoolSpacing.md),
              SectionCard(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    Row(
                      children: [
                        Expanded(
                          child: Text(
                            fieldId == null
                                ? 'الحقل: لم يُختَر'
                                : 'الحقل: ${_fieldName ?? fieldId}',
                            style: context.textStyles.titleSmall,
                          ),
                        ),
                        TextButton(
                          onPressed: state.busy ? null : _pickField,
                          child: Text(fieldId == null ? 'اختر حقلاً' : 'غيّر'),
                        ),
                      ],
                    ),
                    if (_pinsLoading)
                      const Padding(
                        padding: EdgeInsets.all(SahoolSpacing.sm),
                        child: LinearProgressIndicator(),
                      ),
                    if (_pinsError != null)
                      Text(
                        'تعذّر جلب مشاهدات الحقل: $_pinsError',
                        style: muted?.copyWith(color: context.tokens.danger),
                      ),
                    if (fieldId != null &&
                        !_pinsLoading &&
                        _pinsError == null &&
                        _pins.isEmpty)
                      Text(
                        'لا مشاهدات محفوظة لهذا الحقل'
                        '${_pinsNote == null ? '' : ' — $_pinsNote'}. '
                        'سجّل مشاهدة من الاستطلاع أوّلاً.',
                        style: muted?.copyWith(color: context.tokens.warning),
                      ),
                    if (_pins.isNotEmpty)
                      AppDropdown<String>(
                        key: ValueKey('pins-$fieldId'),
                        label: 'مشاهدة الاستطلاع (دبّوس محفوظ)',
                        items: {
                          for (final p in _pins)
                            p.pinId:
                                '${p.issueCode ?? p.categoryWire} · '
                                '${p.severity?.labelAr ?? p.severityWire}',
                        },
                        value: pin?.pinId,
                        onChanged: state.busy ? null : _selectPin,
                      ),
                    if (pin != null && refs != null)
                      _RefsCard(
                        pin: pin,
                        refs: refs,
                        loading: _photoLoading,
                        error: _photoError,
                      ),
                    const SizedBox(height: SahoolSpacing.md),
                    Text(
                      'تقدير الشدّة: ${fmtPct(_severity, fraction: true)}'
                      '${pin == null ? '' : ' · تقدير الكشّاف: ${pin.severity?.labelAr ?? pin.severityWire}'}',
                      style: context.textStyles.bodyMedium,
                    ),
                    Slider(
                      value: _severity,
                      divisions: 10,
                      label: fmtPct(_severity, fraction: true),
                      onChanged: state.busy
                          ? null
                          : (v) => setState(() => _severity = v),
                    ),
                    PrimaryButton(
                      label: 'شغّل التصعيد من المشاهدة',
                      icon: Icons.play_circle_outline,
                      loading: state.busy,
                      onPressed: refs == null || _photoLoading
                          ? null
                          : () => cubit.start(refs: refs, severity: _severity),
                    ),
                  ],
                ),
              ),
              if (state.error != null)
                Padding(
                  padding: const EdgeInsets.only(top: SahoolSpacing.md),
                  child: Semantics(
                    liveRegion: true,
                    child: Text(
                      pestEscalationErrorText(state.error!),
                      style: context.textStyles.bodyMedium?.copyWith(
                        color: context.tokens.danger,
                      ),
                    ),
                  ),
                ),
              if (wf != null) ...[
                const SizedBox(height: SahoolSpacing.md),
                _WorkflowCard(
                  wf: wf,
                  lineage: state.lineage,
                  busy: state.busy,
                  onApprove: () => _approve(cubit),
                  onReject: () => _reject(cubit),
                ),
              ],
            ],
          ),
        );
      },
    );
  }
}

class _RefsCard extends StatelessWidget {
  const _RefsCard({
    required this.pin,
    required this.refs,
    required this.loading,
    required this.error,
  });
  final ScoutingPin pin;
  final EscalationRefs refs;
  final bool loading;
  final String? error;

  @override
  Widget build(BuildContext context) {
    final t = context.tokens;
    final small = context.textStyles.bodySmall;
    return Padding(
      padding: const EdgeInsets.only(top: SahoolSpacing.md),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text('مراجع السلسلة من الخادم', style: context.textStyles.titleSmall),
          Text('الدبّوس: ${pin.pinId}', style: small),
          Text('الآفة/التشخيص: ${refs.pestType ?? '—'}', style: small),
          if (loading) const LinearProgressIndicator(),
          if (error != null)
            Text(error!, style: small?.copyWith(color: t.danger)),
          for (final key in kLineageRefKeys)
            Text(
              '${kLineageRefAr[key]}: ${refs.valueOf(key) ?? 'غائب — ${refs.missing[key] ?? 'لم يُعِده الخادم'}'}',
              style: small?.copyWith(
                color: refs.valueOf(key) == null ? t.warning : null,
              ),
            ),
        ],
      ),
    );
  }
}

class _WorkflowCard extends StatelessWidget {
  const _WorkflowCard({
    required this.wf,
    required this.lineage,
    required this.busy,
    required this.onApprove,
    required this.onReject,
  });
  final PestWorkflow wf;
  final ApprovalLineageGate lineage;
  final bool busy;
  final VoidCallback onApprove;
  final VoidCallback onReject;

  @override
  Widget build(BuildContext context) {
    final t = context.tokens;
    final small = context.textStyles.bodySmall?.copyWith(color: t.muted);
    final rec = wf.context['recommendation_ar'];
    final action = wf.context['action_type'];
    final outcome = readExecutionOutcome(wf.stepResults);
    final tone = switch (wf.status) {
      'completed' => StatusTone.success,
      'suspended' => StatusTone.warning,
      'failed' || 'compensated' || 'compensation_failed' => StatusTone.danger,
      _ => StatusTone.info,
    };
    return SectionCard(
      title: 'حالة التدفّق',
      icon: Icons.account_tree_outlined,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Align(
            alignment: AlignmentDirectional.centerStart,
            child: StatusChip(
              label: kWorkflowStatusAr[wf.status] ?? wf.status,
              tone: tone,
              icon: Icons.circle_outlined,
            ),
          ),
          const SizedBox(height: SahoolSpacing.sm),
          if (wf.completedSteps.isNotEmpty)
            Text(
              'الخطوات المكتملة: ${wf.completedSteps.map((s) => kWorkflowStepAr[s] ?? s).join(' ← ')}',
              style: context.textStyles.bodyMedium,
            ),
          if (wf.currentStep != null)
            Text(
              'الخطوة الحاليّة: ${kWorkflowStepAr[wf.currentStep] ?? wf.currentStep}',
              style: context.textStyles.bodyMedium,
            ),
          if (rec is String && rec.trim().isNotEmpty) ...[
            const SizedBox(height: SahoolSpacing.sm),
            Text('التوصية: $rec', style: context.textStyles.bodyMedium),
          ],
          if (action is String && action.isNotEmpty)
            Text('نوع الإجراء: $action', style: small),
          if (wf.error != null)
            Text(
              'الخطأ: ${wf.error}',
              style: context.textStyles.bodySmall?.copyWith(color: t.danger),
            ),
          Text('معرّف التدفّق: ${wf.workflowId}', style: small),
          if (outcome.state != ExecutionState.pending)
            _OutcomeView(outcome: outcome),
          if (wf.suspended) ...[
            const SizedBox(height: SahoolSpacing.md),
            Text(
              lineage.allowed
                  ? 'عند الموافقة يفحص الخادم السلامة الكيميائيّة، ولا يُنفَّذ إلّا إذا سمح الفحص.'
                  : 'الموافقة محجوبة: الخادم لم يُثبت سلسلة التشخيص والدليل لهذا التدفّق.',
              style: context.textStyles.bodySmall?.copyWith(color: t.warning),
            ),
            if (!lineage.allowed)
              Column(
                key: const ValueKey('lineage-reasons'),
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  for (final r in lineage.reasons) Text('• $r', style: small),
                ],
              ),
            if (lineage.allowed && !lineage.validated)
              Text(
                'التحقّق من التشخيص لدى مالكه غير موصول بعد (validated=false)، '
                'فيُعاد التدقيق عند التنفيذ.',
                style: small,
              ),
            const SizedBox(height: SahoolSpacing.sm),
            PrimaryButton(
              key: const ValueKey('pest-approve'),
              label: 'موافقة الخبير',
              icon: Icons.verified_user_outlined,
              onPressed: busy || !lineage.allowed ? null : onApprove,
            ),
            const SizedBox(height: SahoolSpacing.sm),
            SecondaryButton(
              label: 'رفض التنفيذ',
              icon: Icons.block_outlined,
              onPressed: busy ? null : onReject,
            ),
          ],
        ],
      ),
    );
  }
}

class _OutcomeView extends StatelessWidget {
  const _OutcomeView({required this.outcome});
  final ExecutionOutcome outcome;

  @override
  Widget build(BuildContext context) {
    final t = context.tokens;
    final style = context.textStyles.bodyMedium;
    final executed = outcome.state == ExecutionState.executed;
    return Padding(
      key: const ValueKey('pest-outcome'),
      padding: const EdgeInsets.only(top: SahoolSpacing.sm),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text(
            executed
                ? 'نُفِّذ بحسب الخادم — مرجع التنفيذ: ${outcome.executionRef}'
                : outcome.state == ExecutionState.unconfirmed
                ? 'تنفيذ غير مؤكَّد'
                : 'لم يُنفَّذ (executed=false)',
            style: style?.copyWith(color: executed ? t.success : t.danger),
          ),
          for (final r in outcome.reasons)
            Text(
              r,
              style: context.textStyles.bodySmall?.copyWith(color: t.danger),
            ),
        ],
      ),
    );
  }
}
