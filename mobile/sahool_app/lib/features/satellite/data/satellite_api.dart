// SAHOOL — features/satellite/data/satellite_api.dart
// مؤشّرات الغطاء النباتيّ، تحديث صور Sentinel-2، والسلسلة الزمنيّة لـNDVI.
// يملكه وكيل ميزة الأقمار. صدق المصدر: المؤشّرات تقديرات متوسّط-حقل
// (real_data=false) إلّا حين يتوفّر raster حقيقيّ؛ غياب السلسلة ⇒ قائمة فارغة.
import 'package:sahool_app/core/network/api_client.dart';
import 'package:sahool_app/core/network/response_shape.dart';

import 'satellite_models.dart';

class SatelliteApi {
  SatelliteApi([ApiClient? client]) : _client = client ?? ApiClient.instance;
  static final SatelliteApi instance = SatelliteApi();
  final ApiClient _client;

  /// مؤشّرات الحقل الطيفيّة (NDVI/EVI/...) من خدمة الغطاء النباتيّ —
  /// GET /api/vegetation/v1/analyze?field_id={id} (vegetation-analysis-service،
  /// يُوصَل عبر البوّابة location /api/vegetation/ → /v1/analyze). المسار القديم
  /// /indicators/v1/indicators/{id} لا يطابقه nginx ⇒ 404 يسقط إلى الـSPA.
  /// الخادم يردّ {field_id, real_data, health:{label_ar,...}, indices:{ndvi:{value,
  /// unit, source}, ...}}. حارس الشكل (_asMap) كبقيّة المسارات. صدق المصدر:
  /// المؤشّرات تقديرات متوسّط-حقل (real_data=false) إلّا حين توفّر raster حقيقيّ.
  Future<Map<String, dynamic>> getFieldIndicators(String fieldId) async {
    final r = await _client.get(
      '/api/vegetation/v1/analyze',
      query: {'field_id': fieldId},
    );
    return asJsonMap(r);
  }

  /// يطلق تحديث صور Sentinel-2 الحقيقيّة للحقل عند الطلب —
  /// POST /api/v1/fields/{field_id}/imagery/refresh (يطابق refreshFieldImagery
  /// في الويب). يبحث عن مَشاهد STAC حقيقيّة ويُدرج معالجة COG في raster-service.
  /// صدق: لا بيانات مُلفَّقة — يردّ {status, queued, ...}؛ queued=false/no_scene
  /// حين لا مشهد بعد. الخطأ يُرمى ليعرضه الـUI بصدق.
  Future<Map<String, dynamic>> refreshFieldImagery(String fieldId) async {
    final r = await _client.post('/api/v1/fields/$fieldId/imagery/refresh');
    return asJsonMap(r);
  }

  /// السلسلة الزمنيّة لمؤشّر NDVI للحقل بنمط Climate FieldView —
  /// GET /v1/fields/{field_id}/timeseries?index=ndvi (raster-service، يُوصَل
  /// عبر نفس الـDio/البوّابة كبقيّة مسارات raster مثل /process و/upload).
  /// الخادم يردّ {available, points:[{datetime, mean, ...}]}. صدق: available=false
  /// أو points فارغة ⇒ تُعاد قائمة فارغة (لا اختلاق نقاط)؛ تُتسامَح المفاتيح
  /// الغائبة (stddev/cloudy_pct قد لا يُرسلها الخادم). كلّ عنصر خريطة آمنة الشكل.
  Future<List<Map<String, dynamic>>> getFieldNdviTimeseries(
    String fieldId, {
    String? tag,
  }) async {
    final r = await _client.get(
      '/api/raster/v1/fields/$fieldId/timeseries',
      query: {'index': 'ndvi'},
    );
    final data = asJsonMap(r);
    // صدق: غياب التوفّر ⇒ لا نقاط (الـUI يعرض «غير متاح»).
    if (data['available'] == false) return const [];
    final raw = data['points'];
    if (raw is! List) return const [];
    final out = <Map<String, dynamic>>[];
    for (final e in raw) {
      if (e is! Map) continue;
      final m = e.cast<String, dynamic>();
      // نمرّر فقط ما نحتاجه (datetime/mean/cloudy_pct)، مع تسامح المفاتيح الغائبة.
      out.add({
        'datetime': m['datetime'] ?? m['date'],
        'mean': m['mean'],
        // raster-service يُرسل cloud_pct؛ المفتاح القديم cloudy_pct يبقى مقبولاً.
        if (m['cloudy_pct'] != null || m['cloud_pct'] != null)
          'cloudy_pct': m['cloudy_pct'] ?? m['cloud_pct'],
      });
    }
    return out;
  }

  /// كتالوج المؤشّرات المُنفَّذة فعلاً (GET /api/v1/indicators/catalog):
  /// {indicators:[{id, name_ar, category, unit, renderable, source}]}.
  /// المؤشّرات renderable=true هي ما يملك سلسلة/شبكة مكانيّة في raster-service.
  Future<List<IndexOption>> getIndicatorCatalog() async {
    final data = asJsonMap(await _client.get('/api/v1/indicators/catalog'));
    final raw = data['indicators'];
    if (raw is! List) {
      throw const FormatException(
        'indicators catalog: indicators is not a list',
      );
    }
    return [
      for (final e in raw.whereType<Map>())
        if (e['renderable'] == true && e['id'] is String)
          IndexOption.fromJson(e.cast<String, dynamic>()),
    ];
  }

  /// السلسلة الزمنيّة الحقيقيّة لأيّ مؤشّر قابل للرسم (ndvi/ndwi/ndmi/evi...) —
  /// GET /api/raster/v1/fields/{id}/timeseries?index={index}. الخادم يردّ
  /// {available, points:[{datetime, mean, cloud_pct, valid_pixel_ratio}], note}.
  /// صدق: available=false ⇒ سلسلة فارغة مع ملاحظة الخادم (لا نقاط مختلقة).
  Future<IndexSeries> getFieldIndexTimeseries(
    String fieldId,
    String index,
  ) async {
    final data = asJsonMap(
      await _client.get(
        '/api/raster/v1/fields/$fieldId/timeseries',
        query: {'index': index},
      ),
    );
    return IndexSeries.fromJson(fieldId, index, data);
  }

  /// نفس [getFieldIndicators] مُحلَّلةً إلى [IndicatorSnapshot] (قراءات + صحّة).
  Future<IndicatorSnapshot> getIndicatorSnapshot(String fieldId) async =>
      IndicatorSnapshot.fromJson(fieldId, await getFieldIndicators(fieldId));
}
