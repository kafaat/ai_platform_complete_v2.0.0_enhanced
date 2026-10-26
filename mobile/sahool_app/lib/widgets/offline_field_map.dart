// offline_field_map.dart — خريطة حقل تعمل offline (سدّ فجوة اليمن ضعيف الشبكة).
//
// الممارسة العالميّة للحقول منخفضة الاتّصال: حزمة بلاطات MBTiles (SQLite)
// على الجهاز كأساس offline، مع بلاطات الشبكة كـfallback عند توفّرها.
// هذا يضمن أنّ المزارع في منطقة بلا تغطيّة لا يفقد الخريطة كاملةً.
//
// ودجت توافق: الخريطة الكاملة الجديدة هي SahoolMap
// (lib/features/maps/presentation/widgets/sahool_map.dart). هذا الملفّ يبقى بمساره
// لأنّ بوّابات CI (mobile_contract_gate.py، test_roadmap_phase23.py) تقرؤه، ولأنّ
// شاشة الحقول ومعالج الإنشاء ما زالا يستعملانه. إصلاحات هذه النسخة:
//   • نسبة المصادر ظاهرة (كانت صور Esri تُعرض بلا نسبة).
//   • الكاميرا تتبع center/zoom/bounds عند تغيّرها (MapController؛ كانت ثابتة على
//     القيمة الأولى فتبقى نقاط GPS خارج الشاشة).
//   • التدوير معطّل (كانت إيماءة بإصبعين تميل الخريطة بلا بوصلة ولا رجعة).
//   • الحزمة تُعاد قراءتها حين يتغيّر مسارها، ولا setState بعد الإزالة، وتُغلق.
//   • الشارات بمواضع اتّجاهيّة (RTL) وتلميح محدود العرض.
//   • طبقة الطقس لا ترسم قيماً افتراضيّة مُختلَقة (كانت 30°م ورياح 315°).
//   • الدائرة جيوديسيّة على كرة الخادم (كان 111320 م/درجة ⇒ 399.55 م لنصف قطر 400).
//
// الاستخدام (عرض فقط — الافتراضيّ، يبقى متوافقاً مع المستدعين القدامى):
//   OfflineFieldMap(
//     center: LatLng(16.79, 44.33),   // الجوف
//     offlinePackFilePath: '/data/user/0/ye.sahool.app/files/maps/aljawf.mbtiles',  // اختياري
//     fieldPolygons: [...],
//   )
//
// الاستخدام (وضع الرسم — لمعالج إنشاء الحقل): فعّل drawingEnabled واستقبل
// تغيّر المضلّع عبر onPolygonChanged. النقر على الخريطة يضيف رأساً؛ التحكّم
// (تراجع/مسح) يبقى مسؤوليّة الشاشة المضيفة عبر إعادة بناء drawingPoints.
// العرض-فقط لا يتأثّر: كلّ معطيات الرسم اختياريّة بقيم افتراضيّة.
//
// أدوات الرسم (مستوحاة من Climate FieldView، إضافيّة غير كاسرة):
//   • وضع النقاط (drawMode == DrawMode.points): السلوك القديم — نقرة = رأس.
//   • وضع الدائرة (drawMode == DrawMode.circle): النقرة تحدّد مركزاً وتُبلّغ
//     الشاشة المضيفة عبر onCenterTap كي تطلب نصف القطر بالأمتار (م) وتُولّد
//     مضلّعاً دائريّاً (حقل محوريّ/center-pivot). وحدة الطول دائماً الأمتار.

import 'dart:math' as math;
import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:flutter_map_mbtiles/flutter_map_mbtiles.dart';
import 'package:flutter_map_pmtiles/flutter_map_pmtiles.dart';
import 'package:latlong2/latlong.dart';
import 'package:sahool_app/core/theme/sahool_tokens.dart';
import 'package:sahool_app/core/theme/tokens.dart';
import 'package:sahool_app/features/maps/data/basemaps.dart';
import 'package:sahool_app/features/maps/data/offline_tiles.dart';
import 'package:sahool_app/features/maps/geo/geo_measure.dart';
import 'package:sahool_app/features/maps/presentation/widgets/map_attribution.dart';

