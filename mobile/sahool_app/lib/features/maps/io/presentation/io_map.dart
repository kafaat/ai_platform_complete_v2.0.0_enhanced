// SAHOOL — features/maps/io/presentation/io_map.dart
// خريطة معاينة صغيرة لحزمة io/: صور Esri مع الإسناد الذي تفرضه شروطها، تدوير
// مُعطَّل (لا تميل الخريطة بإصبعين أثناء العمل)، والكاميرا تلاحق المدخلات (تُلائم
// الحدود حين تتغيّر، أو تتبع «أنت هنا» أثناء المشي).
//
// للدمج لاحقاً: SahoolMap في core/ (W2-07) يحلّ محلّها عند الدمج.
import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:latlong2/latlong.dart';
import 'package:sahool_app/core/theme/tokens.dart';

import '../geo/io_geometry.dart';

/// مضلّع معروض مع نمطه.
class IoMapShape {
  const IoMapShape(this.polygon, {this.selected = true, this.label});
  final IoPolygon polygon;
  final bool selected;
  final String? label;
}

class IoMap extends StatefulWidget {
  const IoMap({
    super.key,
    this.shapes = const [],
    this.lines = const [],
    this.dashedClosure,
    this.points = const [],
    this.here,
    this.hereAccuracyM,
    this.follow = false,
    this.onTap,
    this.showBasemap = true,
    this.fallbackCenter = const LatLng(15.35, 44.2), // صنعاء — لا حقل افتراضيّ
  });

  final List<IoMapShape> shapes;

  /// خطوط مفتوحة (مسار المشي، خطّ القطع).
  final List<List<LatLng>> lines;

  /// خطّ إغلاق متقطّع (من آخر نقطة إلى الأولى) أثناء المشي.
  final List<LatLng>? dashedClosure;

  /// رؤوس تُعلَّم بنقاط (خطّ القطع).
  final List<LatLng> points;

  /// الموقع الحاليّ ودائرة دقّته.
  final LatLng? here;
  final double? hereAccuracyM;

  /// true ⇒ الكاميرا تتبع [here]؛ وإلّا تُلائم حدود المحتوى.
  final bool follow;
  final ValueChanged<LatLng>? onTap;

  /// false في الاختبارات (لا شبكة).
  final bool showBasemap;
  final LatLng fallbackCenter;

  @override
  State<IoMap> createState() => _IoMapState();
}

class _IoMapState extends State<IoMap> {
  final _controller = MapController();
  bool _ready = false;

  Iterable<LatLng> get _content sync* {
    for (final s in widget.shapes) {
      yield* s.polygon.outer;
    }
    for (final l in widget.lines) {
      yield* l;
    }
    yield* widget.points;
  }

  IoBounds? _bounds() => IoBounds.of(_content);

  CameraFit? _fit() {
    final b = _bounds();
    if (b == null) return null;
    if (b.north == b.south && b.east == b.west) return null;
    return CameraFit.bounds(
      bounds: LatLngBounds(LatLng(b.south, b.west), LatLng(b.north, b.east)),
      padding: const EdgeInsets.all(SahoolSpacing.xl),
      maxZoom: 19,
    );
  }

  void _sync() {
    if (!_ready) return;
    if (widget.follow && widget.here != null) {
      final zoom = _controller.camera.zoom < 16
          ? 18.0
          : _controller.camera.zoom;
      _controller.move(widget.here!, zoom);
      return;
    }
    final fit = _fit();
    if (fit != null) _controller.fitCamera(fit);
  }

  @override
  void didUpdateWidget(IoMap old) {
    super.didUpdateWidget(old);
    final b0 = IoBounds.of([
      for (final s in old.shapes) ...s.polygon.outer,
      for (final l in old.lines) ...l,
      ...old.points,
    ]);
    final b1 = _bounds();
    final boundsChanged =
        b0?.south != b1?.south ||
        b0?.north != b1?.north ||
        b0?.west != b1?.west ||
        b0?.east != b1?.east;
    final hereChanged = widget.follow && widget.here != old.here;
    if (boundsChanged && !widget.follow || hereChanged) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted) _sync();
      });
    }
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final fit = _fit();
    final center =
        widget.here ??
        (_content.isNotEmpty ? _content.first : widget.fallbackCenter);
    return FlutterMap(
      mapController: _controller,
      options: MapOptions(
        initialCenter: center,
        initialZoom: fit == null && widget.here == null ? 13 : 17,
        initialCameraFit: widget.follow ? null : fit,
        maxZoom: 19,
        interactionOptions: const InteractionOptions(
          flags: InteractiveFlag.all & ~InteractiveFlag.rotate,
        ),
        onMapReady: () {
          _ready = true;
        },
        onTap: widget.onTap == null ? null : (_, p) => widget.onTap!(p),
      ),
      children: [
        if (widget.showBasemap)
          TileLayer(
            urlTemplate:
                'https://server.arcgisonline.com/ArcGIS/rest/services/'
                'World_Imagery/MapServer/tile/{z}/{y}/{x}',
            userAgentPackageName: 'ye.sahool.app',
            maxNativeZoom: 19,
          ),
        PolygonLayer(
          polygons: [
            for (final s in widget.shapes)
              Polygon(
                points: s.polygon.outer,
                holePointsList: s.polygon.holes.isEmpty
                    ? null
                    : s.polygon.holes,
                color: (s.selected ? scheme.primary : scheme.outline)
                    .withValues(alpha: s.selected ? 0.30 : 0.12),
                borderColor: s.selected ? scheme.primary : scheme.outline,
                borderStrokeWidth: s.selected ? 3 : 1.5,
                label: s.label,
                labelStyle: TextStyle(
                  color: scheme.onSurface,
                  fontWeight: SahoolType.semibold,
                  fontSize: SahoolType.caption,
                ),
              ),
          ],
        ),
        PolylineLayer(
          polylines: [
            for (final l in widget.lines)
              Polyline(points: l, color: scheme.tertiary, strokeWidth: 4),
            if (widget.dashedClosure != null)
              Polyline(
                points: widget.dashedClosure!,
                color: scheme.tertiary.withValues(alpha: 0.7),
                strokeWidth: 2,
                pattern: StrokePattern.dashed(segments: const [8, 6]),
              ),
          ],
        ),
        CircleLayer(
          circles: [
            if (widget.here != null && (widget.hereAccuracyM ?? 0) > 0)
              CircleMarker(
                point: widget.here!,
                radius: widget.hereAccuracyM!,
                useRadiusInMeter: true,
                color: scheme.secondary.withValues(alpha: 0.18),
                borderColor: scheme.secondary,
                borderStrokeWidth: 1,
              ),
            for (final p in widget.points)
              CircleMarker(
                point: p,
                radius: 7,
                color: scheme.tertiary,
                borderColor: scheme.surface,
                borderStrokeWidth: 2,
              ),
            if (widget.here != null)
              CircleMarker(
                point: widget.here!,
                radius: 8,
                color: scheme.secondary,
                borderColor: scheme.surface,
                borderStrokeWidth: 3,
              ),
          ],
        ),
        if (widget.showBasemap)
          RichAttributionWidget(
            showFlutterMapAttribution: false,
            attributions: [TextSourceAttribution('Esri — World Imagery')],
          ),
      ],
    );
  }
}
