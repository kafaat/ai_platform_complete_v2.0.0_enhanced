// SAHOOL — lib/widgets/workspace/workspace_sections.dart
// أقسام «مساحة عمل الحقل» الموحّدة (نظرة عامّة/موسم/أقمار/ريّ/أنشطة/تربة/طقس/خطّ
// زمنيّ). تستعمل حالات العرض الموحّدة (LoadingView/ErrorView/EmptyView) ونفس
// السمات الداكنة وRTL العربيّ. صدق: الأقسام التي لا تتوفّر لها واجهة برمجيّة بعد
// تُعرَض كـ«غير متاح بعد» بدل اختلاق بيانات. لا تستدعي إلّا دوال ApiService القائمة.
import 'package:flutter/material.dart';
import '../../services/api_service.dart';
import '../../permissions.dart';
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

// ── شارة حالة ملوّنة موحّدة (لِحالات الموسم/الإلحاح/الخطر/الفئة) ───────
/// شارة صغيرة بنصّ عربيّ ولون دلاليّ. تُعاد استخدامها عبر أقسام مساحة العمل.
class WBadge extends StatelessWidget {
  final String label;
  final Color color;
  const WBadge(this.label, this.color, {super.key});
  @override
  Widget build(BuildContext context) => Container(
        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
        decoration: BoxDecoration(
          color: color.withOpacity(0.16),
          borderRadius: BorderRadius.circular(8),
          border: Border.all(color: color.withOpacity(0.5)),
        ),
        child: Text(label,
            style: TextStyle(
                color: color, fontSize: 11, fontWeight: FontWeight.w700)),
      );
}

// ════════════════════════════════════════════════════════════════════
// قسم الموسم — يجلب GET /api/v1/fields/{id}/seasons (fetchFieldSeasons).
// بطاقة لكلّ موسم: المحاصيل، الصنف، حالة الموسم (شارة)، البذار، نهاية الموسم،
// الإنتاجيّة المستهدفة. صدق: لا مواسم ⇒ EmptyView بلا اختلاق.
// ════════════════════════════════════════════════════════════════════
class WSeasonSection extends StatefulWidget {
  final String fieldId;
  const WSeasonSection({super.key, required this.fieldId});
  @override
  State<WSeasonSection> createState() => _WSeasonSectionState();
}

class _WSeasonSectionState extends State<WSeasonSection> {
  late Future<List<Map<String, dynamic>>> _future;

  @override
  void initState() {
    super.initState();
    _future = _load();
  }

  Future<List<Map<String, dynamic>>> _load() =>
      ApiService.instance.fetchFieldSeasons(widget.fieldId);

  void _retry() => setState(() => _future = _load());

  static const _statusAr = {
    'planned': 'مُخطَّط',
    'active': 'نشط',
    'closed': 'مُغلَق',
  };
  static const _statusColor = {
    'planned': kSecondary,
    'active': kPrimary,
    'closed': Colors.grey,
  };

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<List<Map<String, dynamic>>>(
      future: _future,
      builder: (context, snap) {
        if (snap.connectionState != ConnectionState.done) {
          return const LoadingView();
        }
        if (snap.hasError) {
          return ErrorView(
              message: apiErrorMessage(snap.error!), onRetry: _retry);
        }
        final seasons = snap.data ?? const <Map<String, dynamic>>[];
        if (seasons.isEmpty) {
          return const EmptyView(
              message: 'لا مواسم لهذا الحقل بعد',
              icon: Icons.calendar_month);
        }
        return ListView(
          padding: const EdgeInsets.all(16),
          children: seasons.map((s) {
            final cropsRaw = s['crops'];
            final crops = cropsRaw is List
                ? cropsRaw.map((e) => e.toString()).join('، ')
                : wText(cropsRaw);
            final status = wText(s['status'], '');
            final target = wNum(s['target_yield_kg_ha']);
            return WSectionCard(
              title: crops.isEmpty ? 'موسم' : crops,
              icon: Icons.calendar_month,
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  if (status.isNotEmpty)
                    Padding(
                      padding: const EdgeInsets.only(bottom: 8),
                      child: Align(
                        alignment: AlignmentDirectional.centerStart,
                        child: WBadge(
                          _statusAr[status] ?? status,
                          _statusColor[status] ?? Colors.grey,
                        ),
                      ),
                    ),
                  WInfoRow('الصنف', wText(s['cultivar'])),
                  WInfoRow('تاريخ البذار', wText(s['sowing_date'])),
                  WInfoRow('نهاية الموسم', wText(s['season_end'])),
                  WInfoRow(
                    'الإنتاجيّة المستهدفة',
                    target != null
                        ? '${target.toStringAsFixed(0)} كغ/هـ'
                        : '—',
                  ),
                ],
              ),
            );
          }).toList(),
        );
      },
    );
  }
}

