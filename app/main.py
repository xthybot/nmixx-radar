from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.access import Transport, request_transport
from app.auth import AuthService, AuthenticationError, AuthenticatedSession, SessionError
from app.config import Settings
from app.database import Database
from app.image_proxy import get_optimized_image, image_url
from app.push import get_vapid_public_key
from app.site_data import get_site_data


ASSET_VERSION = "20260917-auth1"
HTTPS_SESSION_COOKIE = "radar_https_session"
LAN_SESSION_COOKIE = "radar_lan_session"


def create_app(settings: Settings | None = None) -> FastAPI:
    active_settings = settings or Settings.from_env()
    database = Database(active_settings)
    database.initialize()
    auth = AuthService(database, active_settings)
    if active_settings.bootstrap_admin_username and active_settings.bootstrap_admin_password:
        auth.bootstrap_admin()

    application = FastAPI(title="NMIXX Radar")
    application.state.settings = active_settings
    application.state.database = database
    application.state.auth = auth
    application.mount("/static", StaticFiles(directory="app/static"), name="static")
    templates = Jinja2Templates(directory="app/templates")

    @application.middleware("http")
    async def response_policy(request: Request, call_next) -> Response:
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
    async def login_form(request: Request) -> HTMLResponse:
        if session_for(request):
            return login_redirect()
        return templates.TemplateResponse(request, "login.html", {"asset_version": ASSET_VERSION, "error": None})

    @application.post("/login")
    async def login(request: Request, username: str = Form(), password: str = Form()) -> Response:
        transport = transport_for(request)
        if transport is Transport.PUBLIC_HTTP:
            raise HTTPException(status_code=403, detail="Login requires HTTPS or a private local network.")
        try:
            session = auth.authenticate(
                username,
                password,
                "https" if transport is Transport.HTTPS else "lan",
            )
        except AuthenticationError:
            return templates.TemplateResponse(
                request,
                "login.html",
                {"asset_version": ASSET_VERSION, "error": "帳號或密碼錯誤。"},
                status_code=401,
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
            auth.revoke_user_sessions(session.user.id)
        return response

    @application.get("/", response_class=HTMLResponse)
    async def home(request: Request) -> HTMLResponse:
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
                **get_site_data(),
            },
        )

    @application.get("/api/updates")
    async def updates_api(request: Request) -> dict[str, object]:
        require_user(request)
        updates = get_site_data()["updates"]
        payload = json.dumps(updates, ensure_ascii=False, sort_keys=True)
        return {"signature": hashlib.sha256(payload.encode("utf-8")).hexdigest(), "count": len(updates), "latest": updates[0] if updates else None, "updates": updates}

    @application.post("/admin/invitations", status_code=201)
    async def create_invitation(request: Request) -> JSONResponse:
        session = require_https_admin(request)
        invitation_code = auth.create_invitation(session.user.id)
        return JSONResponse({"invitation_code": invitation_code}, status_code=201)

    @application.get("/api/push/public-key")
    async def push_public_key(request: Request) -> dict[str, str]:
        require_https_admin(request)
        return {"publicKey": get_vapid_public_key()}

    @application.get("/manifest.webmanifest")
    async def manifest() -> FileResponse:
        return FileResponse("app/static/manifest.webmanifest", media_type="application/manifest+json")

    @application.get("/sw.js")
    async def service_worker() -> FileResponse:
        return FileResponse("app/static/sw.js", media_type="application/javascript")

    @application.get("/image")
    async def optimized_image(request: Request, url: str, w: int = 900, q: int = 74) -> FileResponse:
        require_user(request)
        return get_optimized_image(url, w, q)

    @application.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return application


app = create_app()
