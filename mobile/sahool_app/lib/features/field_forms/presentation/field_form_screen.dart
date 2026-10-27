/// شاشة النموذج الميدانيّ — الحالات العشر (GAP-FIELD-FORMS-01 §15).
///
/// loading, ready, saved locally, queued, syncing, accepted, quarantined,
/// invalid, unsupported schema, sync failure.
///
/// Offline-first: الفتح/التوليد/الظهور الشرطيّ/التحقّق/حفظ المسودّة/الطابور
/// كلّه محليّ؛ الشبكة فقط عند download/sync عبر BFF. كلّ حالة تُعرض بجملة
/// عربيّة للمزارع، لا بمفتاح الخادم الخامّ.
library;

import 'package:equatable/equatable.dart';
import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:sahool_app/core/network/api_exception.dart';
import 'package:sahool_app/core/theme/sahool_tokens.dart';
import 'package:sahool_app/core/theme/tokens.dart';
import 'package:sahool_app/core/widgets/widgets.dart';

import '../../../services/api_service.dart';
import '../../../services/device_id_service.dart';
import '../contract/condition_v1.dart';
import '../contract/form_schema.dart';
import '../data/draft_store.dart';
import '../data/field_forms_api.dart';
import '../data/submission_queue.dart';
import '../data/submission_sender.dart';
import 'field_forms_copy.dart';
import 'field_widget_registry.dart';
import 'schema_form_renderer.dart';

/// حالات الشاشة العشر المثبَّتة.
enum FieldFormStatus {
  loading,
  ready,
  savedLocally,
  queued,
  syncing,
  accepted,
  quarantined,
  invalid,
  unsupportedSchema,
  syncFailure,
}

class FieldFormState extends Equatable {
  final FieldFormStatus status;
  final FormSchema? schema;
  final Map<String, Object?>? logicJson;
  final Map<String, Object?> answers;
  final Map<String, String> fieldErrors;

  /// حالة الاستجابة الخادميّة كما هي (لا نجاح كاذب).
  final String? versionResolutionStatus;
  final String? formValidationStatus;
  final String? message;

  /// سبب الحجر من الخادم (`quarantine_reason`).
  final String? quarantineReason;

  /// أخطاء تحقّق الخادم كما أرسلها (للدعم؛ تُعرض ثانويّة).
  final List<String> serverErrors;

  const FieldFormState({
    required this.status,
    this.schema,
    this.logicJson,
    this.answers = const {},
    this.fieldErrors = const {},
    this.versionResolutionStatus,
    this.formValidationStatus,
    this.message,
    this.quarantineReason,
    this.serverErrors = const [],
  });

  FieldFormState copyWith({
    FieldFormStatus? status,
    FormSchema? schema,
    Map<String, Object?>? logicJson,
    Map<String, Object?>? answers,
    Map<String, String>? fieldErrors,
    String? versionResolutionStatus,
    String? formValidationStatus,
    String? message,
    String? quarantineReason,
    List<String>? serverErrors,
  }) => FieldFormState(
    status: status ?? this.status,
    schema: schema ?? this.schema,
    logicJson: logicJson ?? this.logicJson,
    answers: answers ?? this.answers,
    fieldErrors: fieldErrors ?? this.fieldErrors,
    versionResolutionStatus:
        versionResolutionStatus ?? this.versionResolutionStatus,
    formValidationStatus: formValidationStatus ?? this.formValidationStatus,
    message: message ?? this.message,
    quarantineReason: quarantineReason ?? this.quarantineReason,
    serverErrors: serverErrors ?? this.serverErrors,
  );

  /// حالة جديدة بلا رسالة/نتيجة سابقة (بداية إرسال جديد).
  FieldFormState withStatus(FieldFormStatus next, {String? message}) =>
      FieldFormState(
        status: next,
        schema: schema,
        logicJson: logicJson,
        answers: answers,
        fieldErrors: fieldErrors,
        message: message,
      );

  @override
  List<Object?> get props => [
    status,
    schema,
    logicJson,
    answers,
    fieldErrors,
    versionResolutionStatus,
    formValidationStatus,
    message,
    quarantineReason,
    serverErrors,
  ];
}

