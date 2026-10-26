/// قائمة النماذج الميدانيّة المنزَّلة لحقلٍ — مدخل FieldFormScreen من مساحة عمل الحقل
/// (MOBILE-FIELD-FORM-SCREEN-UNREACHABLE-FROM-NAVIGATION-01).
///
/// Offline-first: تُقرأ الحزم من FormPackageStore المحليّ (يملؤه
/// FieldFormsCoordinator.syncField عند فتح الحقل)، فالقائمة تعمل بلا اتصال.
/// الحالات الصادقة: المخازن غير جاهزة / لا مستأجر / لا نماذج منزَّلة بعد.
library;

import 'package:flutter/material.dart';

import '../../../services/api_service.dart';
import '../../../services/auth_service.dart';
import '../data/draft_store.dart';
import '../data/field_forms_api.dart';
import '../data/field_forms_coordinator.dart';
import '../data/form_package_store.dart';
import '../data/submission_queue.dart';
import 'field_form_screen.dart';

/// زرّ شريط التطبيق الذي يفتح قائمة نماذج الحقل.
class FieldFormsEntryButton extends StatelessWidget {
  final String fieldId;

  /// يُبنى الهدف عند الضغط؛ يُحقَن في الاختبارات.
  final WidgetBuilder? listBuilder;

  const FieldFormsEntryButton({
    super.key,
    required this.fieldId,
    this.listBuilder,
  });

  @override
  Widget build(BuildContext context) {
    return IconButton(
      key: const ValueKey('open_field_forms'),
      icon: const Icon(Icons.fact_check_outlined),
      tooltip: 'النماذج الميدانيّة',
      onPressed: () {
        Navigator.of(context).push<void>(
          MaterialPageRoute(
            builder:
                listBuilder ?? (_) => FieldFormsListScreen(fieldId: fieldId),
          ),
        );
      },
    );
  }
}

class FieldFormsListScreen extends StatefulWidget {
  final String fieldId;

  // كلّها اختياريّة: الافتراضيّ من FieldFormsCoordinator والجلسة.
  final FormPackageStore? packages;
  final SubmissionQueue? queue;
  final FieldFormsApi? api;
  final String? tenantId;
  final String? server;
  final Future<DraftStore> Function()? openDraftStore;

  const FieldFormsListScreen({
    super.key,
    required this.fieldId,
    this.packages,
    this.queue,
    this.api,
    this.tenantId,
    this.server,
    this.openDraftStore,
  });

  @override
  State<FieldFormsListScreen> createState() => _FieldFormsListScreenState();
}

class _FieldFormsListScreenState extends State<FieldFormsListScreen> {
  FormPackageStore? get _packages =>
      widget.packages ?? FieldFormsCoordinator.instance.packages;
  SubmissionQueue? get _queue =>
      widget.queue ?? FieldFormsCoordinator.instance.queue;
  String? get _tenantId => widget.tenantId ?? AuthService.instance.tenantId;

  bool _opening = false;

  static String _title(DownloadedFormPackage package) {
    final title = package.schemaJson['title'];
    if (title is String && title.trim().isNotEmpty) return title.trim();
    return 'نموذج — الإصدار ${package.versionNumber}';
  }

  Future<void> _open(DownloadedFormPackage package) async {
    final queue = _queue;
    final tenantId = _tenantId;
    if (_opening || queue == null || tenantId == null) return;
    setState(() => _opening = true);
    try {
      final draftStore = await (widget.openDraftStore ?? DraftStore.open)();
      final cubit = FieldFormCubit(
        tenantId: tenantId,
        fieldId: widget.fieldId,
        package: package,
        draftStore: draftStore,
        submissionQueue: queue,
        api: widget.api ?? FieldFormsCoordinator.instance.api,
        server: widget.server ?? ApiService.instance.dio.options.baseUrl,
      );
      await cubit.open();
      if (!mounted) {
        await cubit.close();
        return;
      }
      await Navigator.of(context).push<void>(
        MaterialPageRoute(builder: (_) => FieldFormScreen(cubit: cubit)),
      );
      await cubit.close();
    } finally {
      if (mounted) setState(() => _opening = false);
    }
  }

  Widget _message(String text, {Key? key}) => Center(
    child: Padding(
      padding: const EdgeInsets.all(24),
      child: Text(text, key: key, textAlign: TextAlign.center),
    ),
  );

  @override
  Widget build(BuildContext context) {
    final packages = _packages;
    final tenantId = packages == null || _queue == null ? null : _tenantId;
    Widget body;
    if (packages == null || _queue == null) {
      body = _message(
        'مخزن النماذج المحليّ غير جاهز بعد.',
        key: const ValueKey('field_forms_store_unavailable'),
      );
    } else if (tenantId == null) {
      body = _message(
        'سجّل الدخول لعرض نماذج الحقل.',
        key: const ValueKey('field_forms_no_tenant'),
      );
    } else {
      final items = packages.packagesForField(
        tenantId: tenantId,
        fieldId: widget.fieldId,
      );
      if (items.isEmpty) {
        body = _message(
          'لا نماذج منزَّلة لهذا الحقل بعد. تُنزَّل عند فتح الحقل مع الاتصال.',
          key: const ValueKey('field_forms_empty'),
        );
      } else {
        body = ListView.separated(
          itemCount: items.length,
          separatorBuilder: (_, _) => const Divider(height: 1),
          itemBuilder: (context, index) {
            final package = items[index];
            return ListTile(
              key: ValueKey('field_form_${package.assignmentId}'),
              leading: const Icon(Icons.description_outlined),
              title: Text(_title(package)),
              subtitle: Text('الإصدار ${package.versionNumber}'),
              enabled: !_opening,
              onTap: () => _open(package),
            );
          },
        );
      }
    }
    return Scaffold(
      appBar: AppBar(title: const Text('النماذج الميدانيّة')),
      body: body,
    );
  }
}