// ════════════════════════════════════════════════════════════════════
// قسم الأنشطة — يجلب GET /api/v1/fields/{id}/activities (fetchFieldActivities).
// صفّ لكلّ نشاط: العنوان العربيّ، نوع العمليّة (تسمية عربيّة)، الحالة (شارة)،
// التاريخ المُنفَّذ/المُجدوَل. صدق: لا أنشطة ⇒ EmptyView بلا اختلاق.
// ════════════════════════════════════════════════════════════════════


// نموذج إدخال سجلّ يومي من الموبايل — POST /api/v1/fields/{id}/activities.
class WAddActivityForm extends StatefulWidget {
  final String fieldId;
  final VoidCallback onSaved;
  const WAddActivityForm({super.key, required this.fieldId, required this.onSaved});
  @override
  State<WAddActivityForm> createState() => _WAddActivityFormState();
}

class _WAddActivityFormState extends State<WAddActivityForm> {
  final _title = TextEditingController();
  final _notes = TextEditingController();
  String _type = 'irrigation';
  DateTime? _performedOn;
  bool _saving = false;
  String? _error;

  static const _types = {
    'irrigation': 'ريّ',
    'fertilization': 'تسميد',
    'spraying': 'رشّ',
    'scouting': 'كشف ميدانيّ',
    'planting': 'زراعة/بذر',
    'pruning': 'تقليم',
    'harvest': 'حصاد',
  };

  @override
  void dispose() {
    _title.dispose();
    _notes.dispose();
    super.dispose();
  }

  String _date(DateTime d) =>
      '${d.year.toString().padLeft(4, '0')}-${d.month.toString().padLeft(2, '0')}-${d.day.toString().padLeft(2, '0')}';

  Future<void> _pickDate() async {
    final now = DateTime.now();
    final d = await showDatePicker(
      context: context,
      initialDate: _performedOn ?? now,
      firstDate: DateTime(now.year - 2),
      lastDate: DateTime(now.year + 1),
    );
    if (d != null && mounted) setState(() => _performedOn = d);
  }

  Future<void> _save() async {
    if (_saving) return;
    setState(() { _saving = true; _error = null; });
    try {
      await ApiService.instance.createFieldActivity(
        widget.fieldId,
        activityType: _type,
        titleAr: _title.text,
        performedOn: _performedOn == null ? _date(DateTime.now()) : _date(_performedOn!),
        notes: _notes.text,
      );
      if (!mounted) return;
      _title.clear();
      _notes.clear();
      setState(() => _performedOn = null);
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('تم تسجيل العملية في السجل اليومي')),
      );
      widget.onSaved();
    } catch (e) {
      if (!mounted) return;
      setState(() => _error = apiErrorMessage(e));
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return WSectionCard(
      title: 'إدخال سجلّ يومي',
      icon: Icons.add_task,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          DropdownButtonFormField<String>(
            value: _type,
            dropdownColor: kSurface,
            decoration: const InputDecoration(labelText: 'نوع العملية'),
            items: _types.entries
                .map((e) => DropdownMenuItem(value: e.key, child: Text(e.value)))
                .toList(),
            onChanged: (v) => setState(() => _type = v ?? _type),
          ),
          const SizedBox(height: 10),
          TextField(
            controller: _title,
            decoration: const InputDecoration(labelText: 'العنوان / الوصف المختصر'),
          ),
          const SizedBox(height: 10),
          TextField(
            controller: _notes,
            maxLines: 2,
            decoration: const InputDecoration(labelText: 'ملاحظات'),
          ),
          const SizedBox(height: 10),
          OutlinedButton.icon(
            onPressed: _pickDate,
            icon: const Icon(Icons.calendar_today),
            label: Text(_performedOn == null ? 'تاريخ التنفيذ: اليوم' : 'تاريخ التنفيذ: ${_date(_performedOn!)}'),
          ),
          if (_error != null) ...[
            const SizedBox(height: 8),
            Text(_error!, style: const TextStyle(color: Colors.redAccent, fontSize: 12)),
          ],
          const SizedBox(height: 10),
          ElevatedButton.icon(
            onPressed: _saving ? null : _save,
            style: ElevatedButton.styleFrom(backgroundColor: kPrimary),
            icon: _saving
                ? const SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2))
                : const Icon(Icons.check),
            label: Text(_saving ? 'جارٍ الحفظ…' : 'حفظ في السجل'),
          ),
        ],
      ),
    );
  }
}

