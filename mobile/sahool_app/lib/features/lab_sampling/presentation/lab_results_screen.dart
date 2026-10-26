// SAHOOL — features/lab_sampling/presentation/lab_results_screen.dart
// نتائج المختبر للحقل بما يتيحه الخادم فعلاً:
//   • سياق المختبر (lab-context): جاهزيّة التربة للتسميد، توفّر تحليل الماء،
//     العوائق والتحذيرات — أعلام بلا قيم.
//   • فحوص التربة المسجّلة (soil-lab-tests): قيم `result` كما خُزّنت.
// لا وحدات ولا نطاقات مرجعيّة يخترعها التطبيق: الخادم لا يعيدها في أيّ قراءة،
// فنقول ذلك صراحةً.
import 'package:flutter/material.dart';
import 'package:sahool_app/core/network/api_exception.dart';
import 'package:sahool_app/core/theme/sahool_tokens.dart';
import 'package:sahool_app/core/theme/tokens.dart';
import 'package:sahool_app/core/utils/formatters.dart';
import 'package:sahool_app/core/widgets/widgets.dart';

import '../data/lab_models.dart';
import '../data/lab_sampling_api.dart';

const String kUnitsNotProvided =
    'الوحدات والنطاقات المرجعيّة لكلّ قيمة غير متاحة بعد من الخادم — تُعرَض القيم كما سُجّلت.';

/// بطاقة سياق المختبر.
class LabContextCard extends StatelessWidget {
  const LabContextCard({super.key, this.ctx, this.error});
  final LabContext? ctx;
  final ApiException? error;

  @override
  Widget build(BuildContext context) {
    final t = context.tokens;
    final c = ctx;
    return SectionCard(
      title: 'جاهزيّة نتائج المختبر',
      icon: Icons.science_outlined,
      child: error != null
          ? Text(
              error!.messageAr,
              style: context.textStyles.bodyMedium?.copyWith(color: t.danger),
            )
          : c == null
          ? const Text('غير متاح بعد')
          : Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Wrap(
                  spacing: SahoolSpacing.sm,
                  runSpacing: SahoolSpacing.sm,
                  children: [
                    c.soilReadyForFertilizer
                        ? const StatusChip(
                            label: 'التربة جاهزة لقرار التسميد',
                            tone: StatusTone.success,
                          )
                        : const StatusChip(
                            label: 'التربة غير جاهزة لقرار التسميد',
                            tone: StatusTone.warning,
                          ),
                    c.waterLabAvailable
                        ? const StatusChip(
                            label: 'يوجد تحليل ماء ريّ',
                            tone: StatusTone.info,
                          )
                        : const StatusChip(label: 'لا تحليل ماء ريّ'),
                  ],
                ),
                for (final b in c.blockersAr)
                  _line(context, Icons.block, t.danger, b),
                for (final w in c.warningsAr)
                  _line(context, Icons.warning_amber_rounded, t.warning, w),
              ],
            ),
    );
  }

  Widget _line(BuildContext context, IconData icon, Color color, String text) =>
      Padding(
        padding: const EdgeInsetsDirectional.only(top: SahoolSpacing.sm),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Icon(icon, color: color, size: SahoolSizes.iconSm),
            const SizedBox(width: SahoolSpacing.sm),
            Expanded(child: Text(text, style: context.textStyles.bodyMedium)),
          ],
        ),
      );
}

String _value(Object? v) {
  if (v == null) return kNotMeasured;
  if (v is num) return fmtNumber(v, decimals: 2);
  if (v is Map || v is List) return v.toString();
  final s = v.toString();
  return s.isEmpty ? kNotMeasured : s;
}

class LabResultsScreen extends StatefulWidget {
  const LabResultsScreen({super.key, required this.fieldId, this.api});
  final String fieldId;
  final LabSamplingApi? api;

  @override
  State<LabResultsScreen> createState() => _LabResultsScreenState();
}

