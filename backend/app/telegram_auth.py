"""Проверка подписи Telegram Mini App (initData).

https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app
"""
import hashlib
import hmac
import json
import time
from urllib.parse import parse_qsl


class InvalidInitData(Exception):
    pass


def validate_init_data(init_data: str, bot_token: str, max_age_seconds: int = 24 * 3600) -> dict:
    """Возвращает данные пользователя Telegram, если подпись верна. Иначе — InvalidInitData."""
    if not init_data or not bot_token:
        raise InvalidInitData("empty")
    pairs = dict(parse_qsl(init_data, keep_blank_values=True))
    received_hash = pairs.pop("hash", None)
    if not received_hash:
        raise InvalidInitData("no hash")
    data_check = "\n".join(f"{k}={v}" for k, v in sorted(pairs.items()))
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    calculated = hmac.new(secret, data_check.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(calculated, received_hash):
        raise InvalidInitData("bad hash")
    auth_date = int(pairs.get("auth_date", "0"))
    if max_age_seconds and time.time() - auth_date > max_age_seconds:
        raise InvalidInitData("expired")
    user = json.loads(pairs.get("user", "{}"))
    if not user.get("id"):
        raise InvalidInitData("no user")
    pairs["user"] = user
    return pairs


def sign_init_data(fields: dict, bot_token: str) -> str:
    """Для тестов: формирует initData с правильной подписью."""
    from urllib.parse import urlencode

    data = {k: (json.dumps(v, ensure_ascii=False) if isinstance(v, dict) else str(v)) for k, v in fields.items()}
    data_check = "\n".join(f"{k}={v}" for k, v in sorted(data.items()))
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    data["hash"] = hmac.new(secret, data_check.encode(), hashlib.sha256).hexdigest()
    return urlencode(data)
