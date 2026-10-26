// SAHOOL — features/farms/presentation/farm_permissions.dart
// صلاحيّات المزارع على الموبايل مطابقةً للويب والخلفيّة:
// إنشاء مزرعة للمالك فقط (frontend/src/lib/permissions.ts: 'create:farm' =
// owner، canCreateFarm؛ الخلفيّة: FARM_CREATE مقصور على OWNER ⇒ 403 لغيره).
// كان الموبايل يسمح لأيّ دور غير viewer (canMutate) فيصطدم المدير بـ403.
import 'package:sahool_app/core/permissions/permissions.dart';

bool canCreateFarm(AppRole role) => role == AppRole.owner;
