// SAHOOL — features/farms/presentation/farm_form_sheet.dart
// ورقة «مزرعة جديدة» (POST /api/v1/farms، FarmCreateRequest). للمالك فقط.
// مفتاح Idempotency-Key واحد لكلّ فتح للورقة (نيّة واحدة) يُعاد في كلّ محاولة،
// فلا تُنشئ إعادة الإرسال بعد ردّ ضائع مزرعتين. الأخطاء تظهر داخل الورقة لا
// تحتها، والأرقام تقبل الأرقام العربيّة-الهنديّة.
import 'package:flutter/material.dart';
import 'package:sahool_app/core/network/api_exception.dart';
import 'package:sahool_app/core/network/idempotency.dart';
import 'package:sahool_app/core/utils/formatters.dart';
import 'package:sahool_app/core/widgets/widgets.dart';
import 'package:sahool_app/features/farms/data/farms_api.dart';

/// يفتح الورقة ويُعيد true إن أُنشئت مزرعة.
Future<bool> showCreateFarmSheet(BuildContext context, FarmsApi api) async =>
    await showAppBottomSheet<bool>(
      context,
      builder: (_) => FarmFormSheet(api: api),
    ) ??
    false;

class FarmFormSheet extends StatefulWidget {
  const FarmFormSheet({super.key, required this.api});
  final FarmsApi api;

  @override
  State<FarmFormSheet> createState() => _FarmFormSheetState();
}

class _FarmFormSheetState extends State<FarmFormSheet> {
  final _form = GlobalKey<FormState>();
  final _name = TextEditingController();
  final _region = TextEditingController();
  final _location = TextEditingController();
  final _area = TextEditingController();
  final _description = TextEditingController();
  final IdempotencyKey _key = IdempotencyKey.generate();
  bool _submitting = false;
  String? _error;

  @override
  void dispose() {
    _name.dispose();
    _region.dispose();
    _location.dispose();
    _area.dispose();
    _description.dispose();
    super.dispose();
  }

  String? _trimmed(TextEditingController c) {
    final v = c.text.trim();
    return v.isEmpty ? null : v;
  }

  Future<void> _submit() async {
    if (_submitting) return;
    if (!(_form.currentState?.validate() ?? false)) return;
    setState(() {
      _submitting = true;
      _error = null;
    });
    try {
      await widget.api.createFarm({
        'name': _name.text.trim(),
        if (_trimmed(_region) != null) 'region': _trimmed(_region),
        if (_trimmed(_location) != null) 'location': _trimmed(_location),
        if (parseLocalizedNum(_area.text) != null)
          'area_ha': parseLocalizedNum(_area.text),
        if (_trimmed(_description) != null)
          'description': _trimmed(_description),
      }, idempotencyKey: _key);
      if (!mounted) return;
      Navigator.of(context).pop(true);
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _submitting = false;
        _error = ApiException.from(e).messageAr;
      });
    }
  }

  @override
  Widget build(BuildContext context) => Form(
    key: _form,
    child: AppSheet(
      title: 'مزرعة جديدة',
      submitLabel: 'إنشاء المزرعة',
      submitting: _submitting,
      onSubmit: _submit,
      errorText: _error,
      children: [
        AppTextField(
          key: const ValueKey('farm_name'),
          label: 'اسم المزرعة',
          controller: _name,
          textInputAction: TextInputAction.next,
          validator: (v) {
            final t = v?.trim() ?? '';
            if (t.isEmpty) return 'اسم المزرعة مطلوب';
            if (t.length > 100) return 'الاسم أطول من 100 حرف';
            return null;
          },
        ),
        AppTextField(
          key: const ValueKey('farm_region'),
          label: 'المحافظة / المنطقة (اختياريّ)',
          controller: _region,
          validator: (v) =>
              (v ?? '').trim().length > 80 ? 'المنطقة أطول من 80 حرفاً' : null,
        ),
        AppTextField(
          label: 'الموقع (اختياريّ)',
          controller: _location,
          prefixIcon: Icons.place_outlined,
        ),
        AppNumberField(
          key: const ValueKey('farm_area'),
          label: 'المساحة (اختياريّ)',
          controller: _area,
          unit: 'هـ',
          min: 0.01,
        ),
        AppTextField(
          label: 'وصف (اختياريّ)',
          controller: _description,
          maxLines: 2,
        ),
      ],
    ),
  );
}