// نوع حزمة offline: PMTiles (مفضّل — ملفّ واحد، HTTP-range، hybrid) أو
// MBTiles (SQLite، ناضج). PMTiles أقرب لاتّجاه geospatial-first.
enum OfflinePackType { pmtiles, mbtiles, none }

// وضع الرسم على الخريطة: نقاط (مضلّع بالنقر) أو دائرة (مركز + نصف قطر بالأمتار).
enum DrawMode { points, circle }

class OfflineFieldMap extends StatefulWidget {
  final LatLng center;
  final double zoom;
  // مسار حزمة offline على filesystem الجهاز (إن وُجدت). الامتداد يحدّد النوع.
  // لا تقبل assets مباشرةً؛ انقل asset أولاً إلى documents directory ثم مرّر مساره.
  final String? offlinePackFilePath;
  // Deprecated alias kept for source compatibility with older callers. Prefer
  // offlinePackFilePath because this value is resolved with File(path).exists().
  final String? offlinePackPath;
  // رابط بلاطات الشبكة (fallback عند توفّر اتّصال).
  final String networkTileUrl;
  final List<Polygon> fieldPolygons;
  // إطار اختياريّ لتأطير حقل المستخدم (fitBounds): إن وُجد، تُؤطِّر الخريطة حقله
  // بدل مركز/تكبير ثابتين — ويُعاد التأطير كلّما تغيّر الإطار.
  final LatLngBounds? bounds;

  // ── وضع الرسم (اختياريّ — لمعالج إنشاء الحقل) ──
  final bool drawingEnabled;
  // النقاط الحاليّة للمضلّع الجاري رسمه (مصدر الحقيقة تملكه الشاشة المضيفة).
  final List<LatLng> drawingPoints;
  // يُستدعى بعد كلّ إضافة رأس بالنقر — يردّ القائمة المُحدَّثة (بما فيها الرأس الجديد).
  final ValueChanged<List<LatLng>>? onPolygonChanged;

  // وضع الرسم: نقاط (الافتراضيّ، متوافق مع القديم) أو دائرة (مركز + نصف قطر بالأمتار).
  final DrawMode drawMode;
  // في وضع الدائرة: تُستدعى عند النقر لتحديد المركز — تتولّى الشاشة طلب نصف القطر.
  final ValueChanged<LatLng>? onCenterTap;
  // معاينة الدائرة (اختياريّة): مركز + نصف قطر بالأمتار تُرسَم كحلقة شفّافة.
  final LatLng? circlePreviewCenter;
  final double? circlePreviewRadiusMeters;
  // نصّ تعليمات يُعرَض كشريط أعلى الخريطة (إن وُجد) في وضع الرسم.
  final String? instruction;

  // طبقة طقس/رياح اختيارية فوق الخريطة، شبيهة بأسلوب Windy:
  // تظليل حراري/رطوبي + خطوط اتجاه الرياح. تُرسم فوق البلاطات والحقول ولا تلتقط اللمس.
  // صدق: ما لم يُقَس لا يُرسَم (لا قيم افتراضيّة).
  final bool showWeatherOverlay;
  final double? weatherTempC;
  final double? weatherHumidityPct;
  final double? windSpeedKmh;
  final double? windDirectionDeg;
  final double weatherOverlayOpacity;

  const OfflineFieldMap({
    super.key,
    required this.center,
    this.zoom = 13,
    this.offlinePackFilePath,
    this.offlinePackPath,
    this.networkTileUrl =
        'https://server.arcgisonline.com/ArcGIS/rest/services/'
        'World_Imagery/MapServer/tile/{z}/{y}/{x}',
    this.fieldPolygons = const [],
    this.bounds,
    this.drawingEnabled = false,
    this.drawingPoints = const [],
    this.onPolygonChanged,
    this.drawMode = DrawMode.points,
    this.onCenterTap,
    this.circlePreviewCenter,
    this.circlePreviewRadiusMeters,
    this.instruction,
    this.showWeatherOverlay = false,
    this.weatherTempC,
    this.weatherHumidityPct,
    this.windSpeedKmh,
    this.windDirectionDeg,
    this.weatherOverlayOpacity = 0.72,
  });

