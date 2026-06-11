-- v21: عمود المسؤول عن الحقل (manager) لجدول fields
-- الفجوة: نموذج «إضافة حقل» يجمع اسم المسؤول لكن لا عمود يحفظه؛ POST /api/v1/fields
-- صار يكتبه وGET يقرأه (يُمرَّر للواجهة بدل ضياعه). idempotent.

ALTER TABLE fields ADD COLUMN IF NOT EXISTS manager VARCHAR(100);
