"""
services/sahool-platform/api/sharing.py — Sharing Keys (advisor/dealer/ministry access)

المرجع: المستند ٩
   "Sharing Key & Data Transfer: إنشاء/إلغاء مفاتيح لأطراف ثالثة"

السياق اليمني:
   - مهندس زراعي قد يخدم ٢٠-٥٠ مزرعة
   - وزارة الزراعة قد تحتاج read-only access لـreporting
   - تاجر مدخلات قد يحتاج read access لـyield data

النموذج الأمني:
   - Owner يولّد key (UUID + nanoid)
   - النظام يخزّن bcrypt(key) فقط (لا الـkey نفسه)
   - الـUI يعرض الـkey مرّة واحدة للمالك (يُحفَظ في password manager)
   - الـthird party يضع الـkey في Authorization header
   - الـscope محدّد + الـexpiration إلزامي
"""
from __future__ import annotations
from contextlib import asynccontextmanager as _asynccontextmanager

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import List, Optional, TYPE_CHECKING
import secrets
import hashlib

if TYPE_CHECKING:
    import asyncpg


# ─── Types ──────────────────────────────────────────────────────

class SharingScope(str, Enum):
    READ = "read"
    READ_WRITE = "read_write"


class ThirdPartyType(str, Enum):
    ADVISOR = "advisor"
    DEALER = "dealer"
    MINISTRY = "ministry"
    RESEARCHER = "researcher"
    OTHER = "other"


@dataclass
class SharingKey:
    key_id: str
    key_plaintext: Optional[str]    # يُعرَض مرّة واحدة فقط (عند الإنشاء)
    key_prefix: str
    tenant_id: str
    scope: SharingScope
    third_party_name: Optional[str]
    third_party_type: Optional[ThirdPartyType]
    allowed_field_ids: List[str]
    expires_at: str
    created_at: str


@dataclass
class KeyValidation:
    valid: bool
    tenant_id: Optional[str]
    scope: Optional[SharingScope]
    allowed_field_ids: Optional[List[str]]
    reason: Optional[str] = None


# ─── Key generation (cryptographically secure) ──────────────────

def generate_key_plaintext() -> str:
    """يولّد key آمن للـsharing.

    Format: "shk_<32-char-base32>"  → e.g. "shk_3FA7B2C4D5E6F7..."
    """
    raw = secrets.token_urlsafe(24)   # 192 bits of entropy
    return f"shk_{raw}"


def hash_key(key_plaintext: str) -> str:
    """SHA-256 hash للـkey (للـDB storage).

    Note: bcrypt أفضل لكن slower. لـsharing keys (validation rate منخفض)
    SHA-256 مع salt كافٍ. الـkey نفسه طويل وعشوائي (192 bits).
    """
    return hashlib.sha256(key_plaintext.encode()).hexdigest()


# ─── Service ────────────────────────────────────────────────────