class FieldFormCubit extends Cubit<FieldFormState> {
  final String tenantId;
  final String fieldId;
  final DownloadedFormPackage package;
  final DraftStore draftStore;
  final SubmissionQueue submissionQueue;
  final FieldFormsApi? api; // null ⇒ وضع offline كامل

  /// مُعرّف الخادم لخانة envelope.server. فارغ ⇒ عنوان الـAPI الحاليّ (الخادم
  /// يرفض server فارغاً: min_length=1).
  final String server;
  final String provider;

  /// المستخدم الذي يعبّئ النموذج (يُختَم على عنصر الطابور).
  final String? actorId;

  /// مصدر هويّة الجهاز (قابل للحقن في الاختبارات).
  final Future<String> Function() deviceId;

  FieldFormCubit({
    required this.tenantId,
    required this.fieldId,
    required this.package,
    required this.draftStore,
    required this.submissionQueue,
    this.api,
    this.server = '',
    this.provider = kFieldFormsProvider,
    this.actorId,
    Future<String> Function()? deviceId,
  }) : deviceId = deviceId ?? DeviceIdService.instance.deviceId,
       super(const FieldFormState(status: FieldFormStatus.loading));

  bool _submitting = false;
  QueuedSubmission? _lastItem;

  /// آخر عنصر أُرسل/أُدرج من هذه الشاشة (لإعادة المحاولة اليدويّة).
  QueuedSubmission? get lastItem => _lastItem;

  String get _server =>
      server.isNotEmpty ? server : ApiService.instance.dio.options.baseUrl;

  /// فتح النموذج محليًّا: تحقّق من الشرط ثمّ بناء المخطّط ثمّ استرجاع المسودّة.
  Future<void> open() async {
    try {
      final logic = package.logicJson;
      if (logic != null) {
        for (final condition in logic.values) {
          validateCondition(condition); // invalid ⇒ fail-closed أدناه
        }
      }
      final schema = FormSchema.fromJson(package.schemaJson);
      final draft = draftStore.load(
        tenantId: tenantId,
        actorId: actorId,
        fieldId: fieldId,
        assignmentId: package.assignmentId,
        formVersionId: package.formVersionId,
        schemaHash: package.schemaHash,
      );
      _lastItem = null;
      emit(
        FieldFormState(
          status: FieldFormStatus.ready,
          schema: schema,
          logicJson: logic,
          answers: draft?.answers ?? const {},
        ),
      );
    } on UnsupportedFormSchemaException catch (e) {
      emit(
        FieldFormState(
          status: FieldFormStatus.unsupportedSchema,
          message: e.toString(),
        ),
      );
    } on ConditionException catch (e) {
      emit(
        FieldFormState(status: FieldFormStatus.invalid, message: e.toString()),
      );
    } on FormSchemaException catch (e) {
      emit(
        FieldFormState(status: FieldFormStatus.invalid, message: e.toString()),
      );
    }
  }

  void answersChanged(Map<String, Object?> answers) {
    if (state.schema == null) return;
    emit(state.copyWith(answers: answers));
  }

  FormDraft _draft(Map<String, Object?> answers) => FormDraft(
    tenantId: tenantId,
    actorId: actorId,
    fieldId: fieldId,
    assignmentId: package.assignmentId,
    revision: package.revision,
    formVersionId: package.formVersionId,
    schemaHash: package.schemaHash,
    definitionSyncToken: package.definitionSyncToken,
    answers: answers,
    savedAt: DateTime.now().toUtc(),
  );

  /// حفظ مسودّة محليًّا بالمفتاح الخماسيّ — بلا اتصال.
  Future<void> saveDraft() async {
    await draftStore.save(_draft(state.answers));
    emit(state.copyWith(status: FieldFormStatus.savedLocally));
  }

  /// إرسال: يُدرج في الطابور أوّلًا (instance_id وجسم ثابتان)، ثمّ مزامنة إن
  /// وُجد API. ضغطة ثانية أثناء الإرسال تُتجاهَل (لا عنصرين لإجابة واحدة).
  Future<void> submit(Map<String, Object?> answers) async {
    if (_submitting) return;
    _submitting = true;
    try {
      final item = await submissionQueue.enqueue(
        tenantId: tenantId,
        fieldId: fieldId,
        assignmentId: package.assignmentId,
        assignmentRevision: package.revision,
        formVersionId: package.formVersionId,
        schemaHash: package.schemaHash,
        definitionSyncToken: package.definitionSyncToken,
        answers: answers,
        server: _server,
        provider: provider,
        actorId: actorId,
      );
      _lastItem = item;
      // الإجابات صارت في الطابور؛ المسودّة لم تعد مصدرها.
      await draftStore.discard(_draft(answers));
      emit(
        state.withStatus(
          FieldFormStatus.queued,
          message: 'حُفظت الإجابات على الجهاز وستُرسل تلقائيّاً عند الاتصال.',
        ),
      );
      await sync(item);
    } finally {
      _submitting = false;
    }
  }

