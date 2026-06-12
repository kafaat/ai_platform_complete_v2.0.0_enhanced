# إصلاح: Odoo — قاعدة منفصلة + تهيئة base

## العَرَض
سجلّ `sahool-odoo` يكرّر:
```
ERROR: relation "ir_module_module" does not exist
KeyError: 'ir.http'
Tried to poll an undefined table on database sahool.
```

## السبب الجذريّ (تحقُّق بالكود)
1. قاعدة المنصّة اسمها **`sahool`** (`POSTGRES_DB: sahool`).
2. كان `docker-compose.v9.yml` يضبط `ODOO_DB: ${ODOO_DB:-sahool}` للجسر و`DB_NAME`
   لـOdoo → يطلب من Odoo خدمة **قاعدة المنصّة نفسها** (قاعدة RLS، بلا مخطّط Odoo).
3. خدمة Odoo كانت **بلا `command`** → entrypoint الصورة الافتراضي لا يُثبّت `base`،
   فلا مخطّط Odoo أصلاً (`ir_module_module`/`ir.http` غير موجودة).
4. كود الجسر يقصد قاعدة منفصلة (`sahool_erp`) لكنّ الـcompose كان يطمسها.

## الإصلاح (في `docker-compose.v9.yml` + `.env.example`)
1. **قاعدة Odoo منفصلة**: `ODOO_DB` الافتراض الآن `sahool_erp` (للجسر و`DB_NAME`).
2. **تهيئة + حصر** عبر `command` لخدمة Odoo:
   ```
   odoo -d ${ODOO_DB:-sahool_erp} -i base --without-demo=all
        --db-filter=^${ODOO_DB:-sahool_erp}$
   ```
   - `-i base`: يُنشئ القاعدة ويثبّت `base` أوّل تشغيل (لاحقاً no-op).
   - `--db-filter`: يحصر Odoo على قاعدته فلا يلمس قاعدة المنصّة `sahool` (أمان).

## متطلّب تشغيليّ (مهمّ)
`sahool_user` يحتاج صلاحيّة **`CREATEDB`** كي يُنشئ Odoo قاعدة `sahool_erp`:
```sql
ALTER ROLE sahool_user CREATEDB;
```
أو أنشئ القاعدة مسبقاً: `CREATE DATABASE sahool_erp OWNER sahool_user;`
(ثمّ يهيّئها Odoo بـ`-i base`).

## التحقّق (في بيئتك الحيّة)
```bash
docker compose --profile odoo up -d sahool-odoo
docker logs sahool-odoo | grep -iE "Modules loaded|Registry|HTTP service"   # نجاح
# يجب ألّا يظهر ir_module_module/ir.http بعد التهيئة.
```

> ⚠ صدق البيئة: لا يمكن تشغيل Docker/Odoo للتحقّق هنا — الإصلاح بنيويّ على الـcompose
> مدعوم بقراءة الكود. تحقّق منه بيئتك بعد التطبيق (خاصّة صلاحيّة CREATEDB).
