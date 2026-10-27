/// قائمة النماذج الميدانيّة المنزَّلة لحقلٍ — مدخل FieldFormScreen من مساحة عمل الحقل
/// (MOBILE-FIELD-FORM-SCREEN-UNREACHABLE-FROM-NAVIGATION-01).
///
/// Offline-first: تُقرأ الحزم من FormPackageStore المحليّ (يملؤه
/// FieldFormsCoordinator.syncField عند فتح الحقل)، فالقائمة تعمل بلا اتصال.
/// الحالات الصادقة: المخازن غير جاهزة / لا مستأجر / لا نماذج منزَّلة بعد.
library;

import 'package:flutter/material.dart';
import 'package:sahool_app/core/network/api_exception.dart';
import 'package:sahool_app/core/theme/sahool_tokens.dart';
import 'package:sahool_app/core/theme/tokens.dart';
import 'package:sahool_app/core/utils/formatters.dart';
import 'package:sahool_app/core/widgets/widgets.dart';

import '../../../services/api_service.dart';
import '../../../services/auth_service.dart';
import '../data/draft_store.dart';
import '../data/field_forms_api.dart';
import '../data/field_forms_coordinator.dart';
import '../data/form_package_store.dart';
import '../data/submission_queue.dart';
import 'device_pickers.dart';
import 'field_form_screen.dart';
import 'field_widget_registry.dart';

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
  final String? actorId;
  final String? server;
  final Future<DraftStore> Function()? openDraftStore;
  final PhotoPicker? photoPicker;
  final LocationPicker? locationPicker;

  /// يُبلَّغ حين ينتهي تصريف الطابور في الخلفيّة (الافتراضيّ المنسّق).
  final Listenable? refreshSignal;

  const FieldFormsListScreen({
    super.key,
    required this.fieldId,
    this.packages,
    this.queue,
    this.api,
    this.tenantId,
    this.actorId,
    this.server,
    this.openDraftStore,
    this.photoPicker,
    this.locationPicker,
    this.refreshSignal,
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
  String? get _actorId => widget.actorId ?? AuthService.instance.userId;

  Listenable get _signal =>
      widget.refreshSignal ?? FieldFormsCoordinator.instance.drainTick;

  bool _opening = false;
  String? _openError;

  @override
  void initState() {
    super.initState();
    _signal.addListener(_onQueueChanged);
  }

  @override
  void dispose() {
    _signal.removeListener(_onQueueChanged);
    super.dispose();
  }

  void _onQueueChanged() {
    if (mounted) setState(() {});
  }

  static String _title(DownloadedFormPackage package) {
    final title = package.schemaJson['title'];
    if (title is String && title.trim().isNotEmpty) return title.trim();
    return 'نموذج ميدانيّ';
  }

  Future<void> _open(DownloadedFormPackage package) async {
    final queue = _queue;
    final tenantId = _tenantId;
    if (_opening || queue == null || tenantId == null) return;
    setState(() {
      _opening = true;
      _openError = null;
    });
    FieldFormCubit? cubit;
    try {
      final draftStore = await (widget.openDraftStore ?? DraftStore.open)();
      cubit = FieldFormCubit(
        tenantId: tenantId,
        fieldId: widget.fieldId,
        package: package,
        draftStore: draftStore,
        submissionQueue: queue,
        api: widget.api ?? FieldFormsCoordinator.instance.api,
        server: widget.server ?? ApiService.instance.dio.options.baseUrl,
        actorId: _actorId,
      );
      await cubit.open();
      if (!mounted) return;
      await Navigator.of(context).push<void>(
        MaterialPageRoute(
          builder: (_) => FieldFormScreen(
            cubit: cubit!,
            photoPicker: widget.photoPicker ?? pickFieldPhoto,
            locationPicker: widget.locationPicker ?? currentDeviceLocation,
          ),
        ),
      );
    } catch (e) {
      // كان `finally` بلا `catch`: فشل فتح المسودّات يضيع بصمت.
      if (mounted) {
        setState(
          () => _openError =
              'تعذّر فتح النموذج على الجهاز: ${ApiException.from(e).messageAr}',
        );
      }
    } finally {
      await cubit?.close();
      if (mounted) setState(() => _opening = false);
    }
  }

  Future<void> _retryFailed(QueuedSubmission item) async {
    final queue = _queue;
    if (queue == null) return;
    await queue.requeue(item);
    if (!mounted) return;
    setState(() {});
    await FieldFormsCoordinator.instance.drain();
  }

  Future<void> _discardFailed(QueuedSubmission item) async {
    final queue = _queue;
    if (queue == null) return;
    final ok = await showConfirmDialog(
      context,
      title: 'حذف الإرسال من الجهاز؟',
      message:
          'رفض الخادم هذا الإرسال. حذفه يُزيل الإجابات من هذا الجهاز نهائيّاً '
          'ولا يمكن استرجاعها.',
      confirmLabel: 'حذف',
      destructive: true,
    );
    if (!ok) return;
    await queue.remove(item.instanceId);
    if (mounted) setState(() {});
  }

  @override
  Widget build(BuildContext context) {
    final packages = _packages;
    final queue = _queue;
    final tenantId = packages == null || queue == null ? null : _tenantId;
    Widget body;
    if (packages == null || queue == null) {
      body = const EmptyState(
        key: ValueKey('field_forms_store_unavailable'),
        icon: Icons.hourglass_empty_rounded,
        message:
            'مخزن النماذج على الجهاز غير جاهز بعد. أعد فتح الشاشة بعد لحظات.',
      );
    } else if (tenantId == null) {
      body = const EmptyState(
        key: ValueKey('field_forms_no_tenant'),
        icon: Icons.lock_outline_rounded,
        message: 'سجّل الدخول لعرض نماذج الحقل.',
      );
    } else {
      final items = packages.packagesForField(
        tenantId: tenantId,
        fieldId: widget.fieldId,
      );
      List<QueuedSubmission> mine(List<QueuedSubmission> l) =>
          l.where((i) => i.fieldId == widget.fieldId).toList();
      final pending = mine(
        queue.pending(tenantId: tenantId, actorId: _actorId),
      );
      final failed = mine(queue.failed(tenantId: tenantId, actorId: _actorId));
      // صفوف على الجهاز تعذّرت قراءتها: لا تُنسَب لحقل ولا تُرسَل، لكنّها ليست
      // «لا شيء بانتظار الإرسال» — تُعرض عدداً.
      final unreadable = queue.unreadableCount();
      body = ListView(
        padding: const EdgeInsetsDirectional.only(bottom: SahoolSpacing.xl),
        children: [
          if (_openError != null)
            Padding(
              padding: const EdgeInsets.all(SahoolSpacing.lg),
              child: Text(
                _openError!,
                key: const ValueKey('field_forms_open_error'),
                style: context.textStyles.bodyMedium?.copyWith(
                  color: context.tokens.danger,
                ),
              ),
            ),
          if (unreadable > 0)
            Padding(
              padding: const EdgeInsets.all(SahoolSpacing.lg),
              child: Text(
                unreadable == 1
                    ? 'إرسال محفوظ على الجهاز تعذّرت قراءته؛ لم يُرسَل ولم يُحذف.'
                    : '$unreadable إرسالات محفوظة على الجهاز تعذّرت قراءتها؛ '
                          'لم تُرسَل ولم تُحذف.',
                key: const ValueKey('field_forms_unreadable'),
                style: context.textStyles.bodyMedium?.copyWith(
                  color: context.tokens.danger,
                ),
              ),
            ),
          if (pending.isNotEmpty)
            _QueueNote(
              key: const ValueKey('field_forms_pending'),
              count: pending.length,
              outcomeUnknown: pending.where((i) => i.outcomeUnknown).length,
            ),
          if (failed.isNotEmpty) ...[
            const ListSectionHeader('لم يُقبل'),
            for (final f in failed)
              AppListTile(
                key: ValueKey('field_forms_failed_${f.instanceId}'),
                icon: Icons.error_outline,
                iconColor: context.tokens.danger,
                title: 'إرسال بتاريخ ${fmtDateTime(f.localCreatedAt)}',
                subtitle:
                    'رفضه الخادم بعد ${f.attempts} محاولات. أعد المحاولة أو احذفه.',
                trailing: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    AppIconButton(
                      icon: Icons.refresh_rounded,
                      tooltip: 'إعادة المحاولة',
                      onPressed: () => _retryFailed(f),
                    ),
                    AppIconButton(
                      icon: Icons.delete_outline,
                      tooltip: 'حذف من الجهاز',
                      onPressed: () => _discardFailed(f),
                    ),
                  ],
                ),
              ),
          ],
          const ListSectionHeader('النماذج المتاحة لهذا الحقل'),
          if (items.isEmpty)
            const EmptyState(
              key: ValueKey('field_forms_empty'),
              icon: Icons.assignment_outlined,
              message:
                  'لا نماذج منزَّلة لهذا الحقل بعد. تُنزَّل عند فتح الحقل مع '
                  'الاتصال.',
            )
          else
            for (final package in items)
              AppListTile(
                key: ValueKey('field_form_${package.assignmentId}'),
                icon: Icons.description_outlined,
                iconColor: context.colors.primary,
                title: _title(package),
                subtitle: 'الإصدار ${package.versionNumber}',
                onTap: _opening ? null : () => _open(package),
              ),
        ],
      );
    }
    return AppScaffold(title: 'النماذج الميدانيّة', body: body);
  }
}

