// SAHOOL — lib/widgets/workspace/workspace_sections.dart
// أقسام «مساحة عمل الحقل» الموحّدة (نظرة عامّة/موسم/أقمار/ريّ/أنشطة/تربة/طقس/خطّ
// زمنيّ). تستعمل حالات العرض الموحّدة (LoadingView/ErrorView/EmptyView) ونفس
// السمات الداكنة وRTL العربيّ. صدق: الأقسام التي لا تتوفّر لها واجهة برمجيّة بعد
// تُعرَض كـ«غير متاح بعد» بدل اختلاق بيانات. لا تستدعي إلّا دوال ApiService القائمة.
import 'package:flutter/material.dart';
import '../../services/api_service.dart';
import '../state_views.dart';

// ── أدوات تنسيق دفاعيّة مشتركة ──────────────────────────────────────
double? wNum(dynamic v) => v is num ? v.toDouble() : double.tryParse('$v');

String wText(dynamic v, [String fallback = '—']) {
  if (v == null) return fallback;
  final s = v.toString().trim();
  return s.isEmpty ? fallback : s;
}

/// بطاقة قسم موحّدة (عنوان + محتوى) بسمة داكنة.
class WSectionCard extends StatelessWidget {
  final String title;
  final IconData icon;
  final Widget child;
  const WSectionCard({
    super.key,
    required this.title,
    required this.icon,
    required this.child,
  });
  @override
  Widget build(BuildContext context) => Container(
        margin: const EdgeInsets.only(bottom: 12),
        padding: const EdgeInsets.all(16),
        decoration: BoxDecoration(
          color: kSurface,
          borderRadius: BorderRadius.circular(14),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Row(
              children: [
                Icon(icon, color: kPrimary, size: 18),
                const SizedBox(width: 8),
                Text(title,
                    style: const TextStyle(
                        color: Colors.white,
                        fontSize: 15,
                        fontWeight: FontWeight.bold)),
              ],
            ),
            const SizedBox(height: 12),
            child,
          ],
        ),
      );
}

/// صفّ معلومة (مفتاح/قيمة) موحّد.
class WInfoRow extends StatelessWidget {
  final String label;
  final String value;
  const WInfoRow(this.label, this.value, {super.key});
  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.symmetric(vertical: 5),
        child: Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            Text(label, style: const TextStyle(color: Colors.grey, fontSize: 13)),
            const SizedBox(width: 12),
            Flexible(
              child: Text(value,
                  textAlign: TextAlign.left,
                  style: const TextStyle(
                      color: Colors.white,
                      fontSize: 13,
                      fontWeight: FontWeight.w600)),
            ),
          ],
        ),
      );
}

/// قسم «غير متاح بعد» — صادق حين لا تتوفّر واجهة برمجيّة لهذه البيانات.
class WUnavailableSection extends StatelessWidget {
  final String title;
  final IconData icon;
  final String note;
  const WUnavailableSection({
    super.key,
    required this.title,
    required this.icon,
    this.note = 'لم تُربَط واجهة هذه البيانات بالخادم بعد.',
  });
  @override
  Widget build(BuildContext context) => ListView(
        padding: const EdgeInsets.all(16),
        children: [
          WSectionCard(
            title: title,
            icon: icon,
            child: Column(
              children: [
                const SizedBox(height: 8),
                const Icon(Icons.hourglass_empty, color: Colors.grey, size: 36),
                const SizedBox(height: 10),
                const Text('غير متاح بعد',
                    textAlign: TextAlign.center,
                    style: TextStyle(
                        color: Colors.white70,
                        fontSize: 14,
                        fontWeight: FontWeight.bold)),
                const SizedBox(height: 6),
                Text(note,
                    textAlign: TextAlign.center,
                    style: const TextStyle(color: Colors.grey, fontSize: 12)),
                const SizedBox(height: 8),
              ],
            ),
          ),
        ],
      );
}

// ════════════════════════════════════════════════════════════════════
// قسم النظرة العامّة — يُبنى من بيانات الحقل المُمرَّرة (من النظرة العامّة) +
// المؤشّرات الحيّة إن توفّرت. لا طلب شبكة إضافيّ هنا (يصل جاهزاً من الشاشة).
// ════════════════════════════════════════════════════════════════════
class WOverviewSection extends StatelessWidget {
  final Map<String, dynamic> field;
  const WOverviewSection({super.key, required this.field});

