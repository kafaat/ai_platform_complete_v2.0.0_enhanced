// SAHOOL — features/maps/presentation/layers/indicator_raster_layer.dart
// طبقة بلاطات مؤشّر الحقل (NDVI/NDMI/…) من خدمة الراستر، بترويسة المصادقة.
//
// الويب يحمّل البلاطة كـ<img> فلا يرسل ترويسة؛ هنا نجلبها بأنفسنا فنرسل
// `Authorization: Bearer <توكن صالح>` (MapsApi.tileHeaders يحدّثه إن انتهى). التوكن
// يُجدَّد دوريّاً داخل خريطة الترويسات نفسها (NetworkTileProvider يقرؤها عند كلّ
// بلاطة) كي لا تتحوّل الطبقة إلى 401 صامت بعد انتهاء الجلسة القصيرة.
//
// صدق: بلا جلسة لا تُرسَم الطبقة (لا طلب مجهول)؛ والخادم يردّ بلاطة شفّافة حيث
// لا بيانات — فلا لون مُختلَق.
import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';

import '../../data/maps_api.dart';
import '../../geo/geo_json.dart';
import '../widgets/sahool_map.dart' show kTileUserAgentPackage;

/// نسبة بيانات Sentinel-2 (شرط Copernicus) — يضيفها المستدعي إلى extraAttributions.
const kSentinelAttribution = 'Contains modified Copernicus Sentinel data';

class IndicatorRasterLayer extends StatefulWidget {
  const IndicatorRasterLayer({
    super.key,
    required this.fieldId,
    this.index = 'ndvi',
    this.date,
    this.geometry,
    this.preferPersistedCog = false,
    this.opacity = 0.85,
    this.mapsApi,
    this.tokenRefreshEvery = const Duration(minutes: 4),
  });

  final String fieldId;
  final String index;
  final String? date;
  final FieldGeometry? geometry;
  final bool preferPersistedCog;
  final double opacity;
  final MapsApi? mapsApi;
  final Duration tokenRefreshEvery;

  @override
  State<IndicatorRasterLayer> createState() => _IndicatorRasterLayerState();
}

class _IndicatorRasterLayerState extends State<IndicatorRasterLayer> {
  /// خريطة قابلة للتعديل يقرؤها المزوّد عند كلّ بلاطة.
  final Map<String, String> _headers = {};
  NetworkTileProvider? _provider;
  Timer? _refresh;
  bool _hasSession = false;

  MapsApi get _api => widget.mapsApi ?? MapsApi.instance;

  @override
  void initState() {
    super.initState();
    _loadHeaders();
    _refresh = Timer.periodic(widget.tokenRefreshEvery, (_) => _loadHeaders());
  }

  Future<void> _loadHeaders() async {
    Map<String, String> h;
    try {
      h = await _api.tileHeaders();
    } catch (_) {
      h = const {};
    }
    if (!mounted) return;
    _headers
      ..clear()
      ..addAll(h);
    final has = h.containsKey('Authorization');
    if (has != _hasSession) setState(() => _hasSession = has);
  }

  @override
  void dispose() {
    _refresh?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    if (!_hasSession) return const SizedBox.shrink();
    final url = _api.indicatorTileUrl(
      fieldId: widget.fieldId,
      index: widget.index,
      date: widget.date,
      geometry: widget.geometry,
      preferPersistedCog: widget.preferPersistedCog,
    );
    return TileLayer(
      key: ValueKey(url),
      urlTemplate: url,
      maxNativeZoom: 18,
      userAgentPackageName: kTileUserAgentPackage,
      tileProvider: _provider ??= NetworkTileProvider(
        headers: _headers,
        silenceExceptions: true,
      ),
      tileBounds: widget.geometry?.bounds,
      tileBuilder: (context, tile, _) =>
          Opacity(opacity: widget.opacity, child: tile),
    );
  }

  @override
  void didUpdateWidget(IndicatorRasterLayer oldWidget) {
    super.didUpdateWidget(oldWidget);
    // رابط جديد ⇒ مفتاح جديد ⇒ TileLayer جديد يتخلّص من المزوّد القديم.
    if (oldWidget.fieldId != widget.fieldId ||
        oldWidget.index != widget.index ||
        oldWidget.date != widget.date ||
        oldWidget.geometry != widget.geometry ||
        oldWidget.preferPersistedCog != widget.preferPersistedCog) {
      _provider = null;
    }
  }
}
