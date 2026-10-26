// SAHOOL — features/maps/data/maps_api.dart
// نقاط ميزة الخرائط: روابط بلاطات خدمة الراستر (المؤشّرات/التضاريس) وترويسة
// مصادقتها، وتوفّر طبقة التضاريس. يملكه وكيل الخرائط.
//
// المصادقة: الويب يحمّل البلاطات كـ<img> فيعتمد كوكي HttpOnly (أو access_token في
// الرابط في التطوير). التطبيق يجلب البلاطة بنفسه فيرسل ترويسة
// `Authorization: Bearer` — والبوّابة تقرؤها افتراضيّاً
// (nginx/nginx.v9.conf: `set $fwd_auth $http_authorization` ثمّ auth_request
// /_auth_verify ثمّ حقن X-Tenant-Id الموثّق). لا JWT في الرابط إطلاقاً.
//
// المسارات (خدمة الراستر خلف البوّابة على /api/raster/):
//   /v1/fields/{id}/tiles/{z}/{x}/{y}.png       ← COG محفوظ (has_cog)
//   /v1/fields/{id}/cdse-tiles/{z}/{x}/{y}.png  ← مشهد حيّ مقصوص بـpoly/bbox
//   /v1/elevation/hillshade/{z}/{x}/{y}.png     ← تظليل التضاريس
//   /v1/terrain/tilejson?layer=hillshade        ← available + user_message
// عقد الاستعلام منقول من frontend/src/components/maphub/indicatorTileUrl.ts.
import 'package:sahool_app/core/network/api_client.dart';
import 'package:sahool_app/core/network/response_shape.dart';

import '../geo/geo_json.dart';

/// توفّر طبقة تضاريس كما يقوله الخادم — لا نرسم تضاريس غير مُهيّأة.
class TerrainAvailability {
  const TerrainAvailability({
    required this.available,
    this.userMessage,
    this.minZoom,
    this.maxZoom,
  });

  factory TerrainAvailability.fromJson(Map<String, dynamic> j) =>
      TerrainAvailability(
        available: j['available'] == true,
        userMessage: j['user_message'] as String?,
        minZoom: (j['minzoom'] as num?)?.toInt(),
        maxZoom: (j['maxzoom'] as num?)?.toInt(),
      );

  final bool available;
  final String? userMessage;
  final int? minZoom;
  final int? maxZoom;
}

class MapsApi {
  MapsApi([ApiClient? client]) : _client = client ?? ApiClient.instance;
  static final MapsApi instance = MapsApi();
  final ApiClient _client;

  static const rasterPrefix = '/api/raster';

  /// أصل خدمة الراستر خلف البوّابة (بلا شرطة أخيرة).
  String get rasterBaseUrl {
    final base = _client.dio.options.baseUrl.replaceAll(RegExp(r'/+$'), '');
    return '$base$rasterPrefix';
  }

  /// ترويسة مصادقة البلاطات بتوكن صالح الآن (يُحدَّث عند الحاجة). {} ⇒ لا جلسة.
  Future<Map<String, String>> tileHeaders() async {
    final token = await _client.validAccessToken();
    return token == null ? const {} : {'Authorization': 'Bearer $token'};
  }

  /// قالب رابط بلاطات مؤشّر الحقل (ndvi/ndmi/…). [date] null أو 'latest' ⇒ لا
  /// يُرسَل (الخادم يختار أحدث مشهد). [preferPersistedCog] ⇒ مسار `/tiles` المحفوظ؛
  /// وإلّا `/cdse-tiles` مع قصّ poly/bbox من الحلقة الخارجيّة للجزء الأوّل
  /// (كالويب: geomToPolygon).
  String indicatorTileUrl({
    required String fieldId,
    String index = 'ndvi',
    String? date,
    FieldGeometry? geometry,
    bool preferPersistedCog = false,
    int? version,
  }) {
    final q = <String, String>{'index': index};
    if (date != null && date.isNotEmpty && date != 'latest') q['date'] = date;
    if (version != null && version != 0) q['v'] = '$version';
    if (!preferPersistedCog && geometry != null && !geometry.isEmpty) {
      final ring = geometry.polygons.first.outer;
      if (ring.length >= 3) {
        var w = double.infinity, s = double.infinity;
        var e = double.negativeInfinity, n = double.negativeInfinity;
        for (final p in ring) {
          if (p.longitude < w) w = p.longitude;
          if (p.longitude > e) e = p.longitude;
          if (p.latitude < s) s = p.latitude;
          if (p.latitude > n) n = p.latitude;
        }
        q['bbox_w'] = '$w';
        q['bbox_s'] = '$s';
        q['bbox_e'] = '$e';
        q['bbox_n'] = '$n';
        q['poly'] = ring.map((p) => '${p.longitude},${p.latitude}').join(';');
      }
    }
    final segment = preferPersistedCog ? 'tiles' : 'cdse-tiles';
    final qs = Uri(queryParameters: q).query;
    return '$rasterBaseUrl/v1/fields/${Uri.encodeComponent(fieldId)}/$segment/'
        '{z}/{x}/{y}.png?$qs';
  }

  /// قالب بلاطات تظليل التضاريس.
  String hillshadeTileUrl() =>
      '$rasterBaseUrl/v1/elevation/hillshade/{z}/{x}/{y}.png';

  /// هل طبقة التضاريس مُهيّأة؟ (GET /api/raster/v1/terrain/tilejson).
  Future<TerrainAvailability> terrainTileJson({
    String layer = 'hillshade',
  }) async {
    final r = await _client.get(
      '$rasterPrefix/v1/terrain/tilejson',
      query: {'layer': layer},
    );
    return TerrainAvailability.fromJson(asJsonMap(r));
  }
}
