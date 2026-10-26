// SAHOOL — features/maps/draw/draw_map.dart
// خريطة رسم الحدّ: صور الأقمار مع النسبة (شرط Esri)، الدوران مُعطَّل (كان إيماءة
// إصبعين تُميل الخريطة بلا بوصلة)، حدود الحقول القائمة، الحدّ الجاري، ومقابض
// تحرير بحجم ≥48dp (كانت 18px) — سحب الرأس، سحب المنتصف لإدراج رأس، ضغط مطوّل
// للحذف، ومقبضا المركز ونصف القطر للمحور.
//
// الكاميرا تتبع الحالة: حين يُستورَد حدّ أو يُسجَّل رأس GPS خارج الشاشة تُؤطِّره
// (كانت تبقى ثابتة على initialCenter فلا يرى المزارع ما سجّله).
//
// ملاحظة دمج: SahoolMap (حزمة الخرائط W2-07) لم تكن في هذه الشجرة؛ هذه الخريطة
// مكتفية بذاتها، وتُستبدَل قاعدتها بـSahoolMap بعد الدمج دون مسّ المتحكّم.
import 'dart:math' as math;

import 'package:flutter/gestures.dart';
import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:latlong2/latlong.dart';
import 'package:sahool_app/core/theme/sahool_tokens.dart';
import 'package:sahool_app/core/theme/tokens.dart';

import 'draw_controller.dart';
import 'geo_measure.dart';

const String kEsriImageryUrl =
    'https://server.arcgisonline.com/ArcGIS/rest/services/'
    'World_Imagery/MapServer/tile/{z}/{y}/{x}';

/// حجم منطقة لمس المقبض (≥ الحدّ الأدنى 48dp في رموز التصميم).
const double kHandleHitSize = SahoolSizes.minTouchTarget;

class DrawMap extends StatefulWidget {
  const DrawMap({
    super.key,
    required this.controller,
    required this.initialCenter,
    this.initialZoom = 16,
    this.snapPixels = 24,
    this.showBasemap = true,
  });

  final DrawController controller;
  final LatLng initialCenter;
  final double initialZoom;

  /// تسامح الالتقاط بالبكسل (يُحوَّل إلى أمتار بحسب التكبير).
  final double snapPixels;

  /// false في الاختبارات (لا طلبات بلاطات شبكيّة).
  final bool showBasemap;

  @override
  State<DrawMap> createState() => _DrawMapState();
}

class _DrawMapState extends State<DrawMap> {
  final MapController _map = MapController();
  int _seenFit = 0;
  int _seenCount = 0;
  bool _ready = false;

  @override
  void initState() {
    super.initState();
    _seenFit = widget.controller.fitRequest;
    widget.controller.addListener(_onChange);
  }

  @override
  void didUpdateWidget(DrawMap old) {
    super.didUpdateWidget(old);
    if (old.controller != widget.controller) {
      old.controller.removeListener(_onChange);
      widget.controller.addListener(_onChange);
    }
  }

  @override
  void dispose() {
    widget.controller.removeListener(_onChange);
    _map.dispose();
    super.dispose();
  }

  void _onChange() {
    final c = widget.controller;
    if (_ready && c.fitRequest != _seenFit) {
      _seenFit = c.fitRequest;
      _fitTo(c.ring);
    }
  }

  void _fitTo(List<LatLng> pts) {
    if (pts.isEmpty) return;
    if (pts.length == 1) {
      _map.move(pts.first, math.max(_map.camera.zoom, 17));
      return;
    }
    _map.fitCamera(
      CameraFit.bounds(
        bounds: LatLngBounds.fromPoints(pts),
        padding: const EdgeInsets.all(SahoolSpacing.xxl),
        maxZoom: 18,
      ),
    );
  }

  /// بعد إضافة رأس (GPS خصوصاً) يُبقيه ظاهراً؛ لا يتحرّك عند سحب رأسٍ قائم.
  void _followLast() {
    final r = widget.controller.editableVertices;
    final grew = r.length > _seenCount;
    _seenCount = r.length;
    if (!_ready || r.isEmpty || !grew) return;
    final last = r.last;
    if (!_map.camera.visibleBounds.contains(last)) {
      _map.move(last, _map.camera.zoom);
    }
  }

  double _snapToleranceM() {
    if (!_ready) return 0;
    final cam = _map.camera;
    return metersPerPixel(cam.center.latitude, cam.zoom) * widget.snapPixels;
  }

