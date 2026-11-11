"""Настройки приложения. Все значения берутся из переменных окружения (.env)."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Общее
    app_name: str = "Alpha Prime"
    public_url: str = "http://localhost:8000"  # https://app.alpha-prime.group в проде
    dev_mode: bool = False  # True: тестовые данные Kommo и вход без Telegram (только для разработки!)
    secret_key: str = "change-me"  # подпись cookie админки
    database_url: str = "sqlite:///./dev.db"
    uploads_dir: str = "./uploads"
    timezone: str = "Asia/Makassar"

    # Telegram
    bot_token: str = ""
    bot_username: str = "AlphaPrimeBot"
    managers_chat_id: str = ""  # Telegram-группа менеджеров для уведомлений о заявках

    # Kommo
    kommo_base_url: str = ""  # https://baliprimeconsalting.kommo.com
    kommo_token: str = ""
    kommo_mock: bool = True  # True — работать на тестовых данных вместо Kommo

    # Админка
    admin_password: str = "change-me"

    # Контакты компании (показываются в приложении)
    company_whatsapp: str = "6281519845777"
    company_telegram: str = ""
    company_instagram: str = "alpha_prime_id"
    company_address: str = "Jl. Pantai Berawa No.13, Canggu, Kuta Utara, Badung, Bali 80361"
    company_maps_query: str = "Alpha Prime Bali, Jl. Pantai Berawa No.13, Canggu"  # что ищем в Google Maps по кнопке «Офис»


@lru_cache
def get_settings() -> Settings:
    return Settings()
