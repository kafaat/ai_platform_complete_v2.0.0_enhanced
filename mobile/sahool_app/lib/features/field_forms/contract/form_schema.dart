/// SahoolFormSchemaV1 — طبقة العقد للنماذج الميدانيّة (GAP-FIELD-FORMS-01 §8).
///
/// - الأنواع الثمانية مغلقة: text, number, integer, select, multi_select,
///   date, gps, photo. نوع غير معروف ⇒ UnsupportedFormSchemaException
///   (Fail-Closed — لا تحويل إلى text ولا تجاهل صامت).
/// - العقد بلا أسماء widgets؛ presentation_hint يُقرأ ولا يُلزم.
/// - التحقّق المحليّ يطابق دلالات الخادم: لا coercion إطلاقًا.
library;

import 'condition_v1.dart';

/// نوع حقل غير معروف ⇒ حالة "unsupported form schema".
class UnsupportedFormSchemaException implements Exception {
  final String fieldType;
  const UnsupportedFormSchemaException(this.fieldType);
  @override
  String toString() => 'UnsupportedFormSchemaException($fieldType)';
}

/// خلل بنيويّ في schema_json (غير النوع المجهول).
class FormSchemaException implements Exception {
  final String message;
  const FormSchemaException(this.message);
  @override
  String toString() => 'FormSchemaException($message)';
}

/// الأنواع الثمانية المثبَّتة فقط.
enum FormFieldType {
  text,
  number,
  integer,
  select,
  multiSelect,
  date,
  gps,
  photo,
}

FormFieldType _parseType(String raw) {
  switch (raw) {
    case 'text':
      return FormFieldType.text;
    case 'number':
      return FormFieldType.number;
    case 'integer':
      return FormFieldType.integer;
    case 'select':
      return FormFieldType.select;
    case 'multi_select':
      return FormFieldType.multiSelect;
    case 'date':
      return FormFieldType.date;
    case 'gps':
      return FormFieldType.gps;
    case 'photo':
      return FormFieldType.photo;
    default:
      throw UnsupportedFormSchemaException(raw);
  }
}

final RegExp _keyPattern = RegExp(r'^[a-z][a-z0-9_]{0,63}$');
final RegExp _datePattern = RegExp(r'^\d{4}-\d{2}-\d{2}$');

/// قواعد التحقّق المدعومة فقط: required, min, max, min_length, max_length, options.
class FormValidationRules {
  final num? min;
  final num? max;
  final int? minLength;
  final int? maxLength;

  const FormValidationRules({this.min, this.max, this.minLength, this.maxLength});

  factory FormValidationRules.fromJson(Object? json) {
    if (json == null) return const FormValidationRules();
    if (json is! Map) {
      throw const FormSchemaException('validation_rules_must_be_object');
    }
    int? readInt(String k) {
      final v = json[k];
      if (v == null) return null;
      if (v is! int || v is bool) {
        throw FormSchemaException('validation_rule_${k}_must_be_int');
      }
      if (v < 0) throw FormSchemaException('validation_rule_${k}_negative');
      return v;
    }

    num? readNum(String k) {
      final v = json[k];
      if (v == null) return null;
      if (v is! num || v is bool) {
        throw FormSchemaException('validation_rule_${k}_must_be_num');
      }
      return v;
    }

    return FormValidationRules(
      min: readNum('min'),
      max: readNum('max'),
      minLength: readInt('min_length'),
      maxLength: readInt('max_length'),
    );
  }
}

/// تعريف حقل واحد من schema_json.
class FormFieldDef {
  final String key;
  final FormFieldType fieldType;
  final bool required;
  final List<String> options; // إلزاميّة لـ select/multi_select
  final FormValidationRules rules;
  final String? presentationHint; // استشاريّ فقط — لا يُلزم

  const FormFieldDef({
    required this.key,
    required this.fieldType,
    this.required = false,
    this.options = const [],
    this.rules = const FormValidationRules(),
    this.presentationHint,
  });

