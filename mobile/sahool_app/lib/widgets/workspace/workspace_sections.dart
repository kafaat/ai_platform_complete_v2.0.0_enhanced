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
      ],
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
          ],
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
