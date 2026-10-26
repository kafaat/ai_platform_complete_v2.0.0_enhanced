// شاشة المستشار: answer_ar يُعرَض، «غير معايَر» حين يقوله الخادم، 422 يُعرَض
// بصدق مع «أعد المحاولة» دون تكرار السؤال، الرفض بالسياسة معلَن، ولا كاميرا آفات.
import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sahool_app/features/advisor/data/advisor_models.dart';
import 'package:sahool_app/features/advisor/data/chat_history_store.dart';
import 'package:sahool_app/features/advisor/presentation/advisor_chat_cubit.dart';
import 'package:sahool_app/features/advisor/presentation/advisor_screen.dart';
import 'package:sahool_app/features/advisor/presentation/widgets/chat_bubbles.dart';

import '../../core/fake_http.dart';
import 'advisor_test_helpers.dart';

Future<void> pumpAdvisor(
  WidgetTester tester,
  FakeAdapter adapter, {
  AdvisorChatHistory? history,
  String? fieldId,
}) async {
  await tester.pumpWidget(
    hostApp(
      AdvisorScreen(
        api: fakeAdvisorApi(adapter),
        history: Future.value(history ?? MemoryChatHistory()),
        fieldId: fieldId,
        fieldName: fieldId == null ? null : 'الحقل الشماليّ',
      ),
    ),
  );
  await tester.pumpAndSettle();
}

