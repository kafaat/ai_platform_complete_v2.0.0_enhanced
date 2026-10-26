// SAHOOL — features/inventory/presentation/inventory_cubit.dart
// حالة شاشة المخزون: تحميل / فشل (ApiException) / محمَّل (العناصر + الدفعات
// القاربة الانتهاء + التصفية). التحديث لا يمسح القائمة: إن فشل وهناك بيانات
// سابقة تبقى ظاهرة مع خطأ التحديث وعمرها، لا كأنّها حاليّة.
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:sahool_app/core/network/api_exception.dart';
import 'package:sahool_app/features/inventory/data/inventory_api.dart';
import 'package:sahool_app/features/inventory/data/inventory_models.dart';

/// نافذة «قارب الانتهاء» في القائمة (تطابق افتراضيّ الخادم والويب).
const int kExpiringWindowDays = 30;

sealed class InventoryState {
  const InventoryState();
}

class InventoryLoading extends InventoryState {
  const InventoryLoading();
}

class InventoryFailed extends InventoryState {
  const InventoryFailed(this.error);
  final ApiException error;
}

class InventoryLoaded extends InventoryState {
  const InventoryLoaded({
    required this.items,
    required this.expiring,
    required this.fetchedAt,
    this.category,
    this.lowOnly = false,
    this.query = '',
    this.refreshing = false,
    this.refreshError,
  });

  final List<InventoryItem> items;
  final List<ExpiringBatch> expiring;
  final DateTime fetchedAt;

  /// null ⇒ كلّ الفئات.
  final String? category;
  final bool lowOnly;
  final String query;
  final bool refreshing;

  /// فشل آخر تحديث بينما البيانات المعروضة من [fetchedAt].
  final ApiException? refreshError;

  int get lowStockCount => items.where((i) => i.lowStock).length;

  bool get isFiltered => category != null || lowOnly || query.trim().isNotEmpty;

  List<InventoryItem> get visibleItems {
    final q = query.trim().toLowerCase();
    return items.where((i) {
      if (category != null && i.category != category) return false;
      if (lowOnly && !i.lowStock) return false;
      if (q.isNotEmpty && !i.name.toLowerCase().contains(q)) return false;
      return true;
    }).toList();
  }

  InventoryLoaded copyWith({
    List<InventoryItem>? items,
    List<ExpiringBatch>? expiring,
    DateTime? fetchedAt,
    String? Function()? category,
    bool? lowOnly,
    String? query,
    bool? refreshing,
    ApiException? Function()? refreshError,
  }) => InventoryLoaded(
    items: items ?? this.items,
    expiring: expiring ?? this.expiring,
    fetchedAt: fetchedAt ?? this.fetchedAt,
    category: category != null ? category() : this.category,
    lowOnly: lowOnly ?? this.lowOnly,
    query: query ?? this.query,
    refreshing: refreshing ?? this.refreshing,
    refreshError: refreshError != null ? refreshError() : this.refreshError,
  );
}

class InventoryCubit extends Cubit<InventoryState> {
  InventoryCubit(this._api, {DateTime Function()? clock})
    : _clock = clock ?? DateTime.now,
      super(const InventoryLoading());

  final InventoryApi _api;
  final DateTime Function() _clock;

  Future<void> load() async {
    final previous = state;
    if (previous is InventoryLoaded) {
      emit(previous.copyWith(refreshing: true));
    } else {
      emit(const InventoryLoading());
    }
    try {
      // بالتوازي: كانت الشاشة تنتظر القائمة ثمّ الدفعات على شبكة ضعيفة.
      final results = await Future.wait<Object>([
        _api.listItems(),
        _api.listExpiring(days: kExpiringWindowDays),
      ]);
      if (isClosed) return;
      final now = _clock();
      final current = state;
      final base = current is InventoryLoaded ? current : null;
      emit(
        InventoryLoaded(
          items: results[0] as List<InventoryItem>,
          expiring: results[1] as List<ExpiringBatch>,
          fetchedAt: now,
          category: base?.category,
          lowOnly: base?.lowOnly ?? false,
          query: base?.query ?? '',
        ),
      );
    } catch (e) {
      if (isClosed) return;
      final err = ApiException.from(e);
      final current = state;
      if (current is InventoryLoaded) {
        emit(current.copyWith(refreshing: false, refreshError: () => err));
      } else {
        emit(InventoryFailed(err));
      }
    }
  }

  void setCategory(String? category) {
    final s = state;
    if (s is InventoryLoaded) emit(s.copyWith(category: () => category));
  }

  void setLowOnly(bool lowOnly) {
    final s = state;
    if (s is InventoryLoaded) emit(s.copyWith(lowOnly: lowOnly));
  }

  void setQuery(String query) {
    final s = state;
    if (s is InventoryLoaded) emit(s.copyWith(query: query));
  }

  void clearFilters() {
    final s = state;
    if (s is InventoryLoaded) {
      emit(s.copyWith(category: () => null, lowOnly: false, query: ''));
    }
  }
}
