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
    docs_dir: str = "./docs"  # готовые визы/ITK клиентов — НЕ публичная папка, отдаются только по временной ссылке
    timezone: str = "Asia/Makassar"

    # Telegram
    bot_token: str = ""
    bot_username: str = "AlphaPrimeBot"
    managers_chat_id: str = ""  # Telegram-группа менеджеров для уведомлений о заявках

    # Kommo
    kommo_base_url: str = ""  # https://baliprimeconsalting.kommo.com
    kommo_token: str = ""
    kommo_mock: bool = True  # True — работать на тестовых данных вместо Kommo

    # Почта (Яндекс 360, IMAP) — откуда берём готовые ITK/визы. Пароль — «пароль приложения», не основной.
    mail_imap_host: str = "imap.yandex.ru"
    mail_user: str = ""
    mail_password: str = ""

    # ИИ (чтение паспортов и виз) — тот же ключ, что у детского приложения
    anthropic_api_key: str = ""
    ai_model: str = "claude-haiku-5-5"  # дешёвая — читает все документы
    ai_model_strong: str = "claude-sonnet-5-5"  # если дешёвая не разобрала документ
    drive_docs: bool = False  # раз в сутки забирать визы/ITK из папок Google Диска (поле контакта «Документы»)

    # Автозаявка в производство: Google-таблица + Google Диск через Apps Script (см. deploy/intake-apps-script.gs)
    intake_enabled: bool = False  # пока False — работает только ручная проверка: python -m app.intake --lead ID
    intake_script_url: str = ""
    intake_script_secret: str = ""
    # Таблица производства — источник статусов услуг и начислений партнёрам (тот же Apps Script, doGet)
    table_sync: bool = False
    table_move_stages: bool = False
    table_sync_partners: bool = False  # начисления партнёрам по таблице (включить, когда имена партнёров выверены)  # двигать сделку в «Услуга готова», когда в таблице услуга выполнена

    # Админка
    admin_password: str = "change-me"

    # Контакты компании (показываются в приложении)
    company_whatsapp: str = "6281519845777"
    company_telegram: str = "alpha_prime_id"
    company_instagram: str = "alpha_prime_id"
    company_address: str = "Jl. Pantai Berawa No.13, Canggu, Kuta Utara, Badung, Bali 80361"
    # Кнопка «Офис»: сразу карточка нашего офиса в Google Maps (без списка с рекламой)
    company_maps_url: str = ("https://www.google.com/maps/search/?api=1&query=Alpha%20Prime%20Bali"
                             "&query_place_id=ChIJP_eEMABH0i0R3yfZkIGoajw")
    company_maps_query: str = "Alpha Prime Bali, Jl. Pantai Berawa No.13, Canggu"  # что ищем в Google Maps по кнопке «Офис»


@lru_cache
def get_settings() -> Settings:
    return Settings()
