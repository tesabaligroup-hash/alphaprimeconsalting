from datetime import datetime, timezone


def utcnow() -> datetime:
    """Текущее время UTC без часового пояса (так хранится в базе)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)
