"""
services/sahool-platform/api/onboarding.py — استبيان دخول المزارع

المرجع: docs/history/ONBOARDING_QUESTIONNAIRE.md (بحث الوكيل المجالي).

التصميم للسياق اليمني (كما حدّد البحث):
- offline-first: كلّ الأسئلة تُحمّل دفعةً ثمّ تُملأ بلا اتّصال
- RTL + عربيّة: كلّ نصّ بالعربيّة
- أمّيّة رقميّة منخفضة: أسئلة قليلة إلزاميّة، الباقي اختياري متدرّج، وحدات
  مألوفة (فدان/دونم بجانب الهكتار)، خيارات جاهزة بدل إدخال حرّ حيث أمكن

البنية: 9 أقسام، كلّ سؤال له: id, label_ar, type, required, options/unit.
المرحلة الأولى (الإلزاميّة) قصيرة جدّاً لتقليل الاحتكاك؛ الباقي "تعميق"
اختياري يملؤه المزارع لاحقاً ويحسّن دقّة التوصيات.
"""

from __future__ import annotations

import hashlib as _bootstrap_hashlib
import json as _bootstrap_json
from datetime import UTC as _BootstrapTimezoneUTC
from datetime import datetime as _BootstrapDatetime
from uuid import UUID as _BootstrapUUID
from uuid import uuid4 as _bootstrap_uuid4

from pydantic import BaseModel

from shared.field_bootstrap import ClaimedJob as _ClaimedBootstrapJob
from shared.field_bootstrap import LeaseLost as _BootstrapLeaseLost
from shared.field_bootstrap import new_journal as _new_bootstrap_journal
from shared.field_bootstrap import validate_journal as _validate_bootstrap_journal


class OnboardingQuestion(BaseModel):
    id: str
    label_ar: str
    type: str  # text|number|select|multiselect|date|gps|polygon|photo|audio
    required: bool = False
    unit: str | None = None
    options: list[str] | None = None
    hint_ar: str | None = None


class OnboardingSection(BaseModel):
    id: str
    title_ar: str
    phase: int  # 1 = إلزامي مبدئي · 2 = تعميق اختياري
    questions: list[OnboardingQuestion]


# ─── تعريف الاستبيان (9 أقسام) ──────────────────────────────────
# المرحلة 1 (phase=1): الحدّ الأدنى لبدء الاستخدام — قليلة ومألوفة.
# المرحلة 2 (phase=2): تعميق اختياري يحسّن دقّة التوصيات.

