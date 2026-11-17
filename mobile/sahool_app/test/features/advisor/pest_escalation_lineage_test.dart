// W3-07 — تصعيد الآفة من مرجع حقيقيّ: دبّوس الخادم وسياق دليل صورته، حجب الموافقة بلا
// سلسلة أثبتها الخادم (context.chemical_lineage_audit)، ونتيجة التنفيذ كما أعادها
// (executed=false لا يُعرَض نجاحاً). الأشكال مطابقة للخادم: routers/pest_escalation.py،
// shared/governance/chemical_lineage.py، core/pest_escalation_flow.py، وscout-ingest
// media_api.py (get_pin_photo_context). الضابط السالب: لو أُزيل فحص السلسلة من الزرّ
// أو من الـcubit لصار «بلا سلسلة» مُفعَّلاً/مُرسَلاً فيحمرّ اختباره.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sahool_app/core/widgets/widgets.dart';
import 'package:sahool_app/features/advisor/data/advisor_models.dart';
import 'package:sahool_app/features/advisor/data/pest_escalation_lineage.dart';
import 'package:sahool_app/features/advisor/presentation/pest_escalation_cubit.dart';
import 'package:sahool_app/features/advisor/presentation/pest_escalation_screen.dart';
import 'package:sahool_app/features/scouting/data/scouting_api.dart';
import 'package:sahool_app/features/scouting/data/scouting_models.dart';

import '../../core/fake_http.dart';
import 'advisor_test_helpers.dart';

final String _sha = 'c' * 64;
const _seasonId = '11111111-1111-4111-8111-111111111111';
const _linkEvent = '22222222-2222-4222-8222-222222222222';
const _pinsPath = '/api/v1/scouting/pins';
const _ctxPath =
    '/api/v1/scouting-media/fields/fld_1/pins/pin_42/photo/context';
const _runPath = '/api/v1/pest-escalation/run';

Map<String, dynamic> _pinJson() => {
  'pin_id': 'pin_42',
  'field_id': 'fld_1',
  'lat': 15.3,
  'lng': 44.2,
  'issue_category': 'pest',
  'severity': 'high',
  'status': 'new',
  'persistence': 'seasonal',
  'crop': 'tomato',
  'issue_code': 'tomato.tuta',
  'note_ar': null,
  'photo_uri': null,
  'color': null,
  'created_by': 'u1',
  'created_at': '2026-11-10T08:00:00+00:00',
};

Map<String, dynamic> _photoContext() => {
  'schema': 'sahool.scout-photo-evidence-context/v1',
  'source': {'kind': 'scouting_pin', 'field_id': 'fld_1', 'pin_id': 'pin_42'},
  'evidence': {
    'evidence_id': 'ev-1',
    'field_id': 'fld_1',
    'pin_id': 'pin_42',
    'sha256': _sha,
    'persisted': true,
    'verification_state': 'bytes_verified',
    'review_state': 'unreviewed',
  },
  'object_state': 'present_at_check',
  'inspection': {'state': 'not_linked'},
  'season': {
    'state': 'linked_accepted',
    'season_id': _seasonId,
    'link_event_id': _linkEvent,
    'link_proof': kScoutPhotoSeasonLinkProof,
  },
  'human_review': {
    'state': 'human_assessment_recorded',
    'review_event_id': 'rev-3',
    'assessment': 'suspected',
    'diagnosis_code': 'tomato_leafminer',
    'image_sha256': _sha,
  },
  'decision': {'state': 'not_authorized', 'decision_id': null},
  'automatic_pesticide_action_authorized': false,
};

Map<String, dynamic> _suspended(Map<String, dynamic> context) => {
  'workflow': {
    'workflow_id': 'pest-pin-pin_42-r1',
    'status': 'suspended',
    'completed_steps': ['detect', 'confirm', 'recommend'],
    'current_step': 'await_approval',
    'error': null,
  },
  'context': context,
  'step_results': <String, dynamic>{},
};

