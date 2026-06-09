// offline_field_map.dart — خريطة حقل تعمل offline (سدّ فجوة اليمن ضعيف الشبكة).
//
// الممارسة العالميّة للحقول منخفضة الاتّصال: حزمة بلاطات MBTiles (SQLite)
// على الجهاز كأساس offline، مع بلاطات الشبكة كـfallback عند توفّرها.
// هذا يضمن أنّ المزارع في منطقة بلا تغطيّة لا يفقد الخريطة كاملةً.
//
// الاستخدام:
//   OfflineFieldMap(
//     center: LatLng(16.79, 44.33),   // الجوف
//     mbtilesAssetPath: 'assets/maps/aljawf.mbtiles',  // اختياري
//     fields: [...],
//   )

import 'dart:io';
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

class OfflineFieldMap extends StatefulWidget {
  final LatLng center;
  final double zoom;
  // مسار حزمة offline على الجهاز (إن وُجدت). الامتداد يحدّد النوع.
  final String? offlinePackPath;
  // رابط بلاطات الشبكة (fallback عند توفّر اتّصال).
  final String networkTileUrl;
  final List<Polygon> fieldPolygons;

  const OfflineFieldMap({
    super.key,
    required this.center,
    this.zoom = 13,
    this.offlinePackPath,
    this.networkTileUrl =
        'https://server.arcgisonline.com/ArcGIS/rest/services/'
        'World_Imagery/MapServer/tile/{z}/{y}/{x}',
    this.fieldPolygons = const [],
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

  @override
  Widget build(BuildContext context) {
    return Stack(
      children: [
        FlutterMap(
          options: MapOptions(
            initialCenter: widget.center,
            initialZoom: widget.zoom,
          ),
          children: [
            // طبقة الأساس: PMTiles → MBTiles → الشبكة (انظر _baseLayer).
            _baseLayer(),
            // طبقة الحقول (polygons) فوق الأساس.
            if (widget.fieldPolygons.isNotEmpty)
              PolygonLayer(polygons: widget.fieldPolygons),
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
      ],
    );
  }
}