  /// إعادة محاولة يدويّة لآخر عنصر من هذه الشاشة.
  Future<void> retry() async {
    final item = _lastItem;
    if (item == null || _submitting) return;
    _submitting = true;
    try {
      await sync(item);
    } finally {
      _submitting = false;
    }
  }

  /// مزامنة عنصر طابور — retry يمرّر العنصر نفسه بلا instance_id جديد ولا جسم
  /// جديد. الإرسال عبر [SubmissionSender] نفسه الذي يصرّف به المنسّق، فلا يُرسَل
  /// العنصر مرّتين في آنٍ واحد.
  Future<void> sync(QueuedSubmission item) async {
    final currentApi = api;
    if (currentApi == null) return; // يبقى queued حتى يتوفّر اتصال
    emit(state.withStatus(FieldFormStatus.syncing));
    final String device;
    try {
      // §9.2: هويّة الجهاز الثابتة تدخل ترويسة X-Device-Id.
      device = await deviceId();
    } catch (e) {
      emit(
        state.withStatus(
          FieldFormStatus.syncFailure,
          message: 'تعذّر قراءة هويّة الجهاز. الإجابات محفوظة على الجهاز.',
        ),
      );
      return;
    }
    final outcome = await SubmissionSender.send(
      item: item,
      queue: submissionQueue,
      api: currentApi,
      deviceId: device,
      server: _server,
    );
    switch (outcome.kind) {
      case SendOutcomeKind.settled:
        final result = outcome.result!;
        final FieldFormStatus next;
        if (result.isAccepted) {
          next = FieldFormStatus.accepted;
        } else if (result.formValidationStatus == 'invalid') {
          next = FieldFormStatus.invalid;
        } else {
          next = FieldFormStatus.quarantined;
        }
        emit(
          FieldFormState(
            status: next,
            schema: state.schema,
            logicJson: state.logicJson,
            answers: state.answers,
            versionResolutionStatus: result.versionResolutionStatus,
            formValidationStatus: result.formValidationStatus,
            quarantineReason: result.quarantineReason,
            serverErrors: result.validationErrors,
          ),
        );
      case SendOutcomeKind.retryLater:
        _lastItem = outcome.item ?? item;
        final err = ApiException.from(outcome.error ?? 'unknown');
        emit(
          state.withStatus(
            FieldFormStatus.syncFailure,
            message:
                '${err.messageAr} الإجابات محفوظة على الجهاز وستُرسل '
                'تلقائيّاً عند عودة الاتصال.',
          ),
        );
      case SendOutcomeKind.authRejected:
        _lastItem = outcome.item ?? item;
        final err = ApiException.from(outcome.error ?? 'unknown');
        emit(
          state.withStatus(
            FieldFormStatus.syncFailure,
            message: '${err.messageAr} الإجابات محفوظة على الجهاز.',
          ),
        );
      case SendOutcomeKind.failed:
        _lastItem = outcome.item ?? item;
        emit(
          state.withStatus(
            FieldFormStatus.syncFailure,
            message:
                'رفض الخادم هذا الإرسال عدّة مرّات، فأُوقف إرساله التلقائيّ. '
                'تجده في قائمة النماذج تحت «لم يُقبل».',
          ),
        );
    }
  }
}

/// الشاشة: renderer واحد + عرض الحالات العشر بلغة المزارع.
class FieldFormScreen extends StatelessWidget {
  final FieldFormCubit cubit;
  final PhotoPicker? photoPicker;
  final LocationPicker? locationPicker;

  const FieldFormScreen({
    super.key,
    required this.cubit,
    this.photoPicker,
    this.locationPicker,
  });

