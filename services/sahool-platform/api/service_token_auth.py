"""api/service_token_auth.py — حارس التوكن الخدميّ مستقلّ (بلا دورة استيراد)
=========================================================================
نسخة مستقلّة من ``_require_service_token`` لا تستورد من ``api.main`` — كي تستطيع
وحدات الراوتر التي تُستورَد مباشرةً في الاختبارات (مثل phase9-12) أن تفرض المصادقة
على مستوى الراوتر (``APIRouter(dependencies=[Depends(_require_service_token)])``)
دون إطلاق دورة استيراد ``api.main`` (التي تُعيد استيراد الراوتر وهو جزئيّ بعد).

السلوك مطابق لنظيره في ``api.main``: fail-closed، مقارنة بزمن ثابت
(``hmac.compare_digest``) مع ``SAHOOL_AGENT_TOKEN``.
"""

from __future__ import annotations

import hmac
import os

from fastapi import Header, HTTPException


def _require_service_token(x_agent_token: str | None = Header(None, alias="X-Agent-Token")) -> None:
    """يحمي النقاط الداخليّة بالتوكن الخدميّ (fail-closed): يُرفض إن غاب السرّ أو اختلف."""
    expected = os.getenv("SAHOOL_AGENT_TOKEN", "")
    if not expected or not hmac.compare_digest(x_agent_token or "", expected):
        raise HTTPException(status_code=403, detail="نقطة داخليّة محميّة بـSAHOOL_AGENT_TOKEN")
