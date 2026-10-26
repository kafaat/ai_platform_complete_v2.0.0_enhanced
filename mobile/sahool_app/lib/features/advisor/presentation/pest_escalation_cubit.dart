// SAHOOL — features/advisor/presentation/pest_escalation_cubit.dart
// تدفّق تصعيد الآفة (durable + موافقة بشريّة): تشغيل يُعلَّق عند الموافقة، ثمّ
// استئناف بنفس workflow_id. نيّة التشغيل الواحدة تحتفظ بمعرّفها عبر المحاولات،
// فإعادة المحاولة بعد استجابة ضائعة تستأنف نفس التدفّق ولا تُنشئ ثانياً.
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:sahool_app/core/network/api_exception.dart';
import 'package:sahool_app/core/utils/ids.dart';
import 'package:sahool_app/features/advisor/data/advisor_api.dart';
import 'package:sahool_app/features/advisor/data/advisor_models.dart';

class PestEscalationState {
  const PestEscalationState({this.busy = false, this.workflow, this.error});
  final bool busy;
  final PestWorkflow? workflow;
  final ApiException? error;
}

class PestEscalationCubit extends Cubit<PestEscalationState> {
  PestEscalationCubit(this._api, {String Function()? newId})
    : _newId = newId ?? (() => 'pest-${generateRequestId()}'),
      super(const PestEscalationState());

  final AdvisorApi _api;
  final String Function() _newId;

  String? _pendingId;
  String? _pendingInputs;

  Future<void> start({
    required String fieldId,
    required String pestType,
    required double severity,
  }) async {
    if (state.busy) return;
    final inputs = '$fieldId|$pestType|$severity';
    if (_pendingInputs != inputs) {
      _pendingId = _newId();
      _pendingInputs = inputs;
    }
    final id = _pendingId!;
    await _run(
      () => _api.runPestEscalation(
        workflowId: id,
        fieldId: fieldId,
        pestType: pestType,
        severity: severity,
      ),
      onSuccess: () {
        _pendingId = null;
        _pendingInputs = null;
      },
    );
  }

  /// رفض الخبير: يستأنف التدفّق المعلَّق بـapproval_status=rejected.
  Future<void> reject() async {
    final wf = state.workflow;
    if (state.busy || wf == null || !wf.suspended) return;
    await _run(
      () => _api.runPestEscalation(
        workflowId: wf.workflowId,
        approvalStatus: 'rejected',
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
