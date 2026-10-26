// SAHOOL — lib/core/network/response_shape.dart
// حرّاس شكل الاستجابة. عقدٌ تغيّر أو استجابةُ وسيطٍ (HTML من الـSPA مثلاً) تُرمى
// صراحةً كـFormatException فتعرضها الواجهة كخطأ، لا أن تُبتلَع كقائمة فارغة
// مضلِّلة («لا بيانات»).

/// يتوقّع مصفوفة JSON من كائنات.
List<Map<String, dynamic>> asJsonList(dynamic data) {
  if (data is! List) {
    throw const FormatException(
        'استجابة غير متوقّعة من الخادم: تُتوقّع قائمة JSON.');
  }
  return data.map((e) {
    if (e is! Map) {
      throw const FormatException(
          'استجابة غير متوقّعة من الخادم: عنصر ليس كائن JSON.');
    }
    return e.cast<String, dynamic>();
  }).toList();
}

/// يتوقّع كائن JSON.
Map<String, dynamic> asJsonMap(dynamic data) {
  if (data is! Map) {
    throw const FormatException(
        'استجابة غير متوقّعة من الخادم: يُتوقّع كائن JSON.');
  }
  return data.cast<String, dynamic>();
}

/// يقبل مصفوفة مباشرة أو كائناً يغلّفها تحت أحد [keys] (مثل `{tasks: [...]}`).
List<Map<String, dynamic>> asWrappedJsonList(dynamic data, List<String> keys) {
  if (data is Map) {
    for (final k in keys) {
      if (data[k] is List) return asJsonList(data[k]);
    }
  }
  return asJsonList(data);
}
