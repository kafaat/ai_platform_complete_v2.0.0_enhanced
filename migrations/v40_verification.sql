-- ════════════════════════════════════════════════════════════
-- SAHOOL v40 — تأكيد البريد/الهاتف (Email/Phone Verification) على users
-- ════════════════════════════════════════════════════════════
-- تحقّق ناعم (soft) عند التسجيل: المستخدم يطلب رمز OTP من ٦ أرقام (يُخزَّن في
-- Redis قصير الأجل، لا يُحفظ في القاعدة)، ويؤكّده، فنُثبّت العلَم هنا:
--   • verified_email — TRUE بعد تأكيد رمز البريد. FALSE افتراضاً.
--   • verified_phone — TRUE بعد تأكيد رمز الهاتف. FALSE افتراضاً.
-- العلَمان لا يحجبان الدخول (تحقّق ناعم) — مجرّد إشارة ثقة للحساب. idempotent.

ALTER TABLE users ADD COLUMN IF NOT EXISTS verified_email BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE users ADD COLUMN IF NOT EXISTS verified_phone BOOLEAN NOT NULL DEFAULT FALSE;

COMMENT ON COLUMN users.verified_email IS 'البريد مُتحقَّق منه (TRUE بعد تأكيد رمز OTP)';
COMMENT ON COLUMN users.verified_phone IS 'الهاتف مُتحقَّق منه (TRUE بعد تأكيد رمز OTP)';