  int? _daysSince(dynamic raw) {
    if (raw == null) return null;
    final dt = DateTime.tryParse(raw.toString());
    if (dt == null) return null;
    return DateTime.now().difference(dt).inDays;
  }

  @override
  Widget build(BuildContext context) {
    final name = wText(field['field_name'] ?? field['name'], 'حقل');
    final crop = wText(field['crop_ar'] ?? field['crop']);
    final stage = wText(field['stage_ar'] ?? field['stage'] ?? field['phenology']);
    final ndvi = wNum(field['ndvi']);
    final area = wNum(field['area_ha'] ?? field['area']);
    final days = _daysSince(field['sowing_date'] ??
        field['planting_date'] ??
        field['sown_at']);
    final alerts = wNum(field['active_alerts'] ??
        field['alerts_count'] ??
        field['alert_count']);
    final fieldId = wText(field['field_id'] ?? field['id'], '');

    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        WSectionCard(
          title: name,
          icon: Icons.eco,
          child: Column(
            children: [
              WInfoRow('المحصول', crop),
              WInfoRow('المرحلة', stage),
              WInfoRow(
                  'أيّام منذ الزراعة', days != null ? '$days يوم' : '—'),
              WInfoRow('المساحة',
                  area != null ? '${area.toStringAsFixed(1)} هـ' : '—'),
              WInfoRow('NDVI', ndvi != null ? ndvi.toStringAsFixed(2) : '—'),
              WInfoRow('تنبيهات نشطة',
                  alerts != null ? alerts.toInt().toString() : '0'),
            ],
          ),
        ),
        // الحالة القانونيّة الموحّدة (Canonical Field State) — مصدر الحقيقة الواحد
        // الذي تمرّ عبره القرارات. يُجلب حيّاً لكلّ حقل (إن توفّر معرّفه).
        if (fieldId.isNotEmpty) WFieldStateSection(fieldId: fieldId),
      ],
    );
  }
}

// ════════════════════════════════════════════════════════════════════
// قسم الحالة القانونيّة الموحّدة — يجلب GET /api/v1/fields/{id}/state ويعرض
// صلاحيّة القرار + نمط التنفيذ + الحقائق الزراعيّة (حيويّة المحصول/الملوحة) مع
// الأسباب العربيّة. صدق: غياب الحالة ⇒ حالة فارغة/خطأ صريحة بلا اختلاق. مضمّن
// داخل ListView النظرة العامّة فيُعيد بطاقة (لا ListView متداخلاً).
// ════════════════════════════════════════════════════════════════════
class WFieldStateSection extends StatefulWidget {
  final String fieldId;
  const WFieldStateSection({super.key, required this.fieldId});
  @override
  State<WFieldStateSection> createState() => _WFieldStateSectionState();
}

class _WFieldStateSectionState extends State<WFieldStateSection> {
  late Future<Map<String, dynamic>> _future;

  @override
  void initState() {
    super.initState();
    _future = _load();
  }

  Future<Map<String, dynamic>> _load() =>
      ApiService.instance.getFieldState(widget.fieldId);

  void _retry() => setState(() => _future = _load());

  static const _validityAr = {
    'valid': 'صالحة',
    'degraded': 'متدهورة',
    'conflicted': 'متعارضة',
    'insufficient': 'بيانات ناقصة',
  };
  static const _execAr = {
    'auto': 'تلقائيّ',
    'human_review': 'يحتاج مراجعة بشريّة',
    'blocked': 'محجوب',
  };
  static const _salAr = {
    'normal': 'طبيعيّة',
    'low': 'منخفضة',
    'moderate': 'متوسّطة',
    'high': 'عالية',
    'critical': 'حرجة',
  };

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<Map<String, dynamic>>(
      future: _future,
      builder: (context, snap) {
        if (snap.connectionState != ConnectionState.done) {
          return const Padding(
            padding: EdgeInsets.symmetric(vertical: 24),
            // kPrimary لتوحيد التباين مع السمة الداكنة (كبقيّة الشاشات/LoadingView).
            child: Center(child: CircularProgressIndicator(color: kPrimary)),
          );
        }
        if (snap.hasError) {
          return WSectionCard(
            title: 'الحالة القانونيّة الموحّدة',
            icon: Icons.verified,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Text(apiErrorMessage(snap.error!),
                    style: const TextStyle(color: Colors.white70, fontSize: 13)),
                const SizedBox(height: 8),
                TextButton(
                    onPressed: _retry, child: const Text('إعادة المحاولة')),
              ],
            ),
          );
        }
        final s = snap.data ?? const <String, dynamic>{};
        final validity = wText(s['validity'], 'insufficient');
        final exec = wText(s['execution_mode']);
        final agronomic = s['agronomic'];
        final truths =
            (agronomic is Map && agronomic['operational_truths'] is Map)
                ? (agronomic['operational_truths'] as Map)
                    .cast<String, dynamic>()
                : const <String, dynamic>{};
        final vigor = truths['crop_vigor'];
        final sal = wText(truths['salinity_class'], '');
        final reasons = (s['reasons_ar'] is List)
            ? (s['reasons_ar'] as List).map((e) => e.toString()).toList()
            : const <String>[];