ONBOARDING_SECTIONS: list[OnboardingSection] = [
    OnboardingSection(
        id="identity",
        title_ar="التعريف",
        phase=1,
        questions=[
            OnboardingQuestion(
                id="farmer_name", label_ar="اسمك أو اسم المزرعة", type="text", required=True
            ),
            OnboardingQuestion(
                id="field_name",
                label_ar="اسم الحقل",
                type="text",
                required=True,
                hint_ar="اسم تتذكّره بسهولة، مثل: حقل الشمال",
            ),
        ],
    ),
    OnboardingSection(
        id="spatial",
        title_ar="المكان",
        phase=1,
        questions=[
            OnboardingQuestion(
                id="district", label_ar="المديريّة/القرية", type="text", required=True
            ),
            OnboardingQuestion(
                id="boundary",
                label_ar="ارسم حدود حقلك على الخريطة",
                type="polygon",
                required=False,
                hint_ar="ارسم الحدود لحساب المساحة تلقائيّاً",
            ),
            OnboardingQuestion(id="gps", label_ar="موقع الحقل (GPS)", type="gps", required=False),
        ],
    ),
    OnboardingSection(
        id="agronomic",
        title_ar="المحصول",
        phase=1,
        questions=[
            OnboardingQuestion(
                id="crop",
                label_ar="المحصول الرئيسي",
                type="select",
                required=True,
                options=[
                    "قمح",
                    "شعير",
                    "ذرة",
                    "ذرة رفيعة",
                    "سمسم",
                    "بطاطس",
                    "بصل",
                    "طماطم",
                    "بُن",
                    "قات",
                    "أخرى",
                ],
            ),
            OnboardingQuestion(
                id="area",
                label_ar="مساحة الحقل",
                type="number",
                required=True,
                unit="اختر الوحدة",
                hint_ar="أو ارسم الحدود ونحسبها لك",
            ),
            OnboardingQuestion(
                id="area_unit",
                label_ar="وحدة المساحة",
                type="select",
                required=True,
                options=["هكتار", "فدان", "دونم", "لِبنة"],
            ),
            OnboardingQuestion(id="variety", label_ar="الصنف (إن عُرف)", type="text"),
        ],
    ),
    OnboardingSection(
        id="temporal",
        title_ar="التواريخ",
        phase=2,
        questions=[
            OnboardingQuestion(id="sowing_date", label_ar="تاريخ البذار", type="date"),
            OnboardingQuestion(id="harvest_date", label_ar="تاريخ الحصاد المتوقّع", type="date"),
        ],
    ),
    OnboardingSection(
        id="soil_water",
        title_ar="التربة والماء",
        phase=2,
        questions=[
            OnboardingQuestion(
                id="soil_type",
                label_ar="نوع التربة",
                type="select",
                options=["طيني", "رملي", "طمي", "مختلط", "لا أعرف"],
            ),
            OnboardingQuestion(
                id="water_source",
                label_ar="مصدر مياه الري",
                type="select",
                options=["بئر", "سدّ", "مطر", "فيضان/سيل", "شبكة"],
            ),
            OnboardingQuestion(
                id="irrigation_system",
                label_ar="نظام الري",
                type="select",
                options=["محوري", "تنقيط", "سطحي", "سيلي", "بدون (مطري)"],
            ),
            OnboardingQuestion(
                id="water_ec", label_ar="ملوحة ماء الري (إن عُرفت)", type="number", unit="dS/m"
            ),
        ],
    ),
    OnboardingSection(
        id="inputs",
        title_ar="المدخلات",
        phase=2,
        questions=[
            OnboardingQuestion(
                id="seed_rate", label_ar="كميّة البذور", type="number", unit="كجم/هكتار"
            ),
            OnboardingQuestion(
                id="fertilizer",
                label_ar="السماد المستخدم",
                type="multiselect",
                options=["DAP", "Urea", "NPK", "سماد عضوي", "بدون"],
            ),
            OnboardingQuestion(
                id="irrigation_count", label_ar="عدد الريّات في الموسم", type="number"
            ),
        ],
    ),
    OnboardingSection(
        id="pests",
        title_ar="الآفات والأمراض",
        phase=2,
        questions=[
            OnboardingQuestion(id="pest_notes", label_ar="ملاحظات آفات/أمراض", type="text"),
            OnboardingQuestion(
                id="loss_pct", label_ar="نسبة الخسائر التقديريّة", type="number", unit="%"
            ),
        ],
    ),
    OnboardingSection(
        id="economic",
        title_ar="الاقتصاد",
        phase=2,
        questions=[
            OnboardingQuestion(
                id="sale_price", label_ar="سعر بيع الوحدة", type="number", unit="ريال"
            ),
            OnboardingQuestion(id="sale_market", label_ar="مكان البيع", type="text"),
        ],
    ),
    OnboardingSection(
        id="freeform",
        title_ar="ملاحظات حرّة",
        phase=2,
        questions=[
            OnboardingQuestion(id="notes", label_ar="أيّ ملاحظات عن الموسم", type="text"),
            OnboardingQuestion(id="photos", label_ar="صور للحقل", type="photo"),
            OnboardingQuestion(
                id="audio",
                label_ar="تسجيل صوتي (للأمّيّة)",
                type="audio",
                hint_ar="سجّل ملاحظاتك صوتيّاً بدل الكتابة",
            ),
        ],
    ),
]


