/// SahoolFormConditionV1 — DSL الظهور الشرطيّ (GAP-FIELD-FORMS-01 §10).
///
/// مطابقة حرفيّة لـ shared/contracts/forms/condition_v1.py:
/// - validateCondition تُستعمل عند تحميل الحزمة (ترفض بـ ConditionException).
/// - evaluateCondition تُستعمل وقت التشغيل وترفع ConditionTypeException على
///   اختلاف الأنواع (مطابقة حالة "error" في corpus).
library;

/// حدود DoS مطابقة للخادم.
const int kConditionMaxDepth = 5;
const int kConditionMaxNodes = 50;
const int kConditionMaxArrayItems = 100;
const int kConditionMaxStringLength = 500;
const int kConditionMaxVarPathLength = 100;

/// خطأ بنيويّ في الشرط (يُرفض عند التحقّق — حالة "invalid").
class ConditionException implements Exception {
  final String code;
  const ConditionException(this.code);
  @override
  String toString() => 'ConditionException($code)';
}

/// خطأ أنواع وقت التقييم (حالة "error").
class ConditionTypeException implements Exception {
  final String code;
  const ConditionTypeException(this.code);
  @override
  String toString() => 'ConditionTypeException($code)';
}

const Set<String> _comparisons = {'==', '!=', '<', '<=', '>', '>='};
const Set<String> _logic = {'and', 'or', 'not'};
const Set<String> _allowedOps = {'var', 'in', ..._comparisons, ..._logic};

bool _isNumber(Object? v) => v is num && v is! bool;

bool _isNonFinite(Object? v) =>
    v is double && (v.isNaN || v.isInfinite);

void _checkScalar(Object? v) {
  if (v == null || v is bool) return;
  if (_isNumber(v)) {
    if (_isNonFinite(v)) throw const ConditionException('non_finite_number');
    return;
  }
  if (v is String) {
    if (v.length > kConditionMaxStringLength) {
      throw const ConditionException('string_too_long');
    }
    return;
  }
  throw const ConditionException('forbidden_literal');
}

void _checkArrayLiteral(List<Object?> arr) {
  if (arr.length > kConditionMaxArrayItems) {
    throw const ConditionException('max_array_items_exceeded');
  }
  for (final item in arr) {
    if (item is Map || item is List) {
      throw const ConditionException('forbidden_literal');
    }
    _checkScalar(item);
  }
}

void _checkVarPath(Object? path) {
  if (path is! String || path.isEmpty) {
    throw const ConditionException('var_path_invalid');
  }
  if (path.length > kConditionMaxVarPathLength) {
    throw const ConditionException('var_path_too_long');
  }
  for (final seg in path.split('.')) {
    if (seg.isEmpty || seg.startsWith('__')) {
      throw const ConditionException('var_path_forbidden_segment');
    }
  }
}

class _Validator {
  int nodes = 0;

  void visit(Object? node, int depth) {
    if (depth > kConditionMaxDepth) {
      throw const ConditionException('max_depth_exceeded');
    }
    if (node is List) {
      // ثابت مصفوفة حرفيّ.
      _checkArrayLiteral(node.cast<Object?>());
      return;
    }
    if (node is! Map) {
      _checkScalar(node);
      return;
    }
    if (node.length != 1) {
      throw const ConditionException('node_must_have_single_key');
    }
    nodes++;
    if (nodes > kConditionMaxNodes) {
      throw const ConditionException('max_nodes_exceeded');
    }
    final op = node.keys.single as String;
    final args = node.values.single;
    if (!_allowedOps.contains(op)) {
      throw const ConditionException('operator_not_allowed');
    }
    if (op == 'var') {
      _checkVarPath(args);
      return;
    }
    if (args is! List) {
      throw const ConditionException('args_must_be_list');
    }
    if (_comparisons.contains(op) || op == 'in') {
      if (args.length != 2) throw const ConditionException('arity_mismatch');
    } else if (op == 'not') {
      if (args.length != 1) throw const ConditionException('arity_mismatch');
    } else {
      // and/or
      if (args.length < 2) throw const ConditionException('arity_mismatch');
    }
    if (op == 'in') {
      final second = args[1];
      if (second is! List) {
        throw const ConditionException('in_requires_array_literal');
      }
      _checkArrayLiteral(second.cast<Object?>());
    }
    for (final arg in args) {
      if (op == 'in' && identical(arg, args[1])) continue; // تحقّقت أعلاه
      visit(arg, depth + 1);
    }
  }
}

