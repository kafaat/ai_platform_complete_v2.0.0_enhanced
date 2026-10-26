// SAHOOL — features/farms/presentation/farms_cubit.dart
// قائمة المزارع مع عدد حقول كلّ مزرعة. العدد يُشتقّ من GET /api/v1/fields
// (farm_id لكلّ حقل) بطلب واحد لا طلب لكلّ مزرعة. تعذّر الحقول لا يُسقط القائمة:
// يُعرَض «عدد الحقول غير متاح» بدل صفر مختلق.
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:sahool_app/core/network/api_exception.dart';
import 'package:sahool_app/features/farms/data/farms_api.dart';
import 'package:sahool_app/features/fields/data/fields_api.dart';

sealed class FarmsState {
  const FarmsState();
}

final class FarmsLoading extends FarmsState {
  const FarmsLoading();
}

final class FarmsFailed extends FarmsState {
  const FarmsFailed(this.error);
  final ApiException error;
}

final class FarmsLoaded extends FarmsState {
  const FarmsLoaded(this.farms, {this.fieldCounts, this.countsError});

  final List<Map<String, dynamic>> farms;

  /// farm_id ← عدد الحقول؛ null حين تعذّر جلب الحقول.
  final Map<String, int>? fieldCounts;
  final ApiException? countsError;

  int? countFor(String farmId) =>
      fieldCounts == null ? null : (fieldCounts![farmId] ?? 0);
}

class FarmsCubit extends Cubit<FarmsState> {
  FarmsCubit(this._farms, this._fields) : super(const FarmsLoading());

  final FarmsApi _farms;
  final FieldsApi _fields;
  int _gen = 0;

  Future<void> load({bool silent = false}) async {
    final gen = ++_gen;
    if (!silent || state is! FarmsLoaded) emit(const FarmsLoading());
    final fieldsFuture = _fields.listFields().then<Object>(
      (v) => v,
      onError: (Object e) => ApiException.from(e),
    );
    try {
      final farms = await _farms.listFarms();
      final fields = await fieldsFuture;
      if (isClosed || gen != _gen) return;
      if (fields is ApiException) {
        emit(FarmsLoaded(farms, countsError: fields));
        return;
      }
      final counts = <String, int>{};
      for (final f in fields as List<Map<String, dynamic>>) {
        final id = '${f['farm_id'] ?? ''}';
        if (id.isEmpty) continue;
        counts[id] = (counts[id] ?? 0) + 1;
      }
      emit(FarmsLoaded(farms, fieldCounts: counts));
    } catch (e) {
      await fieldsFuture;
      if (isClosed || gen != _gen) return;
      emit(FarmsFailed(ApiException.from(e)));
    }
  }
}