def get_questionnaire(phase: int | None = None) -> dict:
    """يُرجع تعريف الاستبيان. phase=1 للإلزامي فقط، None للكلّ."""
    secs = ONBOARDING_SECTIONS
    if phase is not None:
        secs = [s for s in secs if s.phase == phase]
    return {
        "version": "1.0",
        "rtl": True,
        "lang": "ar",
        "offline_capable": True,
        "sections": [s.model_dump() for s in secs],
        "required_count": sum(1 for s in ONBOARDING_SECTIONS for q in s.questions if q.required),
    }


def validate_response(answers: dict) -> dict:
    """يتحقّق من اكتمال الحقول الإلزاميّة. يُرجع {valid, missing}."""
    required_ids = [q.id for s in ONBOARDING_SECTIONS for q in s.questions if q.required]
    missing = [
        qid for qid in required_ids if qid not in answers or answers.get(qid) in (None, "", [])
    ]
    return {
        "valid": len(missing) == 0,
        "missing": missing,
        "answered": len([k for k in answers if answers.get(k) not in (None, "", [])]),
    }


# READINESS-M4: journal persistence belongs to the existing platform owner.
# Append to api/onboarding.py; no new table or RLS/ownership override is created.
# استيراداتُه نُقِلت إلى رأس الملفّ: الإلحاقُ في الوسط يُخالف E402، والأسماء
# مُلقَّبة أصلاً فلا تصطدم بشيء في الأعلى.
_BOOTSTRAP_JOB_TYPE = "field_bootstrap_v1"


async def _require_bootstrap_tenant(conn, tenant_id: str) -> str:
    tenant = str(_BootstrapUUID(tenant_id))
    actual = await conn.fetchval("SELECT current_setting('app.current_tenant', true)")
    if str(actual) != tenant:
        raise RuntimeError("bootstrap_requires_existing_tenant_transaction")
    if not conn.is_in_transaction():
        raise RuntimeError("bootstrap_requires_transaction")
    return tenant


async def enqueue_field_bootstrap(
    conn, *, tenant_id: str, field_id: str, geometry: dict, created_at: _BootstrapDatetime
) -> int:
    """Call inside the SAME tenant transaction that inserts the field.

    Failure must roll the caller's transaction back. Never catch it as a soft
    side task. No provider call and no local commit occur here. The caller must
    first use the existing guard_field_geometry; this is not a geometry owner.
    """
    tenant = await _require_bootstrap_tenant(conn, tenant_id)
    journal = _new_bootstrap_journal(
        tenant_id=tenant, field_id=field_id, geometry=geometry, created_at=created_at
    )
    key = journal["scope_key"]
    lock_id = int.from_bytes(
        _bootstrap_hashlib.sha256(key.encode()).digest()[:8], "big", signed=True
    )
    # Serialize the missing-row case; job_id in the existing table is NOT UNIQUE.
    await conn.execute("SELECT pg_advisory_xact_lock($1::bigint)", lock_id)
    existing = await conn.fetchval(
        "SELECT id FROM processing_jobs WHERE tenant_id=$1::uuid AND field_id=$2 "
        "AND job_type=$3 AND parameters->>'scope_key'=$4 ORDER BY id LIMIT 1",
        tenant,
        field_id,
        _BOOTSTRAP_JOB_TYPE,
        key,
    )
    if existing is not None:
        return int(existing)
    result = await conn.fetchval(
        "INSERT INTO processing_jobs (tenant_id,field_id,job_type,status,parameters,result) "
        "VALUES ($1::uuid,$2,$3,'pending',$4::jsonb,$5::jsonb) RETURNING id",
        tenant,
        field_id,
        _BOOTSTRAP_JOB_TYPE,
        _bootstrap_json.dumps(
            {
                "schema_version": journal["schema_version"],
                "scope_key": key,
                "scope": journal["scope"],
            }
        ),
        _bootstrap_json.dumps({"journal": journal, "lease": None}),
    )
    if result is None:
        raise RuntimeError("bootstrap_insert_not_persisted")
    return int(result)