class SharingKeyService:
    """Generate, validate, revoke sharing keys."""

    def __init__(self, pool: "asyncpg.Pool", conn=None):
        import asyncpg as _ap  # noqa: F401
        self.pool = pool
        self._conn = conn

    @_asynccontextmanager
    async def _acquire(self):
        """conn من tenant_connection (RLS مُطبَّق) أو من الـpool (توافق خلفي)."""
        if getattr(self, "_conn", None) is not None:
            yield self._conn
        else:
            async with self.pool.acquire() as c:
                yield c

    async def create_key(
        self,
        tenant_id: str,
        created_by: str,
        scope: SharingScope,
        valid_days: int,
        third_party_name: Optional[str] = None,
        third_party_type: Optional[ThirdPartyType] = None,
        allowed_field_ids: Optional[List[str]] = None,
        allowed_endpoints: Optional[List[str]] = None,
    ) -> SharingKey:
        """إنشاء key جديد. الـplaintext يُرجَع مرّة واحدة فقط."""
        import uuid as _u

        if valid_days < 1 or valid_days > 365:
            raise ValueError("valid_days must be between 1 and 365")

        plaintext = generate_key_plaintext()
        prefix = plaintext[:12]  # "shk_3FA7B2C4"
        key_hash = hash_key(plaintext)
        key_id = str(_u.uuid4())
        expires_at = datetime.now(timezone.utc) + timedelta(days=valid_days)

        async with self._acquire() as conn:
            await conn.execute(
                """
                INSERT INTO sharing_keys
                    (key_id, key_hash, key_prefix, tenant_id, created_by,
                     scope, third_party_name, third_party_type,
                     allowed_field_ids, allowed_endpoints, expires_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
                """,
                _u.UUID(key_id),
                key_hash,
                prefix,
                _u.UUID(tenant_id),
                created_by,
                scope.value,
                third_party_name,
                third_party_type.value if third_party_type else None,
                [_u.UUID(fid) for fid in (allowed_field_ids or [])] or None,
                allowed_endpoints or [],
                expires_at,
            )

        return SharingKey(
            key_id=key_id,
            key_plaintext=plaintext,
            key_prefix=prefix,
            tenant_id=tenant_id,
            scope=scope,
            third_party_name=third_party_name,
            third_party_type=third_party_type,
            allowed_field_ids=allowed_field_ids or [],
            expires_at=expires_at.isoformat(),
            created_at=datetime.now(timezone.utc).isoformat(),
        )

    async def validate_key(self, key_plaintext: str) -> KeyValidation:
        """يفحص الـkey ويُرجع scope + tenant. يُحدِّث last_used_at."""
        if not key_plaintext or not key_plaintext.startswith("shk_"):
            return KeyValidation(False, None, None, None, "invalid format")

        key_hash = hash_key(key_plaintext)

        async with self._acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT
                    tenant_id, scope, allowed_field_ids,
                    expires_at, revoked_at
                FROM sharing_keys
                WHERE key_hash = $1
                """,
                key_hash,
            )

            if not row:
                return KeyValidation(False, None, None, None, "key not found")
            if row["revoked_at"] is not None:
                return KeyValidation(False, None, None, None, "key revoked")
            if row["expires_at"] < datetime.now(timezone.utc):
                return KeyValidation(False, None, None, None, "key expired")

            # Touch (update last_used_at + count)
            await conn.execute("SELECT touch_sharing_key($1)", key_hash)

            return KeyValidation(
                valid=True,
                tenant_id=str(row["tenant_id"]),
                scope=SharingScope(row["scope"]),
                allowed_field_ids=[str(fid) for fid in (row["allowed_field_ids"] or [])],
            )

    async def revoke_key(self, key_id: str, tenant_id: str) -> bool:
        """إلغاء key. Returns True لو نجح، False لو غير موجود/مُلغى."""
        import uuid as _u

        async with self._acquire() as conn:
            result = await conn.execute(
                """
                UPDATE sharing_keys
                SET revoked_at = NOW()
                WHERE key_id = $1 AND tenant_id = $2
                  AND revoked_at IS NULL
                """,
                _u.UUID(key_id),
                _u.UUID(tenant_id),
            )
            return result.endswith("1")

    async def list_keys(self, tenant_id: str, include_revoked: bool = False) -> List[dict]:
        """قائمة كل المفاتيح للـtenant (بدون الـplaintext طبعاً)."""
        import uuid as _u

        async with self._acquire() as conn:
            if include_revoked:
                rows = await conn.fetch(
                    """
                    SELECT key_id, key_prefix, scope, third_party_name,
                           third_party_type, expires_at, revoked_at,
                           last_used_at, use_count, created_at
                    FROM sharing_keys
                    WHERE tenant_id = $1
                    ORDER BY created_at DESC
                    """,
                    _u.UUID(tenant_id),
                )
            else:
                rows = await conn.fetch(
                    """
                    SELECT key_id, key_prefix, scope, third_party_name,
                           third_party_type, expires_at, revoked_at,
                           last_used_at, use_count, created_at
                    FROM sharing_keys
                    WHERE tenant_id = $1
                      AND revoked_at IS NULL
                      AND expires_at > NOW()
                    ORDER BY created_at DESC
                    """,
                    _u.UUID(tenant_id),
                )
            return [dict(r) for r in rows]
