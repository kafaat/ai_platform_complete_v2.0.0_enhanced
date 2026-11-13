import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sahool_app/features/scouting/presentation/disease_symptoms_dialog.dart';
import '../../core/fake_http.dart';
import 'scouting_fakes.dart';

void main() {
  testWidgets('appends a suspected cause only after inspector confirmation', (tester) async {
    String? note;
    final (api, _) = fakeApi((request) async {
      if (request.method == 'GET') {
        expect(request.path, '/api/v1/diagnose/symptoms');
        return const FakeReply(200, {'symptoms': [{'code':'orange_pustules','name_ar':'بثور'}]});
      }
      expect(request.path, '/api/v1/diagnose');
      expect(request.data, {'field_id': sanaaField.id, 'crop': sanaaField.crop, 'symptoms':['orange_pustules']});
      return const FakeReply(200, {'candidates':[{'name_ar':'صدأ القمح'}], 'next_step_ar':'راجع المختص'});
    });
    await tester.pumpWidget(MaterialApp(home: Builder(builder: (context) => TextButton(
      child: const Text('فتح'),
      onPressed: () async {
        note = await showDialog<String>(context: context,
            builder: (_) => DiseaseSymptomsDialog(api: api, field: sanaaField));
      },
    ))));
    await tester.tap(find.text('فتح'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('بثور'));
    await tester.pump();
    await tester.tap(find.text('تحليل الأعراض'));
    await tester.pumpAndSettle();
    expect(note, isNull);
    await tester.tap(find.text('إضافة إلى الملاحظة'));
    await tester.pumpAndSettle();
    expect(note, contains('اشتباه أولي بحسب الأعراض: صدأ القمح'));
  });
}