class WActivitiesSection extends StatefulWidget {
  final String fieldId;
  const WActivitiesSection({super.key, required this.fieldId});
  @override
  State<WActivitiesSection> createState() => _WActivitiesSectionState();
}

class _WActivitiesSectionState extends State<WActivitiesSection> {
  late Future<List<Map<String, dynamic>>> _future;

  @override
  void initState() {
    super.initState();
    _future = _load();
  }

  Future<List<Map<String, dynamic>>> _load() =>
      ApiService.instance.fetchFieldActivities(widget.fieldId);

  void _retry() => setState(() => _future = _load());

  static const _typeAr = {
    'planting': 'بذر',
    'sowing': 'بذر',
    'irrigation': 'ريّ',
    'fertilizer': 'تسميد',
    'fertilization': 'تسميد',
    'spraying': 'رشّ',
    'pesticide': 'رشّ مبيد',
    'harvest': 'حصاد',
    'scouting': 'كشف ميدانيّ',
    'tillage': 'حراثة',
  };
  static const _statusAr = {
    'planned': 'مُخطَّط',
    'done': 'مُنجَز',
    'completed': 'مُنجَز',
  };
  static const _statusColor = {
    'planned': kSecondary,
    'done': kPrimary,
    'completed': kPrimary,
  };

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<List<Map<String, dynamic>>>(
      future: _future,
      builder: (context, snap) {
        if (snap.connectionState != ConnectionState.done) {
          return const LoadingView();
        }
        if (snap.hasError) {
          return ErrorView(
              message: apiErrorMessage(snap.error!), onRetry: _retry);
        }
        final activities = snap.data ?? const <Map<String, dynamic>>[];
        if (activities.isEmpty) {
          return ListView(
            padding: const EdgeInsets.all(16),
            children: [
              if (canMutate(currentRole()))
                WAddActivityForm(fieldId: widget.fieldId, onSaved: _retry),
              const SizedBox(height: 16),
              const EmptyView(
                  message: 'لا أنشطة مسجّلة بعد', icon: Icons.assignment),
            ],
          );
        }
        return ListView(
          padding: const EdgeInsets.all(16),
          children: [
            if (canMutate(currentRole()))
              WAddActivityForm(fieldId: widget.fieldId, onSaved: _retry),
            WSectionCard(
              title: 'أنشطة الحقل',
              icon: Icons.assignment,
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: activities.map((a) {
                  final type = wText(a['activity_type'], '');
                  final status = wText(a['status'], '');
                  final when = wText(
                      a['performed_on'] ?? a['scheduled_for'], '');
                  final typeAr = _typeAr[type] ?? type;
                  return Padding(
                    padding: const EdgeInsets.symmetric(vertical: 6),
                    child: Row(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Expanded(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(
                                wText(a['title_ar'],
                                    typeAr.isEmpty ? 'نشاط' : typeAr),
                                style: const TextStyle(
                                    color: Colors.white,
                                    fontSize: 13,
                                    fontWeight: FontWeight.w600),
                              ),
                              if (typeAr.isNotEmpty)
                                Padding(
                                  padding: const EdgeInsets.only(top: 2),
                                  child: Text(typeAr,
                                      style: const TextStyle(
                                          color: Colors.grey, fontSize: 11)),
                                ),
                              if (when.isNotEmpty && when != '—')
                                Padding(
                                  padding: const EdgeInsets.only(top: 2),
                                  child: Text(when,
                                      style: const TextStyle(
                                          color: Colors.grey, fontSize: 11)),
                                ),
                            ],
                          ),
                        ),
                        const SizedBox(width: 8),
                        if (status.isNotEmpty)
                          WBadge(
                            _statusAr[status] ?? status,
                            _statusColor[status] ?? Colors.grey,
                          ),
                      ],
                    ),
                  );
                }).toList(),
              ),
            ),
          ],
        );
      },
    );
  }
}

