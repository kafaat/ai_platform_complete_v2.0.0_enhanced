// SAHOOL — features/maps/draw/boundary_step.dart
// خطوة «حدّ الحقل» في معالج الإنشاء: أوضاع الرسم، الخريطة بمقابضها، أدوات
// التراجع/الإعادة/الحذف/المسح، رأس من موقع الجهاز، لصق GeoJSON/KML، وشريط
// القياس الحيّ بالمساحة التي **سيخزّنها الخادم** مع نتيجة التحقّق الحاجب.
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:geolocator/geolocator.dart';
import 'package:latlong2/latlong.dart';
import 'package:sahool_app/core/theme/sahool_tokens.dart';
import 'package:sahool_app/core/theme/tokens.dart';
import 'package:sahool_app/core/utils/formatters.dart';
import 'package:sahool_app/core/widgets/state_views.dart' show showSnack;
import 'package:sahool_app/core/widgets/widgets.dart';

import 'boundary_import.dart';
import 'boundary_validation.dart';
import 'draw_controller.dart';
import 'draw_map.dart';

/// أسوأ دقّة GPS نقبلها لرأس حدّ (م). أضعف منها ينقل الزاوية أمتاراً.
const double kMaxGpsAccuracyM = 20;

/// مصدر موقع الجهاز (قابل للاستبدال في الاختبارات).
typedef PositionReader = Future<Position> Function();

Future<Position> _readDevicePosition() async {
  if (!await Geolocator.isLocationServiceEnabled()) {
    throw const _GpsFailure('خدمة الموقع غير مُفعَّلة على الجهاز.');
  }
  var perm = await Geolocator.checkPermission();
  if (perm == LocationPermission.denied) {
    perm = await Geolocator.requestPermission();
  }
  if (perm == LocationPermission.denied ||
      perm == LocationPermission.deniedForever) {
    throw const _GpsFailure('إذن الموقع مرفوض — لا يمكن تسجيل الرأس.');
  }
  return Geolocator.getCurrentPosition(desiredAccuracy: LocationAccuracy.best);
}

class _GpsFailure implements Exception {
  const _GpsFailure(this.messageAr);
  final String messageAr;
}

String fmtAreaExact(double? ha) =>
    ha == null ? kNotMeasured : '${fmtNumber(ha, decimals: 2)} هـ';

String fmtMeters(double m) => m >= 1000
    ? '${fmtNumber(m / 1000, decimals: 2)} كم'
    : '${fmtNumber(m, decimals: 0)} م';

class BoundaryStep extends StatefulWidget {
  const BoundaryStep({
    super.key,
    required this.controller,
    required this.initialCenter,
    this.initialZoom = 16,
    this.showBasemap = true,
    this.readPosition,
    this.note,
  });

  final DrawController controller;
  final LatLng initialCenter;
  final double initialZoom;

  /// ملاحظة صادقة فوق الخريطة (مثل تعذّر تحميل الحقول القائمة).
  final String? note;
  final bool showBasemap;
  final PositionReader? readPosition;

  @override
  State<BoundaryStep> createState() => _BoundaryStepState();
}

class _BoundaryStepState extends State<BoundaryStep> {
  final _radius = TextEditingController();
  bool _gpsBusy = false;
  String? _gpsMessage;

  DrawController get c => widget.controller;

  @override
  void initState() {
    super.initState();
    final r = c.radiusM;
    if (r != null) _radius.text = r.toStringAsFixed(0);
  }

  @override
  void dispose() {
    _radius.dispose();
    super.dispose();
  }

  String _hint(DrawMode m) => switch (m) {
    DrawMode.polygon => 'المس كلّ زاوية بالترتيب، ثمّ الرأس الأوّل للإغلاق.',
    DrawMode.rectangle => 'المس زاويتين متقابلتين للحقل.',
    DrawMode.circle => 'المس مركز المحور ثمّ اختر نصف القطر.',
    DrawMode.point => 'المس موقع النقطة.',
  };

