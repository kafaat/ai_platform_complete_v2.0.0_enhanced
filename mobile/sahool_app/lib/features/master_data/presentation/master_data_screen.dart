// SAHOOL — features/master_data/presentation/master_data_screen.dart
// البيانات المرجعيّة: كتالوج (محصول/تربة/سماد/مبيد/صنف بذور/نوع معدّة/أخرى) عبر
// /api/v1/master-data. القراءة لمن يصل الشاشة، والإضافة لأدوار الإدارة
// (canManage — تطابق MasterDataPage في الويب)؛ الخادم يفرض RBAC ويردّ 409 عند
// تكرار (المستأجِر، الفئة، الرمز). لا بيانات مُلفَّقة.
import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:sahool_app/core/network/api_exception.dart';
import 'package:sahool_app/core/network/idempotency.dart';
import 'package:sahool_app/core/permissions/permissions.dart';
import 'package:sahool_app/core/theme/sahool_tokens.dart';
import 'package:sahool_app/core/theme/tokens.dart';
import 'package:sahool_app/core/widgets/widgets.dart';
import 'package:sahool_app/features/master_data/data/master_data_api.dart';

import 'master_data_cubit.dart';

/// الفئات كما يقبلها الخادم (MasterDataRequest.category).
const Map<String, String> kMasterCategories = {
  'crop': 'المحاصيل',
  'soil_type': 'أنواع التربة',
  'fertilizer': 'الأسمدة',
  'pesticide': 'المبيدات',
  'seed_variety': 'أصناف البذور',
  'equipment_type': 'أنواع المعدّات',
  'other': 'أخرى',
};

/// رسالة فشل الإضافة: 409 يحمل تفصيل الخادم «الرمز موجود مسبقاً في هذه الفئة».
String masterDataWriteError(Object error) {
  final e = ApiException.from(error);
  if (e.kind == ApiErrorKind.conflict) {
    final d = e.detail;
    return d is String && d.isNotEmpty ? d : 'هذا الرمز موجود مسبقاً في الفئة.';
  }
  return e.messageAr;
}

class MasterDataScreen extends StatelessWidget {
  const MasterDataScreen({super.key, this.api, this.role});

  /// للاختبارات؛ الافتراضيّ MasterDataApi.instance والدور الحاليّ.
  final MasterDataApi? api;
  final String? role;

  @override
  Widget build(BuildContext context) {
    final mdApi = api ?? MasterDataApi.instance;
    return BlocProvider(
      create: (_) => MasterDataCubit(mdApi)..load(),
      child: _MasterDataView(
        api: mdApi,
        canWrite: canManage(role ?? currentRole()),
      ),
    );
  }
}

class _MasterDataView extends StatelessWidget {
  const _MasterDataView({required this.api, required this.canWrite});
  final MasterDataApi api;
  final bool canWrite;

  Future<void> _openAdd(BuildContext context) async {
    final cubit = context.read<MasterDataCubit>();
    final created = await showAppBottomSheet<bool>(
      context,
      builder: (_) =>
          AddMasterDataSheet(api: api, category: cubit.state.category),
    );
    if (created == true) {
      await cubit.load();
      if (context.mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(const SnackBar(content: Text('أُضيف العنصر')));
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final cubit = context.read<MasterDataCubit>();
    return AppScaffold(
      title: 'البيانات المرجعيّة',
      actions: [
        AppIconButton(
          icon: Icons.refresh_rounded,
          tooltip: 'تحديث',
          onPressed: cubit.load,
        ),
      ],
      floatingActionButton: canWrite
          ? AppFab(
              heroKey: '/master-data',
              label: 'إضافة عنصر',
              icon: Icons.add_rounded,
              onPressed: () => _openAdd(context),
            )
          : null,
      body: BlocBuilder<MasterDataCubit, MasterDataState>(
        builder: (context, state) => Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            SingleChildScrollView(
              scrollDirection: Axis.horizontal,
              padding: const EdgeInsets.symmetric(
                horizontal: SahoolSpacing.lg,
                vertical: SahoolSpacing.sm,
              ),
              child: Row(
                children: [
                  for (final e in kMasterCategories.entries)
                    Padding(
                      padding: const EdgeInsetsDirectional.only(
                        end: SahoolSpacing.sm,
                      ),
                      child: ChoiceChip(
                        key: ValueKey('md_cat:${e.key}'),
                        label: Text(e.value),
                        selected: state.category == e.key,
                        onSelected: (_) => cubit.setCategory(e.key),
                      ),
                    ),
                ],
              ),
            ),
            Expanded(child: _body(context, state)),
          ],
        ),
      ),
    );
  }

