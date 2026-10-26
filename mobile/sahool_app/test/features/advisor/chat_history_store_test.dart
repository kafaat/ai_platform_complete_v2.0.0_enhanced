// السجلّ المشفّر: لكلّ (مستأجر، مستخدم) صندوقه ومفتاحه، لا نصّ صريح على القرص،
// ويُحذَف عند الخروج عبر FeatureModule.onSessionEnd.
import 'dart:io';

import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:hive/hive.dart';
import 'package:sahool_app/core/session/session_scope.dart';
import 'package:sahool_app/features/advisor/advisor_routes.dart';
import 'package:sahool_app/features/advisor/data/advisor_models.dart';
import 'package:sahool_app/features/advisor/data/chat_history_store.dart';

ChatEntry userMsg(String text) =>
    ChatEntry(role: ChatRole.user, text: text, at: DateTime.utc(2026, 10, 26));

void main() {
  late Directory dir;

  setUp(() async {
    dir = await Directory.systemTemp.createTemp('advisor_chat_');
    Hive.init(dir.path);
  });

  tearDown(() async {
    await Hive.close();
    await dir.delete(recursive: true);
  });

  test('two users on one device never see each other\'s chat', () async {
    final store = AdvisorChatStore(vault: MemoryChatKeyVault());
    final a = await store.openFor(tenantId: 't1', userId: 'alice');
    await a.append(userMsg('سؤال أليس'));
    final b = await store.openFor(tenantId: 't1', userId: 'bob');
    expect(a.persistent, isTrue);
    expect(await b.load(), isEmpty);
    await b.append(userMsg('سؤال بوب'));
    expect((await a.load()).map((e) => e.text), ['سؤال أليس']);
  });

  test('the same user id in another tenant gets a separate history', () async {
    final store = AdvisorChatStore(vault: MemoryChatKeyVault());
    final t1 = await store.openFor(tenantId: 't1', userId: 'u');
    await t1.append(userMsg('في المستأجر الأوّل'));
    final t2 = await store.openFor(tenantId: 't2', userId: 'u');
    expect(await t2.load(), isEmpty);
    expect(
      AdvisorChatStore.boxNameFor('t1', 'u'),
      isNot(AdvisorChatStore.boxNameFor('t2', 'u')),
    );
  });

  test('history is encrypted on disk and the key lives in the vault', () async {
    final vault = MemoryChatKeyVault();
    final store = AdvisorChatStore(vault: vault);
    final h = await store.openFor(tenantId: 't1', userId: 'alice');
    const secret = 'PLAINTEXT-MARKER-12345';
    await h.append(userMsg(secret));
    await Hive.close();

    final name = AdvisorChatStore.boxNameFor('t1', 'alice');
    final file = File('${dir.path}/$name.hive');
    expect(file.existsSync(), isTrue);
    final raw = String.fromCharCodes(file.readAsBytesSync());
    expect(raw.contains(secret), isFalse);
    expect(raw.contains('alice'), isFalse, reason: 'box name hides ids');
    expect(vault.values.keys.single, '${name}_key');

    // يُعاد فتحه بنفس المفتاح.
    final again = await store.openFor(tenantId: 't1', userId: 'alice');
    expect((await again.load()).single.text, secret);
  });

  test('endSession deletes the user\'s box and key', () async {
    final vault = MemoryChatKeyVault();
    final store = AdvisorChatStore(vault: vault);
    final h = await store.openFor(tenantId: 't1', userId: 'alice');
    await h.append(userMsg('سرّ'));
    await store.endSession(const SessionEnd(tenantId: 't1', userId: 'alice'));

    expect(vault.values, isEmpty);
    final name = AdvisorChatStore.boxNameFor('t1', 'alice');
    expect(await Hive.boxExists(name), isFalse);
    final reopened = await store.openFor(tenantId: 't1', userId: 'alice');
    expect(await reopened.load(), isEmpty);
  });

  test('the shared plaintext legacy box is wiped and never shown', () async {
    final legacy = await Hive.openBox<dynamic>(kLegacyAdvisorChatBox);
    await legacy.add({'role': 'user', 'text': 'محادثة مستخدم سابق'});
    final store = AdvisorChatStore(vault: MemoryChatKeyVault());
    final h = await store.openFor(tenantId: 't1', userId: 'bob');
    expect(await h.load(), isEmpty);
    expect(await Hive.boxExists(kLegacyAdvisorChatBox), isFalse);
  });

  test(
    'a stale legacy box on disk is deleted even when nothing opened it',
    () async {
      final legacy = await Hive.openBox<dynamic>(kLegacyAdvisorChatBox);
      await legacy.add({'role': 'user', 'text': 'محادثة مستخدم سابق'});
      await legacy.close();
      expect(await Hive.boxExists(kLegacyAdvisorChatBox), isTrue);
      await purgeLegacyAdvisorChat();
      expect(await Hive.boxExists(kLegacyAdvisorChatBox), isFalse);
      // لا صندوق ⇒ لا خطأ.
      await purgeLegacyAdvisorChat();
    },
  );

  test('without a user id the chat is memory-only (never plaintext)', () async {
    final store = AdvisorChatStore(vault: MemoryChatKeyVault());
    final h = await store.openFor(tenantId: 't1', userId: null);
    expect(h.persistent, isFalse);
  });

  test('history keeps at most kAdvisorHistoryCap messages', () async {
    final store = AdvisorChatStore(vault: MemoryChatKeyVault());
    final h = await store.openFor(tenantId: 't', userId: 'u');
    for (var i = 0; i < kAdvisorHistoryCap + 3; i++) {
      await h.append(userMsg('m$i'));
    }
    final items = await h.load();
    expect(items, hasLength(kAdvisorHistoryCap));
    expect(items.first.text, 'm3');
  });

  test(
    'logout through the feature module clears the advisor history',
    () async {
      FlutterSecureStorage.setMockInitialValues({});
      final h = await AdvisorChatStore.instance.openFor(
        tenantId: 't1',
        userId: 'alice',
      );
      await h.append(userMsg('سرّ المستخدم'));

      final scope = SessionScope()
        ..register(advisorFeature.id, advisorFeature.onSessionEnd!);
      final failed = await scope.endSession(
        const SessionEnd(tenantId: 't1', userId: 'alice'),
      );
      expect(failed, isEmpty);

      final name = AdvisorChatStore.boxNameFor('t1', 'alice');
      expect(await Hive.boxExists(name), isFalse);
      final next = await AdvisorChatStore.instance.openFor(
        tenantId: 't1',
        userId: 'alice',
      );
      expect(await next.load(), isEmpty);
    },
  );
}
