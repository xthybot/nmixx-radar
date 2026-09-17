from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Annotated, cast

from fastapi import Body, FastAPI, Form, HTTPException, Request
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    JSONResponse,
    RedirectResponse,
    Response,
)
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.access import Transport, request_transport
from app.auth import (
    AuthenticatedSession,
    AuthenticationError,
    AuthService,
    InvitationError,
    SessionError,
)
from app.config import Settings
from app.database import Database
from app.image_proxy import ImageProxy, image_url
from app.push import PushError, PushService
from app.rate_limit import RateLimiter
from app.runtime_data import RuntimeDataStore
from app.site_data import get_site_data

ASSET_VERSION = "20260917-auth1"
HTTPS_SESSION_COOKIE = "radar_https_session"
LAN_SESSION_COOKIE = "radar_lan_session"


def create_app(settings: Settings | None = None) -> FastAPI:
    active_settings = settings or Settings.from_env()
    database = Database(active_settings)
    database.initialize()
    runtime_data = RuntimeDataStore(
        active_settings.data_dir, active_settings.max_generated_updates
    )
    runtime_data.initialize()
    auth = AuthService(database, active_settings)
    push = PushService(database, active_settings)
    image_proxy = ImageProxy(active_settings)
    rate_limiter = RateLimiter(database)
    if active_settings.bootstrap_admin_username and active_settings.bootstrap_admin_password:
        auth.bootstrap_admin()

    application = FastAPI(title="NMIXX Radar")
    application.state.settings = active_settings
    application.state.database = database
    application.state.auth = auth
    application.state.runtime_data = runtime_data
    application.state.push = push
    application.state.image_proxy = image_proxy
    application.mount("/static", StaticFiles(directory="app/static"), name="static")
    templates = Jinja2Templates(directory="app/templates")

    @application.middleware("http")
    async def response_policy(request: Request, call_next) -> Response:
        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            origin = request.headers.get("origin")
            if origin and request_transport(request, active_settings) is Transport.HTTPS:
                expected_origin = f"https://{request.headers.get('host', '')}"
                if origin.rstrip("/") != expected_origin.rstrip("/"):
                    return JSONResponse({"detail": "Cross-site request rejected."}, status_code=403)
        response = await call_next(request)
        if request.url.path in {"/", "/sw.js", "/manifest.webmanifest"} or request.url.path.startswith("/static/"):
            response.headers["Cache-Control"] = "no-store, max-age=0"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["X-Frame-Options"] = "DENY"
        return response

    def transport_for(request: Request) -> Transport:
        return request_transport(request, active_settings)

    def session_for(request: Request) -> AuthenticatedSession | None:
        transport = transport_for(request)
        cookie_name = HTTPS_SESSION_COOKIE if transport is Transport.HTTPS else LAN_SESSION_COOKIE
        token = request.cookies.get(cookie_name)
        if not token:
            return None
        cookie_kind = "https" if transport is Transport.HTTPS else "lan"
        try:
            return auth.load_session(token, cookie_kind)
        except SessionError:
            return None

    def require_user(request: Request) -> AuthenticatedSession:
        session = session_for(request)
        if not session:
            raise HTTPException(status_code=401, detail="Login required.")
        return session

    def require_https_admin(request: Request) -> AuthenticatedSession:
        if transport_for(request) is not Transport.HTTPS:
            raise HTTPException(status_code=403, detail="This action requires HTTPS.")
        session = require_user(request)
        if session.user.role != "admin":
            raise HTTPException(status_code=403, detail="Administrator access required.")
        return session

    def require_https_user(request: Request) -> AuthenticatedSession:
        if transport_for(request) is not Transport.HTTPS:
            raise HTTPException(status_code=403, detail="This action requires HTTPS.")
        return require_user(request)

    def login_redirect() -> RedirectResponse:
        return RedirectResponse("/login", status_code=303)

    def set_session_cookie(response: Response, session: AuthenticatedSession) -> None:
        https = session.cookie_kind == "https"
        response.set_cookie(
            HTTPS_SESSION_COOKIE if https else LAN_SESSION_COOKIE,
            session.token,
            max_age=max(1, int((session.idle_expires_at - datetime.now(UTC)).total_seconds())),
            httponly=True,
            secure=https,
            samesite="lax",
            path="/",
        )

    @application.get("/login", response_class=HTMLResponse)
    async def login_form(request: Request) -> Response:
        if session_for(request):
            return login_redirect()
        return templates.TemplateResponse(request, "login.html", {"asset_version": ASSET_VERSION, "error": None})

    @application.post("/login")
    async def login(request: Request, username: str = Form(), password: str = Form()) -> Response:
        transport = transport_for(request)
        if transport is Transport.PUBLIC_HTTP:
            raise HTTPException(status_code=403, detail="Login requires HTTPS or a private local network.")
        peer = request.client.host if request.client else "unknown"
        try:
            session = auth.authenticate(
                username,
                password,
                "https" if transport is Transport.HTTPS else "lan",
            )
        except AuthenticationError:
            if not rate_limiter.allow(
                "login", f"{peer}:{username.casefold().strip()}", limit=8, window_seconds=900
            ):
                return templates.TemplateResponse(
                    request,
                    "login.html",
                    {"asset_version": ASSET_VERSION, "error": "嘗試次數過多，請稍後再試。"},
                    status_code=429,
                )
            return templates.TemplateResponse(
                request,
                "login.html",
                {"asset_version": ASSET_VERSION, "error": "帳號或密碼錯誤。"},
                status_code=401,
            )
        response = RedirectResponse("/", status_code=303)
        set_session_cookie(response, session)
        return response

    @application.get("/register", response_class=HTMLResponse)
    async def registration_form(request: Request) -> Response:
        if session_for(request):
            return login_redirect()
        return templates.TemplateResponse(request, "register.html", {"asset_version": ASSET_VERSION, "error": None})

    @application.post("/register")
    async def register(
        request: Request,
        invitation_code: str = Form(),
        username: str = Form(),
        password: str = Form(),
    ) -> Response:
        transport = transport_for(request)
        if transport is Transport.PUBLIC_HTTP:
            raise HTTPException(status_code=403, detail="Registration requires HTTPS or a private local network.")
        peer = request.client.host if request.client else "unknown"
        try:
            user = auth.register(invitation_code, username, password)
            session = auth.authenticate(
                user.username,
                password,
                "https" if transport is Transport.HTTPS else "lan",
            )
        except (InvitationError, ValueError):
            if not rate_limiter.allow("registration", peer, limit=8, window_seconds=3600):
                return templates.TemplateResponse(
                    request,
                    "register.html",
                    {"asset_version": ASSET_VERSION, "error": "註冊嘗試次數過多，請稍後再試。"},
                    status_code=429,
                )
            return templates.TemplateResponse(
                request,
                "register.html",
                {"asset_version": ASSET_VERSION, "error": "邀請碼、帳號或密碼無效。"},
                status_code=400,
            )
        response = RedirectResponse("/", status_code=303)
        set_session_cookie(response, session)
        return response

    @application.post("/logout")
    async def logout(request: Request) -> Response:
        session = session_for(request)
        response = login_redirect()
        for name in (HTTPS_SESSION_COOKIE, LAN_SESSION_COOKIE):
            response.delete_cookie(name, path="/")
        if session:
            auth.revoke_session(session.id)
        return response

    @application.post("/account/renew")
    async def renew_account_session(request: Request, password: str = Form()) -> Response:
        if transport_for(request) is not Transport.HTTPS:
            raise HTTPException(status_code=403, detail="Session renewal requires HTTPS.")
        session = require_user(request)
        try:
            renewed = auth.renew_session(session.token, "https", password)
        except AuthenticationError:
            raise HTTPException(status_code=401, detail="Invalid password.") from None
        response = RedirectResponse("/", status_code=303)
        set_session_cookie(response, renewed)
        return response

    @application.get("/", response_class=HTMLResponse)
    async def home(request: Request) -> Response:
        session = session_for(request)
        if not session:
            return login_redirect()
        return templates.TemplateResponse(
            request,
            "index.html",
            {
                "asset_version": ASSET_VERSION,
                "image_url": image_url,
                "current_user": session.user,
                "session_renewal_required": session.renewal_required,
                **get_site_data(runtime_data),
            },
        )

    @application.get("/api/updates")
    async def updates_api(request: Request) -> dict[str, object]:
        require_user(request)
        updates = cast(list[dict[str, object]], get_site_data(runtime_data)["updates"])
        payload = json.dumps(updates, ensure_ascii=False, sort_keys=True)
        return {"signature": hashlib.sha256(payload.encode("utf-8")).hexdigest(), "count": len(updates), "latest": updates[0] if updates else None, "updates": updates}

    @application.post("/admin/invitations", status_code=201)
    async def create_invitation(request: Request) -> JSONResponse:
        session = require_https_admin(request)
        invitation_code = auth.create_invitation(session.user.id)
        return JSONResponse({"invitation_code": invitation_code}, status_code=201)

    @application.get("/admin", response_class=HTMLResponse)
    async def admin_dashboard(request: Request) -> HTMLResponse:
        require_https_admin(request)
        return templates.TemplateResponse(
            request,
            "admin.html",
            {"asset_version": ASSET_VERSION, "users": auth.list_users()},
        )

    @application.post("/admin/users/{user_id}/disable")
    async def disable_user(request: Request, user_id: int) -> Response:
        require_https_admin(request)
        try:
            auth.set_user_active(user_id, False)
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        return RedirectResponse("/admin", status_code=303)

    @application.post("/admin/users/{user_id}/enable")
    async def enable_user(request: Request, user_id: int) -> Response:
        require_https_admin(request)
        try:
            auth.set_user_active(user_id, True)
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        return RedirectResponse("/admin", status_code=303)

    @application.post("/admin/users/{user_id}/password")
    async def reset_user_password(request: Request, user_id: int, password: str = Form()) -> Response:
        require_https_admin(request)
        try:
            auth.set_password(user_id, password)
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        return RedirectResponse("/admin", status_code=303)

    @application.post("/admin/users/{user_id}/sessions/revoke")
    async def revoke_user_sessions(request: Request, user_id: int) -> Response:
        require_https_admin(request)
        auth.revoke_user_sessions(user_id)
        return RedirectResponse("/admin", status_code=303)

    @application.get("/api/push/public-key")
    async def push_public_key(request: Request) -> dict[str, str]:
        require_https_user(request)
        return {"publicKey": push.public_key()}

    @application.post("/api/push/subscribe", status_code=201)
    async def push_subscribe(
        request: Request, subscription: Annotated[dict[str, object], Body()]
    ) -> Response:
        session = require_https_user(request)
        if not rate_limiter.allow("push-subscribe", str(session.user.id), limit=10, window_seconds=3600):
            raise HTTPException(status_code=429, detail="Too many push subscription changes.")
        try:
            push.subscribe(session.user.id, subscription)
        except PushError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        return Response(status_code=201)

    @application.delete("/api/push/subscribe")
    async def push_unsubscribe(
        request: Request, payload: Annotated[dict[str, object], Body()]
    ) -> Response:
        session = require_https_user(request)
        endpoint = str(payload.get("endpoint", ""))
        try:
            push.unsubscribe(session.user.id, endpoint)
        except PushError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        return Response(status_code=204)

    @application.post("/admin/push/test")
    async def test_push(request: Request) -> dict[str, int]:
        session = require_https_admin(request)
        if not rate_limiter.allow("push-test", str(session.user.id), limit=3, window_seconds=3600):
            raise HTTPException(status_code=429, detail="Too many test notifications.")
        return push.send_test_to_user(session.user.id)

    @application.get("/manifest.webmanifest")
    async def manifest() -> FileResponse:
        return FileResponse("app/static/manifest.webmanifest", media_type="application/manifest+json")

    @application.get("/sw.js")
    async def service_worker() -> FileResponse:
        return FileResponse("app/static/sw.js", media_type="application/javascript")

    @application.get("/image")
    async def optimized_image(request: Request, url: str, w: int = 900, q: int = 74) -> FileResponse:
        require_user(request)
        return await image_proxy.get_optimized_image(url, w, q)

    @application.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return application


app = create_app()
