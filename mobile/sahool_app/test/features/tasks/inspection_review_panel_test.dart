import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sahool_app/core/network/api_client.dart';
import 'package:sahool_app/features/tasks/data/field_task.dart';
import 'package:sahool_app/features/tasks/presentation/inspection_review_panel.dart';

import '../../core/fake_http.dart';

const _task = FieldTask(
  id: 't1',
  fieldId: 'f1',
  type: 'scouting',
  status: 'in_progress',
);
const _path = '/api/v1/field-tasks/fields/f1/tasks/t1/handoff';

Future<FakeAdapter> _open(
  WidgetTester tester,
  Map<String, Object?> history,
) async {
  final adapter = FakeAdapter((request) async => FakeReply(200, history));
  final dio = ApiClient.instance.dio;
  final previous = dio.httpClientAdapter;
  dio.httpClientAdapter = adapter;
  addTearDown(() => dio.httpClientAdapter = previous);
  await tester.pumpWidget(
    const MaterialApp(home: Scaffold(body: InspectionReviewPanel(task: _task))),
  );
  await tester.pumpAndSettle();
  return adapter;
}

void main() {
  testWidgets('submitting inspection text binds the note to the evidence version', (tester) async {
    final adapter = await _open(tester, {
      'revision': 3,
      'can_submit': true,
      'current_evidence': {'photo_evidence_id': 'e-2'},
    });
    await tester.enterText(find.byType(TextField).first, '  تغيّرت القراءة  ');
    await tester.enterText(find.byType(TextField).last, 'eqp_pump_a');
    await tester.pump();
    await tester.tap(find.text('رفع النتيجة للمراجعة'));
    await tester.pumpAndSettle();
    expect(adapter.to('$_path/finding').single.data, {
      'action': 'submit',
      'expected_revision': 3,
      'reason': 'تغيّرت القراءة',
      'notes': 'تغيّرت القراءة',
      'photo_evidence_id': 'e-2',
      'equipment_id': 'eqp_pump_a',
    });
  });

  testWidgets('review sends a comment and the submitted evidence version', (tester) async {
    final adapter = await _open(tester, {
      'revision': 4,
      'can_review': true,
      'events': [{'action': 'submit', 'evidence_version': 2}],
      'evidence': [{'version': 2, 'equipment_id': 'eqp_pump_a'}],
    });
    expect(find.textContaining('المعدّة المصرّح بها: eqp_pump_a'), findsOneWidget);
    await tester.enterText(find.byType(TextField), '  تم التحقق  ');
    await tester.pump();
    await tester.tap(find.text('اعتماد النتيجة'));
    await tester.pumpAndSettle();
    expect(adapter.to('$_path/finding').single.data, {
      'action': 'approve',
      'expected_revision': 4,
      'reason': 'تم التحقق',
      'evidence_version': 2,
    });
  });
}
