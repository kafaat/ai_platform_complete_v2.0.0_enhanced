// D3 — صندوق الإرسال الدائم فوق خادم HTTP محلّيّ حقيقيّ (dart:io HttpServer) وصندوق
// Hive حقيقيّ يُعاد فتحه:
//   • R10: تبدّل المالك أثناء التصريف — لا إرسال لاحق بهويّة جديدة، ولا حذف
//     لعمليّة المالك القديم لأنّ ردّها وصل لجلسةٍ أخرى؛ تُطابَق بنفس المفتاح حين
//     يعود. الإلغاء على الجهاز لا يوقف ما التزم به الخادم.
//   • حارس المالك داخل ApiClient: تجديدٌ بعد 401 أعاد رمز جلسةٍ أخرى ⇒ لا يُعاد
//     طلب المالك القديم بها.
//   • R11: 429 + Retry-After (ثوانٍ وتاريخ HTTP) ثمّ إعادة التشغيل — الموعد محفوظ
//     ولا إعادة فوريّة: لا عند فتح الصندوق، ولا عند عودة الشبكة، ولا يدويّاً.
//   • 503 + Retry-After لا يُعاد ثلاث مرّات فوراً داخل ApiClient.
//   • 409: payload_mismatch ⇒ تحتاج تدخّلاً بلا إعادة عمياء؛ in_progress ⇒ لاحقاً.
//   • تعذّر التجديد (شبكة/5xx) ليس تبدّل مالك: backoff أُسّيّ محفوظ، لا حلقة
//     إعادة/تجديد كلّ ثانية؛ ورفض الحارس بلا تبدّل جلسة يحفظ موعده كذلك.
//
// لا TestWidgetsFlutterBinding هنا: الربط يستبدل HttpClient بعميلٍ يردّ 400 دائماً.
import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:dio/dio.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:hive/hive.dart';
import 'package:sahool_app/core/network/api_client.dart';
import 'package:sahool_app/core/network/idempotency.dart';
import 'package:sahool_app/core/session/session_scope.dart';
import 'package:sahool_app/features/offline_sync/data/durable_offline_outbox.dart';
import 'package:sahool_app/features/offline_sync/data/offline_sync_api.dart';
import 'package:sahool_app/features/offline_sync/data/outbox_record.dart';
import 'package:sahool_app/features/offline_sync/data/outbox_store.dart';

import '../../core/fake_http.dart';
import 'outbox_test_support.dart';

/// طلب كما استقبله الخادم المحلّيّ.
class _Seen {
  _Seen(this.method, this.path, this.auth, this.key, this.body);
  final String method;
  final String path;
  final String? auth;
  final String? key;
  final String body;

  String? get sub {
    final a = auth;
    if (a == null || !a.startsWith('Bearer ')) return null;
    return OutboxOwner.fromAccessToken(a.substring(7))?.userId;
  }
}

typedef _Handler = Future<void> Function(HttpRequest req, _Seen seen);

/// خادم محلّيّ يسجّل كلّ طلب و«يلتزم» بكلّ مفتاح مرّة واحدة (كما يفعل
/// api/main.py:_idempotent): الإعادة بنفس المفتاح تُعيد النتيجة المخزّنة.
class _Server {
  _Server._(this._http);
  final HttpServer _http;
  final List<_Seen> seen = [];

  /// المفاتيح التي نُفّذت فعلاً (التزام الخادم)، بعدد مرّات التنفيذ.
  final Map<String, int> committed = {};
  _Handler? handler;

  static Future<_Server> start() async {
    final http = await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
    final s = _Server._(http);
    http.listen((req) async {
      final body = await utf8.decoder.bind(req).join();
      final seen = _Seen(
        req.method,
        req.uri.path,
        req.headers.value('authorization'),
        req.headers.value(kIdempotencyHeader),
        body,
      );
      s.seen.add(seen);
      final h = s.handler;
      try {
        if (h != null) {
          await h(req, seen);
        } else {
          await s.commitAndReply(req, seen);
        }
      } catch (_) {
        // الاتّصال أُغلق من العميل (إلغاء) — الالتزام حدث قبله.
      }
    });
    return s;
  }