  void _applyRadius([double? v]) {
    final r = v ?? parseLocalizedNum(_radius.text);
    if (r == null || r <= 0) return;
    _radius.text = r.toStringAsFixed(0);
    c.setRadius(r);
  }

  Future<void> _addGps() async {
    if (_gpsBusy) return;
    setState(() {
      _gpsBusy = true;
      _gpsMessage = null;
    });
    try {
      final pos = await (widget.readPosition ?? _readDevicePosition)();
      if (!mounted) return;
      if (pos.accuracy > kMaxGpsAccuracyM) {
        setState(
          () => _gpsMessage =
              'دقّة الموقع ±${pos.accuracy.toStringAsFixed(0)} م أضعف من المطلوب '
              '(${kMaxGpsAccuracyM.toStringAsFixed(0)} م). انتظر قليلاً في مكانٍ '
              'مكشوف ثمّ أعد المحاولة.',
        );
        return;
      }
      c.addVertex(LatLng(pos.latitude, pos.longitude));
      setState(
        () => _gpsMessage =
            'سُجِّل الرأس ${c.vertices.length} (دقّة ±${pos.accuracy.toStringAsFixed(0)} م).',
      );
    } on _GpsFailure catch (e) {
      if (mounted) setState(() => _gpsMessage = e.messageAr);
    } catch (e) {
      if (mounted) setState(() => _gpsMessage = 'تعذّر قراءة الموقع: $e');
    } finally {
      if (mounted) setState(() => _gpsBusy = false);
    }
  }

  Future<void> _openImport() async {
    final text = TextEditingController();
    String? error;
    await showAppBottomSheet<void>(
      context,
      builder: (ctx) => StatefulBuilder(
        builder: (ctx, setSheet) => AppSheet(
          title: 'استيراد حدّ (GeoJSON أو KML)',
          errorText: error,
          submitLabel: 'تحميل الحدّ',
          onSubmit: () {
            try {
              final t = text.text.trim();
              final b = parseBoundaryText(t);
              c.loadRing(
                b.ring,
                source: t.startsWith('<') ? 'import_kml' : 'import_geojson',
              );
              Navigator.pop(ctx);
              if (b.notes.isNotEmpty && mounted) {
                showSnack(context, b.notes.join('\n'));
              }
            } on BoundaryImportException catch (e) {
              setSheet(() => error = e.messageAr);
            }
          },
          children: [
            const SizedBox(height: SahoolSpacing.sm),
            Align(
              alignment: AlignmentDirectional.centerEnd,
              child: TextButton.icon(
                onPressed: () async {
                  final d = await Clipboard.getData(Clipboard.kTextPlain);
                  if (d?.text != null) text.text = d!.text!;
                },
                icon: const Icon(Icons.content_paste),
                label: const Text('لصق من الحافظة'),
              ),
            ),
            AppTextField(
              label: 'المحتوى',
              controller: text,
              maxLines: 6,
              hint: '{"type":"Polygon","coordinates":[[[lon,lat],…]]}',
            ),
          ],
        ),
      ),
    );
    text.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final t = context.tokens;
    return ListenableBuilder(
      listenable: c,
      builder: (context, _) {
        final v = c.validation;
        return Column(
          children: [
            Padding(
              padding: const EdgeInsetsDirectional.fromSTEB(
                SahoolSpacing.md,
                SahoolSpacing.sm,
                SahoolSpacing.md,
                0,
              ),
              child: SegmentedButton<DrawMode>(
                key: const ValueKey('draw-mode'),
                showSelectedIcon: false,
                style: const ButtonStyle(
                  minimumSize: WidgetStatePropertyAll(
                    Size(0, SahoolSizes.minTouchTarget),
                  ),
                ),
                segments: const [
                  ButtonSegment(
                    value: DrawMode.polygon,
                    icon: Icon(Icons.polyline_outlined),
                    label: Text('مضلّع'),
                  ),
                  ButtonSegment(
                    value: DrawMode.rectangle,
                    icon: Icon(Icons.crop_square),
                    label: Text('مستطيل'),
                  ),
                  ButtonSegment(
                    value: DrawMode.circle,
                    icon: Icon(Icons.radio_button_unchecked),
                    label: Text('محور'),
                  ),
                ],
                selected: {c.mode},
                onSelectionChanged: (s) {
                  _radius.clear();
                  c.setMode(s.first);
                },
              ),
            ),
            Padding(
              padding: const EdgeInsetsDirectional.symmetric(
                horizontal: SahoolSpacing.lg,
                vertical: SahoolSpacing.xs,
              ),
              child: Text(
                _hint(c.mode),
                style: context.textStyles.bodySmall?.copyWith(color: t.muted),
              ),
            ),
            if (widget.note != null)
              Padding(
                padding: const EdgeInsetsDirectional.symmetric(
                  horizontal: SahoolSpacing.lg,
                ),
                child: Text(
                  widget.note!,
                  style: context.textStyles.bodySmall?.copyWith(
                    color: t.warning,
                  ),
                ),
              ),
            if (c.mode == DrawMode.circle) _radiusRow(context),
            Expanded(
              child: Stack(
                children: [
                  Positioned.fill(
                    child: DrawMap(
                      controller: c,
                      initialCenter: widget.initialCenter,
                      initialZoom: widget.initialZoom,
                      showBasemap: widget.showBasemap,
                    ),
                  ),
                  PositionedDirectional(
                    top: SahoolSpacing.sm,
                    end: SahoolSpacing.sm,
                    child: _toolPanel(context, _editTools()),
                  ),
                  PositionedDirectional(
                    top: SahoolSpacing.sm,
                    start: SahoolSpacing.sm,
                    child: _toolPanel(context, _sourceTools()),
                  ),
                ],
              ),
            ),
            if (_gpsMessage != null)
              Padding(
                padding: const EdgeInsetsDirectional.symmetric(
                  horizontal: SahoolSpacing.lg,
                ),
                child: Text(
                  _gpsMessage!,
                  style: context.textStyles.bodySmall?.copyWith(color: t.muted),
                ),
              ),
            BoundarySummary(
              validation: v,
              perimeterM: c.perimeter,
              compact: true,
            ),
          ],
        );
      },
    );
  }