Future<void> ask(WidgetTester tester, String text) async {
  await tester.enterText(find.byKey(const Key('advisor-input')), text);
  await tester.tap(find.byTooltip('إرسال'));
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('renders answer_ar, evidence and the uncalibrated label', (
    tester,
  ) async {
    final adapter = FakeAdapter(
      (_) async => FakeReply(200, chatReply(answer: 'المصادر المتاحة: RAG.')),
    );
    await pumpAdvisor(tester, adapter);
    await ask(tester, 'متى أروي؟');

    expect(find.text('متى أروي؟'), findsOneWidget);
    expect(find.text('المصادر المتاحة: RAG.'), findsOneWidget);
    expect(find.text(kNotCalibrated), findsOneWidget);
    expect(find.textContaining('جودة الدليل: 42'), findsOneWidget);
    expect(find.text('RAG · 3'), findsOneWidget);
    expect(find.text('Knowledge Graph · غير متاح'), findsOneWidget);
    expect(find.text('يحتاج مراجعة بشريّة'), findsOneWidget);
  });

  testWidgets('sends field_id when chatting from a field', (tester) async {
    final adapter = FakeAdapter(
      (_) async => FakeReply(200, chatReply(fieldId: 'f-9')),
    );
    await pumpAdvisor(tester, adapter, fieldId: 'f-9');
    expect(find.text('السياق: حقل الحقل الشماليّ'), findsOneWidget);
    await ask(tester, 'كيف حال الحقل؟');
    final body = jsonBody(adapter.requests.single.data);
    expect(body['question'], 'كيف حال الحقل؟');
    expect(body['field_id'], 'f-9');
  });

  testWidgets('a 422 is shown honestly; retry resends without a duplicate', (
    tester,
  ) async {
    var calls = 0;
    final adapter = FakeAdapter(
      (_) async => ++calls == 1
          ? FakeReply(422, fastApi422())
          : FakeReply(200, chatReply()),
    );
    await pumpAdvisor(tester, adapter);
    await ask(tester, 'سؤال');

    expect(find.byKey(const Key('advisor-failure')), findsOneWidget);
    expect(find.textContaining('رفض الخادم السؤال (422)'), findsOneWidget);
    expect(find.textContaining('Field required'), findsOneWidget);
    // لا إجابة مُلفَّقة ولا نصّ «لم أتمكن…» بدل الخطأ.
    expect(find.byType(AssistantBubble), findsNothing);

    await tester.tap(find.text('أعد المحاولة'));
    await tester.pumpAndSettle();
    expect(adapter.requests, hasLength(2));
    expect(jsonBody(adapter.requests.last.data)['question'], 'سؤال');
    expect(find.text('سؤال'), findsOneWidget, reason: 'no duplicate user turn');
    expect(find.byType(AssistantBubble), findsOneWidget);
    expect(find.byKey(const Key('advisor-failure')), findsNothing);
  });

  testWidgets('typing indicator while waiting; a second send is blocked', (
    tester,
  ) async {
    final gate = Completer<FakeReply>();
    final adapter = FakeAdapter((_) => gate.future);
    await pumpAdvisor(tester, adapter);
    await tester.enterText(find.byKey(const Key('advisor-input')), 'أوّل');
    await tester.tap(find.byTooltip('إرسال'));
    await tester.pump();
    await tester.pump();
    expect(find.byKey(const Key('advisor-typing')), findsOneWidget);

    await tester.enterText(find.byKey(const Key('advisor-input')), 'ثانٍ');
    await tester.tap(find.byTooltip('جارٍ الإرسال'));
    await tester.pump();
    expect(adapter.requests, hasLength(1));

    gate.complete(FakeReply(200, chatReply()));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('advisor-typing')), findsNothing);
    expect(find.byType(AssistantBubble), findsOneWidget);
  });

  testWidgets('generation refused by policy is announced, not hidden', (
    tester,
  ) async {
    final adapter = FakeAdapter(
      (_) async => FakeReply(
        200,
        chatReply(
          answer: 'لم تتوفر أدلة كافية للإجابة عن السؤال.',
          generationStatus: GenerationStatus.blockedByPolicy,
        ),
      ),
    );
    await pumpAdvisor(tester, adapter);
    await ask(tester, 'رأيك؟');
    expect(find.byKey(const Key('advisor-policy-blocked')), findsOneWidget);
    expect(find.textContaining('رفضت سياسة الذكاء الاصطناعيّ'), findsOneWidget);
  });

  testWidgets('copy puts the answer on the clipboard', (tester) async {
    String? copied;
    tester.binding.defaultBinaryMessenger.setMockMethodCallHandler(
      SystemChannels.platform,
      (call) async {
        if (call.method == 'Clipboard.setData') {
          copied = (call.arguments as Map)['text'] as String?;
        }
        return null;
      },
    );
    final adapter = FakeAdapter(
      (_) async => FakeReply(200, chatReply(answer: 'انسخني')),
    );
    await pumpAdvisor(tester, adapter);
    await ask(tester, 'س');
    await tester.tap(find.byTooltip('نسخ الإجابة'));
    await tester.pumpAndSettle();
    expect(copied, 'انسخني');
    expect(find.text('تم النسخ'), findsOneWidget);
  });

  testWidgets('saved history of this user is shown on open', (tester) async {
    final history = MemoryChatHistory([
      ChatEntry(
        role: ChatRole.assistant,
        text: 'جواب سابق',
        at: DateTime.utc(2026, 10, 1),
        reply: AdvisorReply.fromJson(chatReply(answer: 'جواب سابق')),
      ),
    ]);
    await pumpAdvisor(
      tester,
      FakeAdapter((_) async => const FakeReply(500)),
      history: history,
    );
    expect(find.text('جواب سابق'), findsOneWidget);
  });

  testWidgets('no pest camera in the advisor; scouting is linked instead', (
    tester,
  ) async {
    final adapter = FakeAdapter((_) async => FakeReply(200, chatReply()));
    await pumpAdvisor(tester, adapter);
    // الزرّ القديم (أيقونة كاميرا بتلميح) في شريط الإدخال اختفى.
    expect(find.byTooltip('تشخيص الآفات بالصورة'), findsNothing);
    await tester.scrollUntilVisible(
      find.text('تشخيص الآفات بالصورة'),
      200,
      scrollable: find.byType(Scrollable).first,
    );
    expect(find.textContaining('الاستكشاف الميدانيّ'), findsOneWidget);
  });

  test('error wording: 502 without field context names the cause', () {
    final text = advisorChatErrorText(
      apiError(502, {
        'detail': {'dependency': 'canonical-field-state', 'field_id': 'f'},
      }),
    );
    expect(text, contains('سياق الحقل'));
  });
}
