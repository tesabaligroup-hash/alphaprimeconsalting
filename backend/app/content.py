"""Новости из репозитория: backend/content/news.json (+ картинки в backend/content/img/).

Так разработчик может добавить новость через GitHub, без входа в админку.
Каждая новость создаётся ОДИН раз (по полю key). Дальше её можно менять или удалять в админке —
при следующем обновлении сервера она не перезапишется и не вернётся.
"""
import json
import logging
import shutil
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import get_settings
from .models import AuditLog, News

log = logging.getLogger(__name__)
CONTENT = Path(__file__).resolve().parent.parent / "content"


def sync_news(db: Session) -> int:
    path = CONTENT / "news.json"
    if not path.exists():
        return 0
    try:
        items = json.loads(path.read_text(encoding="utf-8"))
    except ValueError:
        log.exception("content/news.json: ошибка в JSON")
        return 0
    seen = {a.details.get("key") for a in db.scalars(select(AuditLog).where(AuditLog.action == "content_news")) if a.details}
    uploads = Path(get_settings().uploads_dir)
    uploads.mkdir(parents=True, exist_ok=True)
    added = 0
    for it in items:
        key = it.get("key")
        if not key or key in seen or db.scalar(select(News).where(News.key == key)):
            continue
        image = None
        if it.get("image") and (CONTENT / "img" / it["image"]).is_file():
            image = f"content-{it['image']}"
            shutil.copyfile(CONTENT / "img" / it["image"], uploads / image)
        db.add(News(key=key, kind=it.get("kind", "company"), is_banner=bool(it.get("is_banner")), title=it["title"],
                    body=it.get("body"), partner_name=it.get("partner_name"), image_path=image,
                    link_url=it.get("link_url"), sort_order=int(it.get("sort_order", 0)), published=it.get("published", True)))
        db.add(AuditLog(actor="github", action="content_news", details={"key": key}))  # чтобы удалённая в админке не вернулась
        added += 1
    db.commit()
    if added:
        log.info("Добавлено новостей из content/news.json: %s", added)
    return added