// ════════════════════════════════════════════════════════════════════
// قسم الطقس والإرشاد — يجلب توصية الريّ (irrigation-advice) ومخاطر الأمراض
// (disease-risk) معاً عبر fetchIrrigationAdvice/fetchDiseaseRisk. كلّ بطاقة
// مستقلّة: إن فشل أحد النداءين عُرِض خطؤه سطريّاً مع إبقاء الآخر (تدهور رشيق).
// صدق: لا اختلاق — الأرقام تأتي من الخادم أو لا تُعرَض.
// ════════════════════════════════════════════════════════════════════
class WWeatherSection extends StatefulWidget {
  final String fieldId;
  const WWeatherSection({super.key, required this.fieldId});
  @override
  State<WWeatherSection> createState() => _WWeatherSectionState();
}

class _WWeatherSectionState extends State<WWeatherSection> {
  late Future<Map<String, dynamic>> _irrigation;
  late Future<Map<String, dynamic>> _disease;

  @override
  void initState() {
    super.initState();
    _irrigation = _loadIrrigation();
    _disease = _loadDisease();
  }

  Future<Map<String, dynamic>> _loadIrrigation() =>
      ApiService.instance.fetchIrrigationAdvice(widget.fieldId);
  Future<Map<String, dynamic>> _loadDisease() =>
      ApiService.instance.fetchDiseaseRisk(widget.fieldId);

  void _retryIrrigation() =>
      setState(() => _irrigation = _loadIrrigation());
  void _retryDisease() => setState(() => _disease = _loadDisease());

  static const _urgencyAr = {
    'none': 'لا حاجة',
    'low': 'منخفض',
    'moderate': 'متوسّط',
    'high': 'عاجل',
  };
  static const _urgencyColor = {
    'none': Colors.grey,
    'low': kPrimary,
    'moderate': kWarn,
    'high': Color(0xFFD64545),
  };
  static const _riskAr = {
    'low': 'منخفض',
    'moderate': 'متوسّط',
    'high': 'مرتفع',
  };
  static const _riskColor = {
    'low': kPrimary,
    'moderate': kWarn,
    'high': Color(0xFFD64545),
  };