        return WSectionCard(
          title: 'الحالة القانونيّة الموحّدة',
          icon: Icons.verified,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              WInfoRow('صلاحيّة القرار', _validityAr[validity] ?? validity),
              WInfoRow('نمط التنفيذ', _execAr[exec] ?? exec),
              if (vigor != null)
                WInfoRow(
                    'حيويّة المحصول',
                    vigor is num
                        ? vigor.toStringAsFixed(2)
                        : wText(vigor)),
              if (sal.isNotEmpty)
                WInfoRow('ملوحة التربة', _salAr[sal] ?? sal),
              if (reasons.isNotEmpty) ...[
                const SizedBox(height: 8),
                ...reasons.map((r) => Padding(
                      padding: const EdgeInsets.only(top: 4),
                      child: Text('• $r',
                          style: const TextStyle(
                              color: Colors.white70, fontSize: 12)),
                    )),
              ],
            ],
          ),
        );
      },
    );
  }
}

// ════════════════════════════════════════════════════════════════════
// قسم الأقمار/NDVI — يجلب المؤشّرات الحيّة عبر getFieldIndicators (موجود).
// ════════════════════════════════════════════════════════════════════
class WSatelliteSection extends StatefulWidget {
  final String fieldId;
  const WSatelliteSection({super.key, required this.fieldId});
  @override
  State<WSatelliteSection> createState() => _WSatelliteSectionState();
}

class _WSatelliteSectionState extends State<WSatelliteSection> {
  late Future<Map<String, dynamic>> _future;

  @override
  void initState() {
    super.initState();
    _future = _load();
  }

  Future<Map<String, dynamic>> _load() =>
      ApiService.instance.getFieldIndicators(widget.fieldId);

  void _retry() => setState(() => _future = _load());

  List<MapEntry<String, String>> _parse(Map<String, dynamic> data) {
    final out = <MapEntry<String, String>>[];
    // الشكل الثالث (المصدر الفعليّ — vegetation /v1/analyze): خريطة indices حيث
    // كلّ مفتاح (ndvi/evi/...) → {value, unit, source}. نضيف صفّ «الحالة» من
    // health['label_ar'] أوّلاً (مصدر واحد للصحّة) ثمّ كلّ مؤشّر بقيمته ووحدته.
    final indices = data['indices'];
    if (indices is Map) {
      final health = data['health'];
      if (health is Map) {
        final statusAr = wText(health['label_ar'] ?? health['status'], '');
        if (statusAr.isNotEmpty) out.add(MapEntry('الحالة', statusAr));
      }
      indices.forEach((k, v) {
        if (v is! Map) return;
        final inner = v.cast<String, dynamic>();
        final value = inner['value'];
        final unit = wText(inner['unit'], '');
        final vStr = value is num
            ? value.toStringAsFixed(value.abs() < 1 ? 3 : 2)
            : wText(value);
        out.add(MapEntry(
            k.toString().toUpperCase(), unit.isEmpty ? vStr : '$vStr $unit'));
      });
      if (out.isNotEmpty) return out;
    }
    final list = data['indicators'];
    if (list is List) {
      for (final m in list.whereType<Map>()) {
        final mm = m.cast<String, dynamic>();
        final name = wText(mm['name_ar'] ?? mm['name'] ?? mm['id']);
        final value = mm['value'];
        final unit = wText(mm['unit'], '');
        final v = value is num
            ? value.toStringAsFixed(value.abs() < 1 ? 3 : 2)
            : wText(value);
        out.add(MapEntry(name, unit.isEmpty ? v : '$v $unit'));
      }
      return out;
    }
    data.forEach((k, v) {
      if (v is num) {
        out.add(MapEntry(k.toUpperCase(),
            v.toStringAsFixed(v.abs() < 1 ? 3 : 2)));
      }
    });
    return out;
  }

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<Map<String, dynamic>>(
      future: _future,
      builder: (context, snap) {
        if (snap.connectionState != ConnectionState.done) {
          return const LoadingView();
        }
        if (snap.hasError) {
          return ErrorView(
              message: apiErrorMessage(snap.error!), onRetry: _retry);
        }
        final indicators = _parse(snap.data ?? const {});
        if (indicators.isEmpty) {
          return const EmptyView(
              message: 'لا مؤشّرات أقمار متاحة لهذا الحقل',
              icon: Icons.satellite_alt);
        }
        return ListView(
          padding: const EdgeInsets.all(16),
          children: [
            WSectionCard(
              title: 'مؤشّرات الأقمار',
              icon: Icons.satellite_alt,
              child: Column(
                children: indicators
                    .map((e) => WInfoRow(e.key, e.value))
                    .toList(),
              ),
            ),
            // شريط NDVI الزمنيّ الأفقيّ (بطاقات بالتاريخ) أسفل المؤشّرات الحاليّة.
            WNdviTimelineStrip(fieldId: widget.fieldId),
          ],
        );
      },
    );
  }
}

