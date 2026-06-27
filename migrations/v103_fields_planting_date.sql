-- v103: إضافة عمود planting_date إلى جدول fields
-- السبب: field_state_projection.py (السطر 578) يستعلم عن planting_date في SELECT crop, planting_date, lat FROM fields
--        غيابه يُفشِل recompute_field_state() داخل معاملة إنشاء الحقل ⇒ 503 عند إنشاء أيّ حقل.
-- الإصلاح: عمود date اختياريّ (NULL = لم يُزرَع بعد) يُضاف إن لم يكن موجوداً.

ALTER TABLE fields
    ADD COLUMN IF NOT EXISTS planting_date date;

COMMENT ON COLUMN fields.planting_date IS
    'تاريخ بداية الزراعة (NULL = لم يُزرَع بعد). يُستخدَم في field_state_projection لحساب أيّام النمو.';
