// SAHOOL — features/scouting/presentation/pest_detect_screen.dart
// كشف الآفات بالصورة لحقل محدّد (field_id يُرسل دائماً). النتيجة كما ردّها
// الخادم: الأسماء ونسب الثقة؛ لا كشف مُلفَّق ولا علاج مقترح من الواجهة.
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:sahool_app/core/theme/sahool_tokens.dart';
import 'package:sahool_app/core/theme/tokens.dart';
import 'package:sahool_app/core/utils/formatters.dart';
import 'package:sahool_app/core/widgets/widgets.dart';

import '../data/scouting_models.dart';
import 'new_observation_screen.dart';
import 'pest_detect_cubit.dart';
import 'scouting_deps.dart';

/// مسار المستشار (تبويب «المستشار» — يملكه وكيل المستشار).
const String kAdvisorRoute = '/advisor';

class PestDetectScreen extends StatelessWidget {
  const PestDetectScreen({super.key, required this.field, this.deps});
  final ScoutingField field;
  final ScoutingDeps? deps;

  @override
  Widget build(BuildContext context) {
    final d = deps ?? ScoutingDeps.device();
    return BlocProvider(
      create: (_) => PestDetectCubit(
        field: field,
        api: d.api,
        photos: d.photos,
        connectivity: d.connectivity,
      ),
      child: _PestDetectBody(field: field, deps: d),
    );
  }
}

class _PestDetectBody extends StatelessWidget {
  const _PestDetectBody({required this.field, required this.deps});
  final ScoutingField field;
  final ScoutingDeps deps;

  @override
  Widget build(BuildContext context) {
    final s = context.watch<PestDetectCubit>().state;
    final cubit = context.read<PestDetectCubit>();
    final t = context.tokens;
    final busy = s is PestDetectSending;
    return AppScaffold(
      title: 'كشف الآفات — ${field.nameAr}',
      body: ListView(
        padding: const EdgeInsets.all(SahoolSpacing.md),
        children: [
          Text(
            'صوّر الورقة أو الثمرة المصابة عن قرب وفي ضوء جيّد. تُرسل الصورة '
            'مع معرّف الحقل إلى نموذج الكشف على الخادم.',
            style: TextStyle(color: t.muted),
          ),
          const SizedBox(height: SahoolSpacing.md),
          PrimaryButton(
            label: 'التقاط صورة',
            icon: Icons.photo_camera_outlined,
            loading: busy,
            onPressed: busy ? null : () => cubit.captureAndDetect(),
          ),
          const SizedBox(height: SahoolSpacing.sm),
          SecondaryButton(
            label: 'اختيار من المعرض',
            icon: Icons.photo_library_outlined,
            onPressed: busy
                ? null
                : () => cubit.captureAndDetect(fromCamera: false),
          ),
          const SizedBox(height: SahoolSpacing.lg),
          ..._result(context, s, cubit),
        ],
      ),
    );
  }

  List<Widget> _result(
    BuildContext context,
    PestDetectState s,
    PestDetectCubit cubit,
  ) {
    final t = context.tokens;
    switch (s) {
      case PestDetectIdle(:final message):
        return [
          if (message != null)
            StatusChip(label: message, tone: StatusTone.danger),
        ];
      case PestDetectOffline():
        return const [
          EmptyState(
            icon: Icons.wifi_off_rounded,
            title: 'يتطلّب اتّصالاً',
            message:
                'كشف الآفات يعمل على الخادم ولا يعمل دون اتّصال. سجّل مشاهدة '
                'يدويّة الآن وأعد المحاولة عند توفّر الشبكة.',
          ),
        ];
      case PestDetectSending(:final photoPath):
        return [
          _Thumb(path: photoPath),
          const SizedBox(height: SahoolSpacing.md),
          const LoadingState(message: 'جارٍ تحليل الصورة…'),
        ];
      case PestDetectFailed(:final photoPath, :final error):
        return [
          _Thumb(path: photoPath),
          ErrorState(
            error: error,
            title: 'تعذّر تحليل الصورة',
            onRetry: cubit.retry,
          ),
          if (s.serverDetail != null)
            Text(
              'ردّ الخادم: ${s.serverDetail}',
              textAlign: TextAlign.center,
              style: TextStyle(color: t.muted),
            ),
        ];
      case PestDetectDone(:final photoPath, :final result):
        return [
          _Thumb(path: photoPath),
          const SizedBox(height: SahoolSpacing.md),
          _ResultCard(result: result),
          const SizedBox(height: SahoolSpacing.md),
          if (deps.canRecord)
            PrimaryButton(
              label: 'سجّل كمشاهدة',
              icon: Icons.add_location_alt_outlined,
              onPressed: () => Navigator.of(context).push(
                MaterialPageRoute<bool>(
                  builder: (_) => NewObservationScreen(
                    field: field,
                    deps: deps,
                    initialCategory: IssueCategory.pest,
                    initialNote: _noteFor(result),
                  ),
                ),
              ),
            ),
          const SizedBox(height: SahoolSpacing.sm),
          SecondaryButton(
            label: 'اسأل المستشار',
            icon: Icons.psychology_outlined,
            onPressed: () => Navigator.of(context).pushNamed(
              kAdvisorRoute,
              arguments: {
                'field_id': field.id,
                'question': _questionFor(result),
              },
            ),
          ),
        ];
    }
  }

