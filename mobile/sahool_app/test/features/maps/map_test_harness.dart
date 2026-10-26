// أدوات اختبار ميزة الخرائط: مضيف MaterialApp عربيّ RTL، ومزوّد بلاطات بلا شبكة.
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:sahool_app/core/theme/app_theme.dart';

/// PNG شفّاف 1×1 — بلاطة لا تلمس الشبكة.
final Uint8List kTransparentPng = Uint8List.fromList(const [
  0x89,
  0x50,
  0x4E,
  0x47,
  0x0D,
  0x0A,
  0x1A,
  0x0A,
  0x00,
  0x00,
  0x00,
  0x0D,
  0x49,
  0x48,
  0x44,
  0x52,
  0x00,
  0x00,
  0x00,
  0x01,
  0x00,
  0x00,
  0x00,
  0x01,
  0x08,
  0x06,
  0x00,
  0x00,
  0x00,
  0x1F,
  0x15,
  0xC4,
  0x89,
  0x00,
  0x00,
  0x00,
  0x0D,
  0x49,
  0x44,
  0x41,
  0x54,
  0x78,
  0x9C,
  0x63,
  0x00,
  0x01,
  0x00,
  0x00,
  0x05,
  0x00,
  0x01,
  0x0D,
  0x0A,
  0x2D,
  0xB4,
  0x00,
  0x00,
  0x00,
  0x00,
  0x49,
  0x45,
  0x4E,
  0x44,
  0xAE,
  0x42,
  0x60,
  0x82,
]);

class MemoryTileProvider extends TileProvider {
  MemoryTileProvider();
  int requests = 0;
  @override
  ImageProvider getImage(TileCoordinates coordinates, TileLayer options) {
    requests++;
    return MemoryImage(kTransparentPng);
  }
}

Widget mapHost(Widget child, {double width = 400, double height = 700}) =>
    MaterialApp(
      theme: AppTheme.light,
      locale: const Locale('ar'),
      supportedLocales: const [Locale('ar'), Locale('en')],
      localizationsDelegates: GlobalMaterialLocalizations.delegates,
      home: Scaffold(
        body: Center(
          child: SizedBox(width: width, height: height, child: child),
        ),
      ),
    );

/// صفّ FieldSummary كما يردّه GET /api/v1/fields.
Map<String, dynamic> summary(
  String id,
  Map<String, dynamic>? geometry, {
  String grade = 'READY',
  String name = 'حقل',
}) => {
  'field_id': id,
  'farm_id': 'farm-1',
  'name_ar': name,
  'crop': 'قمح',
  'area_ha': 12.5,
  'quality_grade': grade,
  'health_summary_ar': '—',
  'geometry': geometry,
};

final multiWithHole = {
  'type': 'MultiPolygon',
  'coordinates': [
    [
      [
        [44.0, 15.0],
        [44.01, 15.0],
        [44.01, 15.01],
        [44.0, 15.01],
        [44.0, 15.0],
      ],
      [
        [44.003, 15.003],
        [44.006, 15.003],
        [44.006, 15.006],
        [44.003, 15.006],
        [44.003, 15.003],
      ],
    ],
    [
      [
        [44.02, 15.0],
        [44.025, 15.0],
        [44.025, 15.004],
        [44.02, 15.0],
      ],
    ],
  ],
};
