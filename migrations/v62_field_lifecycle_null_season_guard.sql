-- SAHOOL v62 — migrations/v62_field_lifecycle_null_season_guard.sql
-- ════════════════════════════════════════════════════════════════════
-- الفجوة: سباق (race condition) في FieldLifecycleEngine.get_or_create.
--
-- النمط في الكود: Read → Check → Insert بلا FOR UPDATE ولا ON CONFLICT.
-- القيد الموجود `UNIQUE(field_id, season_id)` (v10) **لا يحمي** الحالة
-- الافتراضيّة، لأنّ season_id يكون NULL حتّى البذر، وفي PostgreSQL
-- ‏`NULL ≠ NULL` داخل قيود UNIQUE — فصفّان بنفس field_id و season_id=NULL
-- لا ينتهكان القيد ⇒ يُسمَح بدورتَي حياة مكرَّرتين لنفس الحقل.
--
-- السيناريو المُثبَت:
--   طلب A: season_id=NULL → SELECT لا يجد → INSERT ✓
--   طلب B: season_id=NULL → SELECT لا يجد → INSERT ✓ (لا ينتهك UNIQUE!)
--   ⇒ دورتا حياة مكرَّرتان، تعارض في الحالة، انتقالات متضاربة.
--
-- الحلّ: فهرس فريد جزئيّ (partial unique index) على (field_id) فقط
-- حيث season_id IS NULL. هذا يفرض الوحدانيّة على الحالة قبل-البذر التي
-- لا يغطّيها قيد UNIQUE العادي، **دون** الإخلال بقيد (field_id, season_id)
-- للمواسم المحدَّدة (PostgreSQL يسمح بصفوف season_id غير-NULL متعدّدة).
--
-- ملاحظة: نُنظّف أيّ تكرارات NULL سابقة قبل إنشاء الفهرس (وإلّا فشل الإنشاء).
-- ════════════════════════════════════════════════════════════════════

BEGIN;

-- ① تنظيف تكرارات ما-قبل-الإصلاح (إن وُجدت): أبقِ أقدم صفّ لكلّ
--    (field_id) حيث season_id IS NULL، واحذف الباقي. الأقدميّة بـ created_at
--    ثمّ lifecycle_id (حتميّ). الانتقالات المرتبطة تُحذف تتالياً إن وُجد FK،
--    وإلّا تبقى يتيمة (نادر جدّاً — هذه حالة شذوذ سباق فعليّ).
WITH ranked AS (
    SELECT
        lifecycle_id,
        ROW_NUMBER() OVER (
            PARTITION BY field_id
            ORDER BY created_at ASC, lifecycle_id ASC
        ) AS rn
    FROM field_lifecycle
    WHERE season_id IS NULL
)
DELETE FROM field_lifecycle fl
USING ranked r
WHERE fl.lifecycle_id = r.lifecycle_id
  AND r.rn > 1;

-- ② الفهرس الفريد الجزئيّ — يسدّ ثغرة NULL.
--    (CONCURRENTLY غير ممكن داخل معاملة؛ هذا الجدول صغير فالقفل وجيز.)
CREATE UNIQUE INDEX IF NOT EXISTS ux_field_lifecycle_field_null_season
    ON field_lifecycle (field_id)
    WHERE season_id IS NULL;

COMMENT ON INDEX ux_field_lifecycle_field_null_season IS
    'يسدّ ثغرة NULL في UNIQUE(field_id, season_id): يفرض وحدانيّة دورة الحياة '
    'قبل-البذر (season_id IS NULL) التي لا يغطّيها قيد UNIQUE العادي لأنّ '
    'NULL≠NULL. يعمل مع get_or_create المُحدَّث (ON CONFLICT). راجع v62.';

COMMIT;
