// صندوق إرسال مزيّف يسجّل العمليّات المودَعة ويردّ بإيصال محدّد.
import 'dart:async';

import 'package:sahool_app/features/offline_sync/offline_outbox.dart';

class FakeOutbox implements OfflineOutbox {
  FakeOutbox({
    this.receipt = const OutboxReceipt.queued(),
    this.throws = false,
  });
  final OutboxReceipt receipt;
  final bool throws;
  final List<OutboxOp> ops = [];
  final _changes = StreamController<int>.broadcast();

  @override
  Future<OutboxReceipt> enqueue(OutboxOp op) async {
    if (throws) throw StateError('disk full');
    ops.add(op);
    if (receipt.queued) _changes.add(ops.length);
    return receipt;
  }

  @override
  Stream<int> get pendingCount async* {
    yield ops.length;
    yield* _changes.stream;
  }
}
