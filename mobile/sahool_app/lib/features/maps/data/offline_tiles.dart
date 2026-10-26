// SAHOOL — features/maps/data/offline_tiles.dart
// فتح حزمة بلاطات على الجهاز (PMTiles أو MBTiles) لتُرسَم كخريطة أساس بلا شبكة.
//
// • الحزمتان **نقطيّتان فقط** (png/jpg/webp): flutter_map_pmtiles 1.0.5 و
//   flutter_map_mbtiles 1.0.4 مزوّدا بلاطات raster. حزمة متّجهة (mvt/pbf) تُرفَض
//   بسبب صريح بدل خريطة فارغة صامتة.
// • fail-safe: ملفّ مفقود/تالف ⇒ [OfflinePackOpenResult.error] والخريطة تبقى على
//   الشبكة، لا تعطّل.
// • المالك يغلق الحزمة بـ[OpenedOfflinePack.dispose] (قاعدة SQLite / ملفّ PMTiles).
//   TileLayer يستدعي dispose على مزوّده عند زواله؛ المزوّدان هنا لا يملكان المصدر
//   فإغلاقه مسؤوليّة الحزمة وحدها.
import 'dart:io';

import 'package:flutter_map/flutter_map.dart';
import 'package:flutter_map_mbtiles/flutter_map_mbtiles.dart';
import 'package:flutter_map_pmtiles/flutter_map_pmtiles.dart';
import 'package:latlong2/latlong.dart';
import 'package:mbtiles/mbtiles.dart';

enum OfflinePackFormat { pmtiles, mbtiles }

/// صيغة الحزمة من امتداد الملفّ؛ null ⇒ ليست حزمة بلاطات.
OfflinePackFormat? offlinePackFormatOf(String path) {
  final p = path.toLowerCase();
  if (p.endsWith('.pmtiles')) return OfflinePackFormat.pmtiles;
  if (p.endsWith('.mbtiles')) return OfflinePackFormat.mbtiles;
  return null;
}

/// حزمة مفتوحة جاهزة للرسم.
class OpenedOfflinePack {
  OpenedOfflinePack._(
    this.path,
    this.format,
    this.tileProvider,
    this._close, {
    this.minZoom,
    this.maxZoom,
    this.bounds,
  });

  final String path;
  final OfflinePackFormat format;
  final int? minZoom;
  final int? maxZoom;
  final LatLngBounds? bounds;

  /// مزوّد البلاطات (واحد لكلّ حزمة كي لا تُعاد تحميل البلاطات مع كلّ بناء):
  /// [PmTilesTileProvider] أو [MbTilesTileProvider].
  final TileProvider tileProvider;
  final Future<void> Function() _close;
  bool _disposed = false;

  Future<void> dispose() async {
    if (_disposed) return;
    _disposed = true;
    try {
      await _close();
    } catch (_) {
      // إغلاق أفضل-جهد.
    }
  }
}

/// نتيجة محاولة فتح حزمة: إمّا [pack] أو [error] عربيّ صريح.
class OfflinePackOpenResult {
  const OfflinePackOpenResult.ok(OpenedOfflinePack this.pack) : error = null;
  const OfflinePackOpenResult.failed(String this.error) : pack = null;
  final OpenedOfflinePack? pack;
  final String? error;
}

/// يفتح الحزمة في [path]. لا يرمي أبداً (fail-safe).
Future<OfflinePackOpenResult> openOfflinePack(String path) async {
  final format = offlinePackFormatOf(path);
  if (format == null) {
    return const OfflinePackOpenResult.failed(
      'صيغة غير مدعومة: الحزمة يجب أن تكون ‎.pmtiles أو ‎.mbtiles',
    );
  }
  try {
    if (!await File(path).exists()) {
      return const OfflinePackOpenResult.failed('ملفّ الحزمة غير موجود');
    }
    switch (format) {
      case OfflinePackFormat.pmtiles:
        final provider = await PmTilesTileProvider.fromSource(path);
        final archive = provider.archive;
        if (archive.tileType.name == 'mvt') {
          await archive.close();
          return const OfflinePackOpenResult.failed(
            'حزمة متّجهة (MVT) — التطبيق يعرض الحزم النقطيّة فقط',
          );
        }
        return OfflinePackOpenResult.ok(
          OpenedOfflinePack._(
            path,
            format,
            provider,
            archive.close,
            minZoom: archive.minZoom,
            maxZoom: archive.maxZoom,
            bounds: _bounds(
              archive.minPosition.latitude,
              archive.minPosition.longitude,
              archive.maxPosition.latitude,
              archive.maxPosition.longitude,
            ),
          ),
        );
      case OfflinePackFormat.mbtiles:
        final db = MbTiles(mbtilesPath: path);
        final meta = db.getMetadata();
        final fmt = meta.format.toLowerCase();
        if (fmt == 'pbf' || fmt == 'mvt') {
          db.dispose();
          return const OfflinePackOpenResult.failed(
            'حزمة متّجهة (pbf) — التطبيق يعرض الحزم النقطيّة فقط',
          );
        }
        final b = meta.bounds;
        return OfflinePackOpenResult.ok(
          OpenedOfflinePack._(
            path,
            format,
            MbTilesTileProvider(mbtiles: db),
            () async => db.dispose(),
            minZoom: meta.minZoom?.round(),
            maxZoom: meta.maxZoom?.round(),
            bounds: b == null
                ? null
                : _bounds(b.bottom, b.left, b.top, b.right),
          ),
        );
    }
  } catch (_) {
    return const OfflinePackOpenResult.failed(
      'تعذّر فتح الحزمة (ملفّ تالف أو غير مقروء)',
    );
  }
}

LatLngBounds? _bounds(double s, double w, double n, double e) {
  if (![s, w, n, e].every((v) => v.isFinite)) return null;
  if (s >= n || w >= e) return null;
  return LatLngBounds(LatLng(s, w), LatLng(n, e));
}
