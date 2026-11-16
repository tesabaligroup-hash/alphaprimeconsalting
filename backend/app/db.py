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
    _backfill_codewords()
    # Лёгкие миграции для уже существующей базы (новые колонки)
    if engine.dialect.name == "postgresql":
        from sqlalchemy import text

        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS kommo_extra_contact_ids JSON"))
            conn.execute(text("ALTER TABLE news ADD COLUMN IF NOT EXISTS key VARCHAR(64) UNIQUE"))
            conn.execute(text("ALTER TABLE news ADD COLUMN IF NOT EXISTS cta_lead BOOLEAN DEFAULT FALSE"))
            conn.execute(text("ALTER TABLE accruals ADD COLUMN IF NOT EXISTS manual_code VARCHAR(32)"))
            conn.execute(text("ALTER TABLE accruals ADD COLUMN IF NOT EXISTS decision VARCHAR(16)"))


def _backfill_codewords() -> None:
    """Основное кодовое слово каждого партнёра — тоже в списке его слов (для старых партнёров)."""
    from sqlalchemy import select

    from .models import Partner, PartnerCodeword

    with SessionLocal() as db:
        have = set(db.scalars(select(PartnerCodeword.word)))
        for p in db.scalars(select(Partner).where(Partner.codeword.is_not(None))):
            if p.codeword not in have:
                db.add(PartnerCodeword(partner_id=p.id, word=p.codeword, created_at=p.created_at))
        db.commit()
