// مكوّنات نظام التصميم: الحالات الصادقة، «غير مقيس»، أهداف اللمس، اللافتة.
import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sahool_app/core/network/api_exception.dart';
import 'package:sahool_app/core/network/connectivity_status.dart';
import 'package:sahool_app/core/theme/app_theme.dart';
import 'package:sahool_app/core/widgets/state_views.dart';
import 'package:sahool_app/core/widgets/widgets.dart';

Widget host(Widget child, {ThemeData? theme}) => MaterialApp(
      theme: theme ?? AppTheme.light,
      locale: const Locale('ar'),
      supportedLocales: const [Locale('ar'), Locale('en')],
      localizationsDelegates: GlobalMaterialLocalizations.delegates,
      home: Scaffold(body: child),
    );

DioException dioWith(int status) {
  final o = RequestOptions(path: '/x');
  return DioException(
      requestOptions: o,
      type: DioExceptionType.badResponse,
      response: Response(requestOptions: o, statusCode: status));
}

void main() {
  testWidgets('ErrorState shows the honest 503 message and a retry', (t) async {
    var retried = 0;
    await t.pumpWidget(host(ErrorState(error: dioWith(503), onRetry: () => retried++)));
    expect(find.text('الخدمة غير متاحة حاليّاً (قاعدة البيانات معطّلة على الخادم).'),
        findsOneWidget);
    await t.tap(find.text('إعادة المحاولة'));
    expect(retried, 1);
  });

  testWidgets('ErrorState: 403 has no retry button (retrying cannot help)',
      (t) async {
    await t.pumpWidget(host(ErrorState(error: dioWith(403), onRetry: () {})));
    expect(find.text('لا تملك صلاحيّة الوصول إلى هذا القسم.'), findsOneWidget);
    expect(find.text('إعادة المحاولة'), findsNothing);
    expect(find.byIcon(Icons.lock_outline_rounded), findsOneWidget);
  });

  test('apiErrorMessage keeps 401/403/404/503 wording through ApiException', () {
    expect(apiErrorMessage(dioWith(401)), 'انتهت الجلسة — يُرجى تسجيل الدخول من جديد.');
    expect(apiErrorMessage(dioWith(404)), 'العنصر غير موجود.');
    expect(apiErrorMessage(const ApiException(
            kind: ApiErrorKind.timeout, messageAr: 'm')),
        'm');
  });

  testWidgets('MetricTile renders null as "غير مقيس" and never a number',
      (t) async {
    await t.pumpWidget(host(const MetricTile(label: 'المساحة', value: null, unit: 'هـ')));
    expect(find.text('غير مقيس'), findsOneWidget);
    expect(find.text('هـ'), findsNothing);
    await t.pumpWidget(host(const MetricTile(label: 'المساحة', value: 1.5, unit: 'هـ')));
    expect(find.text('1.5'), findsOneWidget);
    expect(find.text('هـ'), findsOneWidget);
  });

  testWidgets('PrimaryButton is at least 48dp tall and blocks double submit',
      (t) async {
    var taps = 0;
    await t.pumpWidget(host(PrimaryButton(label: 'حفظ', onPressed: () => taps++)));
    expect(t.getSize(find.byType(FilledButton)).height,
        greaterThanOrEqualTo(48));
    await t.pumpWidget(host(
        PrimaryButton(label: 'حفظ', loading: true, onPressed: () => taps++)));
    await t.tap(find.byType(FilledButton));
    expect(taps, 0);
  });

  testWidgets('StatusChip pairs colour with an icon and text', (t) async {
    await t.pumpWidget(host(const StatusChip(label: 'حرج', tone: StatusTone.danger)));
    expect(find.text('حرج'), findsOneWidget);
    expect(find.byIcon(Icons.error_outline_rounded), findsOneWidget);
  });

  testWidgets('AppNumberField accepts Arabic-Indic digits', (t) async {
    final c = TextEditingController();
    await t.pumpWidget(host(Form(child: AppNumberField(label: 'المساحة', controller: c))));
    await t.enterText(find.byType(TextFormField), '٢٫٥');
    expect(c.text, '2.5');
  });

  testWidgets('offline banner appears only when the network is gone', (t) async {
    final status = ConnectivityStatus();
    await t.pumpWidget(host(OfflineBannerHost(status: status, child: const Text('body'))));
    expect(find.byType(OfflineBanner), findsNothing);
    status.value = false;
    await t.pump();
    expect(find.byType(OfflineBanner), findsOneWidget);
    expect(find.text('body'), findsOneWidget);
  });

  testWidgets('showConfirmDialog returns true only on explicit confirm',
      (t) async {
    bool? result;
    await t.pumpWidget(host(Builder(
        builder: (ctx) => TextButton(
            onPressed: () async => result = await showConfirmDialog(ctx,
                title: 'حذف', message: 'متأكّد؟', destructive: true),
            child: const Text('open')))));
    await t.tap(find.text('open'));
    await t.pumpAndSettle();
    await t.tap(find.text('إلغاء'));
    await t.pumpAndSettle();
    expect(result, isFalse);
    await t.tap(find.text('open'));
    await t.pumpAndSettle();
    await t.tap(find.text('تأكيد'));
    await t.pumpAndSettle();
    expect(result, isTrue);
  });

  for (final entry in {'light': AppTheme.light, 'dark': AppTheme.dark}.entries) {
    testWidgets('showSnack uses theme colours (${entry.key})', (t) async {
      final theme = entry.value;
      await t.pumpWidget(host(
        Builder(
          builder: (context) => Column(children: [
            TextButton(
                onPressed: () => showSnack(context, 'تمّ'),
                child: const Text('ok')),
            TextButton(
                onPressed: () => showSnack(context, 'فشل', error: true),
                child: const Text('err')),
          ]),
        ),
        theme: theme,
      ));
      final scheme = theme.colorScheme;
      await t.tap(find.text('ok'));
      await t.pump();
      var bar = t.widget<SnackBar>(find.byType(SnackBar));
      expect(bar.backgroundColor, scheme.primary);
      expect(t.widget<Text>(find.text('تمّ')).style?.color, scheme.onPrimary);
      ScaffoldMessenger.of(t.element(find.text('ok'))).removeCurrentSnackBar();
      await t.pump();
      await t.tap(find.text('err'));
      await t.pump();
      bar = t.widget<SnackBar>(find.byType(SnackBar));
      expect(bar.backgroundColor, scheme.error);
      expect(t.widget<Text>(find.text('فشل')).style?.color, scheme.onError);
    });
  }
}
