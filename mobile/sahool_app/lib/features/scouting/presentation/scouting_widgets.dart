// SAHOOL — features/scouting/presentation/scouting_widgets.dart
// قطع مشتركة لشاشات الاستكشاف: بوّابة اختيار الحقل، صفّ الدبّوس، وورقة تفاصيله.
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:sahool_app/core/theme/sahool_tokens.dart';
import 'package:sahool_app/core/theme/tokens.dart';
import 'package:sahool_app/core/utils/formatters.dart';
import 'package:sahool_app/core/widgets/widgets.dart';

import '../data/scouting_models.dart';
import 'scouting_deps.dart';
import 'scouting_fields_cubit.dart';

/// يحمّل الحقول ثمّ يبني [builder] للحقل المختار؛ بلا field_id صالح يعرض قائمة
/// اختيار بأزرار كبيرة (لمسة واحدة في الحقل).
class ScoutingFieldGate extends StatelessWidget {
  const ScoutingFieldGate({
    super.key,
    required this.title,
    required this.deps,
    required this.builder,
    this.initialFieldId,
  });

  final String title;
  final ScoutingDeps deps;
  final String? initialFieldId;
  final Widget Function(BuildContext context, ScoutingField field) builder;

  @override
  Widget build(BuildContext context) => BlocProvider(
    create: (_) => ScoutingFieldsCubit(loader: deps.fieldsLoader)..load(),
    child: _GateBody(
      title: title,
      initialFieldId: initialFieldId,
      builder: builder,
    ),
  );
}

class _GateBody extends StatefulWidget {
  const _GateBody({
    required this.title,
    required this.builder,
    this.initialFieldId,
  });
  final String title;
  final String? initialFieldId;
  final Widget Function(BuildContext context, ScoutingField field) builder;

  @override
  State<_GateBody> createState() => _GateBodyState();
}

class _GateBodyState extends State<_GateBody> {
  String? _chosen;

  @override
  void initState() {
    super.initState();
    _chosen = widget.initialFieldId;
  }

  @override
  Widget build(BuildContext context) {
    final state = context.watch<ScoutingFieldsCubit>().state;
    if (state is ScoutingFieldsLoaded) {
      final field = state.byId(_chosen);
      if (field != null) return widget.builder(context, field);
    }
    final cubit = context.read<ScoutingFieldsCubit>();
    return AppScaffold(
      title: widget.title,
      body: switch (state) {
        ScoutingFieldsLoading() => const LoadingState(
          message: 'جارٍ تحميل الحقول…',
        ),
        ScoutingFieldsFailed(:final error) => ErrorState(
          error: error,
          onRetry: cubit.load,
        ),
        ScoutingFieldsLoaded(:final fields) => FieldChoiceList(
          fields: fields,
          missingId: _chosen,
          onChoose: (f) => setState(() => _chosen = f.id),
        ),
      },
    );
  }
}

/// قائمة اختيار حقل بصفوف كبيرة.
class FieldChoiceList extends StatelessWidget {
  const FieldChoiceList({
    super.key,
    required this.fields,
    required this.onChoose,
    this.missingId,
  });

  final List<ScoutingField> fields;
  final ValueChanged<ScoutingField> onChoose;

  /// معرّف طُلب في الرابط ولم يوجد بين حقول المستخدم.
  final String? missingId;

  @override
  Widget build(BuildContext context) {
    if (fields.isEmpty) {
      return const EmptyState(
        icon: Icons.grass_outlined,
        title: 'لا حقول بعد',
        message: 'أضف حقلاً أوّلاً من «الحقول» لتسجيل المشاهدات عليه.',
      );
    }
    return ListView(
      padding: const EdgeInsetsDirectional.only(bottom: SahoolSpacing.xl),
      children: [
        if (missingId != null && missingId!.isNotEmpty)
          Padding(
            padding: const EdgeInsets.all(SahoolSpacing.lg),
            child: StatusChip(
              label: 'الحقل المطلوب غير موجود ضمن حقولك — اختر حقلاً',
              tone: StatusTone.warning,
            ),
          ),
        const ListSectionHeader('اختر الحقل'),
        for (final f in fields)
          AppListTile(
            title: f.nameAr,
            subtitle: f.crop,
            icon: Icons.crop_square_rounded,
            onTap: () => onChoose(f),
          ),
      ],
    );
  }
}