  // مضلّع دائريّ ([segments] رأساً، عكس عقارب الساعة بدءاً من الشرق) حول مركز بنصف
  // قطر بالأمتار — تستعمله الشاشة المضيفة لإنتاج حدّ الحقل وتُعيد استعماله المعاينة.
  // كلّ رأس على بعد [radiusMeters] تماماً على كرة الخادم (R = 6371008.8 م).
  static List<LatLng> circlePolygon(
    LatLng center,
    double radiusMeters, {
    int segments = 48,
  }) {
    if (radiusMeters <= 0 || segments < 3) return const [];
    return [
      for (var i = 0; i < segments; i++)
        destinationPoint(center, radiusMeters, 90.0 - 360.0 * i / segments),
    ];
  }

  @override
  State<OfflineFieldMap> createState() => _OfflineFieldMapState();
}

class _WeatherWindOverlayPainter extends CustomPainter {
  final double? tempC;
  final double? humidityPct;
  final double? windSpeedKmh;
  final double? windDirectionDeg;
  final double opacity;
  final Color hot;
  final Color warm;
  final Color humid;
  final Color mild;
  final Color stroke;

  const _WeatherWindOverlayPainter({
    this.tempC,
    this.humidityPct,
    this.windSpeedKmh,
    this.windDirectionDeg,
    required this.opacity,
    required this.hot,
    required this.warm,
    required this.humid,
    required this.mild,
    required this.stroke,
  });

  // null ⇒ لا تظليل (لا حرارة/رطوبة مُختلَقة).
  Color? _heatColor() {
    final t = tempC;
    final h = humidityPct;
    if (t == null && h == null) return null;
    if (t != null && t >= 38) return hot.withValues(alpha: 0.34 * opacity);
    if (t != null && t >= 32) return warm.withValues(alpha: 0.30 * opacity);
    if (h != null && h >= 75) return humid.withValues(alpha: 0.24 * opacity);
    return mild.withValues(alpha: 0.22 * opacity);
  }

  @override
  void paint(Canvas canvas, Size size) {
    final heat = _heatColor();
    if (heat != null) {
      canvas.drawRect(Offset.zero & size, Paint()..color = heat);
    }
    final dirDeg = windDirectionDeg;
    if (dirDeg == null) return; // اتّجاه غير مقيس ⇒ لا خطوط رياح
    final dir = dirDeg * math.pi / 180.0;
    final speed = windSpeedKmh;
    final width = speed == null
        ? 1.4
        : (1.4 + speed / 18.0).clamp(1.4, 5.0).toDouble();
    final paint = Paint()
      ..color = stroke.withValues(alpha: 0.62 * opacity)
      ..strokeWidth = width
      ..strokeCap = StrokeCap.round
      ..style = PaintingStyle.stroke;
    final spacingY = size.height / 9;
    final spacingX = size.width / 5;
    canvas.save();
    canvas.translate(size.width / 2, size.height / 2);
    canvas.rotate(dir);
    canvas.translate(-size.width / 2, -size.height / 2);
    for (double y = -spacingY; y < size.height + spacingY; y += spacingY) {
      for (double x = -spacingX; x < size.width + spacingX; x += spacingX) {
        final path = ui.Path()
          ..moveTo(x, y)
          ..cubicTo(x + 28, y - 5, x + 54, y + 10, x + 92, y - 2);
        canvas.drawPath(path, paint);
      }
    }
    canvas.restore();
  }

