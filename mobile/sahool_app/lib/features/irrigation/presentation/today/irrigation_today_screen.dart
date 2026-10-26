// SAHOOL — features/irrigation/presentation/today/irrigation_today_screen.dart
// «هل أروي اليوم؟» حقلاً حقلاً: منتقي الحقل ثمّ مرشَّح الخادم كما هو، مع روابط
// دفتر المياه والريّ التشغيليّ والخطّة. يقبل field_id من رابط عميق (مساحة الحقل).
import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:sahool_app/core/permissions/permissions.dart';
import 'package:sahool_app/core/routing/app_navigator.dart';
import 'package:sahool_app/core/theme/sahool_tokens.dart';
import 'package:sahool_app/core/theme/tokens.dart';
import 'package:sahool_app/core/utils/formatters.dart';
import 'package:sahool_app/core/widgets/widgets.dart';
import 'package:sahool_app/features/irrigation/data/irrigation_api.dart';
import 'package:sahool_app/features/irrigation/presentation/irrigation_fields_cubit.dart';
import 'package:sahool_app/features/irrigation/presentation/irrigation_format.dart';
import 'package:sahool_app/features/irrigation/presentation/today/recommendation_card.dart';
import 'package:sahool_app/features/irrigation/presentation/today/recommendation_cubit.dart';

/// مسارات الريّ (مكرّرة هنا تفادياً لاستيراد دائريّ مع irrigation_routes.dart).
abstract final class IrrigationPaths {
  static const today = '/irrigation/today';
  static const ops = '/irrigation/ops';
  static const ledger = '/irrigation/ledger';
  static const plan = '/irrigation/plan';
}

class IrrigationTodayScreen extends StatelessWidget {
  const IrrigationTodayScreen({
    super.key,
    this.initialFieldId,
    this.api,
    this.role,
    this.fieldsLoader,
  });

  final String? initialFieldId;
  final IrrigationApi? api;

  /// للاختبار؛ null ⇒ دور الجلسة.
  final String? role;
  final Future<List<Map<String, dynamic>>> Function()? fieldsLoader;

  @override
  Widget build(BuildContext context) => MultiBlocProvider(
    providers: [
      BlocProvider(
        create: (_) => IrrigationFieldsCubit(loader: fieldsLoader)..load(),
      ),
      BlocProvider(
        create: (_) => RecommendationCubit(api ?? IrrigationApi.instance),
      ),
    ],
    child: _TodayView(
      initialFieldId: initialFieldId,
      role: role ?? currentRole(),
    ),
  );
}

class _TodayView extends StatefulWidget {
  const _TodayView({required this.initialFieldId, required this.role});
  final String? initialFieldId;
  final String? role;

  @override
  State<_TodayView> createState() => _TodayViewState();
}

class _TodayViewState extends State<_TodayView> {
  String? _fieldId;

  void _select(String? id) {
    if (id == null || id == _fieldId) return;
    setState(() => _fieldId = id);
    context.read<RecommendationCubit>().load(id);
  }

  void _onFields(IrrigationFieldsState s) {
    if (s is! IrrigationFieldsLoaded || s.fields.isEmpty) return;
    final wanted =
        s.byId(widget.initialFieldId) ?? s.byId(_fieldId) ?? s.fields.first;
    _fieldId = null; // يُعيد التحميل بعد تحديث القائمة
    _select(wanted.id);
  }

  void _openLedger(IrrigationField f) => context.openRoute<void>(
    IrrigationPaths.ledger,
    arguments: {
      'field_id': f.id,
      'field_name': f.name,
      if (f.areaHa != null) 'area_ha': f.areaHa,
    },
  );