class PlatformBootstrapStore:
    """Tenant-scoped asyncpg adapter using short transactions and DB-clock leases.

    connection_factory must be the platform's tenant_connection for one explicit
    tenant, yielding an asyncpg connection inside a transaction. Never use a raw
    privileged pool. RLS acceptance is mandatory before enabling the scheduler.
    Every compare-and-set protects against stale/expired worker completion.
    """

    def __init__(self, connection_factory, *, tenant_id: str, lease_seconds: int = 120):
        if type(lease_seconds) is not int or not 60 <= lease_seconds <= 300:
            raise ValueError("bootstrap_lease_out_of_range")
        self._connect = connection_factory
        self.tenant_id = str(_BootstrapUUID(tenant_id))
        self.lease_seconds = lease_seconds

    async def due_job_ids(self, *, limit: int = 20) -> list[int]:
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError("bootstrap_batch_limit")
        async with self._connect() as conn:
            await _require_bootstrap_tenant(conn, self.tenant_id)
            rows = await conn.fetch(
                "SELECT id FROM processing_jobs WHERE tenant_id=$1::uuid AND job_type=$2 "
                "AND status IN ('pending','running') "
                "AND (result->'lease' IS NULL OR result->'lease'='null'::jsonb OR "
                "(result->'lease'->>'expires_at')::timestamptz <= clock_timestamp()) "
                "AND (status='running' OR result->'journal'->>'next_attempt_at' IS NULL OR "
                "(result->'journal'->>'next_attempt_at')::timestamptz <= clock_timestamp()) "
                "ORDER BY priority,id LIMIT $3",
                self.tenant_id,
                _BOOTSTRAP_JOB_TYPE,
                limit,
            )
        return [int(row["id"]) for row in rows]

    async def claim(self, job_id: int) -> _ClaimedBootstrapJob | None:
        if type(job_id) is not int or job_id <= 0:
            raise ValueError("bootstrap_job_id")
        token = str(_bootstrap_uuid4())
        async with self._connect() as conn:
            await _require_bootstrap_tenant(conn, self.tenant_id)
            row = await conn.fetchrow(
                "SELECT id,result,field_id,parameters FROM processing_jobs "
                "WHERE id=$1 AND tenant_id=$2::uuid AND job_type=$3 "
                "AND status IN ('pending','running') "
                "AND (result->'lease' IS NULL OR result->'lease'='null'::jsonb OR "
                "(result->'lease'->>'expires_at')::timestamptz <= clock_timestamp()) "
                "AND (status='running' OR result->'journal'->>'next_attempt_at' IS NULL OR "
                "(result->'journal'->>'next_attempt_at')::timestamptz <= clock_timestamp()) "
                "FOR UPDATE SKIP LOCKED",
                job_id,
                self.tenant_id,
                _BOOTSTRAP_JOB_TYPE,
            )
            if row is None:
                return None
            data = (
                _bootstrap_json.loads(row["result"])
                if isinstance(row["result"], str)
                else row["result"]
            )
            params = (
                _bootstrap_json.loads(row["parameters"])
                if isinstance(row["parameters"], str)
                else row["parameters"]
            )
            journal = data["journal"]
            _validate_bootstrap_journal(journal)
            if (
                journal["scope"]["tenant_id"] != self.tenant_id
                or journal["scope"]["field_id"] != row["field_id"]
                or journal["scope_key"] != params["scope_key"]
            ):
                raise RuntimeError("bootstrap_stored_scope_mismatch")
            claimed = await conn.fetchval(
                "UPDATE processing_jobs SET status='running',started_at=COALESCE(started_at,clock_timestamp()), "
                "updated_at=clock_timestamp(),result=jsonb_set(result,'{lease}',jsonb_build_object( "
                "'token',$4::text,'expires_at',clock_timestamp()+make_interval(secs=>$5))) "
                "WHERE id=$1 AND tenant_id=$2::uuid AND job_type=$3 RETURNING id",
                job_id,
                self.tenant_id,
                _BOOTSTRAP_JOB_TYPE,
                token,
                self.lease_seconds,
            )
            if claimed is None:
                raise _BootstrapLeaseLost("bootstrap_claim_lost")
        return _ClaimedBootstrapJob(job_id, token, journal)

    async def checkpoint(self, job_id: int, token: str, journal: dict) -> None:
        await self._save(job_id, token, journal, finish=False)

    async def finish(self, job_id: int, token: str, journal: dict) -> None:
        await self._save(job_id, token, journal, finish=True)

    async def _save(self, job_id: int, token: str, journal: dict, *, finish: bool) -> None:
        _validate_bootstrap_journal(journal)
        if journal["scope"]["tenant_id"] != self.tenant_id:
            raise RuntimeError("bootstrap_tenant_mismatch")
        state = journal["status"]
        status = (
            (
                "completed"
                if state == "completed"
                else "cancelled"
                if state == "superseded"
                else "failed"
                if state == "blocked"
                else "pending"
            )
            if finish
            else "running"
        )
        async with self._connect() as conn:
            await _require_bootstrap_tenant(conn, self.tenant_id)
            saved = await conn.fetchval(
                "UPDATE processing_jobs SET result=jsonb_build_object('journal',$5::jsonb,'lease', "
                "CASE WHEN $6::boolean THEN NULL::jsonb ELSE jsonb_build_object('token',$4::text, "
                "'expires_at',clock_timestamp()+make_interval(secs=>$7)) END), "
                "status=$8,progress=$10,updated_at=clock_timestamp(), "
                "finished_at=CASE WHEN $8 IN ('completed','failed','cancelled') THEN clock_timestamp() ELSE NULL END "
                "WHERE id=$1 AND tenant_id=$2::uuid AND job_type=$3 "
                "AND parameters->>'scope_key'=$9 AND result->'lease'->>'token'=$4 "
                "AND (result->'lease'->>'expires_at')::timestamptz>clock_timestamp() RETURNING id",
                job_id,
                self.tenant_id,
                _BOOTSTRAP_JOB_TYPE,
                token,
                _bootstrap_json.dumps(journal, allow_nan=False),
                finish,
                self.lease_seconds,
                status,
                journal["scope_key"],
                sum(stage["status"] == "completed" for stage in journal["steps"].values()) * 20,
            )
            if saved is None:
                raise _BootstrapLeaseLost("bootstrap_checkpoint_lease_expired_or_replaced")


