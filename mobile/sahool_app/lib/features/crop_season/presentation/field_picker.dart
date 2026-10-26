// SAHOOL — features/crop_season/presentation/field_picker.dart
// اختيار الحقل حين تُفتح الشاشة من «المزيد» بلا field_id. يقرأ قائمة الحقول عبر
// FieldsApi.listFields (قراءة عابرة مسموحة) ويُعيد الحقل المختار. تستعمله
// ميزتا المواسم وعيّنات المختبر (يملكهما الوكيل نفسه).
import 'package:flutter/material.dart';
import 'package:sahool_app/core/network/api_exception.dart';
import 'package:sahool_app/core/utils/formatters.dart';
import 'package:sahool_app/core/widgets/widgets.dart';
import 'package:sahool_app/features/fields/data/fields_api.dart';

/// مرجع حقل مختصر.
class FieldRef {
  const FieldRef({required this.fieldId, this.nameAr, this.areaHa, this.crop});
  final String fieldId;
  final String? nameAr;
  final double? areaHa;
  final String? crop;

  String get label => nameAr ?? fieldId;

  static FieldRef? fromJson(Map<String, dynamic> j) {
    final id = j['field_id']?.toString() ?? j['id']?.toString();
    if (id == null || id.isEmpty) return null;
    final a = j['area_ha'];
    return FieldRef(
      fieldId: id,
      nameAr: (j['name_ar'] ?? j['name'])?.toString(),
      areaHa: a is num ? a.toDouble() : null,
      crop: j['crop']?.toString(),
    );
  }
}

typedef FieldsLoader = Future<List<Map<String, dynamic>>> Function();

/// قائمة حقول قابلة للاختيار. [onPicked] يُستدعى بالحقل المختار.
class FieldPickerView extends StatefulWidget {
  const FieldPickerView({
    super.key,
    required this.onPicked,
    this.loader,
    this.hint = 'اختر الحقل',
  });

  final ValueChanged<FieldRef> onPicked;
  final FieldsLoader? loader;
  final String hint;

  @override
  State<FieldPickerView> createState() => _FieldPickerViewState();
}

class _FieldPickerViewState extends State<FieldPickerView> {
  late Future<List<FieldRef>> _future;

  @override
  void initState() {
    super.initState();
    _future = _load();
  }

  Future<List<FieldRef>> _load() async {
    final rows = await (widget.loader ?? FieldsApi.instance.listFields)();
    return rows.map(FieldRef.fromJson).whereType<FieldRef>().toList();
  }

  @override
  Widget build(BuildContext context) => FutureBuilder<List<FieldRef>>(
    future: _future,
    builder: (context, snap) {
      if (snap.connectionState != ConnectionState.done) {
        return const LoadingState(message: 'جارٍ تحميل الحقول…');
      }
      if (snap.hasError) {
        return ErrorState(
          error: ApiException.from(snap.error!),
          onRetry: () => setState(() => _future = _load()),
        );
      }
      final fields = snap.data!;
      if (fields.isEmpty) {
        return const EmptyState(
          title: 'لا حقول بعد',
          message: 'أضف حقلاً أوّلاً من تبويب «الحقول».',
          icon: Icons.layers_outlined,
        );
      }
      return ListView(
        children: [
          ListSectionHeader(widget.hint),
          for (final f in fields)
            AppListTile(
              title: f.label,
              subtitle: [
                if (f.crop != null && f.crop!.isNotEmpty) f.crop!,
                if (f.areaHa != null) fmtArea(f.areaHa),
              ].join(' · '),
              icon: Icons.grass_outlined,
              onTap: () => widget.onPicked(f),
            ),
        ],
      );
    },
  );
}
