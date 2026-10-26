// SAHOOL — features/advisor/presentation/pest_escalation_screen.dart
// تصعيد الآفة (POST /api/v1/pest-escalation/run، pesticide:approve): رصد ← تأكيد ←
// توصية ← تعليق بانتظار موافقة الخبير. الموافقة على التنفيذ لا تُتاح هنا: الويب
// يمرّرها أوّلاً عبر حواجز السلامة الكيميائيّة (/api/guardrails/v1/validate)،
// وهذا الفحص غير موصول في التطبيق بعد؛ الرفض متاح لأنّه لا ينفّذ شيئاً.
import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:sahool_app/core/network/api_exception.dart';
import 'package:sahool_app/core/theme/sahool_tokens.dart';
import 'package:sahool_app/core/theme/tokens.dart';
import 'package:sahool_app/core/utils/formatters.dart';
import 'package:sahool_app/core/widgets/widgets.dart';
import 'package:sahool_app/features/advisor/data/advisor_api.dart';
import 'package:sahool_app/features/advisor/data/advisor_models.dart';
import 'package:sahool_app/features/advisor/presentation/pest_escalation_cubit.dart';
import 'package:sahool_app/features/advisor/presentation/widgets/field_picker.dart';

/// مرآة PESTS في PestEscalationPage.tsx.
const List<String> kEscalationPests = [
  'صدأ القمح',
  'المنّ',
  'دودة الحشد',
  'الذبابة البيضاء',
  'التربس',
  'العنكبوت الأحمر',
];

String pestEscalationErrorText(ApiException e) {
  final d = e.detail;
  if (d is Map && d['code'] == 'CHEMICAL_LINEAGE_REQUIRED') {
    return 'رفض الخادم التصعيد: يلزم ربط تشخيص ودليل للحقل والموسم قبل أيّ '
        'مسار مبيدات (CHEMICAL_LINEAGE_REQUIRED).';
  }
  return e.messageAr;
}

class PestEscalationScreen extends StatelessWidget {
  const PestEscalationScreen({
    super.key,
    this.fieldId,
    this.api,
    this.fieldLoader,
  });
  final String? fieldId;
  final AdvisorApi? api;
  final FieldLoader? fieldLoader;

  @override
  Widget build(BuildContext context) => BlocProvider(
    create: (_) => PestEscalationCubit(api ?? AdvisorApi.instance),
    child: _PestView(initialFieldId: fieldId, fieldLoader: fieldLoader),
  );
}

class _PestView extends StatefulWidget {
  const _PestView({this.initialFieldId, this.fieldLoader});
  final String? initialFieldId;
  final FieldLoader? fieldLoader;

  @override
  State<_PestView> createState() => _PestViewState();
}

class _PestViewState extends State<_PestView> {
  late String? _fieldId = widget.initialFieldId;
  String? _fieldName;
  String _pest = kEscalationPests.first;
  double _severity = 0.7;

  Future<void> _pickField() async {
    final picked = await pickField(context, loader: widget.fieldLoader);
    if (!mounted || picked == null) return;
    setState(() {
      _fieldId = picked.id;
      _fieldName = picked.name;
    });
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

  @override
  Widget build(BuildContext context) {
    return BlocBuilder<PestEscalationCubit, PestEscalationState>(
      builder: (context, state) {
        final cubit = context.read<PestEscalationCubit>();
        final wf = state.workflow;
        final fieldId = _fieldId;
        return AppScaffold(
          title: 'تصعيد الآفة',
          body: ListView(
            padding: const EdgeInsets.all(SahoolSpacing.lg),
            children: [
              Text(
                'تدفّق بموافقة بشريّة: يُرصَد ويُؤكَّد ويُوصى ثمّ يُعلَّق بانتظار '
                'موافقة الخبير. لا تنفيذ بلا موافقة.',
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
                    AppDropdown<String>(
                      label: 'نوع الآفة',
                      items: {for (final p in kEscalationPests) p: p},
                      value: _pest,
                      onChanged: state.busy
                          ? null
                          : (v) => setState(() => _pest = v ?? _pest),
                    ),
                    const SizedBox(height: SahoolSpacing.md),
                    Text(
                      'الشدّة: ${fmtPct(_severity, fraction: true)}',
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
                      label: 'شغّل التصعيد',
                      icon: Icons.play_circle_outline,
                      loading: state.busy,
                      onPressed: fieldId == null
                          ? null
                          : () => cubit.start(
                              fieldId: fieldId,
                              pestType: _pest,
                              severity: _severity,
                            ),
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
                  busy: state.busy,
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

class _WorkflowCard extends StatelessWidget {
  const _WorkflowCard({
    required this.wf,
    required this.busy,
    required this.onReject,
  });
  final PestWorkflow wf;
  final bool busy;
  final VoidCallback onReject;

  @override
  Widget build(BuildContext context) {
    final t = context.tokens;
    final small = context.textStyles.bodySmall?.copyWith(color: t.muted);
    final rec = wf.context['recommendation_ar'];
    final action = wf.context['action_type'];
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
          if (wf.suspended) ...[
            const SizedBox(height: SahoolSpacing.md),
            Text(
              'الموافقة على التنفيذ تتطلّب فحص حواجز السلامة الكيميائيّة، وهو غير '
              'متاح في التطبيق بعد — وافِق من لوحة الويب. يمكنك الرفض من هنا.',
              style: context.textStyles.bodySmall?.copyWith(color: t.warning),
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