/// يتحقّق بنيويًّا من شرط V1. يرفع ConditionException عند الرفض.
void validateCondition(Object? condition) {
  _Validator().visit(condition, 1);
}

/// حلّ مسار var النقطيّ داخل answers؛ مفقود ⇒ null.
Object? _resolveVar(String path, Map<String, Object?> answers) {
  Object? cur = answers;
  for (final seg in path.split('.')) {
    if (cur is Map && cur.containsKey(seg)) {
      cur = cur[seg];
    } else {
      return null;
    }
  }
  return cur;
}

/// مساواة صارمة لعضويّة in فقط: اختلاف النوع ⇒ false (لا coercion).
bool strictEqual(Object? l, Object? r) {
  if (l == null || r == null) return l == null && r == null;
  if (_isNumber(l) && _isNumber(r)) return l == r; // 1 == 1.0
  if (l.runtimeType != r.runtimeType) return false;
  return l == r;
}

bool _sameNonNumericType(Object? l, Object? r) =>
    (l is String && r is String) || (l is bool && r is bool);

Object? _eval(Object? node, Map<String, Object?> answers) {
  if (node is! Map) return node; // ثابت طرفيّ (أو مصفوفة حرفيّة)
  final op = node.keys.single as String;
  final args = node.values.single;
  if (op == 'var') {
    return _resolveVar(args as String, answers);
  }
  final list = (args as List).cast<Object?>();
  if (op == 'and' || op == 'or') {
    final values = list.map((a) => _eval(a, answers)).toList();
    for (final v in values) {
      if (v is! bool) {
        throw ConditionTypeException('${op}_requires_boolean_operands');
      }
    }
    return op == 'and'
        ? values.every((v) => v as bool)
        : values.any((v) => v as bool);
  }
  if (op == 'not') {
    final v = _eval(list[0], answers);
    if (v is! bool) {
      throw const ConditionTypeException('not_requires_boolean_operands');
    }
    return !v;
  }
  if (op == 'in') {
    final left = _eval(list[0], answers);
    final right = _eval(list[1], answers);
    if (right is! List) {
      throw const ConditionTypeException('in_requires_array');
    }
    return right.any((item) => strictEqual(left, item));
  }
  // مقارنات ==/!=/</<=/>/>=
  final l = _eval(list[0], answers);
  final r = _eval(list[1], answers);
  if (l == null || r == null) return false; // أيّ مقارنة مع null ⇒ false
  if (_isNonFinite(l) || _isNonFinite(r)) {
    throw const ConditionException('non_finite_number');
  }
  final bothNum = _isNumber(l) && _isNumber(r);
  if (!bothNum && !_sameNonNumericType(l, r)) {
    throw const ConditionTypeException('comparison_type_mismatch');
  }
  switch (op) {
    case '==':
      return l == r;
    case '!=':
      return l != r;
  }
  // مقارنات ترتيبيّة: num×num أو String×String (معجميّة) أو bool×bool.
  int cmp;
  if (bothNum) {
    cmp = (l as num).compareTo(r as num);
  } else if (l is String) {
    cmp = l.compareTo(r as String);
  } else {
    cmp = ((l as bool) ? 1 : 0).compareTo((r as bool) ? 1 : 0);
  }
  switch (op) {
    case '<':
      return cmp < 0;
    case '<=':
      return cmp <= 0;
    case '>':
      return cmp > 0;
    case '>=':
      return cmp >= 0;
  }
  throw ConditionException('operator_not_allowed:$op');
}

/// يقيّم شرط V1 ويعيد bool. يرفع ConditionTypeException على اختلاف الأنواع.
bool evaluateCondition(Object? condition, Map<String, Object?> answers) {
  final result = _eval(condition, answers);
  if (result is! bool) {
    throw const ConditionTypeException('condition_root_must_be_boolean');
  }
  return result;
}