  @override
  Widget build(BuildContext context) {
    final c = widget.controller;
    final scheme = Theme.of(context).colorScheme;
    final t = context.tokens;
    return ListenableBuilder(
      listenable: c,
      builder: (context, _) {
        WidgetsBinding.instance.addPostFrameCallback((_) {
          if (mounted) _followLast();
        });
        final ring = c.ring;
        return FlutterMap(
          mapController: _map,
          options: MapOptions(
            initialCenter: widget.initialCenter,
            initialZoom: widget.initialZoom,
            maxZoom: 19,
            backgroundColor: t.surfaceAlt,
            interactionOptions: const InteractionOptions(
              flags: InteractiveFlag.all & ~InteractiveFlag.rotate,
            ),
            onMapReady: () {
              _ready = true;
              if (c.ring.isNotEmpty) _fitTo(c.ring);
            },
            onTap: (_, ll) => c.tap(ll, snapToleranceM: _snapToleranceM()),
          ),
          children: [
            if (widget.showBasemap)
              TileLayer(
                urlTemplate: kEsriImageryUrl,
                userAgentPackageName: 'ye.sahool.app',
                maxNativeZoom: 19,
              ),
            PolygonLayer(
              polygons: [
                for (final f in c.existingFields)
                  for (final r in f.rings)
                    Polygon(
                      points: r,
                      color: t.info.withValues(alpha: 0.12),
                      borderColor: t.info,
                      borderStrokeWidth: 2,
                    ),
                if (ring.length >= 3)
                  Polygon(
                    points: ring,
                    color: (c.validation.canSave ? scheme.primary : t.danger)
                        .withValues(alpha: 0.25),
                    borderColor: c.validation.canSave
                        ? scheme.primary
                        : t.danger,
                    borderStrokeWidth: 3,
                  ),
              ],
            ),
            if (ring.length == 2)
              PolylineLayer(
                polylines: [
                  Polyline(points: ring, color: scheme.primary, strokeWidth: 3),
                ],
              ),
            DrawHandlesLayer(controller: c, snapToleranceM: _snapToleranceM),
            if (widget.showBasemap)
              RichAttributionWidget(
                alignment: AttributionAlignment.bottomLeft,
                attributions: const [
                  TextSourceAttribution(
                    'Esri, Maxar, Earthstar Geographics, GIS User Community',
                  ),
                ],
              ),
          ],
        );
      },
    );
  }
}

/// طبقة المقابض. تقرأ الكاميرا من FlutterMap وتحوّل مواقع الإصبع إلى إحداثيّات.
class DrawHandlesLayer extends StatefulWidget {
  const DrawHandlesLayer({
    super.key,
    required this.controller,
    required this.snapToleranceM,
  });

  final DrawController controller;
  final double Function() snapToleranceM;

  @override
  State<DrawHandlesLayer> createState() => _DrawHandlesLayerState();
}

class _DrawHandlesLayerState extends State<DrawHandlesLayer> {
  final GlobalKey _stackKey = GlobalKey();
  int? _dragIndex;

  LatLng? _toLatLng(MapCamera cam, Offset global) {
    final box = _stackKey.currentContext?.findRenderObject() as RenderBox?;
    if (box == null) return null;
    final local = box.globalToLocal(global);
    return cam.pointToLatLng(math.Point(local.dx, local.dy));
  }

  Widget _handle({
    required Key key,
    required MapCamera cam,
    required LatLng at,
    required Widget visual,
    required String semantics,
    VoidCallback? onTap,
    VoidCallback? onLongPress,
    void Function(Offset global)? onDragStart,
    void Function(Offset global)? onDragUpdate,
    VoidCallback? onDragEnd,
    double size = kHandleHitSize,
  }) {
    final p = cam.latLngToScreenPoint(at);
    return Positioned(
      left: p.x - size / 2,
      top: p.y - size / 2,
      width: size,
      height: size,
      child: Semantics(
        label: semantics,
        button: true,
        // مسافة بدء سحب صغيرة كي يفوز المقبض بالإيماءة قبل سحب الخريطة
        // (HorizontalDrag في flutter_map يقبل عند 18 بكسل، وPan عند 36).
        child: MediaQuery(
          data: MediaQuery.of(context).copyWith(
            gestureSettings: const DeviceGestureSettings(touchSlop: 4),
          ),
          child: GestureDetector(
            key: key,
            behavior: HitTestBehavior.opaque,
            onTap: onTap,
            onLongPress: onLongPress,
            onPanStart: onDragStart == null
                ? null
                : (d) => onDragStart(d.globalPosition),
            onPanUpdate: onDragUpdate == null
                ? null
                : (d) => onDragUpdate(d.globalPosition),
            onPanEnd: onDragEnd == null ? null : (_) => onDragEnd(),
            child: Center(child: visual),
          ),
        ),
      ),
    );
  }