// ════════════════════════════════════════════════════════════════════
// شريط NDVI زمنيّ أفقيّ بنمط Climate FieldView — يجلب السلسلة الزمنيّة عبر
// getFieldNdviTimeseries ويعرض بطاقات لكلّ تاريخ (تاريخ + قيمة NDVI ملوّنة).
// قابل للتمرير أفقيّاً، ديناميكيّ بالبيانات (يُصيَّر ما يُرجِعه الخادم فقط، لا
// تواريخ ثابتة، وينمو تلقائيّاً)، البطاقة المختارة مُحدَّدة بإطار. مفتاح «إخفاء
// الأيّام الغائمة» يُخفي النقاط ذات cloudy_pct > 50 (يُعطَّل إن غاب المفتاح).
// صدق: available=false/لا نقاط ⇒ حالة «غير متاح» بلا اختلاق، ولا تراكب خريطة.
// ════════════════════════════════════════════════════════════════════
class WNdviTimelineStrip extends StatefulWidget {
  final String fieldId;
  const WNdviTimelineStrip({super.key, required this.fieldId});
  @override
  State<WNdviTimelineStrip> createState() => _WNdviTimelineStripState();
}

class _WNdviTimelineStripState extends State<WNdviTimelineStrip> {
  late Future<List<Map<String, dynamic>>> _future;
  int _selected = -1;
  bool _hideCloudy = false;

  @override
  void initState() {
    super.initState();
    _future = _load();
  }

  Future<List<Map<String, dynamic>>> _load() =>
      ApiService.instance.getFieldNdviTimeseries(widget.fieldId);

  void _retry() => setState(() {
        _selected = -1;
        _future = _load();
      });

  // مقياس لون NDVI بسيط أحمر→أصفر→أخضر (لا اعتماد خارجيّ).
  Color _ndviColor(double? v) {
    if (v == null) return Colors.grey;
    final t = v.clamp(0.0, 1.0);
    if (t < 0.5) {
      // أحمر → أصفر
      return Color.lerp(const Color(0xFFD64545), const Color(0xFFE0B341),
          (t / 0.5).clamp(0.0, 1.0))!;
    }
    // أصفر → أخضر (kPrimary)
    return Color.lerp(const Color(0xFFE0B341), kPrimary,
        ((t - 0.5) / 0.5).clamp(0.0, 1.0))!;
  }

  // تاريخ مختصر YYYY-MM-DD ⇒ MM-DD (يتسامح مع صيغ أخرى).
  String _shortDate(dynamic raw) {
    final s = wText(raw, '');
    if (s.isEmpty || s == '—') return '—';
    final dt = DateTime.tryParse(s);
    if (dt != null) {
      final mm = dt.month.toString().padLeft(2, '0');
      final dd = dt.day.toString().padLeft(2, '0');
      return '$mm-$dd';
    }
    // احتياطيّ: خذ آخر 5 محارف لو بدت كتاريخ نصّيّ
    return s.length >= 10 ? s.substring(5, 10) : s;
  }

