// SAHOOL — features/maps/data/basemaps.dart
// سجلّ خرائط الأساس — منقول من الويب frontend/src/lib/layerRegistry.ts (مدخلات
// kind: 'basemap'): الروابط والنَّسَب وأقصى تكبير نفسها. بيانات لا كود.
//
// • satellite (Esri World Imagery) — الافتراضيّ، بلا مفتاح.
// • streets  («خريطة فاتحة» CARTO light_all) — شوارع وأسماء من OpenStreetMap.
// • mapbox-satellite / maptiler-satellite — تظهر فقط إن بُني التطبيق بمفتاح
//   (--dart-define=MAPBOX_TOKEN=… / MAPTILER_KEY=…)، كما يُخفيها الويب بلا مفتاح.
// • Google (رسمي) معطّل في الويب (يتطلّب جلسة Map Tiles API) فلا يُنقَل.
//
// «التضاريس» في الويب ليست خريطة أساس بل طبقة تظليل (hillshade) من خدمة
// الراستر فوق الأساس، تظهر فقط حين يقول الخادم إنّ DEM مُهيّأ
// (GET /api/raster/v1/terrain/tilejson ⇒ available). انظر MapsApi.terrainTileJson.
import 'package:flutter/foundation.dart';

@immutable
class Basemap {
  const Basemap({
    required this.id,
    required this.labelAr,
    required this.urlTemplate,
    required this.attribution,
    required this.maxZoom,
    this.subdomains = const [],
    this.retina = false,
    this.token,
  });

  final String id;
  final String labelAr;

  /// قالب XYZ. `{token}` يُستبدَل بالمفتاح؛ `{s}` بالنطاقات الفرعيّة؛ `{r}` بـ@2x.
  final String urlTemplate;

  /// نصّ النسبة الواجب عرضه (شروط المزوّد/ODbL). نصّ عاديّ بلا HTML.
  final String attribution;
  final int maxZoom;
  final List<String> subdomains;
  final bool retina;

  /// مفتاح المزوّد إن لزم؛ '' ⇒ الطبقة غير متاحة (تُخفى).
  final String? token;

  bool get requiresToken => token != null;
  bool get isAvailable => token == null || token!.isNotEmpty;

  /// القالب بعد استبدال المفتاح.
  String get resolvedUrl =>
      token == null ? urlTemplate : urlTemplate.replaceAll('{token}', token!);
}

abstract final class Basemaps {
  static const _mapboxToken = String.fromEnvironment('MAPBOX_TOKEN');
  static const _maptilerKey = String.fromEnvironment('MAPTILER_KEY');

  static const satellite = Basemap(
    id: 'satellite',
    labelAr: 'صور الأقمار الصناعيّة',
    urlTemplate:
        'https://server.arcgisonline.com/ArcGIS/rest/services/'
        'World_Imagery/MapServer/tile/{z}/{y}/{x}',
    attribution: '© Esri — World Imagery',
    maxZoom: 19,
  );

  static const streets = Basemap(
    id: 'light',
    labelAr: 'خريطة الشوارع (فاتحة)',
    urlTemplate:
        'https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png',
    attribution: '© OpenStreetMap contributors © CARTO',
    maxZoom: 19,
    subdomains: ['a', 'b', 'c', 'd'],
    retina: true,
  );

  static const mapboxSatellite = Basemap(
    id: 'mapbox-satellite',
    labelAr: 'Mapbox Satellite Streets',
    urlTemplate:
        'https://api.mapbox.com/styles/v1/mapbox/satellite-streets-v12/'
        'tiles/256/{z}/{x}/{y}@2x?access_token={token}',
    attribution: '© Mapbox © OpenStreetMap',
    maxZoom: 22,
    token: _mapboxToken,
  );

  static const maptilerSatellite = Basemap(
    id: 'maptiler-satellite',
    labelAr: 'MapTiler Satellite',
    urlTemplate:
        'https://api.maptiler.com/tiles/satellite-v2/{z}/{x}/{y}.jpg?key={token}',
    attribution: '© MapTiler © OpenStreetMap contributors',
    maxZoom: 20,
    token: _maptilerKey,
  );

  /// كلّ المدخلات المنقولة (بما فيها المحتاجة لمفتاح).
  static const all = <Basemap>[
    satellite,
    streets,
    mapboxSatellite,
    maptilerSatellite,
  ];

  /// ما يُعرَض في المنتقي: المتاحة فقط.
  static List<Basemap> get available =>
      all.where((b) => b.isAvailable).toList(growable: false);

  static Basemap get defaultBasemap => satellite;

  static Basemap byId(String? id) =>
      available.firstWhere((b) => b.id == id, orElse: () => satellite);

  /// نسبة رابط شبكيّ عشوائيّ (للودجت القديم): نطابق سجلّنا وإلّا نذكر المضيف.
  static String attributionForUrl(String url) {
    for (final b in all) {
      final host = Uri.tryParse(b.urlTemplate.replaceAll('{s}.', ''))?.host;
      if (host != null && host.isNotEmpty && url.contains(host)) {
        return b.attribution;
      }
    }
    final host = Uri.tryParse(url)?.host ?? '';
    return host.isEmpty ? '© مزوّد البلاطات' : '© $host';
  }
}
