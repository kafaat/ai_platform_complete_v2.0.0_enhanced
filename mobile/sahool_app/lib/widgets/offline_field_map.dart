// offline_field_map.dart — خريطة حقل تعمل offline (سدّ فجوة اليمن ضعيف الشبكة).
//
// الممارسة العالميّة للحقول منخفضة الاتّصال: حزمة بلاطات MBTiles (SQLite)
// على الجهاز كأساس offline، مع بلاطات الشبكة كـfallback عند توفّرها.
// هذا يضمن أنّ المزارع في منطقة بلا تغطيّة لا يفقد الخريطة كاملةً.
//
// الاستخدام (عرض فقط — الافتراضيّ، يبقى متوافقاً مع المستدعين القدامى):
//   OfflineFieldMap(
//     center: LatLng(16.79, 44.33),   // الجوف
//     offlinePackPath: 'assets/maps/aljawf.mbtiles',  // اختياري
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

import 'dart:io';
import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:flutter_map_mbtiles/flutter_map_mbtiles.dart';
import 'package:flutter_map_pmtiles/flutter_map_pmtiles.dart';
import 'package:latlong2/latlong.dart';
import 'package:mbtiles/mbtiles.dart';
import 'package:path_provider/path_provider.dart';

// نوع حزمة offline: PMTiles (مفضّل — ملفّ واحد، HTTP-range، hybrid) أو
// MBTiles (SQLite، ناضج). PMTiles أقرب لاتّجاه geospatial-first.
enum OfflinePackType { pmtiles, mbtiles, none }

// وضع الرسم على الخريطة: نقاط (مضلّع بالنقر) أو دائرة (مركز + نصف قطر بالأمتار).
enum DrawMode { points, circle }

class OfflineFieldMap extends StatefulWidget {
  final LatLng center;
  final double zoom;
  // مسار حزمة offline على الجهاز (إن وُجدت). الامتداد يحدّد النوع.
  final String? offlinePackPath;
  // رابط بلاطات الشبكة (fallback عند توفّر اتّصال).
  final String networkTileUrl;
  final List<Polygon> fieldPolygons;

  // ── وضع الرسم (اختياريّ — لمعالج إنشاء الحقل) ──
  // عند true: النقر على الخريطة يضيف رأساً إلى المضلّع الجاري رسمه، وتُرسَم
  // الرؤوس + الخطّ + ملء المضلّع المغلق فوق الأساس. العرض-فقط (الافتراضيّ false)
  // لا يتأثّر إطلاقاً.
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

  const OfflineFieldMap({
    super.key,
    required this.center,
    this.zoom = 13,
    this.offlinePackPath,
    this.networkTileUrl =
        'https://server.arcgisonline.com/ArcGIS/rest/services/'
        'World_Imagery/MapServer/tile/{z}/{y}/{x}',
    this.fieldPolygons = const [],
    this.drawingEnabled = false,
    this.drawingPoints = const [],
    this.onPolygonChanged,
    this.drawMode = DrawMode.points,
    this.onCenterTap,
    this.circlePreviewCenter,
    this.circlePreviewRadiusMeters,
    this.instruction,
  });

  @override
  State<OfflineFieldMap> createState() => _OfflineFieldMapState();
}

class _OfflineFieldMapState extends State<OfflineFieldMap> {
  MbTiles? _mbtiles;
  PmTilesTileProvider? _pmtiles;
  OfflinePackType _packType = OfflinePackType.none;
  String _source = 'network';

  @override
  void initState() {
    super.initState();
    _initOffline();
  }

  Future<void> _initOffline() async {
    final path = widget.offlinePackPath;
    if (path == null) return;
    try {
      final file = File(path);
      if (!await file.exists()) return;
      if (path.endsWith('.pmtiles')) {
        // PMTiles: ملفّ واحد cloud-optimized (مفضّل). يعمل offline + online.
        _pmtiles = await PmTilesTileProvider.fromSource(path);
        setState(() {
          _packType = OfflinePackType.pmtiles;
          _source = 'offline-pmtiles';
        });
      } else if (path.endsWith('.mbtiles')) {
        // MBTiles: SQLite (ناضج، fallback).
        _mbtiles = MbTiles(mbtilesPath: path);
        setState(() {
          _packType = OfflinePackType.mbtiles;
          _source = 'offline-mbtiles';
        });
      }
    } catch (_) {
      // فشل فتح offline → نبقى على الشبكة (fail-safe، لا تعطّل الخريطة).
      _packType = OfflinePackType.none;
    }
  }

  @override
  void dispose() {
    _mbtiles?.dispose();
    _pmtiles?.dispose();
    super.dispose();
  }

