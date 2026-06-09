-- ═══════════════════════════════════════════════════════════════════
-- SAHOOL v9 — اختبار عزل المستأجرين (RLS) الحيّ
-- ═══════════════════════════════════════════════════════════════════
-- يثبت فعليّاً أنّ مستأجراً لا يرى بيانات مستأجر آخر، وأنّ السياسة
-- fail-closed (بلا app.current_tenant → صفر صفوف).
--
-- الاستخدام (مهمّ — كمستخدم التطبيق غير superuser):
--   psql "postgresql://sahool_user:PASS@host:5432/sahool" \
--        -v ON_ERROR_STOP=1 -f scripts_v9/test_tenant_isolation.sql
--
-- ⚠️ تحذير حرج: superuser و BYPASSRLS يتجاوزان RLS دائماً. شغّل هذا
--    بمستخدم عادي (sahool_user) وإلّا ستظهر كلّ الصفوف وتظنّ العزل فاشلاً.
--    تحقّق أوّلاً:  SELECT rolsuper, rolbypassrls FROM pg_roles
--                  WHERE rolname = current_user;  (يجب f و f)
-- ═══════════════════════════════════════════════════════════════════

\set ON_ERROR_STOP on

\echo '═══ ٠. تحقّق أنّ المستخدم الحالي ليس superuser/BYPASSRLS ═══'
DO $$
DECLARE
    is_super BOOLEAN; is_bypass BOOLEAN;
BEGIN
    SELECT rolsuper, rolbypassrls INTO is_super, is_bypass
    FROM pg_roles WHERE rolname = current_user;
    IF is_super OR is_bypass THEN
        RAISE EXCEPTION
            'المستخدم % يتجاوز RLS (super=% bypass=%). شغّل الاختبار بـsahool_user عادي.',
            current_user, is_super, is_bypass;
    END IF;
    RAISE NOTICE 'المستخدم % عادي (لا يتجاوز RLS) ✓', current_user;
END $$;

-- معرّفات مستأجرَين ثابتة للاختبار
\set tenant_a '11111111-1111-1111-1111-111111111111'
\set tenant_b '22222222-2222-2222-2222-222222222222'

-- ─── تنظيف أيّ بقايا اختبار سابق (يحتاج سياق كلّ مستأجر) ───────────
\echo ''
\echo '═══ ١. تنظيف بيانات اختبار سابقة ═══'
BEGIN;
SELECT set_config('app.current_tenant', :'tenant_a', true);
DELETE FROM commands WHERE actor_id = 'isolation-test';
DELETE FROM events   WHERE actor_id = 'isolation-test';
DELETE FROM soil_readings WHERE sensor_id = 'isolation-test';
COMMIT;
BEGIN;
SELECT set_config('app.current_tenant', :'tenant_b', true);
DELETE FROM commands WHERE actor_id = 'isolation-test';
DELETE FROM events   WHERE actor_id = 'isolation-test';
DELETE FROM soil_readings WHERE sensor_id = 'isolation-test';
COMMIT;

-- ─── كتابة بيانات لكلّ مستأجر (ضمن سياقه) ──────────────────────────
\echo ''
\echo '═══ ٢. كتابة صفّ لكلّ مستأجر (commands/events/soil) ═══'

BEGIN;
SELECT set_config('app.current_tenant', :'tenant_a', true);
INSERT INTO commands (command_id, command_type, actor_id, tenant_id, source, status)
VALUES (gen_random_uuid(), 'test.cmd', 'isolation-test', :'tenant_a', 'web', 'pending');
INSERT INTO events (event_id, event_type, entity_type, entity_id, tenant_id, actor_id)
VALUES (gen_random_uuid(), 'test.event', 'field', gen_random_uuid(), :'tenant_a', 'isolation-test');
INSERT INTO soil_readings (field_id, sensor_id, tenant_id)
VALUES ('test-field-a', 'isolation-test', :'tenant_a');
COMMIT;

BEGIN;
SELECT set_config('app.current_tenant', :'tenant_b', true);
INSERT INTO commands (command_id, command_type, actor_id, tenant_id, source, status)
VALUES (gen_random_uuid(), 'test.cmd', 'isolation-test', :'tenant_b', 'web', 'pending');
INSERT INTO events (event_id, event_type, entity_type, entity_id, tenant_id, actor_id)
VALUES (gen_random_uuid(), 'test.event', 'field', gen_random_uuid(), :'tenant_b', 'isolation-test');
INSERT INTO soil_readings (field_id, sensor_id, tenant_id)
VALUES ('test-field-b', 'isolation-test', :'tenant_b');
COMMIT;
\echo '  كُتب صفّ لكلّ مستأجر ✓'

