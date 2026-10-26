// SAHOOL — features/documents/presentation/documents_cubit.dart
// حالة سجلّ الوثائق: تحميل / محمّل (قد يكون فارغاً) / فشل بالـApiException نفسه.
// تغيير الفئة يعيد الجلب؛ ردّ قديم لفئة سابقة لا يكتب فوق الأحدث.
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:sahool_app/core/network/api_exception.dart';
import 'package:sahool_app/features/documents/data/documents_api.dart';

enum DocumentsStatus { loading, loaded, failed }

class DocumentsState {
  const DocumentsState({
    this.status = DocumentsStatus.loading,
    this.items = const [],
    this.category,
    this.error,
  });

  final DocumentsStatus status;
  final List<Map<String, dynamic>> items;

  /// null = كلّ الفئات.
  final String? category;
  final ApiException? error;
}

class DocumentsCubit extends Cubit<DocumentsState> {
  DocumentsCubit(this.api) : super(const DocumentsState());

  final DocumentsApi api;
  int _seq = 0;

  Future<void> load({String? category, bool keepCategory = true}) async {
    final cat = keepCategory ? (category ?? state.category) : category;
    final seq = ++_seq;
    emit(
      DocumentsState(
        status: DocumentsStatus.loading,
        items: state.items,
        category: cat,
      ),
    );
    try {
      final data = await api.listDocuments(category: cat);
      if (isClosed || seq != _seq) return;
      emit(
        DocumentsState(
          status: DocumentsStatus.loaded,
          items: data,
          category: cat,
        ),
      );
    } catch (e) {
      if (isClosed || seq != _seq) return;
      emit(
        DocumentsState(
          status: DocumentsStatus.failed,
          category: cat,
          error: ApiException.from(e),
        ),
      );
    }
  }

  Future<void> setCategory(String? category) =>
      load(category: category, keepCategory: false);
}
