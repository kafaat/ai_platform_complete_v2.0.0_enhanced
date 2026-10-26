// SAHOOL — features/fields/presentation/common/load_cubit.dart
// Cubit قراءة واحدة عامّ (تحميل ← محمَّل | فشل) يُستعمل لأقسام مساحة العمل
// والأقمار. يحرس من الاستجابات المتأخّرة: كلّ تحميل يأخذ رقم جيل، وأيّ ردّ
// لجيل أقدم يُهمَل (فلا يكتب ردّ بطيء فوق ردّ أحدث). التحديث (refresh) يُبقي
// البيانات المعروضة حتّى يصل الجديد بدل استبدالها بمؤشّر تحميل.
import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:sahool_app/core/network/api_exception.dart';
import 'package:sahool_app/core/theme/sahool_tokens.dart';
import 'package:sahool_app/core/theme/tokens.dart';
import 'package:sahool_app/core/widgets/widgets.dart';

sealed class LoadState<T> {
  const LoadState();
}

final class LoadLoading<T> extends LoadState<T> {
  const LoadLoading();
}

final class LoadLoaded<T> extends LoadState<T> {
  const LoadLoaded(this.data, this.loadedAt);
  final T data;
  final DateTime loadedAt;
}

final class LoadFailed<T> extends LoadState<T> {
  const LoadFailed(this.error);
  final ApiException error;
}

class LoadCubit<T> extends Cubit<LoadState<T>> {
  LoadCubit(this._loader) : super(LoadLoading<T>());

  final Future<T> Function() _loader;
  int _generation = 0;

  T? get dataOrNull => switch (state) {
    LoadLoaded<T>(:final data) => data,
    _ => null,
  };

  /// تحميل من الصفر (يُظهر حالة التحميل).
  Future<void> load() => _run(showLoading: true);

  /// تحديث يُبقي البيانات المعروضة حتّى يصل الجديد (للسحب للتحديث).
  Future<void> refresh() => _run(showLoading: state is! LoadLoaded<T>);

  Future<void> _run({required bool showLoading}) async {
    final gen = ++_generation;
    if (showLoading) emit(LoadLoading<T>());
    try {
      final data = await _loader();
      if (isClosed || gen != _generation) return;
      emit(LoadLoaded<T>(data, DateTime.now()));
    } catch (e) {
      if (isClosed || gen != _generation) return;
      emit(LoadFailed<T>(ApiException.from(e)));
    }
  }
}

/// يعرض حالة [LoadCubit] بملء الصفحة (تحميل/خطأ بإعادة محاولة/بيانات).
class LoadView<T> extends StatelessWidget {
  const LoadView({super.key, required this.builder});

  final Widget Function(BuildContext context, T data) builder;

  @override
  Widget build(BuildContext context) => BlocBuilder<LoadCubit<T>, LoadState<T>>(
    builder: (context, state) => switch (state) {
      LoadLoading<T>() => const LoadingState(),
      LoadFailed<T>(:final error) => ErrorState(
        error: error,
        onRetry: () => context.read<LoadCubit<T>>().load(),
      ),
      LoadLoaded<T>(:final data) => builder(context, data),
    },
  );
}

/// نفس [LoadView] لكن بحجم بطاقة (داخل قائمة): تحميل صغير وخطأ سطريّ.
class InlineLoadView<T> extends StatelessWidget {
  const InlineLoadView({super.key, required this.builder, this.cubit});

  final Widget Function(BuildContext context, T data) builder;

  /// إن لم يُمرَّر يُقرأ من السياق.
  final LoadCubit<T>? cubit;

  @override
  Widget build(BuildContext context) {
    final c = cubit ?? context.read<LoadCubit<T>>();
    return BlocBuilder<LoadCubit<T>, LoadState<T>>(
      bloc: c,
      builder: (context, state) =>
          LoadStateView<T>(state: state, onRetry: c.load, builder: builder),
    );
  }
}

/// يرسم [LoadState] بحجم بطاقة: تحميل صغير · خطأ سطريّ بإعادة · البيانات.
class LoadStateView<T> extends StatelessWidget {
  const LoadStateView({
    super.key,
    required this.state,
    required this.builder,
    this.onRetry,
  });

  final LoadState<T> state;
  final Widget Function(BuildContext context, T data) builder;
  final VoidCallback? onRetry;

  @override
  Widget build(BuildContext context) => switch (state) {
    LoadLoading<T>() => const Padding(
      padding: EdgeInsets.symmetric(vertical: SahoolSpacing.lg),
      child: Center(child: CircularProgressIndicator()),
    ),
    LoadFailed<T>(:final error) => InlineError(error: error, onRetry: onRetry),
    LoadLoaded<T>(:final data) => builder(context, data),
  };
}

/// خطأ سطريّ داخل بطاقة: رسالة ApiException الصادقة + زرّ إعادة.
class InlineError extends StatelessWidget {
  const InlineError({super.key, required this.error, this.onRetry});

  final Object error;
  final VoidCallback? onRetry;

  @override
  Widget build(BuildContext context) {
    final e = ApiException.from(error);
    final retryable =
        onRetry != null &&
        e.kind != ApiErrorKind.forbidden &&
        e.kind != ApiErrorKind.notFound;
    return Semantics(
      liveRegion: true,
      child: Row(
        children: [
          Icon(
            ErrorState.iconFor(e),
            color: e.isConnectivity
                ? context.tokens.warning
                : context.tokens.danger,
            size: SahoolSizes.iconSm,
          ),
          const SizedBox(width: SahoolSpacing.sm),
          Expanded(
            child: Text(e.messageAr, style: context.textStyles.bodyMedium),
          ),
          if (retryable)
            TextButton(onPressed: onRetry, child: const Text('إعادة المحاولة')),
        ],
      ),
    );
  }
}