async def maybe_enqueue_field_bootstrap(conn, *, tenant_id: str, field_id: str, geometry: dict):
    """Rollout is OFF until live RLS and owner adapters are accepted.

    Invoke from _insert_field_within_tx after guard_field_geometry. Existing
    fields are NOT backfilled implicitly. Use their original created_at when a
    separately authorized backfill invokes this helper, never the retry clock.
    """
    import os as _bootstrap_os

    if _bootstrap_os.getenv("FIELD_BOOTSTRAP_ENABLED", "").strip().lower() != "true":
        return None
    tenant = await _require_bootstrap_tenant(conn, tenant_id)
    created_at = await conn.fetchval(
        "SELECT created_at FROM fields WHERE field_id=$1 AND tenant_id=$2::uuid",
        field_id,
        tenant,
    )
    if not isinstance(created_at, _BootstrapDatetime) or created_at.tzinfo is None:
        raise RuntimeError("bootstrap_field_creation_time_unavailable")
    return await enqueue_field_bootstrap(
        conn,
        tenant_id=tenant,
        field_id=field_id,
        geometry=geometry,
        created_at=created_at.astimezone(_BootstrapTimezoneUTC),
    )


async def run_field_bootstrap_once(
    *,
    connection_factory,
    tenant_id: str,
    handlers: dict,
    load_current_geometry_digest,
    batch_size: int = 20,
) -> dict:
    """One bounded scheduler pass for ONE explicitly authorized tenant.

    Registration in the application's existing scheduler and production handler
    wiring are separate rollout steps; this function does not discover tenants
    from a privileged pool. Geometry loader must read from its owner, scoped to
    the supplied tenant and field, and return the digest of current guarded JSON.
    """
    import os as _bootstrap_os

    from shared.field_bootstrap import advance as _advance_bootstrap

    if _bootstrap_os.getenv("FIELD_BOOTSTRAP_ENABLED", "").strip().lower() != "true":
        return {"enabled": False, "claimed": 0, "completed": 0, "lease_lost": 0, "errors": 0}
    store = PlatformBootstrapStore(connection_factory, tenant_id=tenant_id)
    counts = {"enabled": True, "claimed": 0, "completed": 0, "lease_lost": 0, "errors": 0}
    for job_id in await store.due_job_ids(limit=batch_size):
        job = await store.claim(job_id)
        if job is None:
            continue
        counts["claimed"] += 1

        async def load_geometry(_job=job):
            # الربطُ صريحٌ بالمعامل الافتراضيّ: المُغلِّفُ يُستهلَك داخل دورته الحاليّة
            # اليوم، فالخطأُ كامنٌ لا نشِط — لكنّ صحّتَه يجب ألّا تتعلّق بلحظة الاستدعاء.
            return await load_current_geometry_digest(
                tenant_id=store.tenant_id, field_id=_job.journal["scope"]["field_id"]
            )

        try:
            result = await _advance_bootstrap(
                job, store=store, handlers=handlers, load_geometry_digest=load_geometry
            )
        except _BootstrapLeaseLost:
            counts["lease_lost"] += 1
        except Exception:
            # Preserve the committed intent. Expiry permits a future worker to
            # recover, but never leak provider tracebacks or steal a live lease.
            counts["errors"] += 1
        else:
            counts["completed"] += int(result["status"] == "completed")
    return counts


