// ردود الخادم الحقيقيّة (services/scout-ingest-service/field_forms_api.py) لاختبارات
// النماذج الميدانيّة. لا يُخترع شكل: كلّ مفتاح هنا يكتبه submit_form.

/// ردّ القبول كما يبنيه submit_form (الفرع ⑤ «مقبول»).
const Map<String, Object?> kAccepted = {
  'idempotent': false,
  'envelope_id': 7,
  'field_submission_id': '0d4c7a1e-0000-4000-8000-000000000001',
  'trust_status': 'accepted',
  'form_validation_status': 'valid',
  'version_resolution_status': 'current',
  'stale_version': false,
  'answers_hash': 'h',
};