  Widget _body(BuildContext context, MasterDataState state) {
    final cubit = context.read<MasterDataCubit>();
    switch (state.status) {
      case MasterDataStatus.loading:
        return const LoadingState(message: 'جارٍ التحميل…');
      case MasterDataStatus.failed:
        return ErrorState(error: state.error!, onRetry: cubit.load);
      case MasterDataStatus.loaded:
        if (state.items.isEmpty) {
          return EmptyState(
            icon: Icons.inventory_2_outlined,
            message:
                'لا عناصر في «${kMasterCategories[state.category] ?? state.category}» بعد.',
          );
        }
        return RefreshIndicator(
          onRefresh: cubit.load,
          child: ListView.builder(
            padding: const EdgeInsetsDirectional.only(
              bottom: SahoolSpacing.xxl * 3,
            ),
            itemCount: state.items.length,
            itemBuilder: (context, i) {
              final e = state.items[i];
              final nameAr = (e['name_ar'] ?? '').toString().trim();
              final nameEn = (e['name_en'] ?? '').toString().trim();
              final code = (e['code'] ?? '').toString();
              return AppListTile(
                key: ValueKey('md:${e['md_id']}'),
                title: nameAr.isEmpty ? code : nameAr,
                subtitle: nameEn.isEmpty ? null : nameEn,
                trailing: Text(
                  code,
                  textDirection: TextDirection.ltr,
                  style: context.textStyles.bodySmall?.copyWith(
                    color: context.tokens.muted,
                  ),
                ),
              );
            },
          ),
        );
    }
  }
}

/// ورقة إضافة عنصر مرجعيّ. مفتاح idempotency واحد لكلّ فتح للورقة.
class AddMasterDataSheet extends StatefulWidget {
  const AddMasterDataSheet({
    super.key,
    required this.api,
    required this.category,
  });

  final MasterDataApi api;
  final String category;

  @override
  State<AddMasterDataSheet> createState() => _AddMasterDataSheetState();
}

class _AddMasterDataSheetState extends State<AddMasterDataSheet> {
  final _code = TextEditingController();
  final _nameAr = TextEditingController();
  final _nameEn = TextEditingController();
  final _key = IdempotencyKey.generate();
  bool _saving = false;
  String? _error;

  @override
  void dispose() {
    _code.dispose();
    _nameAr.dispose();
    _nameEn.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (_saving) return;
    final code = _code.text.trim();
    final nameAr = _nameAr.text.trim();
    if (code.isEmpty || nameAr.isEmpty) {
      setState(() => _error = 'الرمز والاسم العربيّ مطلوبان.');
      return;
    }
    setState(() {
      _saving = true;
      _error = null;
    });
    try {
      await widget.api.createMasterDataEntry({
        'category': widget.category,
        'code': code,
        'name_ar': nameAr,
        if (_nameEn.text.trim().isNotEmpty) 'name_en': _nameEn.text.trim(),
      }, idempotencyKey: _key);
      if (mounted) Navigator.of(context).pop(true);
    } catch (e) {
      if (mounted) {
        setState(() {
          _saving = false;
          _error = masterDataWriteError(e);
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) => AppSheet(
    title:
        'إضافة إلى «${kMasterCategories[widget.category] ?? widget.category}»',
    submitLabel: 'إضافة',
    submitting: _saving,
    errorText: _error,
    onSubmit: _submit,
    children: [
      AppTextField(
        label: 'الرمز',
        hint: 'مثل: wheat',
        controller: _code,
        textInputAction: TextInputAction.next,
      ),
      AppTextField(
        label: 'الاسم العربيّ',
        controller: _nameAr,
        textInputAction: TextInputAction.next,
      ),
      AppTextField(label: 'الاسم الإنجليزيّ (اختياريّ)', controller: _nameEn),
    ],
  );
}
