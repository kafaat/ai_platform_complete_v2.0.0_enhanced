/// شاشة النموذج الميدانيّ — الحالات العشر (GAP-FIELD-FORMS-01 §15).
///
/// loading, ready, saved locally, queued, syncing, accepted, quarantined,
/// invalid, unsupported schema, sync failure.
///
/// Offline-first: الفتح/التوليد/الظهور الشرطيّ/التحقّق/حفظ المسودّة/الطابور
/// كلّه محليّ؛ الشبكة فقط عند download/sync عبر BFF.
library;

import 'package:equatable/equatable.dart';
import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';

import '../contract/condition_v1.dart';
import '../contract/form_schema.dart';
import '../data/draft_store.dart';
import '../data/field_forms_api.dart';
import '../data/submission_queue.dart';
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

  const FieldFormState({
    required this.status,
    this.schema,
    this.logicJson,
    this.answers = const {},
    this.fieldErrors = const {},
    this.versionResolutionStatus,
    this.formValidationStatus,
    this.message,
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
  }) =>
      FieldFormState(
        status: status ?? this.status,
        schema: schema ?? this.schema,
        logicJson: logicJson ?? this.logicJson,
        answers: answers ?? this.answers,
        fieldErrors: fieldErrors ?? this.fieldErrors,
        versionResolutionStatus:
            versionResolutionStatus ?? this.versionResolutionStatus,
        formValidationStatus: formValidationStatus ?? this.formValidationStatus,
        message: message ?? this.message,
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
      ];
}

class FieldFormCubit extends Cubit<FieldFormState> {
  final String tenantId;
  final String fieldId;
  final DownloadedFormPackage package;
  final DraftStore draftStore;
  final SubmissionQueue submissionQueue;
  final FieldFormsApi? api; // null ⇒ وضع offline كامل

  /// مُعرّف الخادم لخانة envelope.server (مثل AppConfig.apiUri).
  final String server;
  final String provider;

  FieldFormCubit({
    required this.tenantId,
    required this.fieldId,
    required this.package,
    required this.draftStore,
    required this.submissionQueue,
    this.api,
    this.server = '',
    this.provider = 'sahool-flutter',
  }) : super(const FieldFormState(status: FieldFormStatus.loading));

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
        fieldId: fieldId,
        assignmentId: package.assignmentId,
        formVersionId: package.formVersionId,
        schemaHash: package.schemaHash,
      );
      emit(FieldFormState(
        status: FieldFormStatus.ready,
        schema: schema,
        logicJson: logic,
        answers: draft?.answers ?? const {},
      ));
    } on UnsupportedFormSchemaException catch (e) {
      emit(FieldFormState(
        status: FieldFormStatus.unsupportedSchema,
        message: e.toString(),
      ));
    } on ConditionException catch (e) {
      emit(FieldFormState(
        status: FieldFormStatus.invalid,
        message: e.toString(),
      ));
    } on FormSchemaException catch (e) {
      emit(FieldFormState(
        status: FieldFormStatus.invalid,
        message: e.toString(),
      ));
    }
  }

  void answersChanged(Map<String, Object?> answers) {
    if (state.schema == null) return;
    emit(state.copyWith(answers: answers));
  }

  /// حفظ مسودّة محليًّا بالمفتاح الخماسيّ — بلا اتصال.
  Future<void> saveDraft() async {
    await draftStore.save(FormDraft(
      tenantId: tenantId,
      fieldId: fieldId,
      assignmentId: package.assignmentId,
      revision: package.revision,
      formVersionId: package.formVersionId,
      schemaHash: package.schemaHash,
      definitionSyncToken: package.definitionSyncToken,
      answers: state.answers,
      savedAt: DateTime.now().toUtc(),
    ));
    emit(state.copyWith(status: FieldFormStatus.savedLocally));
  }

  /// إرسال: يُدرج في الطابور أوّلًا (instance_id ثابت)، ثمّ مزامنة إن وُجد API.
  Future<void> submit(Map<String, Object?> answers) async {
    final item = await submissionQueue.enqueue(
      tenantId: tenantId,
      fieldId: fieldId,
      assignmentId: package.assignmentId,
      assignmentRevision: package.revision,
      formVersionId: package.formVersionId,
      schemaHash: package.schemaHash,
      definitionSyncToken: package.definitionSyncToken,
      answers: answers,
    );
    emit(state.copyWith(status: FieldFormStatus.queued));
    await sync(item);
  }

  /// مزامنة عنصر طابور — retry يمرّر العنصر نفسه بلا instance_id جديد.
  Future<void> sync(QueuedSubmission item) async {
    final currentApi = api;
    if (currentApi == null) return; // يبقى queued حتى يتوفّر اتصال
    emit(state.copyWith(status: FieldFormStatus.syncing));
    try {
      final result = await currentApi.submit(item.buildEnvelope(
        provider: provider,
        server: server,
      ));
      if (result.status == 'accepted' &&
          result.formValidationStatus != 'invalid') {
        await submissionQueue.remove(item.instanceId);
        emit(state.copyWith(
          status: FieldFormStatus.accepted,
          versionResolutionStatus: result.versionResolutionStatus,
          formValidationStatus: result.formValidationStatus,
        ));
      } else if (result.formValidationStatus == 'invalid') {
        await submissionQueue.remove(item.instanceId);
        emit(state.copyWith(
          status: FieldFormStatus.invalid,
          versionResolutionStatus: result.versionResolutionStatus,
          formValidationStatus: result.formValidationStatus,
        ));
      } else {
        // quarantined — تُعرض حجرًا كما هي (stale_proven وغيرها بحالاتها).
        await submissionQueue.remove(item.instanceId);
        emit(state.copyWith(
          status: FieldFormStatus.quarantined,
          versionResolutionStatus: result.versionResolutionStatus,
          formValidationStatus: result.formValidationStatus,
        ));
      }
    } catch (_) {
      await submissionQueue.markRetry(item); // instance_id ثابت
      emit(state.copyWith(status: FieldFormStatus.syncFailure));
    }
  }
}