  Widget _subError(String message, VoidCallback onRetry) => Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text(message,
              style: const TextStyle(color: Colors.white70, fontSize: 13)),
          const SizedBox(height: 8),
          TextButton(onPressed: onRetry, child: const Text('إعادة المحاولة')),
        ],
      );

  @override
  Widget build(BuildContext context) {
    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        // ── بطاقة توصية الريّ ──
        FutureBuilder<Map<String, dynamic>>(
          future: _irrigation,
          builder: (context, snap) {
            return WSectionCard(
              title: 'توصية الريّ',
              icon: Icons.water_drop,
              child: Builder(
                builder: (_) {
                  if (snap.connectionState != ConnectionState.done) {
                    return const Padding(
                      padding: EdgeInsets.symmetric(vertical: 16),
                      child: LoadingView(),
                    );
                  }
                  if (snap.hasError) {
                    return _subError(
                        apiErrorMessage(snap.error!), _retryIrrigation);
                  }
                  final d = snap.data ?? const <String, dynamic>{};
                  final urgency = wText(d['urgency'], '');
                  final recommended = wNum(d['recommended_mm']);
                  final timing = wText(d['timing_ar']);
                  final rationale = wText(d['rationale_ar'], '');
                  return Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      if (urgency.isNotEmpty)
                        Padding(
                          padding: const EdgeInsets.only(bottom: 8),
                          child: Align(
                            alignment: AlignmentDirectional.centerStart,
                            child: WBadge(
                              _urgencyAr[urgency] ?? urgency,
                              _urgencyColor[urgency] ?? Colors.grey,
                            ),
                          ),
                        ),
                      WInfoRow(
                        'الكمّيّة الموصى بها',
                        recommended != null
                            ? '${recommended.toStringAsFixed(1)} مم'
                            : '—',
                      ),
                      WInfoRow('التوقيت', timing),
                      if (rationale.isNotEmpty && rationale != '—') ...[
                        const SizedBox(height: 8),
                        Text(rationale,
                            style: const TextStyle(
                                color: Colors.white70, fontSize: 12)),
                      ],
                    ],
                  );
                },
              ),
            );
          },
        ),
        // ── بطاقة مخاطر الأمراض ──
        FutureBuilder<Map<String, dynamic>>(
          future: _disease,
          builder: (context, snap) {
            return WSectionCard(
              title: 'مخاطر الأمراض',
              icon: Icons.coronavirus,
              child: Builder(
                builder: (_) {
                  if (snap.connectionState != ConnectionState.done) {
                    return const Padding(
                      padding: EdgeInsets.symmetric(vertical: 16),
                      child: LoadingView(),
                    );
                  }
                  if (snap.hasError) {
                    return _subError(
                        apiErrorMessage(snap.error!), _retryDisease);
                  }
                  final d = snap.data ?? const <String, dynamic>{};
                  final risk = wText(d['risk_level'], '');
                  final temp = wNum(d['temperature_c']);
                  final humidity = wNum(d['humidity_pct']);
                  final diseasesRaw = d['diseases_ar'];
                  final diseases = diseasesRaw is List
                      ? diseasesRaw.map((e) => e.toString()).toList()
                      : const <String>[];
                  final advice = wText(d['advice_ar'], '');
                  return Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      if (risk.isNotEmpty)
                        Padding(
                          padding: const EdgeInsets.only(bottom: 8),
                          child: Align(
                            alignment: AlignmentDirectional.centerStart,
                            child: WBadge(
                              _riskAr[risk] ?? risk,
                              _riskColor[risk] ?? Colors.grey,
                            ),
                          ),
                        ),
                      WInfoRow('الحرارة',
                          temp != null ? '${temp.toStringAsFixed(1)}°م' : '—'),
                      WInfoRow(
                          'الرطوبة',
                          humidity != null
                              ? '${humidity.toStringAsFixed(0)}٪'
                              : '—'),
                      if (diseases.isNotEmpty) ...[
                        const SizedBox(height: 8),
                        ...diseases.map((r) => Padding(
                              padding: const EdgeInsets.only(top: 4),
                              child: Text('• $r',
                                  style: const TextStyle(
                                      color: Colors.white70, fontSize: 12)),
                            )),
                      ],
                      if (advice.isNotEmpty && advice != '—') ...[
                        const SizedBox(height: 8),
                        Text(advice,
                            style: const TextStyle(
                                color: Colors.white70, fontSize: 12)),
                      ],
                    ],
                  );
                },
              ),
            );
          },
        ),
      ],
    );
  }
}

// ════════════════════════════════════════════════════════════════════
// قسم الخطّ الزمنيّ — يجلب GET /api/v1/fields/{id}/unified-timeline
// (fetchUnifiedTimeline). صفّ لكلّ حدث: الوقت + الملخّص العربيّ + شارة الفئة.
// صدق: لا أحداث ⇒ EmptyView؛ note_ar/error (تدهور القاعدة) يُعرَض كما هو.
// ════════════════════════════════════════════════════════════════════
class WTimelineSection extends StatefulWidget {
  final String fieldId;
  const WTimelineSection({super.key, required this.fieldId});
  @override
  State<WTimelineSection> createState() => _WTimelineSectionState();
}