  @override
  Widget build(BuildContext context) {
    final fieldsCubit = context.read<IrrigationFieldsCubit>();
    return AppScaffold(
      title: 'هل أروي اليوم؟',
      actions: [
        AppIconButton(
          icon: Icons.refresh_rounded,
          tooltip: 'تحديث',
          onPressed: () {
            final id = _fieldId;
            if (id != null) context.read<RecommendationCubit>().load(id);
          },
        ),
      ],
      body: BlocConsumer<IrrigationFieldsCubit, IrrigationFieldsState>(
        listener: (_, s) => _onFields(s),
        builder: (context, fs) => switch (fs) {
          IrrigationFieldsLoading() => const LoadingState(
            message: 'جارٍ تحميل الحقول…',
          ),
          IrrigationFieldsFailed(:final error) => ErrorState(
            error: error,
            onRetry: fieldsCubit.load,
          ),
          IrrigationFieldsLoaded(:final fields) when fields.isEmpty =>
            const EmptyState(
              message: 'لا حقول بعد. أضف حقلاً لتظهر له توصية الريّ.',
              icon: Icons.grass_rounded,
            ),
          IrrigationFieldsLoaded() => _body(context, fs),
        },
      ),
    );
  }

  Widget _body(BuildContext context, IrrigationFieldsLoaded fs) {
    final field = fs.byId(_fieldId);
    final canLog = canWriteWaterLedger(widget.role);
    return ListView(
      padding: const EdgeInsetsDirectional.fromSTEB(
        SahoolSpacing.page,
        0,
        SahoolSpacing.page,
        SahoolSpacing.xl,
      ),
      children: [
        AppDropdown<String>(
          key: ValueKey('irr-field-${fs.fields.length}'),
          label: 'الحقل',
          items: {for (final f in fs.fields) f.id: f.name},
          value: _fieldId,
          onChanged: _select,
        ),
        const SizedBox(height: SahoolSpacing.md),
        BlocBuilder<RecommendationCubit, RecommendationState>(
          builder: (context, rs) => switch (rs) {
            RecommendationIdle() => const SizedBox.shrink(),
            RecommendationLoading() => const SizedBox(
              height: 200,
              child: LoadingState(message: 'يحسب الخادم حالة ماء الحقل…'),
            ),
            RecommendationFailed(:final error, :final fieldId) => SizedBox(
              height: 320,
              child: ErrorState(
                error: error,
                onRetry: () =>
                    context.read<RecommendationCubit>().load(fieldId),
              ),
            ),
            RecommendationLoaded(
              :final recommendation,
              :final at,
              :final fieldId,
            ) =>
              Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  RecommendationCard(
                    recommendation: recommendation,
                    areaHa: fs.byId(fieldId)?.areaHa,
                    onLogWater: canLog && field != null
                        ? () => _openLedger(field)
                        : null,
                    onRetry: () =>
                        context.read<RecommendationCubit>().load(fieldId),
                  ),
                  Padding(
                    padding: const EdgeInsetsDirectional.only(
                      top: SahoolSpacing.xs,
                    ),
                    child: Text(
                      'آخر تحديث: ${fmtAge(at)}',
                      style: context.textStyles.bodySmall,
                    ),
                  ),
                ],
              ),
          },
        ),
        const SizedBox(height: SahoolSpacing.lg),
        if (field != null)
          AppListTile(
            title: 'دفتر المياه',
            subtitle: canLog
                ? 'سجلّ الريّ اليوميّ وتسجيل الماء المضاف'
                : 'سجلّ الريّ اليوميّ',
            icon: Icons.menu_book_rounded,
            onTap: () => _openLedger(field),
          ),
        AppListTile(
          title: 'الريّ التشغيليّ',
          subtitle: 'الصمّامات وجداول الريّ',
          icon: Icons.tune_rounded,
          onTap: () => context.openRoute<void>(IrrigationPaths.ops),
        ),
        AppListTile(
          title: 'خطّة ريّ افتراضيّة',
          subtitle: 'احسب جدولاً بمدخلاتك (غير معايَر)',
          icon: Icons.calendar_month_rounded,
          onTap: () => context.openRoute<void>(IrrigationPaths.plan),
        ),
        const SizedBox(height: SahoolSpacing.sm),
        Text(
          'التوصية مرشَّحٌ لا أمر: لا تُشغّل صمّاماً ولا تُنشئ مهمّة.',
          style: context.textStyles.bodySmall?.copyWith(
            color: context.tokens.muted,
          ),
        ),
      ],
    );
  }
}