/// الشاشة: renderer واحد + عرض الحالات العشر.
class FieldFormScreen extends StatelessWidget {
  final FieldFormCubit cubit;
  final PhotoPicker? photoPicker;

  const FieldFormScreen({super.key, required this.cubit, this.photoPicker});

  String _statusLabel(FieldFormState state) {
    switch (state.status) {
      case FieldFormStatus.loading:
        return 'جارٍ التحميل…';
      case FieldFormStatus.ready:
        return 'جاهز';
      case FieldFormStatus.savedLocally:
        return 'محفوظ محليًّا';
      case FieldFormStatus.queued:
        return 'في الطابور';
      case FieldFormStatus.syncing:
        return 'جارٍ المزامنة…';
      case FieldFormStatus.accepted:
        return 'مقبول';
      case FieldFormStatus.quarantined:
        return 'محجوز (quarantined)';
      case FieldFormStatus.invalid:
        return 'غير صالح';
      case FieldFormStatus.unsupportedSchema:
        return 'unsupported form schema';
      case FieldFormStatus.syncFailure:
        return 'فشل المزامنة';
    }
  }

  @override
  Widget build(BuildContext context) {
    return BlocProvider<FieldFormCubit>.value(
      value: cubit,
      child: BlocBuilder<FieldFormCubit, FieldFormState>(
        builder: (context, state) {
          final banner = MaterialBanner(
            key: ValueKey('status_${state.status.name}'),
            content: Text(_statusLabel(state)),
            actions: const [SizedBox.shrink()],
          );
          Widget body;
          switch (state.status) {
            case FieldFormStatus.loading:
              body = const Center(child: CircularProgressIndicator());
              break;
            case FieldFormStatus.unsupportedSchema:
              // Fail-Closed: لا عرض للنموذج إطلاقًا.
              body = Center(
                child: Text(
                  'unsupported form schema',
                  key: const ValueKey('unsupported_schema_message'),
                  style: TextStyle(
                      color: Theme.of(context).colorScheme.error),
                ),
              );
              break;
            default:
              final schema = state.schema;
              if (schema == null) {
                body = const SizedBox.shrink();
              } else {
                body = SchemaFormRenderer(
                  schema: schema,
                  logicJson: state.logicJson,
                  initialAnswers: state.answers,
                  registry: FieldWidgetRegistry(photoPicker: photoPicker),
                  onAnswersChanged: cubit.answersChanged,
                  onValidSubmit: cubit.submit,
                );
              }
          }
          return Scaffold(
            appBar: AppBar(
              title: const Text('نموذج ميدانيّ'),
              actions: [
                if (state.schema != null)
                  IconButton(
                    key: const ValueKey('save_draft_button'),
                    icon: const Icon(Icons.save_outlined),
                    onPressed: cubit.saveDraft,
                  ),
              ],
            ),
            body: Column(
              children: [
                banner,
                if (state.versionResolutionStatus != null)
                  Text('version: ${state.versionResolutionStatus}'),
                if (state.formValidationStatus != null)
                  Text('validation: ${state.formValidationStatus}'),
                Expanded(child: body),
              ],
            ),
          );
        },
      ),
    );
  }
}
