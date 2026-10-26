/// نصوص النماذج الميدانيّة كما يقرؤها المزارع: كلّ حالة/سبب من الخادم يُترجم إلى
/// جملة عربيّة واضحة بدل مفتاح إنجليزيّ خامّ («quarantined»، «version: …»).
/// القيمة الخامّ لا تُخفى عن الدعم: تُعرض ثانويّةً حين لا نعرف ترجمتها.
library;

/// سبب الحجر (`quarantine_reason`) — مصدره `field_forms_api.py` و`dedup_resolution.py`.
String quarantineReasonAr(String? reason) {
  switch (reason) {
    case null:
      return 'استلمه الخادم ووضعه قيد المراجعة.';
    case 'form_version_unknown':
      return 'نسخة النموذج غير معروفة للخادم. حدّث نماذج الحقل ثمّ أعد التعبئة.';
    case 'no_active_assignment':
      return 'هذا النموذج لم يعد مُسنداً لهذا الحقل.';
    case 'form_version_withdrawn':
      return 'سُحب هذا النموذج من الاستعمال، فلن تُعتمد إجاباته.';
    case 'invalid_sync_proof':
      return 'تعذّر إثبات نسخة النموذج التي عُبّئت. افتح الحقل مع الاتصال لتحديث النماذج.';
    case 'form_validation_failed':
      return 'لم تجتز الإجابات تحقّق الخادم.';
    case 'duplicate_key_divergent_payload':
      return 'وصل إرسال سابق بالمعرّف نفسه وبمحتوى مختلف، فوُضع قيد المراجعة.';
    default:
      return 'استلمه الخادم ووضعه قيد المراجعة ($reason).';
  }
}

/// `version_resolution_status` — يُعرض فقط حين يضيف معلومة للمزارع.
String? versionResolutionAr(String? status) {
  switch (status) {
    case null:
    case 'current':
      return null;
    case 'stale_proven':
      return 'عُبّئ على نسخة سابقة من النموذج، وقُبل لأنّها كانت المعتمدة وقت التعبئة.';
    case 'withdrawn_quarantined':
      return 'النسخة المعبّأة مسحوبة.';
    case 'invalid_sync_proof':
      return 'النسخة المعبّأة لم تُثبَت.';
    case 'no_active_assignment':
      return 'لا إسناد فعّال لهذا النموذج على الحقل.';
    default:
      return null;
  }
}