/// صفّ دبّوس في القائمة: الفئة + الشدّة (لون+أيقونة+نصّ) + التاريخ.
class PinTile extends StatelessWidget {
  const PinTile({super.key, required this.pin, required this.onTap});
  final ScoutingPin pin;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final sev = pin.severity;
    final (statusText, statusTone) = pinStatusLabel(pin.status);
    final subtitle = [
      fmtDateTime(pin.createdAt),
      statusText,
      if (pin.noteAr != null) pin.noteAr!,
    ].join(' · ');
    return AppListTile(
      title: pin.category?.labelAr ?? pin.categoryWire,
      subtitle: subtitle,
      icon: pin.category?.icon ?? Icons.help_outline_rounded,
      trailing: StatusChip(
        label:
            sev?.labelAr ?? (pin.severityWire.isEmpty ? '—' : pin.severityWire),
        tone: sev?.tone ?? statusTone,
        icon: sev?.icon,
      ),
      onTap: onTap,
    );
  }
}

/// ورقة تفاصيل دبّوس (قراءة فقط) مع صورته المحلّيّة إن وُجدت على هذا الجهاز.
Future<void> showPinDetails(
  BuildContext context,
  ScoutingPin pin,
  ScoutingDeps deps,
) => showAppBottomSheet<void>(
  context,
  builder: (_) => AppSheet(
    title: pin.category?.labelAr ?? pin.categoryWire,
    children: [_PinDetails(pin: pin, deps: deps)],
  ),
);

class _PinDetails extends StatelessWidget {
  const _PinDetails({required this.pin, required this.deps});
  final ScoutingPin pin;
  final ScoutingDeps deps;

  @override
  Widget build(BuildContext context) {
    final t = context.tokens;
    final sev = pin.severity;
    final (statusText, statusTone) = pinStatusLabel(pin.status);
    Widget row(String k, String v) => Padding(
      padding: const EdgeInsets.symmetric(vertical: SahoolSpacing.xs),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SizedBox(
            width: 110,
            child: Text(k, style: TextStyle(color: t.muted)),
          ),
          Expanded(child: Text(v)),
        ],
      ),
    );
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Wrap(
          spacing: SahoolSpacing.sm,
          runSpacing: SahoolSpacing.sm,
          children: [
            StatusChip(
              label: 'الشدّة: ${sev?.labelAr ?? pin.severityWire}',
              tone: sev?.tone ?? StatusTone.neutral,
              icon: sev?.icon,
            ),
            StatusChip(label: statusText, tone: statusTone),
          ],
        ),
        const SizedBox(height: SahoolSpacing.md),
        row('التاريخ', fmtDateTime(pin.createdAt)),
        row(
          'الموقع',
          '${pin.lat.toStringAsFixed(6)}, ${pin.lng.toStringAsFixed(6)}',
        ),
        if (pin.issueCode != null) row('المشكلة', pin.issueCode!),
        if (pin.crop != null) row('المحصول', pin.crop!),
        row('ملاحظة', pin.noteAr ?? '—'),
        if (pin.photoUri != null) row('مرجع صورة', pin.photoUri!),
        FutureBuilder<String?>(
          future: deps.photoStore.find(pin.pinId),
          builder: (context, snap) {
            final path = snap.data;
            if (path == null) return const SizedBox.shrink();
            return Padding(
              padding: const EdgeInsets.only(top: SahoolSpacing.md),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  ClipRRect(
                    borderRadius: SahoolRadius.mdAll,
                    child: Image.file(
                      File(path),
                      height: 200,
                      fit: BoxFit.cover,
                      errorBuilder: (_, _, _) => const SizedBox.shrink(),
                    ),
                  ),
                  const SizedBox(height: SahoolSpacing.xs),
                  Text(
                    'الصورة محفوظة على هذا الجهاز فقط.',
                    style: TextStyle(color: t.muted),
                  ),
                ],
              ),
            );
          },
        ),
      ],
    );
  }
}
