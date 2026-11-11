from functools import lru_cache

from ..config import get_settings
from .base import KommoClient


@lru_cache
def get_kommo() -> KommoClient:
    s = get_settings()
    if s.kommo_mock or not s.kommo_token:
        from .mock import MockKommo

        return MockKommo()
    from .real import RealKommo

    return RealKommo(s.kommo_base_url, s.kommo_token)
