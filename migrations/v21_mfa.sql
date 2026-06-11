-- ════════════════════════════════════════════════════════════
-- SAHOOL v21 — مصادقة ثنائيّة (MFA / TOTP) على users
-- ════════════════════════════════════════════════════════════
-- الفجوة المسدودة (تدقيق التغطية، الطبقة ١٥ / الأمن): المرفق يطلب MFA صراحةً،
-- والبصمة في الموبايل كانت stub تُرجِع false. هنا أساس TOTP (RFC 6238):
--   • mfa_secret  — السرّ المشترك (base32) يُولَّد عند التسجيل، NULL إن غير مفعّل.
--   • mfa_enabled — يصبح TRUE فقط بعد تأكيد أوّل رمز صحيح (إثبات الاقتران).
-- السرّ حسّاس؛ لا يُعاد أبداً بعد التفعيل (يُعرَض مرّة عند الاقتران فقط).

ALTER TABLE users ADD COLUMN IF NOT EXISTS mfa_secret  VARCHAR(64);
ALTER TABLE users ADD COLUMN IF NOT EXISTS mfa_enabled BOOLEAN NOT NULL DEFAULT FALSE;

COMMENT ON COLUMN users.mfa_secret  IS 'سرّ TOTP المشترك (base32) — حسّاس، لا يُعاد بعد التفعيل';
COMMENT ON COLUMN users.mfa_enabled IS 'MFA مفعّل (TRUE فقط بعد تأكيد أوّل رمز)';
