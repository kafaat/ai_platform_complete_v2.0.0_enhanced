// SAHOOL — features/alerts/presentation/notification_prefs_cubit.dart
// حالة شاشة تفضيلات الإشعار. لا نموذج قابل للتعديل بلا قراءة ناجحة، والحفظ
// يمرّ عبر NotificationPrefsRepository (قراءة-ثمّ-كتابة).
import 'package:flutter/foundation.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:sahool_app/core/network/api_exception.dart';
import 'package:sahool_app/core/network/idempotency.dart';

import '../data/notification_prefs.dart';

@immutable
class NotificationPrefsState {
  const NotificationPrefsState({
    this.prefs,
    this.loadError,
    this.draft = const PrefsDraft(),
    this.saving = false,
    this.saveError,
    this.savedSeq = 0,
  });

  /// null ⇒ لم تنجح القراءة بعد (لا نموذج).
  final NotificationPrefs? prefs;
  final ApiException? loadError;
  final PrefsDraft draft;
  final bool saving;
  final String? saveError;
  final int savedSeq;

  bool get loading => prefs == null && loadError == null;

  NotificationPrefsState copyWith({
    NotificationPrefs? prefs,
    PrefsDraft? draft,
    bool? saving,
    String? saveError,
    bool clearSaveError = false,
    int? savedSeq,
  }) => NotificationPrefsState(
    prefs: prefs ?? this.prefs,
    loadError: loadError,
    draft: draft ?? this.draft,
    saving: saving ?? this.saving,
    saveError: clearSaveError ? null : (saveError ?? this.saveError),
    savedSeq: savedSeq ?? this.savedSeq,
  );
}

class NotificationPrefsCubit extends Cubit<NotificationPrefsState> {
  NotificationPrefsCubit(this._repo) : super(const NotificationPrefsState());

  final NotificationPrefsRepository _repo;

  /// مفتاح نيّة الحفظ الحاليّة: يبقى ثابتاً عبر إعادة المحاولة لنفس التعديلات،
  /// ويُصفَّر بعد النجاح أو بعد أيّ تعديل جديد.
  IdempotencyKey? _saveKey;

  Future<void> load() async {
    emit(const NotificationPrefsState());
    try {
      final p = await _repo.load();
      if (!isClosed) emit(NotificationPrefsState(prefs: p));
    } catch (e) {
      if (!isClosed) {
        emit(NotificationPrefsState(loadError: ApiException.from(e)));
      }
    }
  }

  void _edit(PrefsDraft d) {
    _saveKey = null;
    emit(state.copyWith(draft: d, clearSaveError: true));
  }

  void setEnabled(NotifChannel c, bool v) =>
      _edit(state.draft.setField(c.enabledKey, v));

  void setAddress(NotifChannel c, String v) {
    final k = c.addressKey;
    if (k != null) _edit(state.draft.setField(k, v));
  }

  void toggleEvent(String type, bool on) =>
      _edit(state.draft.toggleEvent(type, on: on));

  void setMinSeverity(String? v) =>
      _edit(state.draft.setField('min_severity', v));

  Future<bool> save() async {
    if (state.prefs == null || state.saving || state.draft.isEmpty) {
      return false;
    }
    final key = _saveKey ??= IdempotencyKey.generate();
    emit(state.copyWith(saving: true, clearSaveError: true));
    try {
      final saved = await _repo.save(state.draft, idempotencyKey: key);
      _saveKey = null;
      if (isClosed) return true;
      emit(NotificationPrefsState(prefs: saved, savedSeq: state.savedSeq + 1));
      return true;
    } catch (e) {
      if (isClosed) return false;
      emit(
        state.copyWith(
          saving: false,
          saveError: 'لم يُحفَظ شيء: ${ApiException.from(e).messageAr}',
        ),
      );
      return false;
    }
  }
}
