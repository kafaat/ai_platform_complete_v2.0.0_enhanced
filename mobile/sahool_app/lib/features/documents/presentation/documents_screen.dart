// SAHOOL — features/documents/presentation/documents_screen.dart
// الوثائق: سجلّ بيانات وصفيّة (عقود/تقارير/صور/خرائط/نتائج مخبريّة) عبر
// /api/v1/documents. صدق: سجلّ metadata فقط — الملفّ الفعليّ في تخزين الكائنات
// وstorage_ref مرجعه؛ التسجيل لا يرفع ملفّاً. القراءة لمن يصل الشاشة، والتسجيل
// لأدوار الإدارة (canManage = document:manage في الويب)؛ الخادم يفرض RBAC.
import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:sahool_app/core/network/api_exception.dart';
import 'package:sahool_app/core/network/idempotency.dart';
import 'package:sahool_app/core/permissions/permissions.dart';
import 'package:sahool_app/core/theme/sahool_tokens.dart';
import 'package:sahool_app/core/theme/tokens.dart';
import 'package:sahool_app/core/utils/formatters.dart';
import 'package:sahool_app/core/widgets/widgets.dart';
import 'package:sahool_app/features/documents/data/documents_api.dart';

import 'documents_cubit.dart';

/// الفئات كما يقبلها الخادم (DocumentRequest.category).
const Map<String, String> kDocCategories = {
  'contract': 'عقد',
  'report': 'تقرير',
  'image': 'صورة',
  'map': 'خريطة',
  'lab_result': 'نتيجة مخبريّة',
  'other': 'أخرى',
};

IconData docCategoryIcon(String cat) {
  switch (cat) {
    case 'contract':
      return Icons.description_outlined;
    case 'report':
      return Icons.bar_chart_rounded;
    case 'image':
      return Icons.image_outlined;
    case 'map':
      return Icons.map_outlined;
    case 'lab_result':
      return Icons.science_outlined;
    default:
      return Icons.insert_drive_file_outlined;
  }
}

/// حجم ملفّ مقروء (بايت ⇒ ك.ب/م.ب)؛ null ⇒ «غير مقيس».
String fmtBytes(Object? raw) {
  final n = raw is num ? raw : num.tryParse('${raw ?? ''}');
  if (n == null) return kNotMeasured;
  if (n < 1024) return '${fmtNumber(n, decimals: 0)} بايت';
  if (n < 1024 * 1024) return '${fmtNumber(n / 1024)} ك.ب';
  return '${fmtNumber(n / (1024 * 1024))} م.ب';
}

class DocumentsScreen extends StatelessWidget {
  const DocumentsScreen({super.key, this.api, this.role});

  /// للاختبارات؛ الافتراضيّ DocumentsApi.instance والدور الحاليّ.
  final DocumentsApi? api;
  final String? role;

  @override
  Widget build(BuildContext context) {
    final docsApi = api ?? DocumentsApi.instance;
    return BlocProvider(
      create: (_) => DocumentsCubit(docsApi)..load(),
      child: _DocumentsView(
        api: docsApi,
        canWrite: canManage(role ?? currentRole()),
      ),
    );
  }
}

class _DocumentsView extends StatelessWidget {
  const _DocumentsView({required this.api, required this.canWrite});
  final DocumentsApi api;
  final bool canWrite;

  Future<void> _openRegister(BuildContext context) async {
    final cubit = context.read<DocumentsCubit>();
    final created = await showAppBottomSheet<bool>(
      context,
      builder: (_) => RegisterDocumentSheet(api: api),
    );
    if (created == true) {
      await cubit.load();
      if (context.mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(const SnackBar(content: Text('سُجّلت الوثيقة')));
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final cubit = context.read<DocumentsCubit>();
    return AppScaffold(
      title: 'الوثائق',
      actions: [
        AppIconButton(
          icon: Icons.refresh_rounded,
          tooltip: 'تحديث',
          onPressed: cubit.load,
        ),
      ],
      floatingActionButton: canWrite
          ? AppFab(
              heroKey: '/documents',
              label: 'تسجيل وثيقة',
              icon: Icons.add_rounded,
              onPressed: () => _openRegister(context),
            )
          : null,
      body: BlocBuilder<DocumentsCubit, DocumentsState>(
        builder: (context, state) => Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            _CategoryChips(
              selected: state.category,
              onSelected: cubit.setCategory,
            ),
            Expanded(child: _body(context, state)),
          ],
        ),
      ),
    );
  }

