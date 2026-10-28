// D2: عقد المخزن نفسه — الحفظ والمسح المشروطان بجيل الجلسة، والجيل يتحرّك مع
// تغيّر هويّة الجلسة لا مع التجديد. AuthService الحقيقيّ فوق تخزين آمن وهميّ،
// ويُعاد فتح المخزن من القرص بعد كلّ سباق. (السلوك عبر ApiClient في
// session_generation_test.dart.)
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sahool_app/core/network/api_client.dart';
import 'package:sahool_app/services/auth_service.dart';

import 'fake_http.dart';

Future<void> settle() async {
  for (var i = 0; i < 20; i++) {
    await Future<void>.delayed(Duration.zero);
  }
}

void main() {
  final expiredA = fakeJwt(const Duration(hours: -1), sub: 'A-old');
  final freshA = fakeJwt(const Duration(hours: 1), sub: 'A2');
  final validB = fakeJwt(const Duration(hours: 1), sub: 'B1');
  const store = AuthServiceTokenStore();
  final auth = AuthService.instance;

  Future<void> signInA() async {
    FlutterSecureStorage.setMockInitialValues({
      'access_token': expiredA,
      'refresh_token': 'rA',
      'user_id': 'A',
      'user_profile': '{"user_id":"A","tenant_id":"t-A","role":"owner"}',
    });
    await auth.loadSaved();
    expect(auth.refreshToken, 'rA');
  }

  Future<void> switchToB() async {
    await auth.clearAuth();
    await auth.saveToken(validB,
        refresh: 'rB',
        profile: {'user_id': 'B', 'tenant_id': 't-B', 'role': 'owner'});
  }

  Future<void> expectBPersisted() async {
    await settle();
    await auth.loadSaved(); // أعِد فتح المخزن: ما على القرص هو الحكم
    expect(auth.token, validB);
    expect(auth.refreshToken, 'rB');
    expect(auth.userId, 'B');
    expect(auth.tenantId, 't-B');
  }

  tearDown(() => auth.clearAuth());

  test('generation-conditional save: a racing login wins in memory and on '
      'disk, and a stale save or clear is refused', () async {
    await signInA();
    final gA = store.generation;

    // (1) الحفظ يبدأ لجيل A (الفحص يمرّ) ثمّ يدخل B قبل أن تكتمل كتابته.
    final saved = store.saveTokens(freshA, refresh: 'rA2', generation: gA);
    final login = switchToB();
    expect(await saved, isTrue, reason: 'جيل A كان حاليّاً لحظة الفحص');
    await login;
    expect(auth.token, validB);
    expect(auth.refreshToken, 'rB');
    await expectBPersisted();

    // (2) بعد التبديل: حفظ ومسح بجيل A مرفوضان ولا يمسّان B.
    expect(store.generation, isNot(gA));
    expect(await store.saveTokens(freshA, refresh: 'rA2', generation: gA),
        isFalse);
    expect(await store.clear(generation: gA), isFalse);
    await expectBPersisted();
  });

  test('a conditional save racing a logout does not resurrect the session',
      () async {
    await signInA();
    final gA = store.generation;
    final saved = store.saveTokens(freshA, refresh: 'rA2', generation: gA);
    final logout = auth.clearAuth();
    await Future.wait([saved, logout]);
    await settle();
    await auth.loadSaved();
    expect(auth.token, isNull);
    expect(auth.refreshToken, isNull);
  });

  test('the session generation moves on restore, login, logout and clear, '
      'not on a refresh', () async {
    await signInA();
    final g0 = auth.sessionGeneration;
    expect(auth.sessionOwner, 't-A/A');
    expect(await auth.saveRefreshedToken(g0, freshA, refresh: 'rA2'), isTrue);
    expect(auth.sessionGeneration, g0, reason: 'التجديد لا يبدّل الجلسة');
    await auth.saveToken(validB, refresh: 'rB', profile: {'user_id': 'B'});
    final g1 = auth.sessionGeneration;
    expect(g1, greaterThan(g0));
    await auth.clearAuth();
    final g2 = auth.sessionGeneration;
    expect(g2, greaterThan(g1));
    await auth.loadSaved();
    expect(auth.sessionGeneration, greaterThan(g2));
    expect(auth.sessionOwner, isNull);
  });
}
