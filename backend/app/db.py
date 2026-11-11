from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import get_settings


class Base(DeclarativeBase):
    pass


_settings = get_settings()
_connect_args = {"check_same_thread": False} if _settings.database_url.startswith("sqlite") else {}
engine = create_engine(_settings.database_url, pool_pre_ping=True, connect_args=_connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    from . import models  # noqa: F401  — регистрирует таблицы

    Base.metadata.create_all(engine)
    # Лёгкие миграции для уже существующей базы (новые колонки)
    if engine.dialect.name == "postgresql":
        from sqlalchemy import text

        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS kommo_extra_contact_ids JSON"))
            conn.execute(text("ALTER TABLE news ADD COLUMN IF NOT EXISTS key VARCHAR(64) UNIQUE"))
