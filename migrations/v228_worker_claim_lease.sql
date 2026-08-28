-- v228: WORKER-CLAIM-NOT-PINNED-BY-A-TRANSACTION-01 — أعمدةُ المطالبة والإجارة.
--
-- العطلُ المقيس: عمّالُ `phase_runtime_workers` يطالبون بـ`FOR UPDATE SKIP LOCKED`
-- داخل اتّصالٍ في وضع autocommit وبلا `conn.transaction()` (صفرُ مواضع في الملفّ
-- كلّه). وفي autocommit يُحرَّر قفلُ الصفّ **فور انتهاء عبارة SELECT** — فالمطالبةُ
-- غيرُ مثبَتة، وعاملٌ ثانٍ يلتقط الصفوفَ نفسَها.
--
-- وأخطرُ مواضعه `run_actuator_once`: يطالِب ثمّ ينشر `sahool.actuator.dispatch.requested`.
-- فعطلُ المطالبة ليس مجرّداً — **عاملان متزامنان قد يطلبان إرسالاً فيزيائيّاً مرّتين
-- للأمر نفسه**.
--
-- والعلاجُ لا يكون بإطالة المعاملة حتّى تشمل النشر: ذلك يُعيد النمطَ الأوّل
-- (`event_bus.py`) الذي يحبس الأقفالَ أثناء I/O شبكيّ. بل بفصلٍ ثلاثيّ:
--   TX-1: مطالبةٌ قصيرة تُثبَّت بـcommit  ⇒ الصفُّ يخرج من نطاق الالتقاط
--   الشبكة: خارج أيّ معاملة
--   TX-2: إنهاءٌ بـCAS على `claim_token`  ⇒ عاملٌ انتهت إجارتُه لا يُنهي مطالبةَ غيره
--
-- ولمَ `claim_token` ولا يكفي `status='claimed'`: عند انتهاء الإجارة يُعيد عاملٌ
-- ثانٍ المطالبةَ، فلو كان الشرطُ الحالةَ وحدَها لأنهى العاملُ الأوّلُ **مطالبةَ
-- الثاني** ظانّاً أنّها مطالبتُه. الرمزُ يجعل الشرطَ هويّةً لا حالة.

ALTER TABLE runtime_event_outbox
  ADD COLUMN IF NOT EXISTS claim_token UUID,
  ADD COLUMN IF NOT EXISTS claimed_by TEXT,
  ADD COLUMN IF NOT EXISTS lease_until TIMESTAMPTZ;

ALTER TABLE marketplace_plugin_execution_runs
  ADD COLUMN IF NOT EXISTS claim_token UUID,
  ADD COLUMN IF NOT EXISTS claimed_by TEXT,
  ADD COLUMN IF NOT EXISTS lease_until TIMESTAMPTZ;

ALTER TABLE marketplace_plugin_runtime_events
  ADD COLUMN IF NOT EXISTS claim_token UUID,
  ADD COLUMN IF NOT EXISTS claimed_by TEXT,
  ADD COLUMN IF NOT EXISTS lease_until TIMESTAMPTZ;

ALTER TABLE model_promotion_history_runtime
  ADD COLUMN IF NOT EXISTS claim_token UUID,
  ADD COLUMN IF NOT EXISTS claimed_by TEXT,
  ADD COLUMN IF NOT EXISTS lease_until TIMESTAMPTZ;

ALTER TABLE model_rollback_history_runtime
  ADD COLUMN IF NOT EXISTS claim_token UUID,
  ADD COLUMN IF NOT EXISTS claimed_by TEXT,
  ADD COLUMN IF NOT EXISTS lease_until TIMESTAMPTZ;

ALTER TABLE iot_command_dispatch
  ADD COLUMN IF NOT EXISTS claim_token UUID,
  ADD COLUMN IF NOT EXISTS claimed_by TEXT,
  ADD COLUMN IF NOT EXISTS lease_until TIMESTAMPTZ;

-- فهارسُ الاستردادِ جزئيّةٌ عمداً: عاملُ `reclaim` يسأل عن المُطالَبِ المنتهيةِ
-- إجارتُه وحدَه، وهو أقلّيّةٌ ضئيلةٌ من الصفوف. فهرسٌ كاملٌ كان سيُكلِّف كلَّ كتابة
-- ولا يخدم إلّا هذا السؤال.
CREATE INDEX IF NOT EXISTS idx_runtime_event_outbox_expired_lease
  ON runtime_event_outbox (lease_until) WHERE claim_token IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_plugin_execution_runs_expired_lease
  ON marketplace_plugin_execution_runs (lease_until) WHERE claim_token IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_plugin_runtime_events_expired_lease
  ON marketplace_plugin_runtime_events (lease_until) WHERE claim_token IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_model_promotion_runtime_expired_lease
  ON model_promotion_history_runtime (lease_until) WHERE claim_token IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_model_rollback_runtime_expired_lease
  ON model_rollback_history_runtime (lease_until) WHERE claim_token IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_iot_command_dispatch_expired_lease
  ON iot_command_dispatch (lease_until) WHERE claim_token IS NOT NULL;
