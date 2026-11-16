// SAHOOL — features/field_plans/presentation/cached_read_view.dart
// Cubit وعرض مشتركان لقراءة محفوظة دون اتّصال: تحميل ← محمَّل (مع عمره ومصدره)
// | فشل صادق. المحمَّل يُعرض دائماً تحت DataAgeBanner، فلا تبدو نسخة قديمة
// حاليّة. ردّ لجيل تحميل أقدم يُهمَل (نمط LoadCubit).
import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:sahool_app/core/network/api_exception.dart';
import 'package:sahool_app/core/offline/cached_loader.dart';
import 'package:sahool_app/core/theme/tokens.dart';
import 'package:sahool_app/core/widgets/widgets.dart';
import 'package:sahool_app/features/field_plans/data/field_plans_models.dart';

sealed class CachedReadState<T> {
  const CachedReadState();
}

final class CachedReadLoading<T> extends CachedReadState<T> {
  const CachedReadLoading();
}

final class CachedReadLoaded<T> extends CachedReadState<T> {
  const CachedReadLoaded(this.result);
  final CachedResult<T> result;
}

final class CachedReadFailed<T> extends CachedReadState<T> {
  const CachedReadFailed(this.error);
  final ApiException error;
}

class CachedReadCubit<T> extends Cubit<CachedReadState<T>> {
  CachedReadCubit(this._loader) : super(CachedReadLoading<T>());

  final Future<CachedResult<T>> Function() _loader;
  int _generation = 0;

  Future<void> load() async {
    final gen = ++_generation;
    if (state is! CachedReadLoaded<T>) emit(CachedReadLoading<T>());
    try {
      final result = await _loader();
      if (isClosed || gen != _generation) return;
      emit(CachedReadLoaded<T>(result));
    } catch (e) {
      if (isClosed || gen != _generation) return;
      emit(CachedReadFailed<T>(ApiException.from(e)));
    }
  }
}

/// جسم الشاشة لحالة [CachedReadCubit]: تحميل/خطأ/بيانات تحت مؤشّر عمرها.
class CachedReadBody<T> extends StatelessWidget {
  const CachedReadBody({super.key, required this.builder, this.now});

  final List<Widget> Function(BuildContext context, T data) builder;

  /// للاختبارات: «الآن» ثابت لحساب العمر.
  final DateTime? now;

  @override
  Widget build(BuildContext context) =>
      BlocBuilder<CachedReadCubit<T>, CachedReadState<T>>(
        builder: (context, state) => switch (state) {
          CachedReadLoading<T>() => const LoadingState(),
          CachedReadFailed<T>(:final error) => ErrorState(
              error: error,
              onRetry: () => context.read<CachedReadCubit<T>>().load(),
            ),
          CachedReadLoaded<T>(:final result) => RefreshIndicator(
              onRefresh: () => context.read<CachedReadCubit<T>>().load(),
              child: ListView(
                padding: const EdgeInsetsDirectional.only(
                  bottom: SahoolSpacing.xl,
                ),
                children: [
                  DataAgeBanner(
                    fetchedAt: result.fetchedAt,
                    fromCache: result.fromCache,
                    refreshError: result.refreshError,
                    now: now,
                  ),
                  ...builder(context, result.data),
                ],
              ),
            ),
        },
      );
}

/// اختيار الحقل من قائمة محفوظة دون اتّصال كذلك.
class FieldChooser extends StatelessWidget {
  const FieldChooser({
    super.key,
    required this.loader,
    required this.onSelected,
    this.now,
  });

  final Future<CachedResult<List<FieldOption>>> Function() loader;
  final ValueChanged<FieldOption> onSelected;
  final DateTime? now;

  @override
  Widget build(BuildContext context) => BlocProvider(
        create: (_) => CachedReadCubit<List<FieldOption>>(loader)..load(),
        child: CachedReadBody<List<FieldOption>>(
          now: now,
          builder: (context, fields) => [
            if (fields.isEmpty)
              const Padding(
                padding: EdgeInsets.all(SahoolSpacing.lg),
                child: EmptyState(message: 'لا حقول بعد. أنشئ حقلاً أوّلاً.'),
              )
            else ...[
              const ListSectionHeader('اختر الحقل'),
              for (final f in fields)
                AppListTile(
                  title: f.name,
                  subtitle: f.crop,
                  icon: Icons.grass_outlined,
                  onTap: () => onSelected(f),
                ),
            ],
          ],
        ),
      );
}
