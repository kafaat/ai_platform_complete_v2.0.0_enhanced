// SAHOOL — features/offline_sync/presentation/sync_status_cubit.dart
// حالة صفحة المزامنة: تستمع إلى لقطات صندوق الإرسال وتنفّذ أفعال المستخدم
// (إرسال الآن، إعادة عمليّة، تجاهل عمليّة بعد التأكيد، حذف صندوق لا يُقرأ).
import 'dart:async';

import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:sahool_app/features/offline_sync/data/durable_offline_outbox.dart';
import 'package:sahool_app/features/offline_sync/data/outbox_store.dart';

sealed class SyncStatusState {
  const SyncStatusState();
}

class SyncStatusLoading extends SyncStatusState {
  const SyncStatusLoading();
}

/// تعذّر فتح الصندوق المشفّر — لا شيء يُعرَض كأنّه محفوظ.
class SyncStatusUnavailable extends SyncStatusState {
  const SyncStatusUnavailable(this.failure, {this.resetting = false});
  final OutboxStoreException failure;
  final bool resetting;
}

class SyncStatusLoaded extends SyncStatusState {
  const SyncStatusLoaded(this.snapshot, {this.busy = const {}});
  final OutboxSnapshot snapshot;

  /// عمليّات يجري عليها فعلٌ الآن (منع الضغط المزدوج).
  final Set<String> busy;

  bool get isEmpty => snapshot.pending.isEmpty && snapshot.rejected.isEmpty;
}

class SyncStatusCubit extends Cubit<SyncStatusState> {
  SyncStatusCubit(this._outbox) : super(const SyncStatusLoading()) {
    _sub = _outbox.watch().listen(_onSnapshot);
  }

  final DurableOfflineOutbox _outbox;
  StreamSubscription<OutboxSnapshot>? _sub;
  final Set<String> _busy = {};

  void _onSnapshot(OutboxSnapshot s) {
    if (isClosed) return;
    final failure = s.failure;
    if (failure != null) {
      emit(SyncStatusUnavailable(failure));
    } else if (!s.opened) {
      emit(const SyncStatusLoading());
    } else {
      emit(SyncStatusLoaded(s, busy: Set.unmodifiable(_busy)));
    }
  }

  void _refresh() => _onSnapshot(_outbox.snapshot());

  Future<void> _withBusy(String id, Future<void> Function() action) async {
    if (_busy.contains(id)) return;
    _busy.add(id);
    _refresh();
    try {
      await action();
    } finally {
      _busy.remove(id);
      if (!isClosed) _refresh();
    }
  }

  /// يرسل كلّ ما ينتظر الآن (يتجاهل مهلة الانتظار).
  Future<void> sendAll() => _outbox.drain(ignoreBackoff: true);

  Future<void> retry(String id) => _withBusy(id, () => _outbox.retry(id));

  Future<void> discard(String id) =>
      _withBusy(id, () => _outbox.discard(id).then((_) {}));

  /// يحذف صندوقاً مفتاحه مفقود ويبدأ صندوقاً جديداً (بعد تأكيد صريح).
  Future<void> resetUnreadableStore() async {
    final s = state;
    if (s is! SyncStatusUnavailable) return;
    emit(SyncStatusUnavailable(s.failure, resetting: true));
    await _outbox.resetUnreadableStore();
    if (!isClosed) _refresh();
  }

  @override
  Future<void> close() async {
    await _sub?.cancel();
    return super.close();
  }
}
