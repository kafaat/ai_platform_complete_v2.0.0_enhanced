# قائمة تسجيل خدمة جديدة (New Service ≈ ~10 Registrations)

**الدرس (من scout-ingest-service، SCOUT-INGEST-01):** إضافة خدمة جديدة تلمس ~10 سجلّات/حُرّاس totality،
وكلّ حارس يكتشفها **واحداً تلو الآخر** في CI (فشل، أصلِح، ادفع، كرّر). **اكسر الدورة:** سجّل كلّ ما دونه
**قبل** الدفع، ثمّ شغّل المسح الاستباقيّ الكامل محليّاً. تكلفة التنقّل مرّة واحدة لا عشراً.

## السجلّات الإلزاميّة (بترتيب الاكتشاف الذي رُصِد فعليّاً)

1. **جرد الخدمات/المسارات:** `python3 scripts/ci/generate_service_inventory.py --write-registry`
   ⇒ `service_inventory.*` · `route_inventory.*` · `SERVICE_REGISTRY.md`.
2. **عقد المستهلك (totality، P0):** أضِف الخدمة إلى `config/service_feature_ui_contracts.json` (evidence =
   كتلة compose + مسار داخليّ + حارس) ثمّ `python3 scripts/ci/service_feature_ui_contract_gate.py` ⇒ 32/32.
3. **تصنيف المسارات المتبقّية:** `python3 scripts/ci/route_residual_classification_guard.py --write`.
4. **صحّة/جاهزيّة:** `python3 scripts/ci/health_readiness_schema_guard.py --write` (+ `runtime_real_smoke` يتبعه).
5. **تعارُض التبعيّات:** `python3 scripts/ci/service_dependency_conflict_guard.py`.
6. **حزمة التبعيّات المباشرة:** `python3 scripts/ci/build_service_dependency_bundle.py` ⇒ `requirements.services.direct.lock`.
7. **إصدار المسارات (api-versioning):** `python3 scripts/ci/api_versioning_policy_guard.py` (مسار `/internal/*` ⇒ `internal_s2s`).
8. **تركيب المسارات:** `python3 scripts/ci/route_mount_contract_guard.py`.
9. **عقد بيئة compose:** أعلِن كلّ `${VAR}` في `docker-compose*.yml` داخل `.env.example` ثمّ
   `python3 scripts/ci/compose_env_contract_gate.py` ⇒ OK.
10. **حزمة الإصدار:** `python3 scripts/release/build_release_bundle.py --root .` + `validate_release_package.py`.

## إن لمست القاعدة (migration/دور/جدول)
- `docs/architecture/db_ownership.yml` (مالك/كاتب وحيد لكلّ جدول جديد) — حارس `test_p0_db_ownership_guard`.
- `migrations/MANIFEST.txt` + `scripts_v9/run_migrations.sql` (خطوة جديدة) — حارس تزامن المُشغّلَين.
- الأدوار/المنح في **كلا** `migrations/bootstrap_postgres.sh` و`migrations/apply_in_compose.sh`.
- `bash scripts/production_validation_gate.sh` محليّاً (main-only، لا يظهر في فحوص الفرع).

## المسح الاستباقيّ (قبل الدفع — يكسر «فشل واحد كلّ مرّة»)
```bash
# كلّ حُرّاس --check
for f in scripts/ci/*.py; do grep -q -- --check "$f" && python3 "$f" --check || true; done
# كلّ استدعاءات ci.yml
grep -oE "python scripts/ci/[a-zA-Z0-9_]+\.py( --[a-z-]+)*" .github/workflows/ci.yml | sort -u | while read c; do bash -c "$c"; done
pytest -m unit -q            # الكامل (درس #179: أيّ migration)
ruff format --check services/ bots/ agents/ tests_v9/
bandit -r services/<new>/ --severity-level high
```
غير القابل محليّاً: `docker_build_matrix_verifier` (يحتاج daemon؛ مصفوفة مُنتقاة 7 خدمات، path-gated — خدمة
دعم جديدة لا تُضاف إليها). المراجع الحيّة: SCOUT-INGEST-01 (scout-ingest) · #201 (field-management-service).
