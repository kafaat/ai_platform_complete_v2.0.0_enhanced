// SAHOOL — features/dashboard/data/today_models.dart
// قراءة حمولات الخادم لشاشة «اليوم» إلى نماذج مُنمَّطة. كلّ قيمة غائبة تبقى null
// فتُعرَض «غير مقيس» — لا صفر ولا «null» ولا رقم مُختلَق.
//
// الأشكال المصدريّة (لا تخمين أسماء):
// - اللوحة: analytics_shapers.py `_shape_indicators_dashboard` ⇒
//   kpis[{id,name_ar,value,unit,status}]، alerts[AlertSummary]،
//   fields_summary[{field_id,field_name,crop,area_ha,has_active_season,geometry}].
// - التنبيه: alert_models.py AlertSummary {alert_id, field_id, alert_type,
//   severity(info|warning|critical), title_ar, message_ar, status, created_at}.
// - المهمّة: api_models.py TaskSummary {task_id, field_id, task_type,
//   priority(1..), status, recommended_date, ...}.
// - المزرعة: routers/farms.py {farm_id, name, centroid_lat, centroid_lon, ...}.
// - الأولويّة: field_priority_queue.py items[{id,type,field_id,title_ar,
//   severity(critical|high|medium|low), due_at, action}].
// - الطقس: weather.py field-weather-summary {sample{temperature_2m_c,
//   relative_humidity_2m_pct, wind_speed_10m_kmh, precipitation_mm},
//   operations{spraying{suitability,score}, irrigation{...}}, cache_state, ...}.

num? _num(Object? v) => v is num ? v : null;

String? _str(Object? v) {
  if (v == null) return null;
  final s = v.toString().trim();
  return s.isEmpty ? null : s;
}

DateTime? _date(Object? v) {
  final s = _str(v);
  return s == null ? null : DateTime.tryParse(s);
}

List<Map<String, dynamic>> _maps(Object? v) => v is List
    ? v.whereType<Map>().map((e) => Map<String, dynamic>.from(e)).toList()
    : const [];

/// مؤشّر واحد من kpis[].
class TodayKpi {
  const TodayKpi({
    required this.id,
    required this.labelAr,
    this.value,
    this.unit,
    this.status,
  });

  final String id;
  final String labelAr;
  final num? value;
  final String? unit;
  final String? status;

  /// المؤشّرات الأربعة التي يُصدرها المُنتِج اليوم — تُعرَض «غير مقيس» إن غابت
  /// القائمة كلّها (حمولة ناقصة) بدل أن تختفي بصمت.
  static const expected = <TodayKpi>[
    TodayKpi(id: 'fields_total', labelAr: 'إجماليّ الحقول', unit: 'حقل'),
    TodayKpi(id: 'area_total', labelAr: 'إجماليّ المساحة', unit: 'هـ'),
    TodayKpi(id: 'active_seasons', labelAr: 'حقول بموسم نشط', unit: 'حقل'),
    TodayKpi(id: 'open_alerts', labelAr: 'تنبيهات مفتوحة', unit: 'تنبيه'),
  ];

  static List<TodayKpi> listFrom(Object? raw) {
    final rows = _maps(raw);
    if (rows.isEmpty) return expected;
    return [
      for (final r in rows)
        TodayKpi(
          id: _str(r['id']) ?? '',
          labelAr: _str(r['name_ar']) ?? _labelFor(_str(r['id'])),
          value: _num(r['value']),
          unit: _str(r['unit']),
          status: _str(r['status']),
        ),
    ];
  }

  static String _labelFor(String? id) {
    for (final k in expected) {
      if (k.id == id) return k.labelAr;
    }
    return 'مؤشّر';
  }
}

/// تنبيه نشط من alerts[].
class TodayAlert {
  const TodayAlert({
    required this.id,
    this.fieldId,
    this.type,
    this.severity,
    this.titleAr,
    this.messageAr,
    this.createdAt,
  });

  final String id;
  final String? fieldId;
  final String? type;
  final String? severity;
  final String? titleAr;
  final String? messageAr;
  final DateTime? createdAt;

  static const _typeAr = {
    'low_moisture': 'رطوبة تربة منخفضة',
    'heavy_rain': 'أمطار غزيرة',
    'disease_risk': 'خطر مرض',
    'heat_stress': 'إجهاد حراريّ',
    'frost_risk': 'خطر صقيع',
    'vegetation_stress': 'إجهاد نباتيّ',
    'other': 'تنبيه',
  };

  /// العنوان المعروض: title_ar، وإلّا ترجمة النوع، وإلّا «تنبيه».
  String get displayTitle => titleAr ?? _typeAr[type] ?? 'تنبيه';

  /// 0 = الأشدّ. الخادم يُصدر info|warning|critical.
  int get severityRank => severityRankOf(severity);