  @override
  bool shouldRepaint(covariant _WeatherWindOverlayPainter oldDelegate) {
    return oldDelegate.tempC != tempC ||
        oldDelegate.humidityPct != humidityPct ||
        oldDelegate.windSpeedKmh != windSpeedKmh ||
        oldDelegate.windDirectionDeg != windDirectionDeg ||
        oldDelegate.opacity != opacity ||
        oldDelegate.stroke != stroke;
  }
}

class _OfflineFieldMapState extends State<OfflineFieldMap> {
  final MapController _mapController = MapController();
  bool _mapReady = false;
  OpenedOfflinePack? _pack;
  OfflinePackType _packType = OfflinePackType.none;
  String _source = 'network';
  int _packGeneration = 0;

  @override
  void initState() {
    super.initState();
    _initOffline();
  }

  @override
  void didUpdateWidget(OfflineFieldMap oldWidget) {
    super.didUpdateWidget(oldWidget);
    final oldPath = oldWidget.offlinePackFilePath ?? oldWidget.offlinePackPath;
    final newPath = widget.offlinePackFilePath ?? widget.offlinePackPath;
    if (oldPath != newPath) _initOffline();
    // الكاميرا تتبع الحالة: إطار جديد ⇒ أطّر؛ مركز/تكبير جديد ⇒ انتقل.
    if (!_mapReady) return;
    final b = widget.bounds;
    if (b != null && b != oldWidget.bounds) {
      _fit(b);
    } else if (b == null &&
        (widget.center != oldWidget.center || widget.zoom != oldWidget.zoom)) {
      _mapController.move(widget.center, widget.zoom);
    }
  }

  void _fit(LatLngBounds b) {
    if (b.south == b.north && b.east == b.west) {
      _mapController.move(b.center, math.max(widget.zoom, 15));
      return;
    }
    _mapController.fitCamera(
      CameraFit.bounds(bounds: b, padding: const EdgeInsets.all(40)),
    );
  }

  Future<void> _initOffline() async {
    final gen = ++_packGeneration;
    final old = _pack;
    final path = widget.offlinePackFilePath ?? widget.offlinePackPath;
    if (path == null) {
      if (old != null) {
        setState(_resetToNetwork);
        await old.dispose();
      }
      return;
    }
    // فتح الحزمة (يتحقّق من وجود الملفّ ويرفض الحزم المتّجهة) — fail-safe:
    // أيّ فشل ⇒ نبقى على الشبكة، لا تعطّل الخريطة.
    final result = await openOfflinePack(path);
    if (!mounted || gen != _packGeneration) {
      await result.pack?.dispose();
      return;
    }
    final pack = result.pack;
    setState(() {
      _pack = pack;
      if (pack == null) {
        _resetToNetwork();
      } else if (pack.format == OfflinePackFormat.pmtiles) {
        // PMTiles: ملفّ واحد cloud-optimized (مفضّل). يعمل offline + online.
        _packType = OfflinePackType.pmtiles;
        _source = 'offline-pmtiles';
      } else {
        // MBTiles: SQLite (ناضج، fallback).
        _packType = OfflinePackType.mbtiles;
        _source = 'offline-mbtiles';
      }
    });
    if (old != null && !identical(old, pack)) await old.dispose();
  }

  void _resetToNetwork() {
    _pack = null;
    _packType = OfflinePackType.none;
    _source = 'network';
  }

  @override
  void dispose() {
    _packGeneration++;
    _pack?.dispose();
    _mapController.dispose();
    super.dispose();
  }

  // طبقة الأساس: الشبكة دائماً (fallback لما خارج الحزمة)، وفوقها الحزمة إن فُتحت.
  // أولويّة: PMTiles → MBTiles → الشبكة.
  // مزوّد واحد يُحفظ عبر عمليّات البناء (مزوّد جديد في كلّ بناء يسرّب عميل HTTP)،
  // ويُسكت فشل البلاطات: بلا شبكة تظهر بلاطة شفّافة لا سيل استثناءات.
  late final NetworkTileProvider _networkTiles = NetworkTileProvider(
    silenceExceptions: true,
  );