Map<String, dynamic> _withLineageContext() => {
  'field_id': 'fld_1',
  'season_id': _seasonId,
  'diagnosis_ref': 'rev-3',
  'evidence_ref': 'scout_photo_evidence:ev-1@$_sha',
  'recommendation_ar': 'مكافحة عاجلة — رشّ موجّه + عزل البؤرة',
  'action_type': 'urgent_spray',
  'approval_status': 'pending',
  'chemical_lineage_audit': {
    'mode': 'audit',
    'boundary': 'draft',
    'compliant': true,
    'validated': false,
    'violations': <String>[],
    'details': <Object>[],
  },
};

Map<String, dynamic> _withoutLineageContext() => {
  'field_id': 'fld_1',
  'recommendation_ar': 'مكافحة عاجلة',
  'action_type': 'urgent_spray',
  'approval_status': 'pending',
  'chemical_lineage_audit': {
    'mode': 'audit',
    'boundary': 'draft',
    'compliant': false,
    'validated': false,
    'violations': [
      'MISSING_SEASON_ID',
      'MISSING_DIAGNOSIS_REF',
      'MISSING_EVIDENCE_REF',
    ],
    'details': <Object>[],
  },
};

Map<String, dynamic> _completedNotExecuted() => {
  'workflow': {
    'workflow_id': 'pest-pin-pin_42-r1',
    'status': 'completed',
    'completed_steps': [
      'detect',
      'confirm',
      'recommend',
      'await_approval',
      'execute',
      'follow_up',
    ],
    'current_step': null,
    'error': null,
  },
  'context': {..._withLineageContext(), 'executed': false},
  'step_results': {
    'execute': {
      'executed': false,
      'blocked_by': 'guardrails',
      'note_ar':
          'لا يُنفَّذ المبيد: أدلّة فحص السلامة الكيميائيّة غير متاحة على الخادم.',
      'guardrails': {
        'allowed': false,
        'status': 'evidence_unavailable',
        'reason_ar':
            'لا يُنفَّذ المبيد: أدلّة فحص السلامة الكيميائيّة غير متاحة على الخادم.',
        'no_server_source': ['action_data.chemical'],
      },
    },
    'follow_up': {'follow_up_scheduled': false},
  },
};

ScoutingPin _pin() => ScoutingPin.fromJson(_pinJson());