  static int severityRankOf(String? s) => switch (s) {
    'critical' => 0,
    'high' => 1,
    'warning' => 1,
    'medium' => 2,
    'info' => 3,
    'low' => 3,
    _ => 2,
  };

  static List<TodayAlert> listFrom(Object? raw) {
    final out = <TodayAlert>[];
    for (final r in _maps(raw)) {
      final id = _str(r['alert_id']);
      if (id == null) continue; // بلا معرّف لا فتح ولا إقرار
      out.add(
        TodayAlert(
          id: id,
          fieldId: _str(r['field_id']),
          type: _str(r['alert_type']),
          severity: _str(r['severity']),
          titleAr: _str(r['title_ar']),
          messageAr: _str(r['message_ar']),
          createdAt: _date(r['created_at']),
        ),
      );
    }
    out.sort((a, b) {
      final s = a.severityRank.compareTo(b.severityRank);
      if (s != 0) return s;
      final at = a.createdAt, bt = b.createdAt;
      if (at == null || bt == null) return at == null ? 1 : -1;
      return bt.compareTo(at);
    });
    return out;
  }
}

/// حقل من fields_summary[].
class TodayField {
  const TodayField({
    required this.id,
    required this.name,
    this.crop,
    this.areaHa,
    this.hasActiveSeason,
    this.centroid,
  });

  final String id;
  final String name;
  final String? crop;

  /// null إن غابت. المُنتِج يحوّل المساحة الغائبة إلى 0.0 فنعامل ≤0 كغير مقيسة.
  final num? areaHa;
  final bool? hasActiveSeason;

  /// (lat, lon) مركز تقريبيّ من حدود المضلّع، إن وُجدت هندسة.
  final (double, double)? centroid;

  static List<TodayField> listFrom(Object? raw) {
    final out = <TodayField>[];
    for (final r in _maps(raw)) {
      final id = _str(r['field_id']);
      if (id == null) continue;
      final area = _num(r['area_ha']);
      final active = r['has_active_season'];
      out.add(
        TodayField(
          id: id,
          name: _str(r['field_name']) ?? _str(r['name']) ?? 'حقل بلا اسم',
          crop: _str(r['crop']),
          areaHa: (area != null && area > 0) ? area : null,
          hasActiveSeason: active is bool ? active : null,
          centroid: centroidOf(r['geometry']),
        ),
      );
    }
    return out;
  }

  /// مركز مستطيل الإحاطة لمضلّع GeoJSON ([lon, lat]). يكفي لنقطة طقس.
  static (double, double)? centroidOf(Object? geometry) {
    if (geometry is! Map) return null;
    double? minLat, maxLat, minLon, maxLon;
    void visit(Object? node) {
      if (node is List) {
        if (node.length >= 2 && node[0] is num && node[1] is num) {
          final lon = (node[0] as num).toDouble();
          final lat = (node[1] as num).toDouble();
          if (lat.abs() > 90 || lon.abs() > 180) return;
          minLat = minLat == null || lat < minLat! ? lat : minLat;
          maxLat = maxLat == null || lat > maxLat! ? lat : maxLat;
          minLon = minLon == null || lon < minLon! ? lon : minLon;
          maxLon = maxLon == null || lon > maxLon! ? lon : maxLon;
        } else {
          node.forEach(visit);
        }
      }
    }

    visit(geometry['coordinates']);
    if (minLat == null || minLon == null) return null;
    return ((minLat! + maxLat!) / 2, (minLon! + maxLon!) / 2);
  }
}

/// مهمّة من GET /api/v1/tasks.
class TodayTask {
  const TodayTask({
    required this.id,
    this.fieldId,
    this.type,
    this.priority,
    this.status,
    this.dueDate,
  });

  final String id;
  final String? fieldId;
  final String? type;
  final int? priority;
  final String? status;
  final DateTime? dueDate;

  static const _typeAr = {
    'irrigation': 'ريّ',
    'fertilization': 'تسميد',
    'spraying': 'رشّ',
    'spray': 'رشّ',
    'harvest': 'حصاد',
    'scouting': 'كشف ميدانيّ',
    'soil_sampling': 'عيّنة تربة',
  };

  String get displayTitle =>
      _typeAr[type] ?? (type == null ? 'مهمّة' : 'مهمّة: $type');

  bool get isOpen => status == 'pending' || status == 'in_progress';

  /// تاريخ الاستحقاق قبل يوم [today] المحلّيّ.
  bool isOverdue(DateTime today) {
    final d = dueDate;
    if (d == null) return false;
    return _day(d).isBefore(_day(today));
  }

  bool isDueBy(DateTime today) {
    final d = dueDate;
    if (d == null) return false;
    return !_day(d).isAfter(_day(today));
  }

