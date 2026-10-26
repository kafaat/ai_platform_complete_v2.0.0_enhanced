// SAHOOL — features/crop_season/presentation/season_form_logic.dart
// منطق نموذج الموسم نقيّاً (بلا ودجات) ليُختبَر مباشرةً: التحقّق يطابق ما يرفضه
// الخادم (fields.py:create_season/update_season + season_models.py) فيُعرَض الخطأ
// سطريّاً قبل الإرسال بدل 422 بعده، وجسم PATCH يحمل الحقول المتغيّرة فقط.
import 'package:sahool_app/core/network/api_exception.dart';
import 'package:sahool_app/core/utils/formatters.dart';

import '../data/season_models.dart';

class SeasonFormInput {
  const SeasonFormInput({
    this.crop,
    this.cultivar = '',
    this.irrigationType,
    this.sowingDate,
    this.seasonEnd,
    this.targetYieldText = '',
    this.notes = '',
  });

  /// crop_id من الفهرس أو نصّ حرّ حين يتعذّر الفهرس.
  final String? crop;
  final String cultivar;
  final String? irrigationType;
  final DateTime? sowingDate;

  /// الحصاد المتوقّع = season_end في الخادم.
  final DateTime? seasonEnd;
  final String targetYieldText;
  final String notes;
}

/// مفاتيح أخطاء النموذج (حقل ← رسالة).
abstract final class SeasonFormField {
  static const crop = 'crop';
  static const cultivar = 'cultivar';
  static const sowing = 'sowing_date';
  static const end = 'season_end';
  static const targetYield = 'target_yield';
  static const notes = 'notes';
}

/// يتحقّق من المدخلات. [original] غير null ⇒ وضع التعديل.
Map<String, String> validateSeasonForm(SeasonFormInput i, {Season? original}) {
  final e = <String, String>{};
  if ((i.crop ?? '').trim().isEmpty) {
    e[SeasonFormField.crop] = 'اختر المحصول';
  }
  if (i.cultivar.trim().length > 100) {
    e[SeasonFormField.cultivar] = 'اسم الصنف أطول من 100 حرف';
  }
  if (i.sowingDate == null) {
    // تاريخ الزراعة شرطُ الفينولوجيا وإجراءات الطور على الخادم.
    e[SeasonFormField.sowing] = original?.sowingDate != null
        ? 'لا يمكن مسح تاريخ الزراعة بعد حفظه'
        : 'حدّد تاريخ الزراعة';
  }
  final s = i.sowingDate, end = i.seasonEnd;
  if (s != null && end != null && end.isBefore(s)) {
    e[SeasonFormField.end] = 'تاريخ الحصاد المتوقّع قبل تاريخ الزراعة';
  } else if (end == null && original?.seasonEnd != null) {
    e[SeasonFormField.end] = 'لا يمكن مسح تاريخ الحصاد بعد حفظه';
  }
  final yt = i.targetYieldText.trim();
  if (yt.isNotEmpty) {
    final v = parseLocalizedNum(yt);
    if (v == null) {
      e[SeasonFormField.targetYield] = 'أدخل رقماً صحيحاً';
    } else if (v < 0) {
      e[SeasonFormField.targetYield] = 'لا تكون الإنتاجيّة سالبة';
    }
  }
  if (i.notes.length > 2000) {
    e[SeasonFormField.notes] = 'الملاحظات أطول من 2000 حرف';
  }
  return e;
}

String? _blankToNull(String s) => s.trim().isEmpty ? null : s.trim();

/// جسم POST /fields/{id}/seasons.
Map<String, dynamic> buildCreateBody(SeasonFormInput i) => {
  'crops': [i.crop!.trim()],
  if (_blankToNull(i.cultivar) != null) 'cultivar': i.cultivar.trim(),
  if (i.irrigationType != null) 'irrigation_type': i.irrigationType,
  if (i.sowingDate != null) 'sowing_date': isoDay(i.sowingDate!),
  if (i.seasonEnd != null) 'season_end': isoDay(i.seasonEnd!),
  if (parseLocalizedNum(i.targetYieldText) != null)
    'target_yield_kg_ha': parseLocalizedNum(i.targetYieldText),
  if (_blankToNull(i.notes) != null) 'notes_ar': i.notes.trim(),
};

/// جسم PATCH: الحقول المتغيّرة فقط (الخادم يحدّث ما يُمرَّر). فارغ ⇒ لا تغيير.
Map<String, dynamic> buildPatchBody(SeasonFormInput i, Season original) {
  final b = <String, dynamic>{};
  final crop = i.crop?.trim();
  if (crop != null && crop.isNotEmpty && crop != original.primaryCrop) {
    // نُبقي المحاصيل الإضافيّة (تحميل بينيّ) كما هي.
    b['crops'] = [crop, ...original.crops.skip(1)];
  }
  final cultivar = _blankToNull(i.cultivar);
  if (cultivar != original.cultivar) b['cultivar'] = cultivar;
  if (i.irrigationType != null && i.irrigationType != original.irrigationType) {
    b['irrigation_type'] = i.irrigationType;
  }
  if (i.sowingDate != null && isoDay(i.sowingDate!) != original.sowingDate) {
    b['sowing_date'] = isoDay(i.sowingDate!);
  }
  if (i.seasonEnd != null && isoDay(i.seasonEnd!) != original.seasonEnd) {
    b['season_end'] = isoDay(i.seasonEnd!);
  }
  final y = parseLocalizedNum(i.targetYieldText);
  if (y != original.targetYieldKgHa) b['target_yield_kg_ha'] = y;
  final notes = _blankToNull(i.notes);
  if (notes != original.notesAr) b['notes_ar'] = notes;
  if (b.isNotEmpty && original.rowVersion != null) {
    // تزامن تفاؤليّ: 409 إن عُدِّل الموسم من جلسة أخرى منذ قراءته.
    b['base_version'] = original.rowVersion;
  }
  return b;
}

/// رسالة خطأ كتابة الموسم: 422/409 تحمل نصّاً عربيّاً من الخادم في `detail`
/// (`message_ar` أو `errors_ar` أو نصّ) فنعرضه؛ غيرها بصياغة ApiException الثابتة.
String seasonWriteError(Object error) {
  final e = ApiException.from(error);
  if (e.kind != ApiErrorKind.validation && e.kind != ApiErrorKind.conflict) {
    return e.messageAr;
  }
  final d = e.detail;
  if (d is String && d.isNotEmpty) return d;
  if (d is Map) {
    final m = d['message_ar'];
    if (m is String && m.isNotEmpty) return m;
    final errs = d['errors_ar'];
    if (errs is List && errs.isNotEmpty) return errs.join('\n');
  }
  return e.messageAr;
}