  TileLayer _baseLayer() {
    // أولويّة: PMTiles → MBTiles → الشبكة (fallback).
    if (_packType == OfflinePackType.pmtiles && _pmtiles != null) {
      return TileLayer(tileProvider: _pmtiles!);
    }
    if (_packType == OfflinePackType.mbtiles && _mbtiles != null) {
      return TileLayer(tileProvider: MbTilesTileProvider(mbtiles: _mbtiles!));
    }
    return TileLayer(
      urlTemplate: widget.networkTileUrl,
      userAgentPackageName: 'ye.sahool.app',
    );
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

  // توليد رؤوس مضلّع دائريّ حول [center] بنصف قطر [radiusMeters] (بالأمتار).
  // تقريب جيوديسيّ بسيط: 1 درجة خطّ عرض ≈ 111320 م، وخطّ الطول يُقاس بـcos(lat).
  // يُستخدَم للمعاينة هنا، وتُكرَّره الشاشة المضيفة لإنتاج الهندسة النهائيّة.
  static List<LatLng> circlePolygon(
    LatLng center,
    double radiusMeters, {
    int segments = 48,
  }) {
    if (radiusMeters <= 0 || segments < 3) return const [];
    const metersPerDegLat = 111320.0;
    final cosLat = math.cos(center.latitude * math.pi / 180.0);
    // حارس: قرب القطبين cos→0؛ نمنع القسمة على صفر.
    final safeCos = cosLat.abs() < 1e-6 ? 1e-6 : cosLat;
    final dLat = radiusMeters / metersPerDegLat;
    final dLon = radiusMeters / (metersPerDegLat * safeCos);
    final pts = <LatLng>[];
    for (var i = 0; i < segments; i++) {
      final theta = 2 * math.pi * i / segments;
      pts.add(LatLng(
        center.latitude + dLat * math.sin(theta),
        center.longitude + dLon * math.cos(theta),
      ));
    }
    return pts;
  }

  // معاينة الدائرة: حلقة + مركز مميّز (وضع الدائرة فقط، عند توفّر مركز ونصف قطر).
  List<Widget> _circlePreviewLayers() {
    final center = widget.circlePreviewCenter;
    final r = widget.circlePreviewRadiusMeters;
    if (center == null || r == null || r <= 0) return const [];
    final ring = circlePolygon(center, r);
    if (ring.length < 3) return const [];
    return [
      PolygonLayer(
        polygons: [
          Polygon(
            points: ring,
            color: const Color(0xFF10B981).withOpacity(0.18),
            borderColor: const Color(0xFF10B981),
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
            child: Container(
              decoration: BoxDecoration(
                color: const Color(0xFFF59E0B),
                shape: BoxShape.circle,
                border: Border.all(color: Colors.white, width: 2),
              ),
            ),
          ),
        ],
      ),
    ];
  }

  // طبقة الرسم: ملء المضلّع المغلق (≥3 نقاط) + خطّ الحدّ + علامات الرؤوس.
  List<Widget> _drawingLayers() {
    final pts = widget.drawingPoints;
    if (pts.isEmpty) return const [];
    return [
      if (pts.length >= 3)
        PolygonLayer(
          polygons: [
            Polygon(
              points: pts,
              color: const Color(0xFF10B981).withOpacity(0.18),
              borderColor: const Color(0xFF10B981),
              borderStrokeWidth: 2,
            ),
          ],
        ),
      if (pts.length >= 2)
        PolylineLayer(
          polylines: [
            Polyline(
              points: pts,
              color: const Color(0xFF10B981),
              strokeWidth: 2,
            ),
          ],
        ),
      MarkerLayer(
        markers: [
          for (var i = 0; i < pts.length; i++)
            Marker(
              point: pts[i],
              width: 18,
              height: 18,
              child: Container(
                decoration: BoxDecoration(
                  color: i == 0
                      ? const Color(0xFFF59E0B) // الرأس الأوّل مميّز (نقطة الإغلاق)
                      : const Color(0xFF10B981),
                  shape: BoxShape.circle,
                  border: Border.all(color: Colors.white, width: 2),
                ),
              ),
            ),
        ],
      ),
    ];
  }

  @override
  Widget build(BuildContext context) {
    return Stack(
      children: [
        FlutterMap(
          options: MapOptions(
            initialCenter: widget.center,
            initialZoom: widget.zoom,
            onTap: widget.drawingEnabled ? _onMapTap : null,
          ),
          children: [
            // طبقة الأساس: PMTiles → MBTiles → الشبكة (انظر _baseLayer).
            _baseLayer(),
            // طبقة الحقول (polygons) فوق الأساس.
            if (widget.fieldPolygons.isNotEmpty)
              PolygonLayer(polygons: widget.fieldPolygons),
            // طبقة الرسم (وضع المعالج فقط — فارغة في العرض-فقط).
            ..._drawingLayers(),
            // معاينة الدائرة (وضع الدائرة فقط — فارغة ما لم يوجد مركز ونصف قطر).
            ..._circlePreviewLayers(),
          ],
        ),
        // مؤشّر المصدر (شفّافيّة: المستخدم يعرف offline أم online).
        Positioned(
          top: 8,
          right: 8,
          child: Container(
            padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
            decoration: BoxDecoration(
              color: Colors.black54,
              borderRadius: BorderRadius.circular(6),
            ),
            child: Text(
              _source.startsWith('offline') ? 'خريطة محفوظة' : 'خريطة الشبكة',
              style: const TextStyle(color: Colors.white, fontSize: 11),
            ),
          ),
        ),
        // تلميح الرسم (وضع المعالج فقط).
        if (widget.drawingEnabled)
          Positioned(
            top: 8,
            left: 8,
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
              decoration: BoxDecoration(
                color: Colors.black54,
                borderRadius: BorderRadius.circular(6),
              ),
              child: Text(
                // نصّ تعليمات الشاشة المضيفة إن توفّر، وإلّا تلميح افتراضيّ.
                widget.instruction ?? 'انقر لإضافة نقطة',
                style: const TextStyle(color: Colors.white, fontSize: 11),
              ),
            ),
          ),
      ],
    );
  }
}