  bool get isChoice =>
      fieldType == FormFieldType.select ||
      fieldType == FormFieldType.multiSelect;

  factory FormFieldDef.fromJson(Object? json) {
    if (json is! Map) throw const FormSchemaException('field_must_be_object');
    final key = json['key'];
    if (key is! String || !_keyPattern.hasMatch(key)) {
      throw const FormSchemaException('field_key_invalid');
    }
    final rawType = json['field_type'];
    if (rawType is! String) {
      throw const FormSchemaException('field_type_missing');
    }
    final type = _parseType(rawType); // unknown ⇒ UnsupportedFormSchemaException
    final required = json['required'] == true;

    final options = <String>[];
    if (json['options'] != null) {
      final rawOptions = json['options'];
      if (rawOptions is! List) {
        throw const FormSchemaException('options_must_be_array');
      }
      for (final o in rawOptions) {
        if (o is! String || o.isEmpty) {
          throw const FormSchemaException('options_must_be_nonempty_strings');
        }
        options.add(o);
      }
    }
    final typeIsChoice =
        type == FormFieldType.select || type == FormFieldType.multiSelect;
    if (typeIsChoice && options.isEmpty) {
      throw const FormSchemaException('choice_field_requires_options');
    }

    return FormFieldDef(
      key: key,
      fieldType: type,
      required: required,
      options: options,
      rules: FormValidationRules.fromJson(json['validation_rules']),
      presentationHint: json['presentation_hint'] is String
          ? json['presentation_hint'] as String
          : null,
    );
  }
}

/// مخطّط النموذج الكامل (fields مرتّبة كما في schema_json).
class FormSchema {
  final List<FormFieldDef> fields;

  const FormSchema(this.fields);

  factory FormSchema.fromJson(Object? json) {
    if (json is! Map || json['fields'] is! List) {
      throw const FormSchemaException('schema_must_have_fields_array');
    }
    final fields = <FormFieldDef>[];
    final seen = <String>{};
    for (final f in (json['fields'] as List)) {
      final def = FormFieldDef.fromJson(f);
      if (!seen.add(def.key)) {
        throw FormSchemaException('duplicate_field_key:${def.key}');
      }
      fields.add(def);
    }
    return FormSchema(fields);
  }

  FormFieldDef? fieldByKey(String key) {
    for (final f in fields) {
      if (f.key == key) return f;
    }
    return null;
  }
}

bool _isNum(Object? v) => v is num && v is! bool;

