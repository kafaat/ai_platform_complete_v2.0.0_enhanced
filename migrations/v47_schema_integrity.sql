-- v47: تقوية سلامة الـSchema (Referential Integrity) — قيود تفرضها القاعدة نفسها
-- لا الـAPI فقط. كلّها idempotent وآمنة على البيانات القائمة (NOT VALID / DO-guard).
-- يعالج فجوات مراجعة الترحيلات: FK مركّب tenant-aware، تفرّد الحقل، قيود تواريخ
-- الموسم، وترقية manager_user_id إلى FK حقيقيّ. يعدّل fields/seasons/activities.

-- ── (1) FK مركّب tenant-aware ────────────────────────────────────
-- يضمن أنّ tenant الموسم/النشاط = tenant الحقل (يمنع الربط عبر المستأجِرين عند
-- خطأ برمجيّ — RLS وحده لا يضمن العلاقة). NOT VALID: يُفرض على الصفوف الجديدة
-- فقط (لا يفشل على بيانات قائمة)؛ شغّل VALIDATE CONSTRAINT لاحقاً بعد التنظيف.
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'uq_fields_tenant_field') THEN
        ALTER TABLE fields ADD CONSTRAINT uq_fields_tenant_field UNIQUE (tenant_id, field_id);
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_seasons_field_tenant') THEN
        ALTER TABLE seasons ADD CONSTRAINT fk_seasons_field_tenant
            FOREIGN KEY (tenant_id, field_id) REFERENCES fields (tenant_id, field_id)
            ON DELETE CASCADE NOT VALID;
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_activities_field_tenant') THEN
        ALTER TABLE activities ADD CONSTRAINT fk_activities_field_tenant
            FOREIGN KEY (tenant_id, field_id) REFERENCES fields (tenant_id, field_id)
            ON DELETE CASCADE NOT VALID;
    END IF;
END $$;

-- ── (2) تفرّد الحقل على مستوى القاعدة ────────────────────────────
-- field_code فريد لكلّ مستأجِر (حيث ليس NULL)، والاسم فريد لكلّ (مستأجِر+مزرعة).
-- DO/EXCEPTION: لو وُجد تكرار في بيانات قائمة لا نُفشل الترحيل — ننبّه فقط.
DO $$ BEGIN
    CREATE UNIQUE INDEX IF NOT EXISTS uq_fields_tenant_field_code
        ON fields (tenant_id, field_code) WHERE field_code IS NOT NULL;
EXCEPTION WHEN OTHERS THEN
    RAISE NOTICE 'تخطّي uq_fields_tenant_field_code — field_code مكرّر موجود؛ نظّف ثمّ أعد التطبيق';
END $$;

DO $$ BEGIN
    CREATE UNIQUE INDEX IF NOT EXISTS uq_fields_tenant_farm_name
        ON fields (tenant_id, COALESCE(farm_id, ''), lower(name));
EXCEPTION WHEN OTHERS THEN
    RAISE NOTICE 'تخطّي uq_fields_tenant_farm_name — أسماء حقول مكرّرة موجودة؛ نظّف ثمّ أعد التطبيق';
END $$;

-- ── (3) قيود تواريخ الموسم (تحمي القاعدة نفسها) ──────────────────
-- ترتيب منطقيّ: تسوية ≤ حراثة ≤ بذر ≤ نهاية. NULL-safe، NOT VALID للبيانات القائمة.
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chk_seasons_dates') THEN
        ALTER TABLE seasons ADD CONSTRAINT chk_seasons_dates CHECK (
            (season_end IS NULL OR sowing_date IS NULL OR season_end >= sowing_date)
            AND (sowing_date IS NULL OR plowing_date IS NULL OR sowing_date >= plowing_date)
            AND (plowing_date IS NULL OR land_leveling_date IS NULL
                 OR plowing_date >= land_leveling_date)
        ) NOT VALID;
    END IF;
END $$;

-- ── (4) ترقية manager_user_id إلى FK حقيقيّ ──────────────────────
-- v41 أضافه VARCHAR(64) (مرجع منطقيّ). users في نفس القاعدة (v9)، فنرقّيه إلى
-- INTEGER + FK users(id). آمن (عمود حديث بلا بيانات؛ USING يحوّل النصوص الرقميّة).
DO $$ BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'fields' AND column_name = 'manager_user_id'
          AND data_type = 'character varying'
    ) THEN
        ALTER TABLE fields ALTER COLUMN manager_user_id TYPE INTEGER
            USING (NULLIF(manager_user_id, '')::INTEGER);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_fields_manager_user') THEN
        ALTER TABLE fields ADD CONSTRAINT fk_fields_manager_user
            FOREIGN KEY (manager_user_id) REFERENCES users (id) ON DELETE SET NULL;
    END IF;
END $$;
