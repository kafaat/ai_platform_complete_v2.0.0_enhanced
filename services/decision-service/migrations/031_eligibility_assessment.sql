-- CANONICAL-SNAPSHOT-ELIGIBILITY-POLICY-01
--
-- الأهليّة كيانٌ **مشتقّ** لا حقلٌ في اللقطة. اللقطة معنونة بمحتواها
-- (`UNIQUE(tenant_id, snapshot_hash)` في ٠١٩ + مُشغِّل يمنع UPDATE/DELETE)، فإضافة
-- حقل أهليّة داخلها تُغيّر كلّ هاش قائم وتكسر إعادة التشغيل ونَسَب الأدلّة.
--
-- ولذلك: جدولٌ منفصل مفتاحه (tenant_id, snapshot_hash, policy_version) — فتُعاد تقييم
-- لقطة قديمة تحت سياسة جديدة **بلا لمس اللقطة ولا تاريخها**، ولا يدخل
-- `policy_version` ولا `assessment_id` في `snapshot_hash` أبداً.
--
-- ملاحظة عن هذه الهجرة تحديداً: **لا تُعدَّل `decision_vegetation_snapshots` هنا بحرف
-- واحد** — لا عمود مضاف ولا قيد مُغيَّر. أيّ سطر يفعل ذلك يُبطِل الغرض من الملفّ.

CREATE TABLE IF NOT EXISTS decision_eligibility_assessments (
  assessment_id      text PRIMARY KEY,
  tenant_id          uuid NOT NULL,
  snapshot_hash      text NOT NULL,
  policy_version     text NOT NULL,
  policy_digest      text NOT NULL,
  contract_version   text NOT NULL,
  -- لحظة التقييم المنطقيّة (مُدخَل، تدخل البصمة) — تُميَّز عن ساعة الحائط أدناه.
  as_of              timestamptz NOT NULL,
  -- ساعة الحائط: تُسجَّل ولا تدخل البصمة. لو دخلت لَما كان التقييم حتميّاً.
  assessed_at        timestamptz NOT NULL DEFAULT now(),
  inputs_digest      text NOT NULL,
  assessment_digest  text NOT NULL,
  stages             jsonb NOT NULL,
  reasons            jsonb NOT NULL,
  created_at         timestamptz NOT NULL DEFAULT now(),
  -- تقييمٌ واحد لكلّ (لقطة، سياسة، لحظة): إعادة التشغيل تُرجِع القائم لا تُكرّره.
  UNIQUE (tenant_id, snapshot_hash, policy_version, as_of),
  CHECK (snapshot_hash ~ '^[a-fA-F0-9]{64}$'),
  CHECK (assessment_digest ~ '^[a-f0-9]{64}$'),
  CHECK (policy_digest ~ '^[a-f0-9]{64}$'),
  CHECK (inputs_digest ~ '^[a-f0-9]{64}$'),
  -- المراحل الأربع حاضرة كلّها وبقيم منطقيّة — «صالحة/غير صالحة» هي الخلط الذي
  -- أوجب الفجوة، فلا يُقبَل تقييم يطوي المراحل.
  CHECK (
    jsonb_typeof(stages) = 'object'
    AND (stages ? 'discover') AND (stages ? 'diagnose')
    AND (stages ? 'propose')  AND (stages ? 'execute')
    AND jsonb_typeof(stages -> 'discover') = 'boolean'
    AND jsonb_typeof(stages -> 'diagnose') = 'boolean'
    AND jsonb_typeof(stages -> 'propose')  = 'boolean'
    AND jsonb_typeof(stages -> 'execute')  = 'boolean'
  ),
  CHECK (jsonb_typeof(reasons) = 'object')
);

CREATE INDEX IF NOT EXISTS idx_eligibility_snapshot
  ON decision_eligibility_assessments (tenant_id, snapshot_hash, policy_version);

-- المرجع مُركَّب بالمستأجِر: لقطةٌ مخمَّنة أو مُعاد تشغيلها من مستأجِر آخر لا تُحقّق
-- المرجع أبداً (نفس نمط ٠١٩). NOT VALID فلا تُفشِل الهجرة على بيانات قائمة.
DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM pg_class WHERE relname = 'decision_vegetation_snapshots')
     AND NOT EXISTS (
       SELECT 1 FROM pg_constraint WHERE conname = 'fk_eligibility_snapshot_tenant'
     ) THEN
    ALTER TABLE decision_eligibility_assessments
      ADD CONSTRAINT fk_eligibility_snapshot_tenant
      FOREIGN KEY (tenant_id, snapshot_hash)
      REFERENCES decision_vegetation_snapshots (tenant_id, snapshot_hash)
      NOT VALID;
  END IF;
END $$;

-- مصنوعٌ مشتقّ لكنّه **دليل**: يُعاد اشتقاقه ولا يُحرَّر. التحرير في مكانه يجعل
-- تقييماً قديماً يبدو وكأنّه صدر بقواعد اليوم.
DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM pg_proc WHERE proname='decision_wx11_completion_append_only') THEN
    EXECUTE 'DROP TRIGGER IF EXISTS trg_decision_eligibility_append_only ON decision_eligibility_assessments';
    EXECUTE 'CREATE TRIGGER trg_decision_eligibility_append_only BEFORE UPDATE OR DELETE ON decision_eligibility_assessments FOR EACH ROW EXECUTE FUNCTION decision_wx11_completion_append_only()';
  END IF;
END $$;

-- عزل المستأجِر — نفس صياغة ٠١٩ حرفيّاً، و`FORCE` كي لا يُفلِت المالك من سياسته.
DO $$ BEGIN
  EXECUTE 'ALTER TABLE decision_eligibility_assessments ENABLE ROW LEVEL SECURITY';
  EXECUTE 'ALTER TABLE decision_eligibility_assessments FORCE ROW LEVEL SECURITY';
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies
    WHERE tablename = 'decision_eligibility_assessments' AND policyname = 'tenant_isolation'
  ) THEN
    EXECUTE 'CREATE POLICY tenant_isolation ON decision_eligibility_assessments USING (tenant_id = nullif(current_setting(''app.current_tenant'', true), '''')::uuid) WITH CHECK (tenant_id = nullif(current_setting(''app.current_tenant'', true), '''')::uuid)';
  END IF;
END $$;