  static DateTime _day(DateTime d) {
    final l = d.toLocal();
    return DateTime(l.year, l.month, l.day);
  }

  static List<TodayTask> listFrom(Object? raw) {
    final out = <TodayTask>[];
    for (final r in _maps(raw)) {
      final id = _str(r['task_id']);
      if (id == null) continue;
      final p = r['priority'];
      out.add(
        TodayTask(
          id: id,
          fieldId: _str(r['field_id']),
          type: _str(r['task_type']),
          priority: p is num ? p.toInt() : null,
          status: _str(r['status']),
          dueDate: _date(r['recommended_date']),
        ),
      );
    }
    return out;
  }

  /// مهامّ اليوم: المفتوحة المستحقّة اليوم أو المتأخّرة أوّلاً (بالأولويّة ثمّ
  /// الموعد)، ثمّ المفتوحة بلا موعد. المستقبليّة لا تخصّ «اليوم».
  static List<TodayTask> forToday(List<TodayTask> all, DateTime today) {
    int byPriority(TodayTask a, TodayTask b) =>
        (a.priority ?? 3).compareTo(b.priority ?? 3);
    final due = all.where((t) => t.isOpen && t.isDueBy(today)).toList()
      ..sort((a, b) {
        final p = byPriority(a, b);
        return p != 0 ? p : a.dueDate!.compareTo(b.dueDate!);
      });
    final undated = all.where((t) => t.isOpen && t.dueDate == null).toList()
      ..sort(byPriority);
    return [...due, ...undated];
  }
}

/// مزرعة من GET /api/v1/farms.
class TodayFarm {
  const TodayFarm({required this.id, required this.name, this.centroid});

  final String id;
  final String name;
  final (double, double)? centroid;

  static List<TodayFarm> listFrom(Object? raw) {
    final out = <TodayFarm>[];
    for (final r in _maps(raw)) {
      final id = _str(r['farm_id']);
      if (id == null) continue;
      final lat = _num(r['centroid_lat']);
      final lon = _num(r['centroid_lon']);
      out.add(
        TodayFarm(
          id: id,
          name: _str(r['name']) ?? 'مزرعة بلا اسم',
          centroid: (lat != null && lon != null)
              ? (lat.toDouble(), lon.toDouble())
              : null,
        ),
      );
    }
    return out;
  }
}

/// عنصر من طابور أولويّات المزرعة.
class PriorityItem {
  const PriorityItem({required this.type, this.fieldId, this.severity});

  final String type;
  final String? fieldId;
  final String? severity;

  static List<PriorityItem> listFrom(Object? raw) => [
    for (final r in _maps(raw))
      PriorityItem(
        type: _str(r['type']) ?? 'other',
        fieldId: _str(r['field_id']),
        severity: _str(r['severity']),
      ),
  ];
}

/// ملخّص الطقس الآن لنقطة مزرعة/حقل.
class TodayWeather {
  const TodayWeather({
    required this.placeAr,
    this.tempC,
    this.humidityPct,
    this.windKmh,
    this.rainMm,
    this.spraying,
    this.irrigation,
    this.alertsAr = const [],
    this.stale = false,
    this.upstreamError,
  });

  final String placeAr;
  final num? tempC;
  final num? humidityPct;
  final num? windKmh;
  final num? rainMm;

  /// optimal|acceptable|poor|unsafe كما يُصدرها الخادم.
  final String? spraying;
  final String? irrigation;
  final List<String> alertsAr;

  /// cache_state=stale: قراءة مخزّنة لدى الخادم لأنّ المصدر تعذّر.
  final bool stale;
  final String? upstreamError;

  static TodayWeather from(Map<String, dynamic> r, String placeAr) {
    final s = r['sample'] is Map
        ? Map<String, dynamic>.from(r['sample'] as Map)
        : const <String, dynamic>{};
    final ops = r['operations'] is Map
        ? Map<String, dynamic>.from(r['operations'] as Map)
        : const <String, dynamic>{};
    String? suit(String op) =>
        ops[op] is Map ? _str((ops[op] as Map)['suitability']) : null;
    return TodayWeather(
      placeAr: placeAr,
      tempC: _num(s['temperature_2m_c']),
      humidityPct: _num(s['relative_humidity_2m_pct']),
      windKmh: _num(s['wind_speed_10m_kmh']),
      rainMm: _num(s['precipitation_mm']),
      spraying: suit('spraying'),
      irrigation: suit('irrigation'),
      alertsAr: [
        if (r['alerts_ar'] is List)
          for (final a in r['alerts_ar'] as List)
            if (_str(a) != null) _str(a)!,
      ],
      stale: _str(r['cache_state']) == 'stale',
      upstreamError: _str(r['upstream_error']),
    );
  }
}