/// يتحقّق من قيمة واحدة مقابل نوع الحقل وقواعده — بلا أيّ coercion.
/// يعيد رسالة خطأ عربيّة أو null عند الصلاح.
String? validateFieldValue(FormFieldDef def, Object? value) {
  if (value == null) {
    return def.required ? 'هذا الحقل مطلوب' : null;
  }
  switch (def.fieldType) {
    case FormFieldType.text:
      if (value is! String) return 'القيمة يجب أن تكون نصًّا';
      final minLen = def.rules.minLength;
      final maxLen = def.rules.maxLength;
      if (minLen != null && value.length < minLen) {
        return 'النصّ أقصر من الحدّ الأدنى ($minLen)';
      }
      if (maxLen != null && value.length > maxLen) {
        return 'النصّ أطول من الحدّ الأقصى ($maxLen)';
      }
      return null;
    case FormFieldType.number:
      // يقبل أيّ JSON number (int/double)؛ السلسلة "3" مرفوضة ولا تُحوَّل.
      if (!_isNum(value)) return 'القيمة يجب أن تكون رقمًا';
      final v = value as num;
      if (def.rules.min != null && v < def.rules.min!) {
        return 'القيمة أقلّ من الحدّ الأدنى (${def.rules.min})';
      }
      if (def.rules.max != null && v > def.rules.max!) {
        return 'القيمة أكبر من الحدّ الأقصى (${def.rules.max})';
      }
      return null;
    case FormFieldType.integer:
      // integer يبقى int — 3.5 مرفوض و"3" مرفوض.
      if (value is! int || value is bool) return 'القيمة يجب أن تكون عددًا صحيحًا';
      final v = value;
      if (def.rules.min != null && v < def.rules.min!) {
        return 'القيمة أقلّ من الحدّ الأدنى (${def.rules.min})';
      }
      if (def.rules.max != null && v > def.rules.max!) {
        return 'القيمة أكبر من الحدّ الأقصى (${def.rules.max})';
      }
      return null;
    case FormFieldType.select:
      if (value is! String) return 'القيمة يجب أن تكون نصًّا من الخيارات';
      if (!def.options.contains(value)) return 'القيمة ليست من الخيارات المعتمدة';
      return null;
    case FormFieldType.multiSelect:
      if (value is! List) return 'القيمة يجب أن تكون قائمة نصوص';
      for (final item in value) {
        if (item is! String) return 'كلّ عنصر يجب أن يكون نصًّا';
        if (!def.options.contains(item)) {
          return 'عنصر ليس من الخيارات المعتمدة';
        }
      }
      return null;
    case FormFieldType.date:
      if (value is! String || !_datePattern.hasMatch(value)) {
        return 'التاريخ يجب أن يكون بصيغة YYYY-MM-DD';
      }
      return null;
    case FormFieldType.gps:
      if (value is! Map) return 'الموقع يجب أن يكون {lat,lng}';
      final lat = value['lat'];
      final lng = value['lng'];
      if (!_isNum(lat) || !_isNum(lng)) return 'إحداثيّات الموقع غير صالحة';
      return null;
    case FormFieldType.photo:
      // مرجع ملفّ غير فارغ — لا Base64 داخل answers.
      if (value is! String || value.isEmpty) return 'مرجع الصورة مطلوب';
      return null;
  }
}

/// نتيجة التحقّق الكامل: خريطة field_key ← رسالة خطأ.
Map<String, String> validateAnswers({
  required FormSchema schema,
  required Set<String> visibleKeys,
  required Map<String, Object?> answers,
}) {
  final errors = <String, String>{};
  final knownKeys = schema.fields.map((f) => f.key).toSet();
  for (final key in answers.keys) {
    if (!knownKeys.contains(key)) {
      errors[key] = 'مفتاح خارج المخطّط';
    } else if (!visibleKeys.contains(key)) {
      errors[key] = 'إجابة لحقل مخفيّ';
    }
  }
  for (final def in schema.fields) {
    if (!visibleKeys.contains(def.key)) continue; // required على الظاهر فقط
    final error = validateFieldValue(def, answers[def.key]);
    if (error != null) errors[def.key] = error;
  }
  return errors;
}

/// يحسب مفاتيح الحقول الظاهرة بتقييم logic_json محليًّا.
/// شرط غير صالح أو خطأ تقييم ⇒ الحقل مخفيّ (Fail-Closed).
Set<String> computeVisibleKeys({
  required FormSchema schema,
  required Map<String, Object?>? logic,
  required Map<String, Object?> answers,
}) {
  final visible = <String>{};
  for (final def in schema.fields) {
    final condition = logic == null ? null : logic[def.key];
    if (condition == null) {
      visible.add(def.key);
      continue;
    }
    try {
      if (evaluateCondition(condition, answers)) visible.add(def.key);
    } on ConditionException {
      // شرط غير صالح ⇒ إخفاء احترازيّ.
    } on ConditionTypeException {
      // خطأ أنواع ⇒ إخفاء احترازيّ.
    }
  }
  return visible;
}

/// يبني payload الإرسال: يُسقط المفاتيح المجهولة وقيم الحقول المخفيّة.
Map<String, Object?> buildSubmissionAnswers({
  required FormSchema schema,
  required Set<String> visibleKeys,
  required Map<String, Object?> answers,
}) {
  final result = <String, Object?>{};
  for (final def in schema.fields) {
    if (!visibleKeys.contains(def.key)) continue;
    if (answers.containsKey(def.key) && answers[def.key] != null) {
      result[def.key] = answers[def.key];
    }
  }
  return result;
}
