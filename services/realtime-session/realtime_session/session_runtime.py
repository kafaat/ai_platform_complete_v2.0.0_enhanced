"""Disabled-by-default, single-node session service; no media or agent dispatch."""

from __future__ import annotations

import asyncio
import contextlib
import fcntl
import os
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import Depends, FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, Field, StrictBool

from .body_limit import BodyLimitMiddleware
from .contracts import SessionError
from .engine import SessionService


class CreateSession(BaseModel):
    model_config = ConfigDict(extra="forbid")
    field_id: str = Field(min_length=1, max_length=128)
    consent: StrictBool


def create_app(service: SessionService | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if service is not None or os.getenv("SAHOOL_REALTIME_ENABLED", "0") != "1":
            yield
            return
        if os.getenv("SAHOOL_REALTIME_MEDIA_TRUST", "") != "self_hosted":
            raise RuntimeError("explicit self-hosted media trust is required")
        if os.getenv("LIVEKIT_AUTO_CREATE_DISABLED", "") != "1":
            raise RuntimeError(
                "SFU room.auto_create=false must be explicitly configured and accepted"
            )
        # Operators must mount the same LOCAL volume and run one instance. Separate
        # replica disks cannot coordinate admission and are not supported.
        db_path = Path(os.getenv("REALTIME_SQLITE_PATH", ""))
        if not db_path.is_absolute() or not db_path.parent.is_dir():
            raise RuntimeError("an absolute persistent session database path is required")
        wss_url = os.getenv("LIVEKIT_WS_URL", "")
        parsed = urlsplit(wss_url)
        if (
            parsed.scheme != "wss"
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
            or parsed.path not in {"", "/"}
        ):
            raise RuntimeError("a trusted WSS media origin is required")
        lock = open(str(db_path) + ".lock", "a", encoding="utf-8")
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            lock.close()
            raise RuntimeError("only one realtime process may use this session store") from None
        client = None
        gateway = None
        worker = None
        try:
            import httpx

            from .livekit_adapter import LiveKitGateway
            from .platform import PlatformAuthority
            from .store import SessionStore

            client = httpx.AsyncClient(timeout=3, follow_redirects=False, trust_env=False)
            authority = PlatformAuthority(os.environ["PLATFORM_API_URL"], client)
            gateway = LiveKitGateway(
                os.environ["LIVEKIT_URL"],
                os.environ["LIVEKIT_API_KEY"],
                os.environ["LIVEKIT_API_SECRET"],
            )
            store = SessionStore(str(db_path))
            await store.initialize()
            app.state.service = SessionService(authority, store, gateway, wss_url)

            async def sweep():
                while True:
                    try:
                        await app.state.service.cleanup()
                        app.state.cleanup_healthy = True
                    except Exception:
                        app.state.cleanup_healthy = False
                    await asyncio.sleep(5)

            worker = asyncio.create_task(sweep())
            yield
        finally:
            if worker is not None:
                worker.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await worker
            if gateway is not None:
                with contextlib.suppress(Exception):
                    await gateway.close()
            if client is not None:
                with contextlib.suppress(Exception):
                    await client.aclose()
            app.state.service = None
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
            lock.close()

    app = FastAPI(title="SAHOOL Realtime Session", version="0.1.0", lifespan=lifespan)
    app.state.service = service
    app.state.cleanup_healthy = service is not None
    security = HTTPBearer(auto_error=False)

    @app.middleware("http")
    async def private_responses(request, call_next):
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["Pragma"] = "no-cache"
        return response

    @app.exception_handler(SessionError)
    async def session_error(_request, exc: SessionError):
        return JSONResponse(status_code=exc.status, content={"detail": {"error": exc.code}})

    @app.exception_handler(RequestValidationError)
    async def invalid_request(_request, _exc):
        # Pydantic's default error can echo an input bearing a credential.
        return JSONResponse(status_code=422, content={"detail": {"error": "invalid_request"}})

    async def bearer(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> str:
        if (
            credentials is None
            or credentials.scheme.lower() != "bearer"
            or len(credentials.credentials) > 16384
        ):
            raise HTTPException(401, "authentication_required")
        return credentials.credentials

    def current() -> SessionService:
        if app.state.service is None:
            raise SessionError(503, "realtime_disabled")
        return app.state.service

    @app.get("/healthz")
    async def health():
        return {"status": "ok"}

    @app.get("/readyz")
    async def ready():
        instance = app.state.service
        ok = bool(instance and app.state.cleanup_healthy and await instance.ready())
        return JSONResponse(status_code=200 if ok else 503, content={"ready": ok})

    @app.post("/api/v1/realtime/sessions", status_code=201)
    async def create_session(body: CreateSession, token: str = Depends(bearer)):
        if app.state.service is not None and not app.state.cleanup_healthy:
            raise SessionError(503, "session_cleanup_unavailable")
        return await current().create(token, body.field_id, body.consent)

    @app.get("/api/v1/realtime/sessions/{session_id}")
    async def get_session(session_id: str, token: str = Depends(bearer)):
        return await current().get(token, session_id)

    @app.delete("/api/v1/realtime/sessions/{session_id}", status_code=202)
    async def close_session(session_id: str, token: str = Depends(bearer)):
        return await current().close(token, session_id)

    app.add_middleware(BodyLimitMiddleware)
    return app


app = create_app()
