// أدوات اختبار سجلّ العمليّات المعلّقة (operation_ledger.dart):
//  • [LocalCommitServer] (test/core/local_commit_server.dart): خادم HTTP حقيقيّ.
//  • [MemoryOperationStore]: مخزن فوق «قرص» في الذاكرة (خريطة نصوص JSON)؛ نسخة جديدة
//    فوق الخريطة نفسها = إعادة فتح التخزين.
import 'dart:io';

import 'package:sahool_app/core/network/api_client.dart';
import 'package:sahool_app/features/offline_sync/data/operation_ledger.dart';
import 'package:sahool_app/features/offline_sync/data/outbox_record.dart';
import 'package:sahool_app/features/offline_sync/data/outbox_store.dart';

export '../../core/local_commit_server.dart';
export 'outbox_test_support.dart' show jwtFor;

class MemoryOperationStore implements OperationStore {
  /// [disk] يبقى بعد «إغلاق التطبيق»؛ نسخة جديدة فوقه تقرأ ما كُتب فقط.
  MemoryOperationStore([Map<String, String>? disk]) : disk = disk ?? {} {
    for (final raw in this.disk.values) {
      final r = OperationRecord.decode(raw);
      _records[r.operationId] = r;
    }
  }

  final Map<String, String> disk;
  final Map<String, OperationRecord> _records = {};

  /// يحاكي فشل الكتابة المحلّيّة (قرص ممتلئ/مفتاح مقفل).
  bool failWrites = false;
  int writes = 0;

  @override
  List<OperationRecord> get records => _records.values.toList();

  @override
  Future<void> put(OperationRecord record) async {
    if (failWrites) throw const FileSystemException('disk full');
    writes++;
    disk[record.operationId] = record.encode();
    _records[record.operationId] = record;
  }

  @override
  Future<void> remove(String operationId) async {
    disk.remove(operationId);
    _records.remove(operationId);
  }
}

/// مفتاح تشفير في الذاكرة لصندوق Hive الحقيقيّ في الاختبار.
class MemoryKeyStore implements OutboxKeyStore {
  String? value;
  @override
  Future<String?> read() async => value;
  @override
  Future<void> write(String base64Key) async => value = base64Key;
}

/// سجلّ عمليّات بمالكٍ يُقرأ من نفس مخزن التوكنات الذي يرسل به ApiClient.
OperationLedger ledgerFor(
  TokenStore tokens,
  OperationStore store, {
  ApiClient? client,
  DateTime Function()? clock,
  CommandLookup? lookup,
  bool useCommandLookup = true,
}) => OperationLedger(
  openStore: () async => store,
  currentOwner: () => OutboxOwner.fromAccessToken(tokens.accessToken),
  lookup:
      lookup ??
      (useCommandLookup && client != null
          ? (id) => CommandStatusApi(client).exists(id)
          : null),
  clock: clock,
);

