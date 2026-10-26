// SAHOOL — features/maps/io/presentation/import_screen.dart
// استيراد حدود GeoJSON/KML مع معاينة على الخريطة قبل الحفظ (كان لصقاً بلا معاينة،
// والمعاينة تقرأ Polygon فقط). يُختار ما يُنشأ من المضلّعات ويُسمّى كلٌّ منها،
// ويُعلَن ما أُهمل (أجزاء غير مضلّعة، ثقوب لا يحفظها الخادم) قبل الإرسال.
//
// وضع الالتقاط ([pickMode]): لتدفّق الرسم — يُعيد `Navigator.pop` مضلّعاً واحداً
// GeoJSON (`Map<String, dynamic>`، حلقة خارجيّة) دون أيّ كتابة على الخادم.
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:sahool_app/core/theme/sahool_tokens.dart';
import 'package:sahool_app/core/theme/tokens.dart';
import 'package:sahool_app/core/utils/formatters.dart';
import 'package:sahool_app/core/widgets/widgets.dart';

import '../data/maps_io_api.dart';
import '../geo/import_model.dart';
import '../geo/io_geometry.dart';
import 'import_cubit.dart';
import 'io_map.dart';

class ImportScreen extends StatelessWidget {
  const ImportScreen({
    super.key,
    this.api,
    this.farmId,
    this.pickMode = false,
    this.showBasemap = true,
  });

  final MapsIoApi? api;
  final String? farmId;
  final bool pickMode;
  final bool showBasemap;

  @override
  Widget build(BuildContext context) => BlocProvider(
    create: (_) => ImportCubit(api ?? MapsIoApi.instance, farmId: farmId),
    child: _ImportView(pickMode: pickMode, showBasemap: showBasemap),
  );
}

class _ImportView extends StatefulWidget {
  const _ImportView({required this.pickMode, required this.showBasemap});
  final bool pickMode;
  final bool showBasemap;

  @override
  State<_ImportView> createState() => _ImportViewState();
}

class _ImportViewState extends State<_ImportView> {
  final _text = TextEditingController();
  BoundaryFormat? _format;
  int _generation = 0;

  @override
  void dispose() {
    _text.dispose();
    super.dispose();
  }

  Future<void> _paste() async {
    final data = await Clipboard.getData(Clipboard.kTextPlain);
    if (!mounted) return;
    final t = data?.text;
    if (t == null || t.trim().isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('الحافظة فارغة — انسخ محتوى الملفّ أوّلاً.'),
        ),
      );
      return;
    }
    setState(() => _text.text = t);
  }

  void _preview() {
    FocusScope.of(context).unfocus();
    _generation++;
    context.read<ImportCubit>().parse(_text.text, format: _format);
  }

  @override
  Widget build(BuildContext context) {
    return BlocBuilder<ImportCubit, ImportState>(
      builder: (context, s) => AppScaffold(
        title: widget.pickMode ? 'اختيار حدود من ملفّ' : 'استيراد حدود الحقول',
        body: s.parsed == null ? _input(context, s) : _previewBody(context, s),
      ),
    );
  }

  Widget _input(BuildContext context, ImportState s) {
    final t = context.tokens;
    return ListView(
      padding: const EdgeInsets.all(SahoolSpacing.page),
      children: [
        SectionCard(
          title: 'المصدر',
          icon: Icons.upload_file_outlined,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Text(
                'الصق محتوى ملفّ GeoJSON أو KML (من Google Earth أو أيّ برنامج خرائط). '
                'فتح الملفّات من ذاكرة الهاتف غير متاح بعد في التطبيق.',
                style: context.textStyles.bodyMedium?.copyWith(color: t.muted),
              ),
              const SizedBox(height: SahoolSpacing.md),
              SegmentedButton<BoundaryFormat?>(
                segments: const [
                  ButtonSegment(value: null, label: Text('تلقائيّ')),
                  ButtonSegment(
                    value: BoundaryFormat.geojson,
                    label: Text('GeoJSON'),
                  ),
                  ButtonSegment(value: BoundaryFormat.kml, label: Text('KML')),
                ],
                selected: {_format},
                onSelectionChanged: (v) => setState(() => _format = v.first),
              ),
              const SizedBox(height: SahoolSpacing.md),
              TextField(
                key: const Key('import-text'),
                controller: _text,
                minLines: 6,
                maxLines: 12,
                textDirection: TextDirection.ltr,
                style: const TextStyle(
                  fontFamily: 'monospace',
                  fontSize: SahoolType.caption,
                ),
                decoration: InputDecoration(
                  labelText: 'محتوى الملفّ',
                  hintText:
                      '{"type":"FeatureCollection", ...}  أو  <kml>…</kml>',
                  errorText: s.parseError,
                  errorMaxLines: 6,
                  alignLabelWithHint: true,
                ),
              ),
              const SizedBox(height: SahoolSpacing.sm),
              SecondaryButton(
                label: 'لصق من الحافظة',
                icon: Icons.content_paste_rounded,
                onPressed: _paste,
              ),
            ],
          ),
        ),
        const SizedBox(height: SahoolSpacing.lg),
        PrimaryButton(
          label: 'معاينة على الخريطة',
          icon: Icons.map_outlined,
          onPressed: _preview,
        ),
      ],
    );
  }

  Widget _previewBody(BuildContext context, ImportState s) {
    final cubit = context.read<ImportCubit>();
    final parsed = s.parsed!;
    if (!widget.pickMode && s.allDone) {
      return EmptyState(
        icon: Icons.check_circle_outline_rounded,
        title: 'تمّ الاستيراد',
        message:
            'أُنشئ ${s.createdCount} حقل من ملفّ ${parsed.format.labelAr}.',
        actionLabel: 'العودة',
        onAction: () => Navigator.of(context).maybePop(true),
      );
    }
    return Column(
      children: [
        SizedBox(
          height: 260,
          child: IoMap(
            showBasemap: widget.showBasemap,
            shapes: [
              for (var i = 0; i < s.rows.length; i++)
                IoMapShape(
                  s.rows[i].shape.polygon,
                  selected: s.rows[i].selected && !s.rows[i].blocked,
                  label: '${i + 1}',
                ),
            ],
          ),
        ),
        Expanded(
          child: ListView(
            padding: const EdgeInsets.all(SahoolSpacing.page),
            children: [
              Text(
                'وُجد ${s.rows.length} مضلّع في ملفّ ${parsed.format.labelAr}'
                '${widget.pickMode ? ' — اختر واحداً لاستخدامه في الرسم.' : ' — اختر ما يُنشأ حقولاً.'}',
                style: context.textStyles.titleMedium,
              ),
              for (final w in parsed.warnings)
                Padding(
                  padding: const EdgeInsets.only(top: SahoolSpacing.sm),
                  child: StatusChip(label: w, tone: StatusTone.warning),
                ),
              for (var i = 0; i < s.rows.length; i++)
                _RowCard(
                  key: ValueKey('row-$_generation-$i'),
                  index: i,
                  row: s.rows[i],
                  pickMode: widget.pickMode,
                  enabled: !s.submitting,
                  onToggle: (v) => cubit.toggle(i, v),
                  onRename: (v) => cubit.rename(i, v),
                  onPick: () => Navigator.of(
                    context,
                  ).pop(polygonToGeoJson(s.rows[i].shape.polygon.outerOnly())),
                ),
              if (s.formError != null)
                Padding(
                  padding: const EdgeInsets.only(top: SahoolSpacing.md),
                  child: Semantics(
                    liveRegion: true,
                    child: Text(
                      s.formError!,
                      style: context.textStyles.bodyMedium?.copyWith(
                        color: context.tokens.danger,
                      ),
                    ),
                  ),
                ),
              const SizedBox(height: SahoolSpacing.lg),
              if (!widget.pickMode)
                PrimaryButton(
                  label: s.rows.any((r) => r.status == RowStatus.failed)
                      ? 'إعادة محاولة ${s.selectedCount} حقل'
                      : 'استيراد ${s.selectedCount} حقل',
                  icon: Icons.cloud_upload_outlined,
                  loading: s.submitting,
                  onPressed: s.selectedCount == 0 ? null : cubit.submit,
                ),
              const SizedBox(height: SahoolSpacing.sm),
              SecondaryButton(
                label: 'تغيير المحتوى',
                icon: Icons.edit_note_rounded,
                onPressed: s.submitting ? null : cubit.clear,
              ),
            ],
          ),
        ),
      ],
    );
  }
}

