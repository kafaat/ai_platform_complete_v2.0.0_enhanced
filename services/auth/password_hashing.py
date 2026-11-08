"""password_hashing.py — تجزئة/تحقّق bcrypt بحدّ ٧٢ بايت حتميّ (S8).

bcrypt يقرأ أوّل ٧٢ بايت فقط من كلمة المرور. حتّى ٤.x كان يقتطع بصمت؛ ومنذ ٥.٠.٠ يرمي
``ValueError`` لِما يتجاوزها ⇒ HTTP 500 في التسجيل/الدخول/الاستعادة. حدّ ``max_length=128``
في النماذج يعدّ **محارف** لا بايتات (٣٧ محرفاً عربيّاً = ٧٤ بايت UTF-8)، فلا يحمي.

الحسم (bcrypt-version-independent):
  - كلمة مرور **جديدة** (تسجيل/استعادة/تغيير/قبول دعوة) > ٧٢ بايت ⇒ رفض 422 عند التحقّق
    من المدخلات برسالة واضحة (``NewPassword``)، لا اقتطاع صامت.
  - التحقّق (``verify_password``) لمدخل > ٧٢ بايت أو تجزئة تالفة ⇒ ``False`` (401)، لا 500.
  - ``hash_password`` يرفض > ٧٢ بايت صراحةً (حزام أخير لأيّ مُستدعٍ خارج النماذج).
التجزئات القائمة ($2a$/$2b$/$2y$) تبقى صالحة كما هي.

وحدة شقيقة نقيّة (bcrypt + pydantic فقط) — قابلة للاختبار وحدةً دون رفع الخدمة.
"""

from __future__ import annotations

from typing import Annotated

import bcrypt
from pydantic import AfterValidator, Field

MAX_PASSWORD_BYTES = 72
PASSWORD_TOO_LONG_MSG = (
    f"كلمة المرور أطول من {MAX_PASSWORD_BYTES} بايت (UTF-8) — اختصرها "
    f"(password exceeds {MAX_PASSWORD_BYTES} bytes)"
)


def password_too_long(password: str) -> bool:
    """True إن تجاوزت كلمة المرور حدّ bcrypt بالبايتات (UTF-8)، لا بالمحارف."""
    return len(password.encode("utf-8")) > MAX_PASSWORD_BYTES


def check_password_bytes(password: str) -> str:
    """مُتحقِّق pydantic: يرفض > ٧٢ بايت بـValueError ⇒ 422 برسالة واضحة."""
    if password_too_long(password):
        raise ValueError(PASSWORD_TOO_LONG_MSG)
    return password


# نوع كلمة مرور جديدة: حدود المحارف القائمة + حدّ bcrypt بالبايتات.
NewPassword = Annotated[
    str, Field(min_length=8, max_length=128), AfterValidator(check_password_bytes)
]


def hash_password(password: str, rounds: int) -> str:
    """تجزئة bcrypt؛ ترفض > ٧٢ بايت بـValueError صريح (لا اقتطاع صامت)."""
    if password_too_long(password):
        raise ValueError(PASSWORD_TOO_LONG_MSG)
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds)).decode()


def verify_password(password: str, hashed: str | bytes | None) -> bool:
    """تحقّق ثابت السلوك: False (لا استثناء) لمدخل > ٧٢ بايت أو تجزئة مفقودة/تالفة."""
    if not hashed or password_too_long(password):
        return False
    hashed_b = hashed if isinstance(hashed, bytes) else hashed.encode("utf-8")
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed_b)
    except ValueError:  # تجزئة تالفة (Invalid salt) — رفض لا 500
        return False