-- ─── الاختبار ١: مستأجر A يرى صفوفه فقط ────────────────────────────
\echo ''
\echo '═══ ٣. اختبار: مستأجر A يرى صفوف A فقط (لا B) ═══'
BEGIN;
SELECT set_config('app.current_tenant', :'tenant_a', true);
DO $$
DECLARE
    a_cnt INT; b_cnt INT;
BEGIN
    SELECT count(*) INTO a_cnt FROM commands
        WHERE actor_id='isolation-test' AND tenant_id='11111111-1111-1111-1111-111111111111';
    SELECT count(*) INTO b_cnt FROM commands
        WHERE actor_id='isolation-test' AND tenant_id='22222222-2222-2222-2222-222222222222';
    IF a_cnt >= 1 AND b_cnt = 0 THEN
        RAISE NOTICE 'commands: A يرى صفوفه (%) ولا يرى B (%) ✓', a_cnt, b_cnt;
    ELSE
        RAISE EXCEPTION 'تسريب! A=%، B=% (المتوقّع A>=1, B=0)', a_cnt, b_cnt;
    END IF;
END $$;
COMMIT;

-- ─── الاختبار ٢: مستأجر B لا يرى صفوف A (الاتّجاه المعاكس) ──────────
\echo ''
\echo '═══ ٤. اختبار: مستأجر B لا يرى صفوف A (events + soil) ═══'
BEGIN;
SELECT set_config('app.current_tenant', :'tenant_b', true);
DO $$
DECLARE
    ev_a INT; soil_a INT;
BEGIN
    -- من سياق B، حاول رؤية بيانات A صراحةً
    SELECT count(*) INTO ev_a FROM events
        WHERE actor_id='isolation-test' AND tenant_id='11111111-1111-1111-1111-111111111111';
    SELECT count(*) INTO soil_a FROM soil_readings
        WHERE sensor_id='isolation-test' AND tenant_id='11111111-1111-1111-1111-111111111111';
    IF ev_a = 0 AND soil_a = 0 THEN
        RAISE NOTICE 'events/soil: B لا يرى أيّ صفّ من A ✓ (عزل سليم)';
    ELSE
        RAISE EXCEPTION 'تسريب IDOR! B يرى من A: events=%، soil=%', ev_a, soil_a;
    END IF;
END $$;
COMMIT;

-- ─── الاختبار ٣: fail-closed (بلا ضبط app.current_tenant → صفر) ────
\echo ''
\echo '═══ ٥. اختبار fail-closed: بلا app.current_tenant → صفر صفوف ═══'
BEGIN;
-- لا نضبط app.current_tenant إطلاقاً (محاكاة اتّصال خام تجاوز tenant_connection)
RESET app.current_tenant;
DO $$
DECLARE
    leaked INT;
BEGIN
    SELECT count(*) INTO leaked FROM commands WHERE actor_id='isolation-test';
    IF leaked = 0 THEN
        RAISE NOTICE 'fail-closed: بلا GUC → صفر صفوف ✓ (لا تسريب للاتّصال الخام)';
    ELSE
        RAISE EXCEPTION 'ثغرة fail-open! بلا GUC ظهر % صفّ', leaked;
    END IF;
END $$;
COMMIT;

-- ─── تنظيف ──────────────────────────────────────────────────────────
\echo ''
\echo '═══ ٦. تنظيف بيانات الاختبار ═══'
BEGIN;
SELECT set_config('app.current_tenant', :'tenant_a', true);
DELETE FROM commands WHERE actor_id='isolation-test';
DELETE FROM events   WHERE actor_id='isolation-test';
DELETE FROM soil_readings WHERE sensor_id='isolation-test';
COMMIT;
BEGIN;
SELECT set_config('app.current_tenant', :'tenant_b', true);
DELETE FROM commands WHERE actor_id='isolation-test';
DELETE FROM events   WHERE actor_id='isolation-test';
DELETE FROM soil_readings WHERE sensor_id='isolation-test';
COMMIT;

\echo ''
\echo '═══════════════════════════════════════════════════════════════'
\echo '✅ كلّ اختبارات العزل نجحت — RLS يعمل فعليّاً (fail-closed + لا IDOR)'
\echo '═══════════════════════════════════════════════════════════════'
