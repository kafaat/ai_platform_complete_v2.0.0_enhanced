"""zlmedia_client.py — عميل ZLMediaKit HTTP (خالٍ من fastapi).

يغلّف واجهة ``/index/api/*`` بعقود أوسع من التدفّق المضمَّن في ``main.py``، ويعيد
استخدام اصطلاح حقن ``secret`` نفسه (نظير ``_zlmedia_params``). كلّ نداء يبني الرابط
من ``<base>/index/api/<method>`` (مع ``rstrip('/')`` للأساس).

فشل ليّن (fail-soft): كلّ دالّة تُرجِع ``dict`` منظّماً ``{ok: bool, ...}`` ولا ترفع
أبداً على 4xx/5xx أو خطأ اتصال — كي لا يُسقِط عطلُ ZLMediaKit مسارَ الطلب.

النداء (httpx) قابل للحقن: مرّر ``request_fn`` كي تختبر الوحدة بلا خادم حيّ.
يبقى خالياً من fastapi (قد يستورد httpx فقط).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

try:  # httpx متوفّر في الخدمة؛ الحقن يُغني عنه في الاختبار.
    import httpx
except ImportError:  # pragma: no cover - httpx حاضر في requirements
    httpx = None  # type: ignore[assignment]

# توقيع الاستجابة المتوقَّع من ``request_fn``: كائن به ``status_code`` و``json()`` و``content``.
ResponseLike = Any
RequestFn = Callable[[str, dict[str, Any]], ResponseLike]


class ZLMediaKitClient:
    """عميل رقيق لواجهة ZLMediaKit، فشل-ليّن، وقابل للحقن (mockable)."""

    def __init__(
        self,
        base_url: str,
        secret: str = "",
        timeout: float = 10.0,
        request_fn: RequestFn | None = None,
    ) -> None:
        self.base_url = (base_url or "").rstrip("/")
        self.secret = secret or ""
        self.timeout = timeout
        # الحقن: افتراضيّاً GET عبر httpx؛ الاختبار يمرّر بديلاً بلا شبكة.
        self._request_fn: RequestFn = request_fn or self._default_request

    # ── بناء الرابط والمُعامِلات (منطق صرف، يُعاد استخدام اصطلاح secret) ──
    def _url(self, method: str) -> str:
        return f"{self.base_url}/index/api/{method}"

    def _params(self, **params: Any) -> dict[str, Any]:
        """يحقن ``secret`` عند ضبطه فقط (نظير ``main._zlmedia_params``)."""
        if self.secret:
            params.setdefault("secret", self.secret)
        return params

    def _default_request(self, url: str, params: dict[str, Any]) -> ResponseLike:
        if httpx is None:  # pragma: no cover - httpx حاضر عمليّاً
            raise RuntimeError("httpx غير متوفّر ولا request_fn محقون")
        with httpx.Client(timeout=self.timeout) as client:
            return client.get(url, params=params)

    def _call(self, method: str, *, binary: bool = False, **params: Any) -> dict[str, Any]:
        """ينفّذ نداءً ويُطبّع الردّ إلى ``dict`` منظّم فشلاً-ليّناً."""
        url = self._url(method)
        p = self._params(**params)
        try:
            resp = self._request_fn(url, p)
        except Exception as e:  # noqa: BLE001 — فشل ليّن: لا نرفع على خطأ اتصال
            return {"ok": False, "method": method, "url": url, "error": type(e).__name__}
        status = getattr(resp, "status_code", 0)
        ok = 200 <= int(status) < 400
        out: dict[str, Any] = {"ok": ok, "method": method, "url": url, "status_code": status}
        if binary:
            out["content"] = getattr(resp, "content", b"")
            headers = getattr(resp, "headers", None) or {}
            out["content_type"] = headers.get("content-type") if hasattr(headers, "get") else None
        else:
            try:
                out["data"] = resp.json()
            except Exception:  # noqa: BLE001 — ردّ غير JSON (خطأ/HTML): لا نرفع
                out["data"] = None
                text = getattr(resp, "text", None)
                if text is not None:
                    out["text"] = text[:500]
        return out

    # ── العقود ────────────────────────────────────────────────────
    def add_stream_proxy(
        self,
        stream_id: str,
        source_url: str,
        app: str = "live",
        vhost: str = "__defaultVhost__",
    ) -> dict[str, Any]:
        """يضيف بثّاً وكيلاً (RTSP/RTMP… → ZLMediaKit) عبر ``addStreamProxy``."""
        return self._call("addStreamProxy", vhost=vhost, app=app, stream=stream_id, url=source_url)

    def del_stream_proxy(self, proxy_key: str) -> dict[str, Any]:
        """يزيل بثّاً وكيلاً عبر ``delStreamProxy`` (بمفتاح الوكيل المُعاد من الإضافة)."""
        return self._call("delStreamProxy", key=proxy_key)

    def get_media_list(self, app: str | None = None, vhost: str | None = None) -> dict[str, Any]:
        """يسرد الوسائط النشِطة عبر ``getMediaList``."""
        params: dict[str, Any] = {}
        if app is not None:
            params["app"] = app
        if vhost is not None:
            params["vhost"] = vhost
        return self._call("getMediaList", **params)

    def snapshot(
        self, stream_id: str, app: str = "live", vhost: str = "__defaultVhost__"
    ) -> dict[str, Any]:
        """يلتقط لقطة (JPEG) للبثّ عبر ``getSnap`` — يُرجِع ``content`` ثنائيّاً."""
        stream_url = f"{self.base_url}/{app}/{stream_id}.live.flv"
        return self._call("getSnap", binary=True, url=stream_url, timeout_sec=5, expire_sec=10)

    def start_record(
        self, stream_id: str, app: str = "live", vhost: str = "__defaultVhost__"
    ) -> dict[str, Any]:
        """يبدأ تسجيل MP4 للبثّ عبر ``startRecord`` (``type=1`` = mp4)."""
        return self._call("startRecord", type=1, vhost=vhost, app=app, stream=stream_id)

    def stop_record(
        self, stream_id: str, app: str = "live", vhost: str = "__defaultVhost__"
    ) -> dict[str, Any]:
        """يوقف تسجيل MP4 للبثّ عبر ``stopRecord`` (``type=1`` = mp4)."""
        return self._call("stopRecord", type=1, vhost=vhost, app=app, stream=stream_id)