  Widget _radiusRow(BuildContext context) {
    return Padding(
      padding: const EdgeInsetsDirectional.symmetric(
        horizontal: SahoolSpacing.md,
      ),
      child: Row(
        children: [
          Expanded(
            child: SingleChildScrollView(
              scrollDirection: Axis.horizontal,
              child: Row(
                children: [
                  for (final r in const [50.0, 100.0, 200.0, 300.0, 400.0])
                    Padding(
                      padding: const EdgeInsetsDirectional.only(
                        end: SahoolSpacing.xs,
                      ),
                      child: ChoiceChip(
                        key: ValueKey('radius-${r.toInt()}'),
                        label: Text('${r.toInt()} م'),
                        selected: c.radiusM == r,
                        onSelected: (_) => _applyRadius(r),
                      ),
                    ),
                ],
              ),
            ),
          ),
          SizedBox(
            width: 96,
            child: TextField(
              key: const ValueKey('radius-input'),
              controller: _radius,
              keyboardType: const TextInputType.numberWithOptions(
                decimal: true,
              ),
              inputFormatters: [LocalizedDigitsFormatter()],
              decoration: const InputDecoration(
                labelText: 'نصف القطر',
                suffixText: 'م',
              ),
              onSubmitted: (_) => _applyRadius(),
            ),
          ),
        ],
      ),
    );
  }

  Widget _toolPanel(BuildContext context, List<Widget> tools) => Material(
    color: Theme.of(context).colorScheme.surface.withValues(alpha: 0.92),
    borderRadius: SahoolRadius.mdAll,
    elevation: 2,
    child: Column(mainAxisSize: MainAxisSize.min, children: tools),
  );