class _LabResultsScreenState extends State<LabResultsScreen> {
  late Future<(LabContext?, ApiException?, List<Map<String, dynamic>>)> _future;

  LabSamplingApi get _api => widget.api ?? LabSamplingApi.instance;

  @override
  void initState() {
    super.initState();
    _future = _load();
  }

  Future<(LabContext?, ApiException?, List<Map<String, dynamic>>)>
  _load() async {
    LabContext? ctx;
    ApiException? ctxErr;
    try {
      ctx = await _api.getLabContext(widget.fieldId);
    } catch (e) {
      ctxErr = ApiException.from(e);
    }
    // سجلّ الفحوص هو المحتوى الرئيسيّ: فشله يُعرَض كخطأ الشاشة.
    final tests = await _api.listSoilLabTests(widget.fieldId);
    return (ctx, ctxErr, tests);
  }

  @override
  Widget build(BuildContext context) => AppScaffold(
    title: 'نتائج المختبر',
    body: FutureBuilder(
      future: _future,
      builder: (context, snap) {
        if (snap.connectionState != ConnectionState.done) {
          return const LoadingState();
        }
        if (snap.hasError) {
          return ErrorState(
            error: ApiException.from(snap.error!),
            onRetry: () => setState(() => _future = _load()),
          );
        }
        final (ctx, ctxErr, tests) = snap.data!;
        final t = context.tokens;
        return ListView(
          padding: const EdgeInsets.all(SahoolSpacing.page),
          children: [
            LabContextCard(ctx: ctx, error: ctxErr),
            const ListSectionHeader('فحوص التربة المسجّلة'),
            Text(
              kUnitsNotProvided,
              style: context.textStyles.bodySmall?.copyWith(color: t.muted),
            ),
            if (tests.isEmpty)
              const EmptyState(
                title: 'لا نتائج بعد',
                message: 'لم تُسجَّل نتيجة فحص تربة لهذا الحقل.',
                icon: Icons.science_outlined,
              ),
            for (final test in tests) _TestCard(test),
          ],
        );
      },
    ),
  );
}

class _TestCard extends StatelessWidget {
  const _TestCard(this.test);
  final Map<String, dynamic> test;

  @override
  Widget build(BuildContext context) {
    final t = context.tokens;
    final status = LabSampleStatus.parse(test['status']);
    final result = test['result'] is Map
        ? (test['result'] as Map).cast<String, dynamic>()
        : const <String, dynamic>{};
    return Padding(
      padding: const EdgeInsetsDirectional.only(top: SahoolSpacing.md),
      child: SectionCard(
        title: test['lab_name']?.toString() ?? 'فحص تربة',
        icon: Icons.biotech_outlined,
        trailing: StatusChip(
          label: status?.labelAr ?? test['status']?.toString() ?? '—',
          tone:
              status == LabSampleStatus.published ||
                  status == LabSampleStatus.approved
              ? StatusTone.success
              : StatusTone.neutral,
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text(
              'تاريخ العيّنة: ${fmtIsoDate(test['sampled_on']?.toString())}',
              style: context.textStyles.bodyMedium?.copyWith(color: t.muted),
            ),
            if (result.isEmpty)
              const Padding(
                padding: EdgeInsetsDirectional.only(top: SahoolSpacing.sm),
                child: Text('لا قيم مسجّلة بعد'),
              ),
            for (final e in result.entries)
              Padding(
                padding: const EdgeInsetsDirectional.only(
                  top: SahoolSpacing.xs,
                ),
                child: Row(
                  children: [
                    Expanded(
                      child: Text(
                        e.key,
                        textDirection: TextDirection.ltr,
                        textAlign: TextAlign.start,
                        style: context.textStyles.bodyMedium?.copyWith(
                          color: t.muted,
                        ),
                      ),
                    ),
                    Text(_value(e.value), style: context.textStyles.titleSmall),
                  ],
                ),
              ),
          ],
        ),
      ),
    );
  }
}