  Widget _body(BuildContext context, DocumentsState state) {
    final cubit = context.read<DocumentsCubit>();
    switch (state.status) {
      case DocumentsStatus.loading:
        return const LoadingState(message: 'جارٍ تحميل الوثائق…');
      case DocumentsStatus.failed:
        return ErrorState(error: state.error!, onRetry: cubit.load);
      case DocumentsStatus.loaded:
        if (state.items.isEmpty) {
          final cat = state.category;
          return EmptyState(
            icon: Icons.folder_open_outlined,
            message: cat == null
                ? 'لا وثائق مسجّلة بعد.'
                : 'لا وثائق في فئة «${kDocCategories[cat] ?? cat}».',
            actionLabel: cat == null ? null : 'عرض كلّ الفئات',
            onAction: cat == null ? null : () => cubit.setCategory(null),
          );
        }
        return RefreshIndicator(
          onRefresh: cubit.load,
          child: ListView(
            padding: const EdgeInsetsDirectional.only(
              bottom: SahoolSpacing.xxl * 3,
            ),
            children: [
              const _MetadataNote(),
              for (final d in state.items)
                _DocumentTile(key: ValueKey('doc:${d['doc_id']}'), doc: d),
            ],
          ),
        );
    }
  }
}

class _CategoryChips extends StatelessWidget {
  const _CategoryChips({required this.selected, required this.onSelected});
  final String? selected;
  final ValueChanged<String?> onSelected;

  @override
  Widget build(BuildContext context) => SingleChildScrollView(
    scrollDirection: Axis.horizontal,
    padding: const EdgeInsets.symmetric(
      horizontal: SahoolSpacing.lg,
      vertical: SahoolSpacing.sm,
    ),
    child: Row(
      children: [
        for (final e in <String?, String>{
          null: 'الكلّ',
          ...kDocCategories,
        }.entries)
          Padding(
            padding: const EdgeInsetsDirectional.only(end: SahoolSpacing.sm),
            child: ChoiceChip(
              key: ValueKey('doc_cat:${e.key ?? 'all'}'),
              label: Text(e.value),
              selected: selected == e.key,
              onSelected: (_) => onSelected(e.key),
            ),
          ),
      ],
    ),
  );
}

class _MetadataNote extends StatelessWidget {
  const _MetadataNote();

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsetsDirectional.fromSTEB(
      SahoolSpacing.lg,
      SahoolSpacing.sm,
      SahoolSpacing.lg,
      SahoolSpacing.sm,
    ),
    child: Text(
      'سجلّ بيانات وصفيّة: الملفّ نفسه محفوظ في تخزين المنشأة، وهنا مرجعه فقط. '
      'رفع الملفّات من التطبيق غير متاح بعد.',
      style: context.textStyles.bodySmall?.copyWith(
        color: context.tokens.muted,
      ),
    ),
  );
}

class _DocumentTile extends StatelessWidget {
  const _DocumentTile({super.key, required this.doc});
  final Map<String, dynamic> doc;

  @override
  Widget build(BuildContext context) {
    final cat = (doc['category'] ?? 'other').toString();
    final title = (doc['title'] ?? '').toString().trim();
    final version = doc['version'];
    return AppListTile(
      icon: docCategoryIcon(cat),
      iconColor: context.colors.primary,
      title: title.isEmpty ? 'وثيقة بلا عنوان' : title,
      subtitle: [
        kDocCategories[cat] ?? cat,
        if (version != null) 'الإصدار $version',
      ].join(' · '),
      onTap: () => showAppBottomSheet<void>(
        context,
        builder: (_) => _DocumentDetails(doc: doc),
      ),
    );
  }
}

