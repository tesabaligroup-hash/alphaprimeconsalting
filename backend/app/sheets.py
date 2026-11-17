"""Отправка заявки в Google-таблицу производства и папку на Google Диске через Apps Script (deploy/intake-apps-script.gs)."""
import logging

import httpx

from .config import get_settings

log = logging.getLogger(__name__)

# Колонки A…Z — точно как на листе «Производство» (строку можно скопировать туда целиком), дальше — служебные
HEADER = ["Год", "Мес.", "Начало работы", "Менеджер", "ПАРТНЕР", "% партнера", "Услуга", "Где перепика с клиентом",
          "Контакты клиента", "Какие документы есть", "Ссылка на документы клиента", "Крайняя дата подать документы",
          "Куда пришли деньги", "Куда пришли деньги 2", "Клиент", "Процесс работы \\ подрядчик",
          "Когда клиент идет на получение документов", "Комментарии", "Опл. PNBP", "Цена", "Себес", "Оплатил клиент",
          "Долг", "Доля партнеров", "% менеджера", "ЧП", "ID сделки", "Проверить (ИИ)", "Сделка в Kommo"]


def send_intake(folder_name: str, rows: list[list], files: list[dict], folder_id: str | None = None) -> dict:
    """files: [{"name", "mime", "data"(base64)}]. Возвращает {"ok": bool, "folder_url": …, "error": …}."""
    s = get_settings()
    if not s.intake_script_url:
        return {"ok": False, "error": "не задан INTAKE_SCRIPT_URL"}
    try:
        r = httpx.post(s.intake_script_url, timeout=120, follow_redirects=True,
                       json={"secret": s.intake_script_secret, "folder_name": folder_name, "header": HEADER,
                             "rows": rows, "files": files, "folder_id": folder_id})
        data = r.json()
    except Exception as exc:
        log.warning("Таблица производства недоступна: %s", exc)
        return {"ok": False, "error": str(exc)}
    return data if isinstance(data, dict) else {"ok": False, "error": "непонятный ответ"}
