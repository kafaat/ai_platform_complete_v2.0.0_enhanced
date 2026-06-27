"""SAHOOL v9.1.0 — Shared Test Fixtures."""

from __future__ import annotations

import asyncio
import os
import sys
from datetime import UTC, datetime, timedelta, timezone
from uuid import uuid4

import httpx
import pytest
from jose import jwt

# جذر المستودع على sys.path حتى تُستورَد حِزَم المشروع (sahool_ai, shared) في CI.
# CI يشغّل `pytest` (سكربت الكونسول) لا `python -m pytest`، فلا يُضاف cwd تلقائيّاً
# إلى sys.path ⇒ كانت test_cookbook/test_research_pipeline/test_farm_memory تفشل
# بـModuleNotFoundError عند الجمع. conftest يُنفَّذ قبل استيراد وحدات الاختبار،
# فيدرَج الجذر هنا (بعد استيرادات conftest نفسها تفادياً لـE402).
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

# ── Test Config ───────────────────────────────────────────────
TEST_JWT_SECRET = "test_secret_min_32_chars_for_sahool_v9"
os.environ.setdefault("JWT_SECRET", TEST_JWT_SECRET)
TEST_DB_URL = os.getenv(
    "TEST_DATABASE_URL", "postgresql://sahool_test:test_password@127.0.0.1:5433/sahool_test"
)
TEST_REDIS_URL = os.getenv("TEST_REDIS_URL", "redis://:test_redis_pass@127.0.0.1:6380/0")
TEST_NATS_URL = os.getenv("TEST_NATS_URL", "nats://127.0.0.1:4223")
TEST_QDRANT_URL = os.getenv("TEST_QDRANT_URL", "http://127.0.0.1:6334")
TEST_QDRANT_KEY = "test_qdrant_key"

service_urls = {
    "auth": os.getenv("AUTH_URL", "http://127.0.0.1:8120"),
    "supervisor": os.getenv("SUPERVISOR_URL", "http://127.0.0.1:8200"),
    "guardrails": os.getenv("GUARDRAILS_URL", "http://127.0.0.1:8201"),
    "vegetation": os.getenv("VEGETATION_URL", "http://127.0.0.1:8202"),
    "rag": os.getenv("RAG_URL", "http://127.0.0.1:8203"),
    "odoo": os.getenv("ODOO_BRIDGE_URL", "http://127.0.0.1:8204"),
    "edge": os.getenv("EDGE_URL", "http://127.0.0.1:8205"),
    "indicators": os.getenv("INDICATORS_URL", "http://127.0.0.1:8206"),
    "market": os.getenv("MARKET_URL", "http://127.0.0.1:8207"),
    "soil": os.getenv("SOIL_URL", "http://127.0.0.1:8208"),
    "video": os.getenv("VIDEO_URL", "http://127.0.0.1:8209"),
    "tts": os.getenv("TTS_URL", "http://127.0.0.1:8210"),
}


def make_token(
    user_id: int = 1, role: str = "farmer", tenant_id: str = None, expired: bool = False
) -> str:
    """Create a test JWT token."""
    now = datetime.now(UTC)
    exp = now - timedelta(hours=1) if expired else now + timedelta(hours=1)
    return jwt.encode(
        {
            "sub": str(user_id),
            "email": f"test_{user_id}@sahool.ye",
            "role": role,
            "full_name": "مختبر SAHOOL",
            "tenant_id": tenant_id or str(uuid4()),
            "jti": str(uuid4()),
            "iss": "sahool-auth",
            "aud": "sahool",
            "iat": int(now.timestamp()),
            "nbf": int(now.timestamp()),
            "exp": int(exp.timestamp()),
        },
        TEST_JWT_SECRET,
        algorithm="HS256",
    )


@pytest.fixture
def valid_token() -> str:
    return make_token(user_id=1, role="farmer")


@pytest.fixture
def admin_token() -> str:
    return make_token(user_id=99, role="admin")


@pytest.fixture
def expired_token() -> str:
    return make_token(expired=True)


@pytest.fixture
def auth_headers(valid_token) -> dict:
    return {"Authorization": f"Bearer {valid_token}"}


@pytest.fixture
def admin_headers(admin_token) -> dict:
    return {"Authorization": f"Bearer {admin_token}"}


class _SkipOnConnError:
    """يلفّ AsyncClient فيحوّل أخطاء الاتصال إلى pytest.skip بدل فشل زائف
    حين لا تكون الخدمة قيد التشغيل. اختبارات التكامل/الأمان التي تنادي خدمات
    HTTP حيّة (auth/rag/...) كانت تفشل بـConnectError في أيّ بيئة بلا تلك
    الخدمات — بما فيها وظيفة security في CI (لا تُشغّل الخدمات) — بدل التخطّي."""

    _WRAP = {"get", "post", "put", "patch", "delete", "head", "request"}

    def __init__(self, client):
        self._c = client

    def __getattr__(self, name):
        attr = getattr(self._c, name)
        if name in self._WRAP and callable(attr):

            async def _wrapped(*a, **k):
                try:
                    return await attr(*a, **k)
                except (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadError) as e:
                    pytest.skip(f"خدمة غير مشغّلة ({a[0] if a else name}): {type(e).__name__}")

            return _wrapped
        return attr


@pytest.fixture
async def http_client():
    async with httpx.AsyncClient(timeout=10.0) as client:
        yield _SkipOnConnError(client)


# ── fixtures مفقودة كانت تكسر اختبارات supervisor/MCP/e2e (المراجعة) ──
@pytest.fixture
def mock_jwt_token() -> str:
    """رمز JWT اختباري للمستأجر (كان مفقوداً → 'fixture not found')."""
    return make_token(user_id=1, role="farmer")


@pytest.fixture
def mock_field_data() -> dict:
    """بيانات حقل اختباريّة لاختبارات التكامل (كانت مفقودة).

    FIX: أُضيفت crop/planting_date/soil_type — اختبارات MCP (WOFOST) كانت
    تصل إليها (mock_field_data['crop']) فتفشل بـKeyError قبل بلوغ الخدمة.
    """
    return {
        "field_id": "test-field-001",
        "tenant_id": "test-tenant-001",
        "crop_id": "wheat",
        "crop": "wheat",
        "planting_date": "2026-01-15",
        "soil_type": "loam",
        "geometry": {
            "type": "Polygon",
            "coordinates": [
                [[44.33, 16.79], [44.34, 16.79], [44.34, 16.80], [44.33, 16.80], [44.33, 16.79]]
            ],
        },
    }


@pytest.fixture
def mock_weather_data() -> dict:
    """بيانات طقس اختباريّة (lat/lon + درجات لحساب Hargreaves ET0).

    FIX: كانت مفقودة ⇒ اختبارات Weather MCP تُخطئ بـ'fixture not found'.
    """
    return {
        "lat": 15.35,
        "lon": 44.20,  # صنعاء
        "tmin": 12.0,
        "tmax": 28.0,
        "tmean": 20.0,
        "date": "2026-06-09",
    }


@pytest.fixture
def mock_market_data() -> dict:
    """بيانات سوق اختباريّة (محصول + سوق).

    FIX: كانت مفقودة ⇒ اختبارات Market MCP تُخطئ بـ'fixture not found'.
    """
    return {"crop": "wheat", "market": "sanaa"}
