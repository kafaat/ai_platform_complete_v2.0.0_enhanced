// SAHOOL — features/advisor/presentation/pest_escalation_cubit.dart
// تدفّق تصعيد الآفة (durable + موافقة بشريّة): تشغيل يُعلَّق عند الموافقة، ثمّ
// استئناف بنفس workflow_id. نيّة التشغيل الواحدة تحتفظ بمعرّفها عبر المحاولات،
// فإعادة المحاولة بعد استجابة ضائعة تستأنف نفس التدفّق ولا تُنشئ ثانياً.
// W3-07: التشغيل يبدأ من دبّوس استطلاع أعاده الخادم ومراجع دليله (EscalationRefs)،
// والموافقة لا تُرسَل ما لم يُثبت الخادم سلسلة المبيد في context.chemical_lineage_audit.
// الموافقة والرفض يعيدان المراجع من سياق الخادم (لا من حالة الواجهة) ليدقّقها الخادم
// عند حدّ التنفيذ.
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:sahool_app/core/network/api_exception.dart';
import 'package:sahool_app/core/utils/ids.dart';
import 'package:sahool_app/features/advisor/data/advisor_api.dart';
import 'package:sahool_app/features/advisor/data/advisor_models.dart';
import 'package:sahool_app/features/advisor/data/pest_escalation_lineage.dart';

class PestEscalationState {
  const PestEscalationState({this.busy = false, this.workflow, this.error});
  final bool busy;
  final PestWorkflow? workflow;
  final ApiException? error;

  /// حكم السلسلة من ردّ الخادم الأخير (لا ردّ ⇒ محجوبة).
  ApprovalLineageGate get lineage => evaluateApprovalLineage(workflow?.context);
}

class PestEscalationCubit extends Cubit<PestEscalationState> {
  PestEscalationCubit(this._api, {String Function(String pinId)? newId})
    : _newId =
          newId ??
          ((pinId) => pestWorkflowIdForPin(pinId, generateRequestId())),
      super(const PestEscalationState());

  final AdvisorApi _api;
  final String Function(String pinId) _newId;

  String? _pendingId;
  String? _pendingInputs;

  Future<void> start({
    required EscalationRefs refs,
    required double severity,
  }) async {
    if (state.busy) return;
    final inputs = [
      refs.pinId,
      refs.fieldId,
      refs.seasonId,
      refs.diagnosisRef,
      refs.evidenceRef,
      refs.pestType,
      severity,
    ].join('|');
    if (_pendingInputs != inputs) {
      _pendingId = _newId(refs.pinId);
      _pendingInputs = inputs;
    }
    final id = _pendingId!;
    await _run(
      () => _api.runPestEscalation(
        workflowId: id,
        fieldId: refs.fieldId,
        seasonId: refs.seasonId,
        diagnosisRef: refs.diagnosisRef,
        evidenceRef: refs.evidenceRef,
        pestType: refs.pestType,
        severity: severity,
      ),
      onSuccess: () {
        _pendingId = null;
        _pendingInputs = null;
      },
    );
  }

  /// موافقة الخبير: محجوبة ما لم يُثبت الخادم السلسلة (حارس ثانٍ خلف الزرّ المعطَّل).
  Future<void> approve() async {
    final wf = state.workflow;
    if (state.busy || wf == null || !wf.suspended) return;
    if (!state.lineage.allowed) return;
    await _resume(wf, 'approved');
  }

  /// رفض الخبير: يستأنف التدفّق المعلَّق بـapproval_status=rejected (لا ينفّذ شيئاً).
  Future<void> reject() async {
    final wf = state.workflow;
    if (state.busy || wf == null || !wf.suspended) return;
    await _resume(wf, 'rejected');
  }

  Future<void> _resume(PestWorkflow wf, String approvalStatus) {
    final refs = lineageRefsFromContext(wf.context);
    return _run(
      () => _api.runPestEscalation(
        workflowId: wf.workflowId,
        fieldId: refs['field_id'],
        seasonId: refs['season_id'],
        diagnosisRef: refs['diagnosis_ref'],
        evidenceRef: refs['evidence_ref'],
        approvalStatus: approvalStatus,
      ),
    );
  }

  Future<void> _run(
    Future<Map<String, dynamic>> Function() call, {
    void Function()? onSuccess,
  }) async {
    emit(PestEscalationState(busy: true, workflow: state.workflow));
    try {
      final wf = PestWorkflow.fromJson(await call());
      onSuccess?.call();
      if (isClosed) return;
      emit(PestEscalationState(workflow: wf));
    } catch (e) {
      if (isClosed) return;
      emit(
        PestEscalationState(
          workflow: state.workflow,
          error: ApiException.from(e),
        ),
      );
    }
  }
}
