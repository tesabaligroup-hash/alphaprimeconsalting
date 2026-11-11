"""Веб-сервер: API для Mini App, админка, файлы и собранный фронтенд."""
import logging
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from . import admin, api
from .config import get_settings
from .db import SessionLocal, init_db

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
settings = get_settings()

app = FastAPI(title="Alpha Prime", docs_url="/api/docs" if settings.dev_mode else None, redoc_url=None, openapi_url="/api/openapi.json" if settings.dev_mode else None)
app.add_middleware(SessionMiddleware, secret_key=settings.secret_key, session_cookie="ap_admin", same_site="strict",
                   https_only=settings.public_url.startswith("https"), max_age=12 * 3600)
app.include_router(api.router)
app.include_router(admin.router)


@app.exception_handler(admin.NotLoggedIn)
def _login_redirect(request: Request, exc: admin.NotLoggedIn):
    return RedirectResponse("/admin/login", 303)


@app.on_event("startup")
def _startup() -> None:
    if not settings.dev_mode and settings.secret_key in ("", "change-me"):
        raise RuntimeError("Задайте SECRET_KEY в .env (openssl rand -hex 32)")
    init_db()
    Path(settings.uploads_dir).mkdir(parents=True, exist_ok=True)
    from .content import sync_news

    with SessionLocal() as db:
        sync_news(db)
    if settings.dev_mode:
        from .seed import seed_dev

        with SessionLocal() as db:
            seed_dev(db)


app.mount("/uploads", StaticFiles(directory=settings.uploads_dir, check_dir=False), name="uploads")

# Собранный фронтенд (frontend/dist) — отдаём как одностраничное приложение
FRONT = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if not FRONT.exists():
    FRONT = Path("/srv/frontend")
if (FRONT / "assets").exists():
    app.mount("/assets", StaticFiles(directory=FRONT / "assets"), name="assets")


@app.get("/{path:path}", include_in_schema=False)
def spa(path: str):
    index = FRONT / "index.html"
    candidate = (FRONT / path).resolve()
    if path and candidate.is_file() and FRONT.resolve() in candidate.parents:
        return FileResponse(candidate)
    if index.exists():  # без кэша — чтобы Telegram сразу подхватывал новую версию приложения
        return FileResponse(index, headers={"Cache-Control": "no-cache, no-store, must-revalidate"})
    return {"ok": True, "message": "Frontend is not built yet"}
