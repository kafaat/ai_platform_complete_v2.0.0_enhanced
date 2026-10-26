// SAHOOL — features/maps/presentation/offline_packs_cubit.dart
// إدارة حزم الخرائط على الجهاز: سرد، فحص (نقطيّة؟ تُفتح؟ أيّ تكبير؟)، تفعيل،
// إلغاء تفعيل، حذف. كلّ حزمة تُفتح للفحص ثمّ تُغلق فوراً.
import 'package:flutter/foundation.dart';
import 'package:flutter_bloc/flutter_bloc.dart';

import '../data/offline_pack_store.dart';
import '../data/offline_tiles.dart';

@immutable
class OfflinePackEntry {
  const OfflinePackEntry(this.file, {this.minZoom, this.maxZoom, this.error});
  final OfflinePackFile file;
  final int? minZoom;
  final int? maxZoom;

  /// سبب عدم الصلاحيّة (متّجهة/تالفة)؛ null ⇒ صالحة للعرض.
  final String? error;
  bool get usable => error == null;
}

enum OfflinePacksStatus { loading, loaded, failed }

@immutable
class OfflinePacksState {
  const OfflinePacksState({
    this.status = OfflinePacksStatus.loading,
    this.packs = const [],
    this.activePath,
    this.folders = const [],
    this.message,
    this.busyPath,
  });

  final OfflinePacksStatus status;
  final List<OfflinePackEntry> packs;
  final String? activePath;
  final List<String> folders;

  /// خطأ السرد (failed) أو نتيجة إجراء.
  final String? message;

  /// حزمة يجري عليها إجراء (منع النقر المزدوج).
  final String? busyPath;

  OfflinePacksState copyWith({
    OfflinePacksStatus? status,
    List<OfflinePackEntry>? packs,
    String? activePath,
    bool clearActive = false,
    List<String>? folders,
    String? message,
    bool clearMessage = false,
    String? busyPath,
    bool clearBusy = false,
  }) => OfflinePacksState(
    status: status ?? this.status,
    packs: packs ?? this.packs,
    activePath: clearActive ? null : (activePath ?? this.activePath),
    folders: folders ?? this.folders,
    message: clearMessage ? null : (message ?? this.message),
    busyPath: clearBusy ? null : (busyPath ?? this.busyPath),
  );
}

typedef PackOpener = Future<OfflinePackOpenResult> Function(String path);

class OfflinePacksCubit extends Cubit<OfflinePacksState> {
  OfflinePacksCubit(this._store, {PackOpener? opener})
    : _open = opener ?? openOfflinePack,
      super(const OfflinePacksState());

  final OfflinePackStore _store;
  final PackOpener _open;

  Future<void> load() async {
    emit(
      state.copyWith(status: OfflinePacksStatus.loading, clearMessage: true),
    );
    try {
      final folders = await _store.folders();
      final files = await _store.list();
      final entries = <OfflinePackEntry>[];
      for (final f in files) {
        final r = await _open(f.path);
        final pack = r.pack;
        entries.add(
          OfflinePackEntry(
            f,
            minZoom: pack?.minZoom,
            maxZoom: pack?.maxZoom,
            error: r.error,
          ),
        );
        await pack?.dispose();
      }
      final active = await _store.activePath();
      if (isClosed) return;
      emit(
        OfflinePacksState(
          status: OfflinePacksStatus.loaded,
          packs: entries,
          activePath: active,
          folders: folders,
        ),
      );
    } catch (_) {
      if (isClosed) return;
      emit(
        state.copyWith(
          status: OfflinePacksStatus.failed,
          message: 'تعذّر قراءة مجلّد الخرائط على الجهاز',
        ),
      );
    }
  }

  Future<void> activate(OfflinePackEntry e) async {
    if (!e.usable || state.busyPath != null) return;
    emit(state.copyWith(busyPath: e.file.path, clearMessage: true));
    await _store.setActive(e.file.path);
    if (isClosed) return;
    emit(
      state.copyWith(
        activePath: e.file.path,
        clearBusy: true,
        message: 'فُعّلت «${e.file.name}» — تظهر على خريطة حقولي',
      ),
    );
  }

  Future<void> deactivate() async {
    await _store.setActive(null);
    if (isClosed) return;
    emit(
      state.copyWith(
        clearActive: true,
        message: 'أُلغي التفعيل — تُعرض خريطة الشبكة',
      ),
    );
  }

  Future<void> delete(OfflinePackEntry e) async {
    if (state.busyPath != null) return;
    emit(state.copyWith(busyPath: e.file.path, clearMessage: true));
    try {
      await _store.delete(e.file);
      if (isClosed) return;
      final wasActive = state.activePath == e.file.path;
      emit(
        state.copyWith(
          packs: state.packs.where((p) => p.file.path != e.file.path).toList(),
          clearActive: wasActive,
          clearBusy: true,
          message: 'حُذفت «${e.file.name}»',
        ),
      );
    } catch (_) {
      if (isClosed) return;
      emit(
        state.copyWith(clearBusy: true, message: 'تعذّر حذف «${e.file.name}»'),
      );
    }
  }
}