  static String statusLabel(FieldFormStatus status) {
    switch (status) {
      case FieldFormStatus.loading:
        return 'جارٍ فتح النموذج…';
      case FieldFormStatus.ready:
        return 'املأ الحقول ثمّ اضغط «إرسال».';
      case FieldFormStatus.savedLocally:
        return 'حُفظت المسودّة على الجهاز.';
      case FieldFormStatus.queued:
        return 'محفوظ على الجهاز بانتظار الإرسال';
      case FieldFormStatus.syncing:
        return 'جارٍ الإرسال…';
      case FieldFormStatus.accepted:
        return 'استُلم واعتُمد';
      case FieldFormStatus.quarantined:
        return 'استُلم وهو قيد المراجعة';
      case FieldFormStatus.invalid:
        return 'لم يُقبل';
      case FieldFormStatus.unsupportedSchema:
        return 'نموذج غير مدعوم في هذا الإصدار';
      case FieldFormStatus.syncFailure:
        return 'لم يُرسَل بعد';
    }
  }

  static StatusTone _tone(FieldFormStatus status) {
    switch (status) {
      case FieldFormStatus.accepted:
      case FieldFormStatus.savedLocally:
        return StatusTone.success;
      case FieldFormStatus.quarantined:
      case FieldFormStatus.queued:
      case FieldFormStatus.syncFailure:
        return StatusTone.warning;
      case FieldFormStatus.invalid:
      case FieldFormStatus.unsupportedSchema:
        return StatusTone.danger;
      case FieldFormStatus.loading:
      case FieldFormStatus.ready:
      case FieldFormStatus.syncing:
        return StatusTone.info;
    }
  }

  String get _title {
    final t = cubit.package.schemaJson['title'];
    return t is String && t.trim().isNotEmpty ? t.trim() : 'نموذج ميدانيّ';
  }

  @override
  Widget build(BuildContext context) {
    return BlocProvider<FieldFormCubit>.value(
      value: cubit,
      child: BlocBuilder<FieldFormCubit, FieldFormState>(
        builder: (context, state) {
          final schema = state.schema;
          final settled =
              state.status == FieldFormStatus.accepted ||
              state.status == FieldFormStatus.quarantined ||
              (state.status == FieldFormStatus.invalid && schema != null);
          final pending =
              state.status == FieldFormStatus.queued ||
              state.status == FieldFormStatus.syncFailure;
          Widget body;
          switch (state.status) {
            case FieldFormStatus.loading:
              body = const LoadingState(message: 'جارٍ فتح النموذج…');
            case FieldFormStatus.syncing:
              body = const LoadingState(message: 'جارٍ إرسال الإجابات…');
            case FieldFormStatus.unsupportedSchema:
              // Fail-Closed: لا عرض للنموذج إطلاقًا.
              body = const EmptyState(
                key: ValueKey('unsupported_schema_message'),
                icon: Icons.system_update_outlined,
                title: 'نموذج غير مدعوم',
                message:
                    'يستعمل هذا النموذج نوع حقل لا يدعمه هذا الإصدار من '
                    'التطبيق. حدّث التطبيق ثمّ افتحه من جديد.',
              );
            default:
              if (schema == null) {
                body = const EmptyState(
                  key: ValueKey('invalid_schema_message'),
                  icon: Icons.report_gmailerrorred_outlined,
                  title: 'تعريف النموذج غير صالح',
                  message:
                      'لا يمكن عرض هذا النموذج. أبلغ مسؤول المزرعة ليُصحّح '
                      'تعريفه.',
                );
              } else if (settled || pending) {
                body = _ResultPanel(state: state, cubit: cubit);
              } else {
                body = SchemaFormRenderer(
                  schema: schema,
                  logicJson: state.logicJson,
                  initialAnswers: state.answers,
                  registry: FieldWidgetRegistry(
                    photoPicker: photoPicker,
                    locationPicker: locationPicker,
                  ),
                  onAnswersChanged: cubit.answersChanged,
                  onValidSubmit: cubit.submit,
                );
              }
          }
          final editable =
              schema != null &&
              (state.status == FieldFormStatus.ready ||
                  state.status == FieldFormStatus.savedLocally);
          return AppScaffold(
            title: _title,
            actions: [
              if (editable)
                AppIconButton(
                  key: const ValueKey('save_draft_button'),
                  icon: Icons.save_outlined,
                  tooltip: 'حفظ مسودّة على الجهاز',
                  onPressed: cubit.saveDraft,
                ),
            ],
            body: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Padding(
                  key: ValueKey('status_${state.status.name}'),
                  padding: const EdgeInsetsDirectional.fromSTEB(
                    SahoolSpacing.lg,
                    SahoolSpacing.md,
                    SahoolSpacing.lg,
                    0,
                  ),
                  child: Semantics(
                    liveRegion: true,
                    child: Align(
                      alignment: AlignmentDirectional.centerStart,
                      child: StatusChip(
                        label: statusLabel(state.status),
                        tone: _tone(state.status),
                      ),
                    ),
                  ),
                ),
                Expanded(child: body),
              ],
            ),
          );
        },
      ),
    );
  }
}

