// SAHOOL — features/satellite/presentation/satellite_screen.dart
// شاشة الأقمار: اختيار حقل (من GET /api/v1/fields) ثمّ لوحة مؤشّراته (بطاقات +
// مبدّل NDVI/NDWI/… من الكتالوج + رسم زمنيّ). زرّ تحديث صور Sentinel-2 يُطلق
// المعالجة الحقيقيّة ويُبلِغ بنتيجتها كما هي. طبقة الخريطة ملك ميزة الخرائط.
//
// التبديل السريع بين الحقول آمن: FieldIndicatorsCubit يُهمل الردود المتأخّرة.
import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:sahool_app/core/network/api_exception.dart';
import 'package:sahool_app/core/permissions/permissions.dart';
import 'package:sahool_app/core/theme/sahool_tokens.dart';
import 'package:sahool_app/core/theme/tokens.dart';
import 'package:sahool_app/core/widgets/widgets.dart';
import 'package:sahool_app/features/fields/data/fields_api.dart';
import 'package:sahool_app/features/fields/presentation/common/field_labels.dart';
import 'package:sahool_app/features/fields/presentation/common/load_cubit.dart';
import 'package:sahool_app/features/satellite/data/satellite_api.dart';

import 'field_indicators_cubit.dart';
import 'field_indicators_panel.dart';

class SatelliteScreen extends StatelessWidget {
  const SatelliteScreen({
    super.key,
    this.initialFieldId,
    this.api,
    this.fieldsApi,
    this.role,
  });

  final String? initialFieldId;
  final SatelliteApi? api;
  final FieldsApi? fieldsApi;

  /// الدور (للاختبار)؛ افتراضيّاً من الجلسة.
  final AppRole Function()? role;

  @override
  Widget build(BuildContext context) {
    final satellite = api ?? SatelliteApi.instance;
    final fields = fieldsApi ?? FieldsApi.instance;
    return MultiBlocProvider(
      providers: [
        BlocProvider(
          create: (_) =>
              LoadCubit<List<Map<String, dynamic>>>(fields.listFields)..load(),
        ),
        BlocProvider(
          create: (_) => FieldIndicatorsCubit(satellite)..loadCatalog(),
        ),
      ],
      child: _SatelliteView(
        api: satellite,
        initialFieldId: initialFieldId,
        role: role ?? () => normalizeRole(currentRole()),
      ),
    );
  }
}

class _SatelliteView extends StatefulWidget {
  const _SatelliteView({
    required this.api,
    required this.initialFieldId,
    required this.role,
  });

  final SatelliteApi api;
  final String? initialFieldId;
  final AppRole Function() role;

  @override
  State<_SatelliteView> createState() => _SatelliteViewState();
}

class _SatelliteViewState extends State<_SatelliteView> {
  bool _refreshingImagery = false;

  void _onFieldsLoaded(List<Map<String, dynamic>> fields) {
    final cubit = context.read<FieldIndicatorsCubit>();
    if (cubit.state.fieldId != null || fields.isEmpty) return;
    final wanted = widget.initialFieldId;
    final id = (wanted != null && fields.any((f) => fieldIdOf(f) == wanted))
        ? wanted
        : fieldIdOf(fields.first);
    cubit.selectField(id);
  }

  // يُطلق تحديث صور Sentinel-2 للحقل المختار. لا نزعم نجاحاً: الرسالة من ردّ
  // الخادم (queued/status/note) أو خطؤه كما هو. مُعطَّل أثناء طلب جارٍ.
  Future<void> _refreshImagery(String fieldId) async {
    if (_refreshingImagery) return;
    setState(() => _refreshingImagery = true);
    final messenger = ScaffoldMessenger.of(context);
    try {
      final r = await widget.api.refreshFieldImagery(fieldId);
      final status = wText(r['status'], '');
      final note = wText(r['note_ar'] ?? r['note'] ?? r['message_ar'], '');
      final msg = r['queued'] == true
          ? 'أُطلق تحديث صور Sentinel-2 — قد يستغرق دقائق.'
          : (note.isNotEmpty
                ? note
                : (status.isNotEmpty
                      ? 'حالة التحديث: $status'
                      : 'لا مشهد جديد متاح بعد لهذا الحقل.'));
      messenger.showSnackBar(SnackBar(content: Text(msg)));
    } catch (e) {
      messenger.showSnackBar(
        SnackBar(content: Text(ApiException.from(e).messageAr)),
      );
    } finally {
      if (mounted) setState(() => _refreshingImagery = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final selected = context.select<FieldIndicatorsCubit, String?>(
      (c) => c.state.fieldId,
    );
    final canTrigger = canMutate(widget.role().name);
    return Scaffold(
      appBar: AppBar(
        title: const Text('الأقمار الصناعيّة'),
        actions: [
          if (canTrigger)
            AppIconButton(
              icon: Icons.satellite_alt_outlined,
              tooltip: 'تحديث صور الأقمار',
              onPressed: (selected == null || _refreshingImagery)
                  ? null
                  : () => _refreshImagery(selected),
            ),
        ],
      ),
      body:
          BlocConsumer<
            LoadCubit<List<Map<String, dynamic>>>,
            LoadState<List<Map<String, dynamic>>>
          >(
            listener: (context, s) {
              if (s is LoadLoaded<List<Map<String, dynamic>>>) {
                _onFieldsLoaded(s.data);
              }
            },
            builder: (context, s) => switch (s) {
              LoadLoading() => const LoadingState(message: 'جارٍ تحميل الحقول'),
              LoadFailed(:final error) => ErrorState(
                error: error,
                title: 'تعذّر تحميل الحقول',
                onRetry: context
                    .read<LoadCubit<List<Map<String, dynamic>>>>()
                    .load,
              ),
              LoadLoaded(:final data) when data.isEmpty => const EmptyState(
                icon: Icons.satellite_alt_outlined,
                message: 'لا حقول بعد لعرض مؤشّراتها — أضف حقلاً أوّلاً.',
              ),
              LoadLoaded(:final data) => RefreshIndicator(
                onRefresh: context.read<FieldIndicatorsCubit>().refresh,
                child: ListView(
                  padding: const EdgeInsets.all(SahoolSpacing.page),
                  children: [
                    _FieldPicker(fields: data, selected: selected),
                    const SizedBox(height: SahoolSpacing.md),
                    if (selected != null) const FieldIndicatorsPanel(),
                  ],
                ),
              ),
            },
          ),
    );
  }
}

class _FieldPicker extends StatelessWidget {
  const _FieldPicker({required this.fields, required this.selected});

  final List<Map<String, dynamic>> fields;
  final String? selected;

  @override
  Widget build(BuildContext context) => KeyedSubtree(
    key: const ValueKey('satellite_field_picker'),
    child: DropdownButtonFormField<String>(
      // يُعاد بناؤه حين يتغيّر الاختيار من خارج القائمة (الاختيار الأوّليّ).
      key: ValueKey('picker_$selected'),
      initialValue: selected,
      isExpanded: true,
      decoration: const InputDecoration(labelText: 'الحقل'),
      items: [
        for (final f in fields)
          DropdownMenuItem(
            value: fieldIdOf(f),
            child: Text(
              fieldNameOf(f),
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: context.textStyles.bodyLarge,
            ),
          ),
      ],
      onChanged: (v) {
        if (v != null) context.read<FieldIndicatorsCubit>().selectField(v);
      },
    ),
  );
}