  bool _anyCloud(List<Map<String, dynamic>> pts) =>
      pts.any((p) => p['cloudy_pct'] != null);

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<List<Map<String, dynamic>>>(
      future: _future,
      builder: (context, snap) {
        if (snap.connectionState != ConnectionState.done) {
          return const WSectionCard(
            title: 'خطّ NDVI الزمنيّ',
            icon: Icons.timeline,
            child: Padding(
              padding: EdgeInsets.symmetric(vertical: 16),
              child: LoadingView(),
            ),
          );
        }
        if (snap.hasError) {
          return WSectionCard(
            title: 'خطّ NDVI الزمنيّ',
            icon: Icons.timeline,
            child: Column(
              children: [
                Text(apiErrorMessage(snap.error!),
                    textAlign: TextAlign.center,
                    style: const TextStyle(color: Colors.white70, fontSize: 12)),
                const SizedBox(height: 10),
                ElevatedButton(
                  onPressed: _retry,
                  style: ElevatedButton.styleFrom(backgroundColor: kPrimary),
                  child: const Text('إعادة المحاولة'),
                ),
              ],
            ),
          );
        }

        final all = snap.data ?? const <Map<String, dynamic>>[];
        // صدق: لا نقاط (available=false أو points فارغة) ⇒ حالة «غير متاح».
        if (all.isEmpty) {
          return WSectionCard(
            title: 'خطّ NDVI الزمنيّ',
            icon: Icons.timeline,
            child: Column(
              children: const [
                SizedBox(height: 8),
                Icon(Icons.hourglass_empty, color: Colors.grey, size: 32),
                SizedBox(height: 10),
                Text('لا سلسلة NDVI زمنيّة متاحة لهذا الحقل بعد',
                    textAlign: TextAlign.center,
                    style: TextStyle(color: Colors.white70, fontSize: 13)),
                SizedBox(height: 4),
                Text('تظهر البطاقات تلقائيّاً عند توفّر مشاهد مقصوصة للحقل.',
                    textAlign: TextAlign.center,
                    style: TextStyle(color: Colors.grey, fontSize: 11)),
                SizedBox(height: 8),
              ],
            ),
          );
        }

        final hasCloud = _anyCloud(all);
        // تطبيق فلتر «إخفاء الأيّام الغائمة» (cloudy_pct > 50) إن توفّر المفتاح.
        final points = (_hideCloudy && hasCloud)
            ? all.where((p) {
                final c = wNum(p['cloudy_pct']);
                return c == null || c <= 50;
              }).toList()
            : all;

        // ضبط المؤشّر المختار ضمن الحدود (آخر نقطة افتراضاً = الأحدث).
        if (points.isNotEmpty &&
            (_selected < 0 || _selected >= points.length)) {
          _selected = points.length - 1;
        }
        final selected = (_selected >= 0 && _selected < points.length)
            ? points[_selected]
            : null;
        final selMean = selected != null ? wNum(selected['mean']) : null;

        return WSectionCard(
          title: 'خطّ NDVI الزمنيّ',
          icon: Icons.timeline,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              // ملخّص التاريخ المختار (يتحدّث عند اللمس) — لا تراكب خريطة.
              WInfoRow(
                'التاريخ المختار',
                selected != null
                    ? wText(selected['datetime'])
                    : '—',
              ),
              WInfoRow(
                'متوسّط NDVI',
                selMean != null ? selMean.toStringAsFixed(2) : '—',
              ),
              const SizedBox(height: 8),
              // مفتاح إخفاء الأيّام الغائمة — يُعطَّل بلطف إن غاب cloudy_pct.
              Row(
                children: [
                  const Expanded(
                    child: Text('إخفاء الأيّام الغائمة',
                        style: TextStyle(color: Colors.grey, fontSize: 13)),
                  ),
                  Switch(
                    value: _hideCloudy && hasCloud,
                    onChanged: hasCloud
                        ? (v) => setState(() => _hideCloudy = v)
                        : null,
                    activeColor: kPrimary,
                  ),
                ],
              ),
              if (!hasCloud)
                const Padding(
                  padding: EdgeInsets.only(bottom: 4),
                  child: Text('نسبة الغيوم غير متوفّرة في هذه البيانات.',
                      style: TextStyle(color: Colors.grey, fontSize: 11)),
                ),
              const SizedBox(height: 8),
              if (points.isEmpty)
                const Padding(
                  padding: EdgeInsets.symmetric(vertical: 12),
                  child: Text('كلّ الأيّام المتاحة غائمة — أوقف الفلتر لعرضها.',
                      textAlign: TextAlign.center,
                      style: TextStyle(color: Colors.grey, fontSize: 12)),
                )
              else
                SizedBox(
                  height: 86,
                  child: ListView.builder(
                    scrollDirection: Axis.horizontal,
                    itemCount: points.length,
                    itemBuilder: (context, i) {
                      final p = points[i];
                      final mean = wNum(p['mean']);
                      final isSel = i == _selected;
                      return GestureDetector(
                        onTap: () => setState(() => _selected = i),
                        child: Container(
                          width: 72,
                          margin: const EdgeInsets.only(left: 8),
                          padding: const EdgeInsets.symmetric(
                              horizontal: 6, vertical: 8),
                          decoration: BoxDecoration(
                            color: kBg,
                            borderRadius: BorderRadius.circular(10),
                            border: Border.all(
                              color: isSel ? kPrimary : Colors.transparent,
                              width: 2,
                            ),
                          ),
                          child: Column(
                            mainAxisAlignment: MainAxisAlignment.center,
                            children: [
                              Text(_shortDate(p['datetime']),
                                  style: const TextStyle(
                                      color: Colors.white70, fontSize: 11)),
                              const SizedBox(height: 6),
                              Container(
                                width: 28,
                                height: 28,
                                decoration: BoxDecoration(
                                  color: _ndviColor(mean),
                                  shape: BoxShape.circle,
                                ),
                              ),
                              const SizedBox(height: 6),
                              Text(
                                mean != null ? mean.toStringAsFixed(2) : '—',
                                style: const TextStyle(
                                    color: Colors.white,
                                    fontSize: 12,
                                    fontWeight: FontWeight.w600),
                              ),
                            ],
                          ),
                        ),
                      );
                    },
                  ),
                ),
            ],
          ),
        );
      },
    );
  }
}