/// تنبيه بعدد الإرسالات المحفوظة على الجهاز بانتظار الاتصال.
class _QueueNote extends StatelessWidget {
  const _QueueNote({super.key, required this.count, this.outcomeUnknown = 0});
  final int count;

  /// منها ما ربّما وصل الخادم ولم يصل تأكيده — لا يُقال عنه «بانتظار الاتصال» فقط.
  final int outcomeUnknown;

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.all(SahoolSpacing.lg),
    child: SectionCard(
      child: Row(
        children: [
          Icon(Icons.cloud_upload_outlined, color: context.tokens.warning),
          const SizedBox(width: SahoolSpacing.md),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  count == 1
                      ? 'إرسال واحد محفوظ على الجهاز بانتظار الاتصال.'
                      : '$count إرسالات محفوظة على الجهاز بانتظار الاتصال.',
                  style: context.textStyles.bodyMedium,
                ),
                if (outcomeUnknown > 0)
                  Text(
                    'نتيجة $outcomeUnknown منها غير مؤكَّدة: ربّما وصلت ولم '
                    'يصل تأكيدها، وتُطابَق تلقائيّاً بالمعرّف نفسه.',
                    key: const ValueKey('field_forms_outcome_unknown'),
                    style: context.textStyles.bodySmall?.copyWith(
                      color: context.tokens.warning,
                    ),
                  ),
              ],
            ),
          ),
        ],
      ),
    ),
  );
}
