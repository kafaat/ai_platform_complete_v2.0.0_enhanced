-- ═══════════════════════════════════════════════════════════════════
-- v9_edge_idempotency.sql — منع تكرار مزامنة edge (Hardening مراجعة 7)
-- ═══════════════════════════════════════════════════════════════════
-- العميل (sync_service.py) يرسل idempotency_key ثابتاً لكلّ عنصر.
-- العمود + UNIQUE يجعلان إعادة الإرسال (بعد انقطاع شبكة) لا تُكرّر الصفّ.

ALTER TABLE edge_results ADD COLUMN IF NOT EXISTS idempotency_key VARCHAR(32);

-- فهرس فريد جزئي (يتجاهل NULL للصفوف القديمة) → ON CONFLICT يعمل
CREATE UNIQUE INDEX IF NOT EXISTS uq_edge_idempotency
    ON edge_results (idempotency_key)
    WHERE idempotency_key IS NOT NULL;