// ════════════════════════════════════════════════════════════════════
// قسم الريّ — معلومات نوع الريّ من بيانات الحقل + جداول الريّ الحيّة للحقل
// عبر listSchedules(fieldId) (موجود ويقبل field_id).
// ════════════════════════════════════════════════════════════════════
class WIrrigationSection extends StatefulWidget {
  final String fieldId;
  final Map<String, dynamic> field;
  const WIrrigationSection(
      {super.key, required this.fieldId, required this.field});
  @override
  State<WIrrigationSection> createState() => _WIrrigationSectionState();
}

class _WIrrigationSectionState extends State<WIrrigationSection> {
  late Future<List<Map<String, dynamic>>> _future;

  @override
  void initState() {
    super.initState();
    _future = _load();
  }

  Future<List<Map<String, dynamic>>> _load() =>
      ApiService.instance.listSchedules(fieldId: widget.fieldId);

  void _retry() => setState(() => _future = _load());

  @override
  Widget build(BuildContext context) {
    final type = wText(
        widget.field['irrigation_type_ar'] ?? widget.field['irrigation_type']);
    final water = wText(
        widget.field['water_source_ar'] ?? widget.field['water_source']);
    return FutureBuilder<List<Map<String, dynamic>>>(
      future: _future,
      builder: (context, snap) {
        final loading = snap.connectionState != ConnectionState.done;
        return ListView(
          padding: const EdgeInsets.all(16),
          children: [
            const InfoBanner(
              text:
                  'تغيير حالة الصمّامات يجري من شاشة الري التشغيلي — هنا عرض فقط.',
            ),
            const SizedBox(height: 12),
            WSectionCard(
              title: 'معلومات الريّ',
              icon: Icons.water_drop,
              child: Column(
                children: [
                  WInfoRow('نوع الريّ', type),
                  WInfoRow('مصدر المياه', water),
                ],
              ),
            ),
            WSectionCard(
              title: 'جداول الريّ',
              icon: Icons.schedule,
              child: Builder(
                builder: (_) {
                  if (loading) {
                    return const Padding(
                      padding: EdgeInsets.symmetric(vertical: 16),
                      child: LoadingView(),
                    );
                  }
                  if (snap.hasError) {
                    return Column(
                      children: [
                        Text(apiErrorMessage(snap.error!),
                            textAlign: TextAlign.center,
                            style: const TextStyle(
                                color: Colors.white70, fontSize: 12)),
                        const SizedBox(height: 10),
                        ElevatedButton(
                          onPressed: _retry,
                          style: ElevatedButton.styleFrom(
                              backgroundColor: kPrimary),
                          child: const Text('إعادة المحاولة'),
                        ),
                      ],
                    );
                  }
                  final schedules = snap.data ?? const [];
                  if (schedules.isEmpty) {
                    return const Padding(
                      padding: EdgeInsets.symmetric(vertical: 8),
                      child: Text('لا جداول ريّ مرتبطة بهذا الحقل',
                          textAlign: TextAlign.center,
                          style: TextStyle(color: Colors.grey, fontSize: 13)),
                    );
                  }
                  return Column(
                    children: schedules.map((s) {
                      final enabled = s['enabled'] == true;
                      return Padding(
                        padding: const EdgeInsets.symmetric(vertical: 6),
                        child: Row(
                          children: [
                            Icon(Icons.schedule,
                                color: enabled ? kPrimary : Colors.grey,
                                size: 18),
                            const SizedBox(width: 10),
                            Expanded(
                              child: Text(wText(s['name']),
                                  style: const TextStyle(
                                      color: Colors.white, fontSize: 13)),
                            ),
                            Text(
                              '${wText(s['start_time'], '')} · ${s['duration_min'] ?? 0} د',
                              style: const TextStyle(
                                  color: Colors.grey, fontSize: 12),
                            ),
                          ],
                        ),
                      );
                    }).toList(),
                  );
                },
              ),
            ),
          ],
        );
      },
    );
  }
}