  TileLayer _networkLayer() => TileLayer(
    urlTemplate: widget.networkTileUrl,
    userAgentPackageName: 'ye.sahool.app',
    tileProvider: _networkTiles,
  );

  TileLayer? _baseLayer() {
    final provider = _pack?.tileProvider;
    if (_packType == OfflinePackType.pmtiles &&
        provider is PmTilesTileProvider) {
      return TileLayer(tileProvider: provider, tileBounds: _pack!.bounds);
    }
    if (_packType == OfflinePackType.mbtiles &&
        provider is MbTilesTileProvider) {
      return TileLayer(tileProvider: provider, tileBounds: _pack!.bounds);
    }
    return null;
  }

  // النقر على الخريطة في وضع الرسم.
  // وضع النقاط: يضيف رأساً ويبلّغ onPolygonChanged (السلوك القديم).
  // وضع الدائرة: يبلّغ onCenterTap بالمركز (تتولّى الشاشة طلب نصف القطر بالأمتار).
  void _onMapTap(TapPosition _, LatLng latlng) {
    if (!widget.drawingEnabled) return;
    if (widget.drawMode == DrawMode.circle) {
      widget.onCenterTap?.call(latlng);
      return;
    }
    final updated = [...widget.drawingPoints, latlng];
    widget.onPolygonChanged?.call(updated);
  }

  // معاينة الدائرة: حلقة + مركز مميّز (وضع الدائرة فقط، عند توفّر مركز ونصف قطر).
  List<Widget> _circlePreviewLayers(Color draw, Color accent, Color surface) {
    final center = widget.circlePreviewCenter;
    final r = widget.circlePreviewRadiusMeters;
    if (center == null || r == null || r <= 0) return const [];
    final ring = OfflineFieldMap.circlePolygon(center, r);
    if (ring.length < 3) return const [];
    return [
      PolygonLayer(
        polygons: [
          Polygon(
            points: ring,
            color: draw.withValues(alpha: 0.18),
            borderColor: draw,
            borderStrokeWidth: 2,
          ),
        ],
      ),
      MarkerLayer(
        markers: [
          Marker(
            point: center,
            width: 18,
            height: 18,
            child: _dot(accent, surface),
          ),
        ],
      ),
    ];
  }

  Widget _dot(Color fill, Color border) => DecoratedBox(
    decoration: BoxDecoration(
      color: fill,
      shape: BoxShape.circle,
      border: Border.all(color: border, width: 2),
    ),
  );

  // طبقة الرسم: ملء المضلّع المغلق (≥3 نقاط) + خطّ الحدّ + علامات الرؤوس.
  List<Widget> _drawingLayers(Color draw, Color accent, Color surface) {
    final pts = widget.drawingPoints;
    if (pts.isEmpty) return const [];
    return [
      if (pts.length >= 3)
        PolygonLayer(
          polygons: [
            Polygon(
              points: pts,
              color: draw.withValues(alpha: 0.18),
              borderColor: draw,
              borderStrokeWidth: 2,
            ),
          ],
        ),
      if (pts.length >= 2)
        PolylineLayer(
          polylines: [Polyline(points: pts, color: draw, strokeWidth: 2)],
        ),
      MarkerLayer(
        markers: [
          for (var i = 0; i < pts.length; i++)
            Marker(
              point: pts[i],
              width: 18,
              height: 18,
              // الرأس الأوّل مميّز (نقطة الإغلاق).
              child: _dot(i == 0 ? accent : draw, surface),
            ),
        ],
      ),
    ];
  }