class _WTimelineSectionState extends State<WTimelineSection> {
  late Future<Map<String, dynamic>> _future;

  @override
  void initState() {
    super.initState();
    _future = _load();
  }

  Future<Map<String, dynamic>> _load() =>
      ApiService.instance.fetchUnifiedTimeline(widget.fieldId);

  void _retry() => setState(() => _future = _load());

  static const _categoryAr = {
    'lifecycle': 'دورة الحياة',
    'operation': 'عمليّة',
    'observation': 'مشاهدة',
    'calibration': 'معايرة',
    'weather': 'طقس',
    'system': 'نظام',
  };
  static const _categoryColor = {
    'lifecycle': kSecondary,
    'operation': kPrimary,
    'observation': kWarn,
    'calibration': Color(0xFFA855F7),
    'weather': kSecondary,
    'system': Colors.grey,
  };

  // تنسيق وقت ISO ⇒ YYYY-MM-DD HH:mm (يتسامح مع صيغ أخرى).
  String _fmt(dynamic raw) {
    final s = wText(raw, '');
    if (s.isEmpty || s == '—') return '—';
    final dt = DateTime.tryParse(s);
    if (dt == null) return s;
    String two(int n) => n.toString().padLeft(2, '0');
    return '${dt.year}-${two(dt.month)}-${two(dt.day)} '
        '${two(dt.hour)}:${two(dt.minute)}';
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
        final data = snap.data ?? const <String, dynamic>{};
        final eventsRaw = data['events'];
        final events = eventsRaw is List
            ? eventsRaw.whereType<Map>().map((e) => e.cast<String, dynamic>())
                .toList()
            : const <Map<String, dynamic>>[];
        // تدهور رشيق صادق: القاعدة معطّلة ⇒ note_ar/error بدل اختلاق تاريخ.
        final note = wText(data['note_ar'] ?? data['error'], '');

        if (events.isEmpty) {
          if (note.isNotEmpty && note != '—') {
            return ListView(
              padding: const EdgeInsets.all(16),
              children: [
                WSectionCard(
                  title: 'الخطّ الزمنيّ',
                  icon: Icons.timeline,
                  child: Text(note,
                      textAlign: TextAlign.center,
                      style: const TextStyle(
                          color: Colors.white70, fontSize: 13)),
                ),
              ],
            );
          }
          return const EmptyView(
              message: 'لا أحداث بعد', icon: Icons.timeline);
        }

        return ListView(
          padding: const EdgeInsets.all(16),
          children: [
            if (note.isNotEmpty && note != '—')
              Padding(
                padding: const EdgeInsets.only(bottom: 8),
                child: InfoBanner(text: note),
              ),
            WSectionCard(
              title: 'الخطّ الزمنيّ',
              icon: Icons.timeline,
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: events.map((e) {
                  final category = wText(e['category'], '');
                  return Padding(
                    padding: const EdgeInsets.symmetric(vertical: 6),
                    child: Row(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Expanded(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(
                                wText(e['summary_ar'],
                                    wText(e['event_type'], 'حدث')),
                                style: const TextStyle(
                                    color: Colors.white, fontSize: 13),
                              ),
                              Padding(
                                padding: const EdgeInsets.only(top: 2),
                                child: Text(_fmt(e['timestamp']),
                                    style: const TextStyle(
                                        color: Colors.grey, fontSize: 11)),
                              ),
                            ],
                          ),
                        ),
                        const SizedBox(width: 8),
                        if (category.isNotEmpty)
                          WBadge(
                            _categoryAr[category] ?? category,
                            _categoryColor[category] ?? Colors.grey,
                          ),
                      ],
                    ),
                  );
                }).toList(),
              ),
            ),
          ],
        );
      },
    );
  }
}