class _RowCard extends StatelessWidget {
  const _RowCard({
    super.key,
    required this.index,
    required this.row,
    required this.pickMode,
    required this.enabled,
    required this.onToggle,
    required this.onRename,
    required this.onPick,
  });

  final int index;
  final ImportRow row;
  final bool pickMode;
  final bool enabled;
  final ValueChanged<bool> onToggle;
  final ValueChanged<String> onRename;
  final VoidCallback onPick;

  @override
  Widget build(BuildContext context) {
    final created = row.status == RowStatus.created;
    return Padding(
      padding: const EdgeInsets.only(top: SahoolSpacing.md),
      child: SectionCard(
        title:
            '${index + 1}. ${fmtArea(row.areaHa, decimals: 2)} · ${row.shape.polygon.vertexCount} رأس',
        icon: Icons.crop_square_rounded,
        trailing: pickMode
            ? null
            : Checkbox(
                value: row.selected && !row.blocked,
                onChanged: (!enabled || row.blocked || created)
                    ? null
                    : (v) => onToggle(v ?? false),
              ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text(
              'المساحة تقديريّة على الجهاز؛ الخادم يحسب المساحة المعتمدة عند الحفظ.',
              style: context.textStyles.bodySmall?.copyWith(
                color: context.tokens.muted,
              ),
            ),
            if (!pickMode)
              Padding(
                padding: const EdgeInsets.only(top: SahoolSpacing.md),
                child: TextFormField(
                  key: ValueKey('name-$index'),
                  initialValue: row.name,
                  enabled: enabled && !created && !row.blocked,
                  maxLength: 100,
                  onChanged: onRename,
                  decoration: const InputDecoration(labelText: 'اسم الحقل'),
                ),
              ),
            for (final issue in row.issues)
              Padding(
                padding: const EdgeInsets.only(top: SahoolSpacing.sm),
                child: StatusChip(
                  label: issue.messageAr,
                  tone: issue.blocking ? StatusTone.danger : StatusTone.warning,
                ),
              ),
            if (row.status != RowStatus.pending)
              Padding(
                padding: const EdgeInsets.only(top: SahoolSpacing.sm),
                child: switch (row.status) {
                  RowStatus.sending => const StatusChip(
                    label: 'جارٍ الإرسال…',
                    tone: StatusTone.info,
                  ),
                  RowStatus.created => const StatusChip(
                    label: 'أُنشئ الحقل',
                    tone: StatusTone.success,
                  ),
                  RowStatus.failed => StatusChip(
                    label: row.error ?? 'تعذّر الحفظ',
                    tone: StatusTone.danger,
                  ),
                  RowStatus.pending => const SizedBox.shrink(),
                },
              ),
            if (pickMode) ...[
              const SizedBox(height: SahoolSpacing.sm),
              PrimaryButton(
                label: 'استخدم هذا المضلّع',
                icon: Icons.check_rounded,
                onPressed: row.blocked ? null : onPick,
              ),
            ],
          ],
        ),
      ),
    );
  }
}