void main() {
  group('refsFromPin — المراجع من ردود الخادم فقط', () {
    test('دبّوس + سياق دليل كامل ⇒ المراجع الأربعة وكود التشخيص المراجَع', () {
      final refs = refsFromPin(_pin(), _photoContext());
      expect(refs.fieldId, 'fld_1');
      expect(refs.seasonId, _seasonId);
      expect(refs.diagnosisRef, 'rev-3');
      expect(refs.evidenceRef, 'scout_photo_evidence:ev-1@$_sha');
      expect(refs.pestType, 'tomato_leafminer');
      expect(refs.missing, isEmpty);
    });

    test('بلا سياق دليل ⇒ لا يخترع مرجعاً، ويعود لكود الدبّوس', () {
      final refs = refsFromPin(_pin(), null);
      expect(refs.evidenceRef, isNull);
      expect(refs.seasonId, isNull);
      expect(refs.diagnosisRef, isNull);
      expect(refs.pestType, 'tomato.tuta');
      expect(refs.missing.keys.toSet(), {
        'evidence_ref',
        'season_id',
        'diagnosis_ref',
      });
    });

    test('تقييم «مستبعَد» أو بصمة مختلفة أو موسم غير مقبول ⇒ لا مرجع', () {
      final ruledOut = _photoContext()
        ..['human_review'] = {
          'state': 'human_assessment_recorded',
          'review_event_id': 'rev-3',
          'assessment': 'ruled_out',
          'image_sha256': _sha,
        }
        ..['season'] = {'state': 'linked_not_accepted', 'season_id': _seasonId};
      final refs = refsFromPin(_pin(), ruledOut);
      expect(refs.diagnosisRef, isNull);
      expect(refs.seasonId, isNull);

      final otherSha = _photoContext()
        ..['human_review'] = {
          ...(_photoContext()['human_review'] as Map<String, dynamic>),
          'image_sha256': 'd' * 64,
        };
      expect(refsFromPin(_pin(), otherSha).diagnosisRef, isNull);
    });
  });

  group('evaluateApprovalLineage', () {
    test('سلسلة متوافقة أعادها الخادم ⇒ مُتاحة', () {
      final gate = evaluateApprovalLineage(_withLineageContext());
      expect(gate.allowed, isTrue);
      expect(gate.reasons, isEmpty);
    });

    test('مخالفات، أو تدقيق غائب، أو mode=off ⇒ محجوبة ومشروحة', () {
      final gate = evaluateApprovalLineage(_withoutLineageContext());
      expect(gate.allowed, isFalse);
      expect(gate.reasons.join(' '), contains('MISSING_DIAGNOSIS_REF'));

      final noAudit = _withLineageContext()..remove('chemical_lineage_audit');
      expect(evaluateApprovalLineage(noAudit).allowed, isFalse);

      final off = _withLineageContext()
        ..['chemical_lineage_audit'] = {
          'mode': 'off',
          'compliant': true,
          'violations': <String>[],
        };
      expect(evaluateApprovalLineage(off).allowed, isFalse);
      expect(evaluateApprovalLineage(null).allowed, isFalse);
    });
  });

  group('readExecutionOutcome', () {
    test('executed=false ⇒ لم يُنفَّذ مع السبب؛ لا خطوة ⇒ pending', () {
      final o = readExecutionOutcome(
        _completedNotExecuted()['step_results'] as Map<String, dynamic>,
      );
      expect(o.state, ExecutionState.notExecuted);
      expect(o.blockedBy, 'guardrails');
      expect(o.guardrailsStatus, 'evidence_unavailable');
      expect(o.reasons.last, contains('action_data.chemical'));
      expect(readExecutionOutcome(const {}).state, ExecutionState.pending);
    });

    test('executed=true بمرجع ⇒ نُفِّذ؛ بلا مرجع ⇒ غير مؤكَّد', () {
      final ok = readExecutionOutcome({
        'execute': {'executed': true, 'execution_ref': 'task-42'},
      });
      expect(ok.state, ExecutionState.executed);
      expect(ok.executionRef, 'task-42');
      expect(
        readExecutionOutcome({
          'execute': {'executed': true},
        }).state,
        ExecutionState.unconfirmed,
      );
    });
  });

  group('server execution projection', () {
    test('unknown physical effect overrides legacy executed=false', () {
      final wf = PestWorkflow.fromJson({
        'workflow': {'workflow_id': 'wf-uncertain', 'status': 'completed'},
        'execution': {
          'status': 'reconciliation_required',
          'executed': null,
          'reason': 'execution_not_confirmed',
        },
        'step_results': {
          'execute': {'executed': false, 'reason': 'execution_not_confirmed'},
        },
      });
      final o = readPestExecutionOutcome(wf.stepResults, wf.execution);
      expect(o.state, ExecutionState.unconfirmed);
      expect(o.reasons.single, contains('execution_not_confirmed'));
    });
    test('confirmed denial, not attempted, and truthful success stay distinct', () {
      expect(readPestExecutionOutcome({
        'execute': {'executed': false, 'blocked_by': 'guardrails'},
      }, {'status': 'not_executed', 'executed': false}).state, ExecutionState.notExecuted);
      expect(readPestExecutionOutcome({}, {
        'status': 'not_attempted', 'executed': false,
      }).state, ExecutionState.pending);
      expect(readPestExecutionOutcome({
        'execute': {'executed': true, 'execution_ref': 'job-7'},
      }, {
        'status': 'executed', 'executed': true, 'execution_ref': 'job-7',
      }).state, ExecutionState.executed);
      expect(readPestExecutionOutcome({
        'execute': {'executed': true, 'execution_ref': 'job-7'},
      }, {'status': 'not_executed', 'executed': false}).state, ExecutionState.unconfirmed);
    });
  });

  group('the server answer with no executor wired', () {
    test('executor_not_configured is not executed, with its note only', () {
      final o = readExecutionOutcome({
        'recommend': {'action_type': 'urgent_spray'},
        'execute': {
          'executed': false,
          'execution_ref': null,
          'reason': 'executor_not_configured',
          'note_ar': 'لم يُنفَّذ: لا منفّذ موصول لهذا الإجراء — القرار يبقى بشريّاً',
          'guardrails': {
            'allowed': true,
            'status': 'allowed',
            'reason_ar': 'سمح محرّك السلامة الكيميائيّة بالتنفيذ.',
          },
        },
      });
      expect(o.state, ExecutionState.notExecuted);
      expect(o.reasons, ['لم يُنفَّذ: لا منفّذ موصول لهذا الإجراء — القرار يبقى بشريّاً']);
      expect(o.blockedBy, isNull);
      expect(o.guardrailsStatus, 'allowed');
    });
  });

  group('an older server placeholder reference', () {
    test('exec-<action_type> with no executor wired is unconfirmed', () {
      final fromRecommend = readExecutionOutcome({
        'recommend': {'action_type': 'urgent_spray'},
        'execute': {'executed': true, 'execution_ref': 'exec-urgent_spray'},
      });
      expect(fromRecommend.state, ExecutionState.unconfirmed);
      expect(fromRecommend.reasons.single, contains('لا منفّذ موصول'));
      expect(
        readExecutionOutcome({
          'execute': {'executed': true, 'execution_ref': 'exec-biocontrol'},
        }, contextActionType: 'biocontrol').state,
        ExecutionState.unconfirmed,
      );
      final real = readExecutionOutcome({
        'execute': {'executed': true, 'execution_ref': 'task-7'},
      }, contextActionType: 'urgent_spray');
      expect(real.state, ExecutionState.executed);
      expect(real.executionRef, 'task-7');
    });
  });

  group('PestEscalationCubit — الموافقة', () {
    test('بلا سلسلة ⇒ approve لا يرسل شيئاً', () async {
      final adapter = FakeAdapter(
        (_) async => FakeReply(200, _suspended(_withoutLineageContext())),
      );
      final cubit = PestEscalationCubit(
        fakeAdvisorApi(adapter),
        newId: (pinId) => 'pest-pin-$pinId-r1',
      );
      await cubit.start(refs: refsFromPin(_pin(), null), severity: 0.85);
      expect(cubit.state.lineage.allowed, isFalse);
      await cubit.approve();
      expect(adapter.requests, hasLength(1));
      expect(
        jsonBody(adapter.requests.single.data)['workflow_id'],
        'pest-pin-pin_42-r1',
      );
    });

    test('بسلسلة ⇒ approve يعيد المراجع من سياق الخادم', () async {
      var calls = 0;
      final adapter = FakeAdapter(
        (_) async => ++calls == 1
            ? FakeReply(200, _suspended(_withLineageContext()))
            : FakeReply(200, _completedNotExecuted()),
      );
      final cubit = PestEscalationCubit(
        fakeAdvisorApi(adapter),
        newId: (pinId) => 'pest-pin-$pinId-r1',
      );
      await cubit.start(
        refs: refsFromPin(_pin(), _photoContext()),
        severity: 0.85,
      );
      expect(jsonBody(adapter.requests.first.data), {
        'workflow_id': 'pest-pin-pin_42-r1',
        'field_id': 'fld_1',
        'season_id': _seasonId,
        'diagnosis_ref': 'rev-3',
        'evidence_ref': 'scout_photo_evidence:ev-1@$_sha',
        'pest_type': 'tomato_leafminer',
        'severity': 0.85,
      });
      await cubit.approve();
      expect(jsonBody(adapter.requests.last.data), {
        'workflow_id': 'pest-pin-pin_42-r1',
        'field_id': 'fld_1',
        'season_id': _seasonId,
        'diagnosis_ref': 'rev-3',
        'evidence_ref': 'scout_photo_evidence:ev-1@$_sha',
        'approval_status': 'approved',
      });
      expect(cubit.state.workflow!.status, 'completed');
    });
  });

  group('PestEscalationScreen', () {
    Future<FakeAdapter> pumpScreen(
      WidgetTester tester,
      Map<String, dynamic> Function(int call) runReply,
    ) async {
      var runs = 0;
      final adapter = FakeAdapter((o) async {
        if (o.path == _pinsPath) {
          return FakeReply(200, {
            'field_id': 'fld_1',
            'pins': [_pinJson()],
            'total': 1,
          });
        }
        if (o.path == _ctxPath) return FakeReply(200, _photoContext());
        if (o.path == _runPath) return FakeReply(200, runReply(++runs));
        return const FakeReply(404, {'detail': 'not found'});
      });
      final client = testClient(
        adapter,
        MemoryTokenStore(accessToken: fakeJwt(const Duration(hours: 1))),
      );
      await tester.pumpWidget(
        hostApp(
          PestEscalationScreen(
            fieldId: 'fld_1',
            api: fakeAdvisorApi(adapter),
            scoutingApi: ScoutingApi(client),
          ),
        ),
      );
      await tester.pumpAndSettle();
      return adapter;
    }

    Future<void> pickPinAndStart(WidgetTester tester) async {
      final start = find.widgetWithText(
        PrimaryButton,
        'شغّل التصعيد من المشاهدة',
      );
      expect(tester.widget<PrimaryButton>(start).onPressed, isNull);
      await tester.tap(find.byType(DropdownButtonFormField<String>));
      await tester.pumpAndSettle();
      await tester.tap(find.text('tomato.tuta · شديدة').last);
      await tester.pumpAndSettle();
      expect(find.textContaining('scout_photo_evidence:ev-1@'), findsOneWidget);
      await tester.ensureVisible(start);
      await tester.tap(start);
      await tester.pumpAndSettle();
    }

    PrimaryButton approveButton(WidgetTester tester) => tester
        .widget<PrimaryButton>(find.byKey(const ValueKey('pest-approve')));

    testWidgets('بلا سلسلة ⇒ زرّ الموافقة معطَّل ومشروح', (tester) async {
      final adapter = await pumpScreen(
        tester,
        (_) => _suspended(_withoutLineageContext()),
      );
      await pickPinAndStart(tester);
      expect(adapter.to(_runPath), hasLength(1));
      expect(approveButton(tester).onPressed, isNull);
      expect(find.textContaining('الموافقة محجوبة'), findsOneWidget);
      expect(find.textContaining('MISSING_DIAGNOSIS_REF'), findsOneWidget);
    });

    testWidgets(
      'بسلسلة ⇒ زرّ الموافقة مُفعَّل، وexecuted=false يُعرَض «لم يُنفَّذ»',
      (tester) async {
        final adapter = await pumpScreen(
          tester,
          (call) => call == 1
              ? _suspended(_withLineageContext())
              : _completedNotExecuted(),
        );
        await pickPinAndStart(tester);
        expect(approveButton(tester).onPressed, isNotNull);
        expect(find.byKey(const ValueKey('lineage-reasons')), findsNothing);

        approveButton(tester).onPressed!();
        await tester.pumpAndSettle();
        await tester.tap(find.text('موافقة').last);
        await tester.pumpAndSettle();

        expect(adapter.to(_runPath), hasLength(2));
        expect(
          jsonBody(adapter.to(_runPath).last.data)['approval_status'],
          'approved',
        );
        expect(find.text('لم يُنفَّذ (executed=false)'), findsOneWidget);
        expect(find.textContaining('نُفِّذ بحسب الخادم'), findsNothing);
        expect(find.textContaining('action_data.chemical'), findsOneWidget);
        expect(find.byKey(const ValueKey('pest-approve')), findsNothing);
      },
    );
  });
}