  String? _noteFor(PestDetectResult r) {
    if (r.detections.isEmpty) return null;
    final top = r.detections.first;
    return 'كشف بالصورة: ${top.labelAr} '
        '(ثقة ${fmtPct(top.confidence, fraction: true)})';
  }

  String _questionFor(PestDetectResult r) {
    if (r.detections.isEmpty) {
      return 'صوّرت نباتاً في حقل ${field.nameAr} ولم يكتشف النموذج آفة. '
          'ما الذي أفحصه؟';
    }
    final top = r.detections.first;
    return 'كشف النموذج «${top.labelAr}» بثقة '
        '${fmtPct(top.confidence, fraction: true)} في حقل ${field.nameAr}. '
        'كيف أتأكّد وما الخطوات المناسبة؟';
  }
}

class _Thumb extends StatelessWidget {
  const _Thumb({required this.path});
  final String path;
  @override
  Widget build(BuildContext context) => ClipRRect(
    borderRadius: SahoolRadius.mdAll,
    child: Image.file(
      File(path),
      height: 180,
      fit: BoxFit.cover,
      errorBuilder: (_, _, _) => const SizedBox.shrink(),
    ),
  );
}

class _ResultCard extends StatelessWidget {
  const _ResultCard({required this.result});
  final PestDetectResult result;

  @override
  Widget build(BuildContext context) {
    final t = context.tokens;
    final alert = result.alertAr?.replaceAll('**', '').trim();
    return SectionCard(
      title: 'نتيجة الكشف',
      icon: Icons.pest_control_outlined,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          if (result.detections.isEmpty)
            const Text(
              'لم يكتشف النموذج آفات فوق عتبة الثقة في هذه الصورة. هذا لا يعني '
              'خلوّ النبات — إن لاحظت أعراضاً صوّر عن قرب أو سجّل مشاهدة.',
            )
          else
            for (final d in result.detections)
              AppListTile(
                title: d.labelAr,
                subtitle: d.severity == null
                    ? null
                    : 'الشدّة حسب النموذج: ${PinSeverity.fromWire(d.severity)?.labelAr ?? d.severity}',
                icon: Icons.bug_report_outlined,
                trailing: StatusChip(
                  label: 'الثقة ${fmtPct(d.confidence, fraction: true)}',
                  tone: (d.confidence ?? 0) > 0.8
                      ? StatusTone.danger
                      : StatusTone.warning,
                ),
              ),
          if (alert != null && alert.isNotEmpty) ...[
            const SizedBox(height: SahoolSpacing.sm),
            Text(alert),
          ],
          const SizedBox(height: SahoolSpacing.sm),
          Text(
            [
              if (result.modelVersion != null)
                'إصدار النموذج: ${result.modelVersion}',
              if (result.syncStatus != null)
                result.syncStatus == 'synced'
                    ? 'سُجّلت النتيجة على الخادم'
                    : 'النتيجة بانتظار المزامنة على الحافّة',
            ].join(' · '),
            style: TextStyle(color: t.muted, fontSize: SahoolType.caption),
          ),
        ],
      ),
    );
  }
}