class _DocumentDetails extends StatelessWidget {
  const _DocumentDetails({required this.doc});
  final Map<String, dynamic> doc;

  @override
  Widget build(BuildContext context) {
    String v(String k) {
      final s = doc[k]?.toString().trim();
      return (s == null || s.isEmpty) ? 'غير متاح' : s;
    }

    final cat = (doc['category'] ?? 'other').toString();
    Widget row(String label, String value, {bool ltr = false}) => Padding(
      padding: const EdgeInsets.only(top: SahoolSpacing.md),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            label,
            style: context.textStyles.bodySmall?.copyWith(
              color: context.tokens.muted,
            ),
          ),
          SelectableText(
            value,
            textDirection: ltr ? TextDirection.ltr : null,
            style: context.textStyles.bodyLarge,
          ),
        ],
      ),
    );
    return AppSheet(
      title: v('title'),
      children: [
        row('الفئة', kDocCategories[cat] ?? cat),
        row('الإصدار', v('version')),
        row('نوع المحتوى', v('content_type'), ltr: true),
        row('الحجم', fmtBytes(doc['size_bytes'])),
        row('الحقل', v('field_id'), ltr: true),
        row('مرجع التخزين', v('storage_ref'), ltr: true),
        const SizedBox(height: SahoolSpacing.lg),
      ],
    );
  }
}

/// ورقة تسجيل وثيقة (مرجع). مفتاح idempotency واحد لكلّ فتح للورقة: إعادة
/// الضغط بعد انقطاع لا تسجّل الوثيقة مرّتين (الخادم يحترمه: command_store).
class RegisterDocumentSheet extends StatefulWidget {
  const RegisterDocumentSheet({super.key, required this.api});
  final DocumentsApi api;

  @override
  State<RegisterDocumentSheet> createState() => _RegisterDocumentSheetState();
}

class _RegisterDocumentSheetState extends State<RegisterDocumentSheet> {
  final _title = TextEditingController();
  final _storageRef = TextEditingController();
  final _contentType = TextEditingController();
  final _key = IdempotencyKey.generate();
  String _category = 'report';
  bool _saving = false;
  String? _error;

  @override
  void dispose() {
    _title.dispose();
    _storageRef.dispose();
    _contentType.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (_saving) return;
    final title = _title.text.trim();
    if (title.isEmpty) {
      setState(() => _error = 'العنوان مطلوب.');
      return;
    }
    setState(() {
      _saving = true;
      _error = null;
    });
    try {
      await widget.api.createDocument({
        'category': _category,
        'title': title,
        if (_storageRef.text.trim().isNotEmpty)
          'storage_ref': _storageRef.text.trim(),
        if (_contentType.text.trim().isNotEmpty)
          'content_type': _contentType.text.trim(),
      }, idempotencyKey: _key);
      if (mounted) Navigator.of(context).pop(true);
    } catch (e) {
      if (mounted) {
        setState(() {
          _saving = false;
          _error = ApiException.from(e).messageAr;
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) => AppSheet(
    title: 'تسجيل وثيقة (مرجع)',
    submitLabel: 'تسجيل',
    submitting: _saving,
    errorText: _error,
    onSubmit: _submit,
    children: [
      const SizedBox(height: SahoolSpacing.md),
      AppDropdown<String>(
        label: 'الفئة',
        items: kDocCategories,
        value: _category,
        onChanged: (v) => setState(() => _category = v ?? 'other'),
      ),
      AppTextField(
        label: 'العنوان',
        controller: _title,
        textInputAction: TextInputAction.next,
      ),
      AppTextField(
        label: 'مرجع التخزين (مسار أو رابط)',
        controller: _storageRef,
        keyboardType: TextInputType.url,
      ),
      AppTextField(
        label: 'نوع المحتوى (اختياريّ)',
        hint: 'application/pdf',
        controller: _contentType,
      ),
    ],
  );
}