  Widget _badge(BuildContext context, String text, {Key? key}) {
    final scheme = Theme.of(context).colorScheme;
    return DecoratedBox(
      decoration: BoxDecoration(
        color: scheme.surface.withValues(alpha: 0.88),
        borderRadius: SahoolRadius.smAll,
      ),
      child: Padding(
        padding: const EdgeInsetsDirectional.symmetric(
          horizontal: SahoolSpacing.sm,
          vertical: SahoolSpacing.xs,
        ),
        child: Text(
          text,
          key: key,
          maxLines: 2,
          overflow: TextOverflow.ellipsis,
          style: TextStyle(
            color: scheme.onSurface,
            fontSize: SahoolType.caption,
          ),
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final t = context.tokens;
    final draw = scheme.primary;
    final accent = t.accent;
    final surface = scheme.surface;
    final b = widget.bounds;
    final degenerate = b != null && b.south == b.north && b.east == b.west;
    final base = _baseLayer();
    return Stack(
      children: [
        FlutterMap(
          mapController: _mapController,
          options: MapOptions(
            // إن توفّر إطار حقل المستخدم نُؤطّره (fitBounds مع حاشية)؛ وإلّا
            // مركز/تكبير ثابتان. flutter_map يُفضّل initialCameraFit إن وُجد.
            initialCameraFit: (b != null && !degenerate)
                ? CameraFit.bounds(bounds: b, padding: const EdgeInsets.all(40))
                : null,
            initialCenter: degenerate ? b.center : widget.center,
            initialZoom: widget.zoom,
            interactionOptions: const InteractionOptions(
              flags: InteractiveFlag.all & ~InteractiveFlag.rotate,
            ),
            onMapReady: () => _mapReady = true,
            onTap: widget.drawingEnabled ? _onMapTap : null,
          ),
          children: [
            _networkLayer(),
            // الحزمة المحفوظة فوق الشبكة: PMTiles → MBTiles (انظر _baseLayer).
            if (base != null) base,
            // طبقة الحقول (polygons) فوق الأساس.
            if (widget.fieldPolygons.isNotEmpty)
              PolygonLayer(polygons: widget.fieldPolygons),
            // طبقة الرسم (وضع المعالج فقط — فارغة في العرض-فقط).
            ..._drawingLayers(draw, accent, surface),
            // معاينة الدائرة (وضع الدائرة فقط — فارغة ما لم يوجد مركز ونصف قطر).
            ..._circlePreviewLayers(draw, accent, surface),
          ],
        ),
        if (widget.showWeatherOverlay)
          Positioned.fill(
            child: IgnorePointer(
              child: CustomPaint(
                painter: _WeatherWindOverlayPainter(
                  tempC: widget.weatherTempC,
                  humidityPct: widget.weatherHumidityPct,
                  windSpeedKmh: widget.windSpeedKmh,
                  windDirectionDeg: widget.windDirectionDeg,
                  opacity: widget.weatherOverlayOpacity,
                  hot: SahoolColors.statusCritical,
                  warm: SahoolColors.statusPoor,
                  humid: t.info,
                  mild: SahoolColors.statusFair,
                  stroke: surface,
                ),
              ),
            ),
          ),
        // مؤشّر المصدر (شفّافيّة: المستخدم يعرف offline أم online) — أعلى البداية.
        PositionedDirectional(
          top: SahoolSpacing.sm,
          start: SahoolSpacing.sm,
          child: _badge(
            context,
            _source.startsWith('offline') ? 'خريطة محفوظة' : 'خريطة الشبكة',
            key: const ValueKey('offline-map-source'),
          ),
        ),
        // تلميح الرسم (وضع المعالج فقط) — أعلى النهاية، بعرض محدود كي لا يغطّي الشارة.
        if (widget.drawingEnabled)
          PositionedDirectional(
            top: SahoolSpacing.sm,
            end: SahoolSpacing.sm,
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 200),
              // نصّ تعليمات الشاشة المضيفة إن توفّر، وإلّا تلميح افتراضيّ.
              child: _badge(context, widget.instruction ?? 'انقر لإضافة نقطة'),
            ),
          ),
        PositionedDirectional(
          bottom: SahoolSpacing.xs,
          start: SahoolSpacing.xs,
          child: MapAttribution(
            sources: [
              Basemaps.attributionForUrl(widget.networkTileUrl),
              if (_pack != null) 'خريطة محفوظة على الجهاز',
            ],
          ),
        ),
      ],
    );
  }
}