/// نتيجة الإرسال (أو انتظاره) بدل النموذج: لا يعاد إرسال الإجابات نفسها بضغطة
/// ثانية تُنشئ عنصراً جديداً.
class _ResultPanel extends StatelessWidget {
  const _ResultPanel({required this.state, required this.cubit});

  final FieldFormState state;
  final FieldFormCubit cubit;

  @override
  Widget build(BuildContext context) {
    final t = context.tokens;
    final styles = context.textStyles;
    final (
      IconData icon,
      Color color,
      String title,
      String body,
    ) = switch (state.status) {
      FieldFormStatus.accepted => (
        Icons.check_circle_outline,
        t.success,
        'استُلمت إجاباتك واعتُمدت.',
        versionResolutionAr(state.versionResolutionStatus) ?? '',
      ),
      FieldFormStatus.quarantined => (
        Icons.hourglass_top_rounded,
        t.warning,
        'استُلمت إجاباتك ولم تُعتمد بعد.',
        quarantineReasonAr(state.quarantineReason),
      ),
      FieldFormStatus.invalid => (
        Icons.error_outline,
        t.danger,
        'استُلمت إجاباتك لكنّها لم تُقبل.',
        quarantineReasonAr(state.quarantineReason ?? 'form_validation_failed'),
      ),
      _ => (
        Icons.cloud_off_outlined,
        t.warning,
        'لم تُرسل الإجابات بعد.',
        state.message ?? '',
      ),
    };
    final settled =
        state.status == FieldFormStatus.accepted ||
        state.status == FieldFormStatus.quarantined ||
        state.status == FieldFormStatus.invalid;
    return ListView(
      key: const ValueKey('field_form_result'),
      padding: const EdgeInsets.all(SahoolSpacing.lg),
      children: [
        SectionCard(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Icon(icon, color: color, size: SahoolSizes.iconLg),
                  const SizedBox(width: SahoolSpacing.md),
                  Expanded(child: Text(title, style: styles.titleMedium)),
                ],
              ),
              if (body.isNotEmpty) ...[
                const SizedBox(height: SahoolSpacing.sm),
                Text(body, style: styles.bodyLarge),
              ],
              if (state.serverErrors.isNotEmpty) ...[
                const SizedBox(height: SahoolSpacing.md),
                Text(
                  'تفاصيل للدعم الفنّيّ:',
                  style: styles.bodySmall?.copyWith(color: t.muted),
                ),
                for (final e in state.serverErrors)
                  Text(
                    e,
                    textDirection: TextDirection.ltr,
                    style: styles.bodySmall?.copyWith(color: t.muted),
                  ),
              ],
            ],
          ),
        ),
        const SizedBox(height: SahoolSpacing.xl),
        if (!settled && cubit.api != null && cubit.lastItem != null) ...[
          PrimaryButton(
            key: const ValueKey('field_form_retry'),
            label: 'إعادة المحاولة الآن',
            icon: Icons.refresh_rounded,
            onPressed: cubit.retry,
          ),
          const SizedBox(height: SahoolSpacing.md),
        ],
        if (settled) ...[
          PrimaryButton(
            key: const ValueKey('field_form_new'),
            label: 'تعبئة جديدة',
            icon: Icons.add_rounded,
            onPressed: cubit.open,
          ),
          const SizedBox(height: SahoolSpacing.md),
        ],
        SecondaryButton(
          label: 'العودة إلى النماذج',
          onPressed: () => Navigator.of(context).maybePop(),
        ),
      ],
    );
  }
}
