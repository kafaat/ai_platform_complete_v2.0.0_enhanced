/// الـrenderer الواحد schema-driven (GAP-FIELD-FORMS-01 §8/§15).
///
/// يبني الحقول وقت التشغيل من schema_json + logic_json فقط:
/// - يعيد تقييم logic عند كلّ تغيير إجابة فيحسب الظاهر/المخفيّ.
/// - يحذف قيم الحقول المخفيّة من payload النهائيّ.
/// - يتحقّق محليًّا (required على الظاهر فقط + الأنواع + الحدود) بلا coercion.
/// - V1 وV2 يُعرضان بنفس هذا الكود بلا تعديل.
library;

import 'package:flutter/material.dart';

import '../contract/condition_v1.dart';
import '../contract/form_schema.dart';
import 'field_widget_registry.dart';

/// نتيجة الإرسال المحليّ: الإجابات النظيفة أو أخطاء التحقّق.
class RendererSubmitResult {
  final Map<String, Object?>? answers;
  final Map<String, String> errors;

  const RendererSubmitResult.ok(this.answers) : errors = const {};
  const RendererSubmitResult.invalid(this.errors) : answers = null;

  bool get isValid => answers != null;
}

class SchemaFormRenderer extends StatefulWidget {
  final FormSchema schema;
  final Map<String, Object?>? logicJson;
  final Map<String, Object?> initialAnswers;
  final FieldWidgetRegistry registry;

  /// يُستدعى عند ضغط إرسال بعد نجاح التحقّق المحليّ.
  final void Function(Map<String, Object?> answers)? onValidSubmit;

  /// يُستدعى عند كلّ تغيير (لحفظ المسودّة مثلًا).
  final void Function(Map<String, Object?> answers)? onAnswersChanged;

  /// زرّ إرسال مضمَّن (يمكن إخفاؤه إن أدارت الشاشة الإرسال بنفسها).
  final bool showSubmitButton;

  const SchemaFormRenderer({
    super.key,
    required this.schema,
    this.logicJson,
    this.initialAnswers = const {},
    this.registry = const FieldWidgetRegistry(),
    this.onValidSubmit,
    this.onAnswersChanged,
    this.showSubmitButton = true,
  });

  @override
  State<SchemaFormRenderer> createState() => SchemaFormRendererState();
}

class SchemaFormRendererState extends State<SchemaFormRenderer> {
  late final Map<String, Object?> _answers =
      Map<String, Object?>.from(widget.initialAnswers);
  Map<String, String> _errors = const {};

  Set<String> get _visibleKeys => computeVisibleKeys(
        schema: widget.schema,
        logic: widget.logicJson,
        answers: _answers,
      );

  void _onFieldChanged(FormFieldDef def, Object? value) {
    setState(() {
      if (value == null) {
        _answers.remove(def.key);
      } else {
        _answers[def.key] = value;
      }
      // حقل اختفى بسبب التغيير ⇒ تُزال قيمته فورًا من الحالة.
      final visible = _visibleKeys;
      _answers.removeWhere((key, _) => !visible.contains(key));
      _errors = const {}; // يعاد التحقّق عند الإرسال
    });
    widget.onAnswersChanged?.call(Map<String, Object?>.from(_answers));
  }

  /// تحقّق محليّ كامل + بناء payload (يُسقط المجهول والمخفيّ).
  RendererSubmitResult validateAndBuild() {
    final visible = _visibleKeys;
    final errors = validateAnswers(
      schema: widget.schema,
      visibleKeys: visible,
      answers: _answers,
    );
    setState(() => _errors = errors);
    if (errors.isNotEmpty) return RendererSubmitResult.invalid(errors);
    return RendererSubmitResult.ok(buildSubmissionAnswers(
      schema: widget.schema,
      visibleKeys: visible,
      answers: _answers,
    ));
  }

  void _submit() {
    final result = validateAndBuild();
    if (result.isValid) widget.onValidSubmit?.call(result.answers!);
  }

  @override
  Widget build(BuildContext context) {
    final visible = _visibleKeys;
    final children = <Widget>[];
    for (final def in widget.schema.fields) {
      if (!visible.contains(def.key)) continue;
      final builder = widget.registry.builderFor(def.fieldType);
      if (builder == null) continue; // لا يحدث: العقد يرفض الأنواع المجهولة
      children.add(Padding(
        padding: const EdgeInsets.symmetric(vertical: 8),
        child: builder(
            context, def, _answers[def.key], _errors[def.key],
            (v) => _onFieldChanged(def, v)),
      ));
    }
    if (widget.showSubmitButton) {
      children.add(Padding(
        padding: const EdgeInsets.symmetric(vertical: 16),
        child: FilledButton(
          key: const ValueKey('schema_form_submit'),
          onPressed: _submit,
          child: const Text('إرسال'),
        ),
      ));
    }
    return SingleChildScrollView(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: children,
      ),
    );
  }
}