  String get base => 'http://127.0.0.1:${_http.port}';

  List<_Seen> to(String path) => seen.where((r) => r.path == path).toList();

  /// ينفّذ مرّة واحدة لكلّ مفتاح ويردّ 200 (أو إعادة idempotent).
  Future<void> commitAndReply(HttpRequest req, _Seen seen) async {
    final key = seen.key ?? '';
    final replay = committed.containsKey(key);
    if (!replay) committed[key] = 1;
    req.response
      ..statusCode = 200
      ..headers.contentType = ContentType.json
      ..write(jsonEncode({'ok': true, 'idempotent_replay': replay}));
    await req.response.close();
  }

  static Future<void> reply(
    HttpRequest req,
    int status, {
    Object? body,
    Map<String, String> headers = const {},
  }) async {
    req.response.statusCode = status;
    req.response.headers.contentType = ContentType.json;
    headers.forEach(req.response.headers.set);
    req.response.write(jsonEncode(body ?? {}));
    await req.response.close();
  }

  Future<void> close() => _http.close(force: true);
}

void main() {
  late Directory dir;
  late _Server server;
  late MemoryTokenStore tokens;
  late ApiClient client;

  setUp(() async {
    dir = Directory.systemTemp.createTempSync('d3_outbox');
    Hive.init(dir.path);
    FlutterSecureStorage.setMockInitialValues({});
    server = await _Server.start();
    tokens = MemoryTokenStore(accessToken: jwtFor('alice'));
    client = ApiClient(
      baseUrl: server.base,
      tokens: tokens,
      retryBaseDelay: const Duration(milliseconds: 1),
      retryJitterMs: 0,
    );
  });

  tearDown(() async {
    await server.close();
    await Hive.close();
    dir.deleteSync(recursive: true);
  });

  /// صندوق دائم فوق Hive الحقيقيّ و ApiClient الحقيقيّ والخادم المحلّيّ.
  DurableOfflineOutbox outboxOver({
    required ValueNotifier<bool> connectivity,
    DateTime Function()? clock,
    List<RecordedTimer>? timers,
    bool drainOnOpen = false,
    OutboxOwner? Function()? currentOwner,
  }) => DurableOfflineOutbox(
    openStore: HiveOutboxStore.openEncrypted,
    currentOwner:
        currentOwner ?? () => OutboxOwner.fromAccessToken(tokens.accessToken),
    api: OfflineSyncApi(client),
    connectivity: connectivity,
    drainOnOpen: drainOnOpen,
    clock: clock,
    timer: (d, cb) {
      final t = RecordedTimer(d, cb);
      timers?.add(t);
      return t;
    },
  );

  Map<String, dynamic> rawRow(String id) {
    final box = Hive.box<String>(HiveOutboxStore.boxName);
    return jsonDecode(box.get(id)!) as Map<String, dynamic>;
  }

  Future<void> until(bool Function() cond) async {
    for (var i = 0; i < 400 && !cond(); i++) {
      await Future<void>.delayed(const Duration(milliseconds: 5));
    }
    expect(cond(), isTrue);
  }

  group('R10 — تبدّل المالك أثناء التصريف', () {
    test('ردّ 2xx وصل بعد تبدّل الجلسة: لا إرسال بهويّة bob، ولا حذف لعمليّة '
        'alice؛ تبقى «غير مؤكَّدة» عبر إعادة التشغيل وتُطابَق بنفس المفتاح حين '
        'تعود', () async {
      final offline = ValueNotifier<bool>(false);
      final outbox = outboxOver(connectivity: offline);
      final o1 = op('/api/v1/tasks/1', fieldId: 'f1');
      final o2 = op('/api/v1/tasks/2', fieldId: 'f2');
      expect((await outbox.enqueue(o1)).queued, isTrue);
      expect((await outbox.enqueue(o2)).queued, isTrue);
      final id1 = outbox.snapshot().pending.first.id;
      final id2 = outbox.snapshot().pending.last.id;

      final gate = Completer<void>();
      server.handler = (req, seen) async {
        if (seen.path == '/api/v1/tasks/1' && !gate.isCompleted) {
          // الخادم يلتزم ثمّ يتأخّر ردّه.
          server.committed[seen.key!] = 1;
          await gate.future;
          await _Server.reply(req, 200, body: {'ok': true});
          return;
        }
        await server.commitAndReply(req, seen);
      };
      final run = outbox.drain();
      await until(() => server.seen.length == 1);
      // bob يدخل قبل أن يصل إشعار الخروج (لا onSessionEnd) — الردّ في الطريق.
      tokens.accessToken = jwtFor('bob');
      gate.complete();
      await run;

      expect(server.seen, hasLength(1), reason: 'لا طلب لاحق بعد التبدّل');
      expect(server.seen.single.sub, 'alice');
      final store = (await outbox.ensureOpen())!;
      expect(
        store.byId(id1),
        isNotNull,
        reason: 'ردٌّ وصل لجلسة bob لا يحذف عمليّة alice',
      );
      expect(rawRow(id1)['outcome_unknown'], isTrue);
      expect(store.byId(id2)!.attempts, 0, reason: 'الثانية لم تُمسّ');

      // bob يصرّف يدويّاً: لا شيء من عمليّات alice يُرسَل.
      await outbox.drain(ignoreBackoff: true);
      expect(server.seen, hasLength(1));

      // إعادة تشغيل التطبيق ثمّ عودة alice.
      await Hive.close();
      tokens.accessToken = jwtFor('alice');
      final reopened = outboxOver(connectivity: ValueNotifier<bool>(true));
      await reopened.ensureOpen();
      expect(reopened.snapshot().pending.map((r) => r.id), [id1, id2]);
      await reopened.drain();
      await until(() => reopened.snapshot().pending.isEmpty);

      final sentKeys = server.seen.map((r) => r.key).toList();
      expect(sentKeys, [
        o1.idempotencyKey,
        o1.idempotencyKey,
        o2.idempotencyKey,
      ]);
      expect(server.seen.every((r) => r.sub == 'alice'), isTrue);
      expect(
        server.committed[o1.idempotencyKey],
        1,
        reason: 'المطابقة بنفس المفتاح لم تُنشئ عملاً ثانياً',
      );
    });

    test('نهاية الجلسة تلغي الطلب الجاري على الجهاز، لكنّ الخادم التزم: '
        'العمليّة تبقى «غير مؤكَّدة» لا «محفوظة لم تُرسَل»', () async {
      final outbox = outboxOver(connectivity: ValueNotifier<bool>(false));
      final o1 = op('/api/v1/tasks/1');
      await outbox.enqueue(o1);
      final id1 = outbox.snapshot().pending.single.id;
      final hold = Completer<void>();
      server.handler = (req, seen) async {
        server.committed[seen.key!] = 1; // التزم
        await hold.future; // ولم يردّ بعد
        await _Server.reply(req, 200);
      };
      final run = outbox.drain();
      await until(() => server.seen.length == 1);
      await outbox.onSessionEnd(
        const SessionEnd(userId: 'alice', tenantId: 't1'),
      );
      await run;
      hold.complete();

      expect(server.committed[o1.idempotencyKey], 1);
      final row = rawRow(id1);
      expect(row['state'], 'pending');
      expect(
        row['outcome_unknown'],
        isTrue,
        reason: 'الإلغاء على الجهاز ليس دليلاً على أنّ الخادم لم ينفّذ',
      );
      expect(row['attempts'], 1);
    });

    test('حارس المالك داخل ApiClient: تجديدٌ بعد 401 أعاد رمز bob ⇒ لا يُعاد '
        'طلب alice برمز bob', () async {
      tokens.refreshToken = 'refresh-alice';
      final outbox = outboxOver(connectivity: ValueNotifier<bool>(false));
      await outbox.enqueue(op('/api/v1/tasks/1'));
      final gate = Completer<void>();
      server.handler = (req, seen) async {
        if (seen.path == '/auth/refresh') {
          // الخادم يجدّد لصاحب رمز التحديث المرسَل — وهو الآن bob.
          final sent = (jsonDecode(seen.body) as Map)['refresh_token'];
          final who = sent == 'refresh-bob' ? 'bob' : 'alice';
          await _Server.reply(
            req,
            200,
            body: {'access_token': jwtFor(who), 'refresh_token': 'r2-$who'},
          );
          return;
        }
        if (seen.sub == 'alice') {
          await gate.future;
          await _Server.reply(req, 401, body: {'detail': 'expired'});
          return;
        }
        await server.commitAndReply(req, seen);
      };
      final run = outbox.drain();
      await until(() => server.seen.length == 1);
      // تبدّل الجلسة إلى bob أثناء الطلب.
      tokens.accessToken = jwtFor('bob');
      tokens.refreshToken = 'refresh-bob';
      gate.complete();
      await run;

      final opRequests = server.to('/api/v1/tasks/1');
      expect(opRequests.map((r) => r.sub), [
        'alice',
      ], reason: 'لا نسخة من طلب alice تخرج برمز bob');
      expect(server.committed, isEmpty);
      final kept = (await outbox.ensureOpen())!.records.single;
      expect(kept.owner.userId, 'alice');
      expect(kept.isPending, isTrue);
    });
  });

  group('R11 — Retry-After محفوظ عبر إعادة التشغيل', () {
    Future<void> scenario(
      String Function(DateTime now) retryAfterHeader,
      Duration expectedWait,
    ) async {
      // ساعة على ثانية كاملة (تاريخ HTTP بدقّة الثانية).
      var now = DateTime.utc(2026, 10, 27, 9);
      var limited = true;
      server.handler = (req, seen) async {
        if (limited) {
          await _Server.reply(
            req,
            429,
            body: {'detail': 'rate limited'},
            headers: {'Retry-After': retryAfterHeader(now)},
          );
          return;
        }
        await server.commitAndReply(req, seen);
      };
      final online = ValueNotifier<bool>(true);
      final first = outboxOver(connectivity: online, clock: () => now);
      final o = op('/api/v1/tasks/9');
      await first.enqueue(o); // متّصل ⇒ يُرسَل فوراً
      await until(() => server.seen.isNotEmpty);
      await first.drain();
      expect(server.seen, hasLength(1));
      final id = first.snapshot().pending.single.id;
      final row = rawRow(id);
      expect(row['attempts'], 1);
      expect(
        DateTime.parse(row['not_before'] as String),
        now.add(expectedWait),
        reason: 'Retry-After محفوظ في السجلّ نفسه',
      );
      expect(
        DateTime.parse(
          row['next_attempt_at'] as String,
        ).isBefore(now.add(expectedWait)),
        isFalse,
      );

      // الشبكة تنقطع وتعود: وجودها لا يلغي الموعد.
      online.value = false;
      online.value = true;
      await first.drain();
      expect(server.seen, hasLength(1), reason: 'عودة الشبكة لا تُرسل');

      // إعادة تشغيل التطبيق: صندوق يُعاد فتحه ويصرّف عند الفتح.
      await Hive.close();
      final timers = <RecordedTimer>[];
      final second = outboxOver(
        connectivity: ValueNotifier<bool>(true),
        clock: () => now,
        timers: timers,
        drainOnOpen: true,
      );
      await second.ensureOpen();
      await second.drain();
      expect(server.seen, hasLength(1), reason: 'لا إعادة فوريّة بعد الإقلاع');
      // «إرسال الآن» يتخطّى backoff لا Retry-After.
      await second.drain(ignoreBackoff: true);
      expect(server.seen, hasLength(1), reason: 'ولا يدويّاً قبل الموعد');
      final active = timers.where((t) => t.isActive).toList();
      expect(active, isNotEmpty);
      expect(active.last.delay, greaterThanOrEqualTo(expectedWait));

      // حين يحين الموعد يُرسَل بنفس المفتاح.
      limited = false;
      now = now.add(active.last.delay);
      active.last.fire();
      await until(() => second.snapshot().pending.isEmpty);
      expect(server.seen, hasLength(2));
      expect(server.seen.map((r) => r.key).toSet(), {o.idempotencyKey});
    }

    test('صيغة الثواني', () async {
      await scenario((_) => '120', const Duration(seconds: 120));
    });

    test('صيغة تاريخ HTTP', () async {
      await scenario(
        (now) => HttpDate.format(now.add(const Duration(seconds: 90))),
        const Duration(seconds: 90),
      );
    });
  });

  test('503 + Retry-After: طلب واحد — لا ثلاث إعادات فوريّة داخل ApiClient '
      'تتجاهل الموعد', () async {
    server.handler = (req, seen) => _Server.reply(
      req,
      503,
      body: {'detail': 'maintenance'},
      headers: {'Retry-After': '120'},
    );
    final now = DateTime.utc(2026, 10, 27, 9);
    final outbox = outboxOver(
      connectivity: ValueNotifier<bool>(false),
      clock: () => now,
    );
    await outbox.enqueue(op('/api/v1/tasks/3'));
    await outbox.drain();
    expect(server.seen, hasLength(1));
    final r = outbox.snapshot().pending.single;
    expect(r.toJson()['not_before'], isNotNull);
    expect(r.toJson()['outcome_unknown'], isFalse, reason: '503 ⇒ لم يُنفَّذ');
  });

  test('عودة الشبكة تتخطّى انتظاراً سببه انقطاعها هي فقط (حارس انحدار: لا '
      'ينتظر المزارع backoff نصف ساعة بعد عودة الاتّصال)', () async {
    var reachable = false;
    final h = Harness(
      handler: (_) async => reachable
          ? const FakeReply(200, {'ok': true})
          : const FakeReply.fail(DioExceptionType.connectionError),
    );
    await h.outbox.enqueue(op('/api/v1/tasks/1'));
    await h.outbox.drain();
    final r = h.store.records.single;
    expect(r.attempts, 1);
    expect(r.nextAttemptAt!.isAfter(h.now), isTrue);
    reachable = true;
    h.connectivity.value = true; // عادت الشبكة
    await h.settle();
    expect(h.store.records, isEmpty);
  });

  group('409 تعارض المفتاح', () {
    test(
      'payload_mismatch (رمز الخادم أو نصّه الحاليّ) ⇒ تحتاج تدخّلاً، ولا '
      'تُعاد — ولا حتى بطلب «إعادة المحاولة»؛ in_progress ⇒ تبقى لاحقاً',
      () async {
        server.handler = (req, seen) => switch (seen.path) {
          '/m' => _Server.reply(
            req,
            409,
            body: {
              'detail': {
                'reason': 'payload_mismatch',
                'message_ar': 'المفتاح مستعمَل لحمولة أخرى.',
              },
            },
          ),
          '/legacy' => _Server.reply(
            req,
            409,
            body: {
              'detail':
                  'Idempotency-Key أُعيد استعماله بحمولةٍ مختلفة — استعمل مفتاحاً جديداً',
            },
          ),
          _ => _Server.reply(
            req,
            409,
            body: {
              'detail': {'reason': 'in_progress'},
            },
          ),
        };
        final outbox = outboxOver(connectivity: ValueNotifier<bool>(false));
        await outbox.enqueue(op('/m', method: 'POST'));
        await outbox.enqueue(op('/legacy', method: 'POST'));
        await outbox.enqueue(op('/p', method: 'POST'));
        await outbox.drain();
        final s = outbox.snapshot();
        expect(s.rejected.map((r) => r.op.path), ['/m', '/legacy']);
        for (final r in s.rejected) {
          expect(r.toJson()['conflict_reason'], 'payload_mismatch');
        }
        expect(s.pending.map((r) => r.op.path), ['/p']);
        expect(s.pending.single.toJson()['outcome_unknown'], isTrue);

        final before = server.seen.length;
        for (final r in s.rejected) {
          await outbox.retry(r.id);
        }
        expect(
          server.seen.length,
          before,
          reason: 'لا إعادة عمياء لتعارض حمولة',
        );
      },
    );
  });

  group('تعذّر التجديد ليس تبدّل مالك — لا حلقة كلّ ثانية', () {
    /// يُطلق المؤقّت النشط ويصرّف؛ يُعيد مهلته. الساعة تتقدّم بقدرها.
    Future<Duration> fireNext(
      DurableOfflineOutbox outbox,
      List<RecordedTimer> timers,
      void Function(Duration) advance,
    ) async {
      final active = timers.where((t) => t.isActive).toList();
      expect(active, hasLength(1), reason: 'مؤقّت واحد على أقرب موعد محفوظ');
      final t = active.single;
      advance(t.delay);
      t.fire();
      await outbox.drain();
      return t.delay;
    }

    /// السيناريو المقيس في المراجعة: أوّل إرسال 503، ثمّ ينتهي رمز الوصول
    /// و[failRefresh] يُفشل التجديد. يُثبت: backoff أُسّيّ محفوظ (المهلة تنمو،
    /// المحاولات تُعَدّ)، ولا يخرج طلب بهويّة أحد غير alice، والموعد يبقى بعد
    /// إعادة فتح التخزين.
    Future<void> expiredTokenRefreshFails(
      Future<void> Function() failRefresh, {
      required String expectedOutcome,
    }) async {
      var now = DateTime.utc(2026, 10, 27, 9);
      final timers = <RecordedTimer>[];
      var refreshes = 0;
      server.handler = (req, seen) async {
        if (seen.path == '/auth/refresh') {
          refreshes++;
          await _Server.reply(req, 503, body: {'detail': 'auth down'});
          return;
        }
        if (seen.auth == null) {
          await _Server.reply(req, 401, body: {'detail': 'no auth'});
          return;
        }
        await _Server.reply(req, 503, body: {'detail': 'maintenance'});
      };
      final outbox = outboxOver(
        connectivity: ValueNotifier<bool>(false),
        clock: () => now,
        timers: timers,
      );
      final o = op('/api/v1/tasks/1');
      await outbox.enqueue(o);
      await outbox.drain();
      final id = outbox.snapshot().pending.single.id;
      expect(rawRow(id)['attempts'], 1);

      // الليل: رمز الوصول انتهى، والتجديد يتعذّر (لا رفض صريح للجلسة).
      tokens.accessToken = jwtFor('alice', ttl: const Duration(hours: -1));
      tokens.refreshToken = 'refresh-alice';
      await failRefresh();

      final delays = <Duration>[];
      for (var i = 0; i < 4; i++) {
        delays.add(await fireNext(outbox, timers, (d) => now = now.add(d)));
        final row = rawRow(id);
        expect(
          row['attempts'],
          2 + i,
          reason: 'كلّ إطلاق محاولةٌ محسوبة بموعدها — لا رفض بلا أثر',
        );
        expect(row['last_outcome'], expectedOutcome);
        expect(
          DateTime.parse(row['next_attempt_at'] as String).isAfter(now),
          isTrue,
          reason: 'next_attempt_at محفوظ في المستقبل لا في الماضي',
        );
      }
      final next = timers.where((t) => t.isActive).single.delay;
      delays.add(next);
      for (final d in delays) {
        expect(
          d,
          greaterThanOrEqualTo(const Duration(seconds: 15)),
          reason: 'لا مؤقّت ثانيةٍ واحدة: $delays',
        );
      }
      for (var i = 1; i < delays.length; i++) {
        expect(
          delays[i] > delays[i - 1],
          isTrue,
          reason: 'backoff أُسّيّ: $delays',
        );
      }
      // التجديد محدود بالمحاولات (≤ مرّتين لكلّ محاولة: قبل الإرسال وبعد 401).
      expect(refreshes, lessThanOrEqualTo(2 * 4));
      // لا طلب يخرج بهويّة غير alice.
      expect(
        server
            .to('/api/v1/tasks/1')
            .every((r) => r.sub == null || r.sub == 'alice'),
        isTrue,
      );
      expect(server.committed, isEmpty);

      // إعادة تشغيل التطبيق: الموعد محفوظ، والفتح لا يعيد فوراً.
      final sentBefore = server.seen.length;
      await Hive.close();
      final reopened = outboxOver(
        connectivity: ValueNotifier<bool>(false),
        clock: () => now,
        timers: <RecordedTimer>[],
        drainOnOpen: true,
      );
      await reopened.ensureOpen();
      await reopened.drain();
      expect(
        server.seen.length,
        sentBefore,
        reason: 'لا إعادة فوريّة بعد الإقلاع',
      );
      final kept = reopened.snapshot().pending.single;
      expect(kept.attempts, 5);
      expect(kept.op.idempotencyKey, o.idempotencyKey);
      expect(kept.nextAttemptAt!.isAfter(now), isTrue);
    }

    test('تجديدٌ يردّ 5xx: الطلب يخرج بلا هويّة ويُصنَّف 401 بـbackoff أُسّيّ '
        '(لا رفض «تبدّل مالك» يعيد التجديد كلّ ثانية)', () async {
      await expiredTokenRefreshFails(
        () async {},
        expectedOutcome: OutboxOutcomeKind.sessionProblem.name,
      );
    });

    test('هاتف بلا اتّصال ليلاً: التجديد والإرسال يفشلان بالشبكة ⇒ «انقطاع» '
        'بـbackoff أُسّيّ محفوظ', () async {
      await expiredTokenRefreshFails(
        // الخادم يُغلَق: كلّ اتّصال (التجديد والعمليّة) يُرفض على الجهاز.
        () => server.close(),
        expectedOutcome: OutboxOutcomeKind.offline.name,
      );
    });

    test('رفض الحارس والجلسة لم تتبدّل (رمز لا يُعرَف صاحبه): لم يُرسَل شيء، '
        'لكنّ الموعد يُحفَظ بـbackoff ولا يُعاد كلّ ثانية', () async {
      var now = DateTime.utc(2026, 10, 27, 9);
      final timers = <RecordedTimer>[];
      final alice = OutboxOwner.fromAccessToken(jwtFor('alice'));
      server.handler = (req, seen) =>
          _Server.reply(req, 503, body: {'detail': 'maintenance'});
      final outbox = outboxOver(
        connectivity: ValueNotifier<bool>(false),
        clock: () => now,
        timers: timers,
        // الجلسة المحفوظة ما زالت لـalice…
        currentOwner: () => alice,
      );
      await outbox.enqueue(op('/api/v1/tasks/1'));
      await outbox.drain();
      final id = outbox.snapshot().pending.single.id;
      expect(server.seen, hasLength(1));

      // …لكنّ رمز الوصول الصالح لا يحمل `sub`: الحارس لا يُرسل به.
      String b64(Map<String, Object> m) =>
          base64Url.encode(utf8.encode(jsonEncode(m))).replaceAll('=', '');
      final exp =
          DateTime.now().add(const Duration(hours: 1)).millisecondsSinceEpoch ~/
          1000;
      tokens.accessToken = '${b64({'alg': 'none'})}.${b64({'exp': exp})}.sig';

      final delays = <Duration>[];
      for (var i = 0; i < 3; i++) {
        delays.add(await fireNext(outbox, timers, (d) => now = now.add(d)));
        final row = rawRow(id);
        expect(row['attempts'], 2 + i);
        expect(row['last_outcome'], OutboxOutcomeKind.notSent.name);
        expect(
          DateTime.parse(row['next_attempt_at'] as String).isAfter(now),
          isTrue,
        );
      }
      delays.add(timers.where((t) => t.isActive).single.delay);
      expect(server.seen, hasLength(1), reason: 'الحارس لم يُخرج أيّ طلب');
      for (var i = 0; i < delays.length; i++) {
        expect(delays[i], greaterThanOrEqualTo(const Duration(seconds: 15)));
        if (i > 0) expect(delays[i] > delays[i - 1], isTrue, reason: '$delays');
      }
      final row = rawRow(id);
      expect(row['state'], 'pending');
      expect(row['outcome_unknown'], isFalse);
    });
  });
}