async def register_field_creation_intents(
    conn, *, tenant_id: str, field_id: str, geometry: dict, lat: float | None, lon: float | None
):
    """نيّاتُ إنشاء الحقل الثلاث في معاملة المُستدعي؛ بلا نداء مزوّد.

    مدخلٌ واحد لا ثلاثة نداءاتٍ في الراوتر، فلا ينمو سقفُ حجمه ولا تُضاف وحدةُ منصّة.

    **دمجٌ لا استبدال:** الحزمةُ الأصليّة كانت تُعيد كتابة كتلةِ الراوتر لتسجّل الصورَ
    ومهمّةَ التهيئة، وكانت `main` قد استبدلت الكتلةَ نفسَها لتسجّل الصورَ **والطقس**
    (#1009). أخذُ أيٍّ منهما حرفيّاً يُسقِط عملَ الآخر صامتاً، فالثلاثةُ تُسجَّل هنا:
    الصورُ والطقسُ عبر `register_field_tracking_intents` القائم، ثمّ مهمّةُ التهيئة.

    الترتيبُ مقصود: نيّةُ المتابعة أوّلاً لأنّها العقدُ القائم الذي يعتمد عليه المُجدوِل،
    ومهمّةُ التهيئة بعده وهي **مطفأةٌ بالراية افتراضيّاً** فلا تُغيّر سلوكاً قائماً.
    وبلا إحداثيّة مركز لا يُسجَّل طقس: لا يُختلَق موقع.
    """
    from api.imagery_automation import register_field_tracking_intents

    tracking = await register_field_tracking_intents(
        conn, tenant_id=tenant_id, field_id=field_id, geometry=geometry, lat=lat, lon=lon
    )
    bootstrap = await maybe_enqueue_field_bootstrap(
        conn,
        tenant_id=tenant_id,
        field_id=field_id,
        geometry=geometry,
    )
    return {**tracking, "bootstrap": bootstrap is not None}