  Widget _dot(Color fill, Color border, double d) => Container(
    width: d,
    height: d,
    decoration: BoxDecoration(
      color: fill,
      shape: BoxShape.circle,
      border: Border.all(color: border, width: 3),
    ),
  );

  @override
  Widget build(BuildContext context) {
    final cam = MapCamera.of(context);
    final c = widget.controller;
    final scheme = Theme.of(context).colorScheme;
    final t = context.tokens;
    final handles = <Widget>[];

    final verts = c.editableVertices;
    final mids = c.midpoints;
    for (var i = 0; i < mids.length; i++) {
      handles.add(
        _handle(
          key: ValueKey('draw-mid-$i'),
          cam: cam,
          at: mids[i],
          semantics: 'إدراج رأس بين الرأسين ${i + 1} و${i + 2}',
          visual: _dot(
            scheme.surface.withValues(alpha: 0.85),
            scheme.primary,
            16,
          ),
          onTap: () => c.insertVertex(i, mids[i]),
          onDragStart: (g) {
            final ll = _toLatLng(cam, g) ?? mids[i];
            _dragIndex = c.beginInsertAt(i, ll);
          },
          onDragUpdate: (g) {
            final ll = _toLatLng(MapCamera.of(context), g);
            if (ll != null && _dragIndex != null) {
              c.updateVertex(
                _dragIndex!,
                ll,
                snapToleranceM: widget.snapToleranceM(),
              );
            }
          },
          onDragEnd: () {
            _dragIndex = null;
            c.endEdit();
          },
        ),
      );
    }
    for (var i = 0; i < verts.length; i++) {
      final selected = c.selectedVertex == i;
      handles.add(
        _handle(
          key: ValueKey('draw-vertex-$i'),
          cam: cam,
          at: verts[i],
          semantics: 'الرأس ${i + 1}: اسحب للتحريك، اضغط مطوّلاً للحذف',
          visual: _dot(
            selected ? t.warning : scheme.primary,
            scheme.surface,
            selected ? 28 : 24,
          ),
          onTap: () => c.selectVertex(selected ? null : i),
          onLongPress: () => c.deleteVertex(i),
          onDragStart: (_) => c.beginEdit(),
          onDragUpdate: (g) {
            final ll = _toLatLng(MapCamera.of(context), g);
            if (ll != null) {
              c.updateVertex(i, ll, snapToleranceM: widget.snapToleranceM());
            }
          },
          onDragEnd: c.endEdit,
        ),
      );
    }
    if (c.mode == DrawMode.rectangle &&
        c.cornerA != null &&
        c.cornerB == null) {
      handles.add(
        _handle(
          key: const ValueKey('draw-corner-a'),
          cam: cam,
          at: c.cornerA!,
          semantics: 'الزاوية الأولى للمستطيل',
          visual: _dot(scheme.primary, scheme.surface, 24),
        ),
      );
    }
    final center = c.center;
    if (c.mode == DrawMode.circle && center != null) {
      handles.add(
        _handle(
          key: const ValueKey('draw-center'),
          cam: cam,
          at: center,
          semantics: 'مركز المحور: اسحب للتحريك',
          visual: _dot(scheme.primary, scheme.surface, 26),
          onDragStart: (_) => c.beginEdit(),
          onDragUpdate: (g) {
            final ll = _toLatLng(MapCamera.of(context), g);
            if (ll != null) c.updateCenter(ll);
          },
          onDragEnd: c.endEdit,
        ),
      );
      final r = c.radiusM;
      if (r != null && r > 0) {
        handles.add(
          _handle(
            key: const ValueKey('draw-radius'),
            cam: cam,
            at: destinationPoint(center, r, math.pi / 2),
            semantics: 'نصف القطر: اسحب للتكبير أو التصغير',
            visual: _dot(scheme.surface, scheme.primary, 22),
            onDragStart: (_) => c.beginEdit(),
            onDragUpdate: (g) {
              final ll = _toLatLng(MapCamera.of(context), g);
              if (ll != null) c.updateRadiusFrom(ll);
            },
            onDragEnd: c.endEdit,
          ),
        );
      }
    }
    final pt = c.point;
    if (c.mode == DrawMode.point && pt != null) {
      handles.add(
        _handle(
          key: const ValueKey('draw-point'),
          cam: cam,
          at: pt,
          semantics: 'النقطة المحدَّدة',
          visual: Icon(Icons.place, color: scheme.primary, size: 36),
        ),
      );
    }

    return Stack(key: _stackKey, fit: StackFit.expand, children: handles);
  }
}
