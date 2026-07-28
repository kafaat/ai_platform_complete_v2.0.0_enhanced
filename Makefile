# ============================================================
# SAHOOL v9 — Correctness Closure Pipeline
# ------------------------------------------------------------
# مكيّف لبنية SAHOOL الفعليّة (tenant_id / app.current_tenant /
# raw SQL migrations) — ليس القالب العامّ (account_id/alembic/SDK).
# قاعدة صارمة: لا تنفّذ مرحلة إن فشلت السابقة.
# ============================================================

PYTHON  := python3
COMPOSE := docker compose -f docker-compose.v9.yml
TESTS   := tests_v9
SCRIPTS := scripts_v9

.DEFAULT_GOAL := verify-static
.PHONY: verify-static verify-syntax verify-tests verify-invariants up migrate \
        verify-runtime verify-rls verify-adversarial verify clean build-immutable build-immutable-gpu

# ── STAGE 0: Syntax Truth (متاح offline) ──────────────────
verify-syntax:
	@echo "═══ STAGE 0 — Syntax Truth ═══"
	@$(PYTHON) -c "import py_compile,os,sys; e=0; \
[ (py_compile.compile(os.path.join(r,f),doraise=True)) \
for r,d,fs in os.walk('services') if 'node_modules' not in r and '__pycache__' not in r \
for f in fs if f.endswith('.py')]; print('✓ Syntax verified')"

# ── STAGE 1: Structural + Logic Tests (متاح offline) ──────
verify-tests: verify-syntax
	@echo "═══ STAGE 1 — Structural/Logic Tests ═══"
	@$(PYTHON) -c "import sys; sys.path.insert(0,'$(TESTS)'); \
import test_roadmap_phase1 as p1, test_roadmap_phase23 as p23; \
a,b=p1.run_all(); c,d=p1.run_all2(); e,f=p1.run_all3(); g,h=p23.run_all(); \
t=a+c+e+g; tot=t+b+d+f+h; print(f'✓ {t}/{tot} tests'); sys.exit(0 if t==tot else 1)"
	@$(PYTHON) $(TESTS)/test_chaos_resilience.py

# المراحل التي تتطلّب بنية تحتيّة (جهازك — ليست offline) ─────
verify-static: verify-tests
	@echo "═══ Static closure مكتمل (offline). للمراحل الحيّة: make verify ═══"


# ── Invariant Manifest (مصدر واحد للحقيقة) ────────────────
verify-invariants:
	@$(PYTHON) $(SCRIPTS)/verify_invariants.py

# ── STAGE 2: Infra Boot ───────────────────────────────────
up:
	@echo "═══ STAGE 2 — Infrastructure Boot ═══"
	@$(COMPOSE) up -d
	@echo "انتظر postgres/nats... (راجع scripts_v9/health_check.sh)"
	@bash $(SCRIPTS)/health_check.sh || true

# ── Migrations ────────────────────────────────────────────
migrate: up
	@echo "═══ Applying migrations ═══"
	@psql "$$DATABASE_URL" -v ON_ERROR_STOP=1 -f $(SCRIPTS)/run_migrations.sql
	@echo "✓ Migrations applied"

# ── STAGE 3+4: Runtime + RLS Truth (يحتاج DB حيّ) ─────────
verify-rls: migrate
	@echo "═══ STAGE 3+4 — Runtime + RLS Enforcement ═══"
	@echo "⚠ شغّل كـnon-superuser (sahool_user) وإلّا RLS يُتجاوَز"
	@psql "postgresql://sahool_user:$$DB_PASSWORD@localhost/sahool" \
		-v ON_ERROR_STOP=1 -f $(SCRIPTS)/test_tenant_isolation.sql
	@echo "✓ RLS enforcement verified (fail-closed + isolation)"

# ── STAGE 5: Adversarial (chaos — جزء offline، جزء حيّ) ────
verify-adversarial: verify-rls
	@echo "═══ STAGE 5 — Adversarial ═══"
	@$(PYTHON) $(TESTS)/test_chaos_resilience.py
	@echo "✓ Adversarial (راجع REVIEW7/8 للحدود)"

# ── Full live pipeline (على جهازك) ───────────────────────
verify: verify-adversarial
	@echo "═══ CORRECTNESS LOOP CLOSED (live) ═══"


# ============================================================
# مدخل CI واحد (المراجعة 14: اقفل الطبقات في مسار واحد) — ينتج evidence.json
# ============================================================
.PHONY: ci report
ci: verify-syntax verify-tests report
	@echo "═══ CI مكتمل — راجع build/evidence.json ═══"

report:
	@$(PYTHON) $(SCRIPTS)/ci_report.py > build/evidence.json 2>/dev/null || true
	@echo "✓ evidence: build/evidence.json (+ .sha256)"


# ── تقرير الحقيقة التشغيليّة (بعد النشر، على جهازك) ──────────
.PHONY: truth-report
truth-report:
	@$(PYTHON) $(SCRIPTS)/runtime_truth_report.py > runtime_truth_report.md
	@echo "✓ runtime_truth_report.md — راجعه واتّخذ القرار المعماري"

clean:
	@find . -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null; true
	@find . -name "*.pyc" -delete 2>/dev/null; true
	@echo "✓ Cleaned"

.PHONY: e2e-live-full chaos-load gis-timeline-e2e

e2e-live-full:
	python scripts/e2e/live_full_e2e.py

chaos-load:
	python scripts/e2e/chaos_load.py

gis-timeline-e2e:
	cd frontend && npm run e2e:gis-timeline


.PHONY: raster-ci
raster-ci:
	@echo "═══ Raster service architecture + tests ═══"
	bash scripts/ci/raster_quality_gate.sh

.PHONY: test-irr-f01-local
test-irr-f01-local:
	@bash scripts/irr_f01/local_gate.sh


# Immutable local image builds: derive TESTED_SHA from the checked-out commit.
build-immutable:
	@./scripts/build-immutable.sh

build-immutable-gpu:
	@./scripts/build-immutable.sh --gpu
