// SAHOOL — features/advisor/presentation/widgets/field_picker.dart
// ورقة اختيار حقل (المحادثة/التوصيات/تصعيد الآفة): قائمة كبيرة اللمس بدل كتابة
// معرّف. المصدر GET /api/v1/fields (FieldsApi.listFields — قراءة عبر الميزات).
import 'package:flutter/material.dart';
import 'package:sahool_app/core/network/api_exception.dart';
import 'package:sahool_app/core/theme/sahool_tokens.dart';
import 'package:sahool_app/core/theme/tokens.dart';
import 'package:sahool_app/core/widgets/widgets.dart';
import 'package:sahool_app/features/fields/data/fields_api.dart';

/// حقل مختار بما يلزم المستشار من FieldSummary (field_models.py).
class FieldChoice {
  const FieldChoice({
    required this.id,
    required this.name,
    this.crop,
    this.farmId,
  });

  final String id;
  final String name;
  final String? crop;
  final String? farmId;

  static FieldChoice? fromJson(Map<String, dynamic> m) {
    final id = (m['field_id'] ?? m['id'])?.toString();
    if (id == null || id.isEmpty) return null;
    String? s(Object? v) {
      final t = v?.toString().trim();
      return (t == null || t.isEmpty) ? null : t;
    }

    return FieldChoice(
      id: id,
      name: s(m['name_ar']) ?? s(m['name']) ?? id,
      crop: s(m['crop']),
      farmId: s(m['farm_id']),
    );
  }
}

typedef FieldLoader = Future<List<Map<String, dynamic>>> Function();

Future<List<Map<String, dynamic>>> _defaultLoader() =>
    FieldsApi.instance.listFields();

/// يفتح الورقة ويُرجع الحقل المختار (أو null عند الإغلاق).
Future<FieldChoice?> pickField(BuildContext context, {FieldLoader? loader}) =>
    showAppBottomSheet<FieldChoice>(
      context,
      builder: (_) => FieldPickerSheet(loader: loader ?? _defaultLoader),
    );

class FieldPickerSheet extends StatefulWidget {
  const FieldPickerSheet({super.key, required this.loader});
  final FieldLoader loader;

  @override
  State<FieldPickerSheet> createState() => _FieldPickerSheetState();
}

class _FieldPickerSheetState extends State<FieldPickerSheet> {
  late Future<List<FieldChoice>> _future;

  @override
  void initState() {
    super.initState();
    _future = _load();
  }

  Future<List<FieldChoice>> _load() async => (await widget.loader())
      .map(FieldChoice.fromJson)
      .whereType<FieldChoice>()
      .toList();

  @override
  Widget build(BuildContext context) => AppSheet(
    title: 'اختر الحقل',
    children: [
      const SizedBox(height: SahoolSpacing.md),
      FutureBuilder<List<FieldChoice>>(
        future: _future,
        builder: (context, snap) {
          if (snap.connectionState != ConnectionState.done) {
            return const SizedBox(
              height: 160,
              child: LoadingState(message: 'جارٍ تحميل الحقول…'),
            );
          }
          if (snap.hasError) {
            return ErrorState(
              error: ApiException.from(snap.error!),
              onRetry: () => setState(() => _future = _load()),
            );
          }
          final fields = snap.data ?? const [];
          if (fields.isEmpty) {
            return const EmptyState(
              message: 'لا حقول متاحة — أنشئ حقلاً أوّلاً من «الحقول».',
              icon: Icons.grass_outlined,
            );
          }
          return Column(
            children: [
              for (final f in fields)
                AppListTile(
                  title: f.name,
                  subtitle: f.crop,
                  icon: Icons.grass_outlined,
                  iconColor: context.tokens.success,
                  onTap: () => Navigator.of(context).pop(f),
                ),
            ],
          );
        },
      ),
    ],
  );
}
