// SAHOOL — features/master_data/presentation/master_data_cubit.dart
// حالة كتالوج البيانات المرجعيّة لفئة واحدة: تحميل / محمّل / فشل. ردّ متأخّر
// لفئة سابقة لا يكتب فوق الفئة الحاليّة.
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:sahool_app/core/network/api_exception.dart';
import 'package:sahool_app/features/master_data/data/master_data_api.dart';

enum MasterDataStatus { loading, loaded, failed }

class MasterDataState {
  const MasterDataState({
    required this.category,
    this.status = MasterDataStatus.loading,
    this.items = const [],
    this.error,
  });

  final String category;
  final MasterDataStatus status;
  final List<Map<String, dynamic>> items;
  final ApiException? error;
}

class MasterDataCubit extends Cubit<MasterDataState> {
  MasterDataCubit(this.api, {String initialCategory = 'crop'})
    : super(MasterDataState(category: initialCategory));

  final MasterDataApi api;
  int _seq = 0;

  Future<void> load() => _load(state.category);

  Future<void> setCategory(String category) => _load(category);

  Future<void> _load(String category) async {
    final seq = ++_seq;
    emit(MasterDataState(category: category));
    try {
      final data = await api.getMasterData(category);
      if (isClosed || seq != _seq) return;
      emit(
        MasterDataState(
          category: category,
          status: MasterDataStatus.loaded,
          items: data,
        ),
      );
    } catch (e) {
      if (isClosed || seq != _seq) return;
      emit(
        MasterDataState(
          category: category,
          status: MasterDataStatus.failed,
          error: ApiException.from(e),
        ),
      );
    }
  }
}