// ════════════════════════════════════════════════════════════════════
// قسم التربة — يُبنى من بيانات الحقل المتاحة (نوع التربة + كيمياء إن وُجدت).
// لا توجد واجهة كيمياء تربة متقدّمة في ApiService بعد ⇒ يُعرَض المتاح فقط.
// ════════════════════════════════════════════════════════════════════
class WSoilSection extends StatelessWidget {
  final Map<String, dynamic> field;
  const WSoilSection({super.key, required this.field});

  @override
  Widget build(BuildContext context) {
    final soilType = wText(field['soil_type_ar'] ?? field['soil_type']);
    // كيمياء متقدّمة إن أرسلها الخادم ضمن بيانات الحقل (لا اختلاق).
    final ph = wNum(field['soil_ph'] ?? field['ph']);
    final ec = wNum(field['soil_ec'] ?? field['ec']);
    final om = wNum(field['organic_matter'] ?? field['soil_om']);
    final n = wNum(field['nitrogen'] ?? field['soil_n']);
    final p = wNum(field['phosphorus'] ?? field['soil_p']);
    final k = wNum(field['potassium'] ?? field['soil_k']);

    final chem = <Widget>[
      if (ph != null) WInfoRow('درجة الحموضة (pH)', ph.toStringAsFixed(1)),
      if (ec != null) WInfoRow('التوصيل الكهربائيّ (EC)', ec.toStringAsFixed(2)),
      if (om != null) WInfoRow('المادّة العضويّة', '${om.toStringAsFixed(1)}%'),
      if (n != null) WInfoRow('النيتروجين (N)', n.toStringAsFixed(1)),
      if (p != null) WInfoRow('الفوسفور (P)', p.toStringAsFixed(1)),
      if (k != null) WInfoRow('البوتاسيوم (K)', k.toStringAsFixed(1)),
    ];

    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        WSectionCard(
          title: 'التربة',
          icon: Icons.landscape,
          child: Column(
            children: [WInfoRow('نوع التربة', soilType)],
          ),
        ),
        WSectionCard(
          title: 'الكيمياء المتقدّمة',
          icon: Icons.science,
          child: chem.isEmpty
              ? const Padding(
                  padding: EdgeInsets.symmetric(vertical: 8),
                  child: Text('غير متاح بعد — لم تُرسَل بيانات كيمياء التربة.',
                      textAlign: TextAlign.center,
                      style: TextStyle(color: Colors.grey, fontSize: 12)),
                )
              : Column(children: chem),
        ),
      ],
    );
  }
}