  List<Widget> _editTools() {
    final sel = c.selectedVertex;
    return [
      AppIconButton(
        icon: Icons.undo,
        tooltip: 'تراجع',
        onPressed: c.canUndo ? c.undo : null,
      ),
      AppIconButton(
        icon: Icons.redo,
        tooltip: 'إعادة',
        onPressed: c.canRedo ? c.redo : null,
      ),
      AppIconButton(
        icon: Icons.remove_circle_outline,
        tooltip: 'حذف الرأس المحدَّد',
        onPressed: sel == null ? null : () => c.deleteVertex(sel),
      ),
      AppIconButton(
        icon: Icons.layers_clear_outlined,
        tooltip: 'مسح الحدّ',
        onPressed: c.ring.isEmpty && c.center == null && c.cornerA == null
            ? null
            : c.clear,
      ),
    ];
  }

  List<Widget> _sourceTools() => [
    AppIconButton(
      icon: c.snapEnabled ? Icons.link : Icons.link_off,
      tooltip: c.snapEnabled
          ? 'الالتقاط بحدود الحقول المجاورة: مفعَّل'
          : 'الالتقاط بحدود الحقول المجاورة: معطَّل',
      onPressed: () => setState(() => c.snapEnabled = !c.snapEnabled),
    ),
    AppIconButton(
      icon: Icons.my_location,
      tooltip: 'إضافة رأس من موقعي الحاليّ',
      onPressed: _gpsBusy ? null : _addGps,
    ),
    AppIconButton(
      icon: Icons.file_upload_outlined,
      tooltip: 'استيراد GeoJSON أو KML',
      onPressed: _openImport,
    ),
  ];
}

/// ملخّص الحدّ: المساحة التي سيخزّنها الخادم، المحيط، الرؤوس، ونتيجة التحقّق.
class BoundarySummary extends StatelessWidget {
  const BoundarySummary({
    super.key,
    required this.validation,
    required this.perimeterM,
    this.compact = false,
  });

  final BoundaryValidation validation;
  final double perimeterM;
  final bool compact;

  @override
  Widget build(BuildContext context) {
    final t = context.tokens;
    final v = validation;
    final hasRing = v.storedAreaHa != null;
    final issues = compact
        ? [...v.blocking.take(1), if (v.blocking.isEmpty) ...v.warnings.take(1)]
        : v.issues;
    return Padding(
      padding: const EdgeInsetsDirectional.all(SahoolSpacing.md),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text(
            hasRing
                ? 'المساحة كما سيحفظها الخادم: ${fmtAreaExact(v.storedAreaHa)}'
                : 'المساحة: لم يكتمل الحدّ بعد',
            key: const ValueKey('boundary-area'),
            style: context.textStyles.titleMedium,
          ),
          if (hasRing)
            Text(
              'المحيط ${fmtMeters(perimeterM)} · ${v.vertexCount - 1} رأساً',
              style: context.textStyles.bodyMedium?.copyWith(color: t.muted),
            ),
          for (final i in issues)
            Padding(
              padding: const EdgeInsets.only(top: SahoolSpacing.xs),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Icon(
                    i.blocking ? Icons.block : Icons.warning_amber_rounded,
                    color: i.blocking ? t.danger : t.warning,
                    size: SahoolSizes.iconSm,
                  ),
                  const SizedBox(width: SahoolSpacing.xs),
                  Expanded(
                    child: Text(
                      i.messageAr,
                      key: ValueKey('issue-${i.code}'),
                      style: context.textStyles.bodyMedium,
                    ),
                  ),
                ],
              ),
            ),
          if (compact && v.issues.length > issues.length)
            Text(
              '+${v.issues.length - issues.length} ملاحظات أخرى في المراجعة',
              style: context.textStyles.bodySmall?.copyWith(color: t.muted),
            ),
        ],
      ),
    );
  }
}
