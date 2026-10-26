// أدوات اختبار صندوق الإرسال: مخزن في الذاكرة (لاختبارات المنطق والودجات؛ Hive
// الحقيقيّ مُختبَر في outbox_store_test.dart)، JWT بمستأجِر، ومؤقّت مسجَّل.
import 'dart:async';
import 'dart:convert';

import 'package:flutter/foundation.dart';

import 'package:sahool_app/core/utils/ids.dart';
import 'package:sahool_app/features/offline_sync/data/durable_offline_outbox.dart';
import 'package:sahool_app/features/offline_sync/data/offline_sync_api.dart';
import 'package:sahool_app/features/offline_sync/data/outbox_record.dart';
import 'package:sahool_app/features/offline_sync/data/outbox_store.dart';
import 'package:sahool_app/features/offline_sync/offline_outbox.dart';

import '../../core/fake_http.dart';

class MemoryOutboxStore implements OutboxStore {
  final Map<String, OutboxRecord> _m = {};
  int _seq = 0;

  @override
  List<OutboxRecord> get records =>
      _m.values.toList()..sort((a, b) => a.seq.compareTo(b.seq));

  @override
  OutboxRecord? byId(String id) => _m[id];

  @override
  int nextSeq() => ++_seq;

  @override
  Future<void> put(OutboxRecord record) async => _m[record.id] = record;

  @override
  Future<void> remove(String id) async => _m.remove(id);
}

/// JWT غير موقَّع يحمل sub وtenant_id (كما يصدره services/auth).
String jwtFor(
  String sub, {
  String tenant = 't1',
  Duration ttl = const Duration(hours: 1),
}) {
  String b64(Map<String, Object> m) =>
      base64Url.encode(utf8.encode(jsonEncode(m))).replaceAll('=', '');
  final exp = DateTime.now().add(ttl).millisecondsSinceEpoch ~/ 1000;
  return '${b64({'alg': 'none'})}.${b64({'sub': sub, 'tenant_id': tenant, 'exp': exp})}.sig';
}

/// يفكّ sub من ترويسة Authorization لطلب مسجَّل.
String? subOf(RecordedRequest r) {
  final auth = r.headers['Authorization']?.toString();
  if (auth == null || !auth.startsWith('Bearer ')) return null;
  return OutboxOwner.fromAccessToken(auth.substring(7))?.userId;
}

class RecordedTimer implements Timer {
  RecordedTimer(this.delay, this.callback);
  final Duration delay;
  final void Function() callback;
  bool _active = true;
  @override
  void cancel() => _active = false;
  @override
  bool get isActive => _active;
  @override
  int get tick => 0;
  void fire() {
    if (!_active) return;
    _active = false;
    callback();
  }
}

class Harness {
  Harness({FakeHandler? handler, String user = 'alice', bool online = false})
    : tokens = MemoryTokenStore(accessToken: jwtFor(user)),
      store = MemoryOutboxStore(),
      connectivity = ValueNotifier<bool>(online) {
    adapter = FakeAdapter(
      handler ?? (_) async => const FakeReply(200, {'ok': true}),
    );
    final client = testClient(adapter, tokens);
    outbox = DurableOfflineOutbox(
      openStore: () async => store,
      // الهويّة من نفس مخزن التوكنات الذي يرسل به ApiClient.
      currentOwner: () => OutboxOwner.fromAccessToken(tokens.accessToken),
      api: OfflineSyncApi(client),
      connectivity: connectivity,
      clock: () => now,
      timer: (d, cb) {
        final t = RecordedTimer(d, cb);
        timers.add(t);
        return t;
      },
    );
  }

  final MemoryTokenStore tokens;
  final MemoryOutboxStore store;
  late final FakeAdapter adapter;
  late final DurableOfflineOutbox outbox;
  final ValueNotifier<bool> connectivity;
  DateTime now = DateTime.utc(2026, 10, 26, 8);
  final List<RecordedTimer> timers = [];

  void signInAs(String user, {String tenant = 't1'}) =>
      tokens.accessToken = jwtFor(user, tenant: tenant);

  /// ينتظر انتهاء أيّ تصريف بدأ من enqueue.
  Future<void> settle() async {
    for (var i = 0; i < 5; i++) {
      await outbox.drain();
      await Future<void>.delayed(Duration.zero);
    }
  }
}

OutboxOp op(
  String path, {
  String method = 'PATCH',
  Map<String, dynamic>? body,
  String? key,
  String? fieldId,
  String kind = 'task_update',
  String? label,
}) => OutboxOp(
  kind: kind,
  method: method,
  path: path,
  body: body ?? {'status': 'done'},
  idempotencyKey: key ?? generateRequestId(),
  fieldId: fieldId,
  labelAr: label,
);
