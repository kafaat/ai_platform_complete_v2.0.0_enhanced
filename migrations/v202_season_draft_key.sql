-- v202: SEASON-RECORD-ENTRY-01 — مفتاح idempotency للمسودّة (draft_key).
--
-- المدخل (SEASON-RECORD-ENTRY-01 §6): «idempotency على draft_key — إعادة إرسال نفس المسودّة لا
-- تُنشئ نسخة». v201 لم يُضمّن العمود (كان أساس السجلّ فقط)، فهذا يضيفه إضافةً غير كاسرة.
--
-- **توضيح ملزم (المواصفة §5):** ``draft_key`` مفتاح **منع نسخ فقط** — ليس مرجع ثقة، لا يظهر في أيّ
-- قرار قبول، ولا يُكتب في ``accepted_by``. القبول يعتمد حصراً على الهويّة المُصدَّقة من الحافّة (§4-①).
--
-- **الفهرس الفريد جزئيّ:** يمنع تكرار (tenant_id, field_id, draft_key) عندما ``draft_key`` مُقدَّم فقط.
-- ``draft_key IS NULL`` (لا idempotency مطلوب) يبقى مسموحاً بلا حدّ — فلا نفرض مفتاحاً على من لا يريده.
-- المستأجِر جزء من المفتاح ⇒ لا تصادم عبر المستأجرين (متّسق مع RLS على season_records من v201).

ALTER TABLE season_records ADD COLUMN IF NOT EXISTS draft_key TEXT;

CREATE UNIQUE INDEX IF NOT EXISTS ux_season_records_draft_key
    ON season_records (tenant_id, field_id, draft_key)
    WHERE draft_key IS NOT NULL;

COMMENT ON COLUMN season_records.draft_key IS
  'SEASON-RECORD-ENTRY-01: مفتاح idempotency لمنع نسخ المسودّة (dedup على tenant+field_id+draft_key). '
  'ليس مرجع ثقة ولا يدخل قرار القبول (المواصفة §5). NULL مسموح (لا idempotency مطلوب).';
