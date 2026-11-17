"""Отправка заявки в Google-таблицу производства и папку на Google Диске через Apps Script (deploy/intake-apps-script.gs)."""
import logging

import httpx

from .config import get_settings

log = logging.getLogger(__name__)

HEADER = ["ID сделки", "Дата оплаты", "Клиент (по паспорту)", "Гражданство", "Паспорт №", "Паспорт до", "Дата рождения",
          "Услуга", "Менеджер", "Сумма, IDR", "Оплачено, IDR", "Телефон", "Папка с документами", "Документы",
          "Не хватает / проверить", "Сделка в Kommo", "Статус"]


def send_intake(folder_name: str, row: list, files: list[dict]) -> dict:
    """files: [{"name", "mime", "data"(base64)}]. Возвращает {"ok": bool, "folder_url": …, "error": …}."""
    s = get_settings()
    if not s.intake_script_url:
        return {"ok": False, "error": "не задан INTAKE_SCRIPT_URL"}
    try:
        r = httpx.post(s.intake_script_url, timeout=120, follow_redirects=True,
                       json={"secret": s.intake_script_secret, "folder_name": folder_name, "header": HEADER,
                             "row": row, "files": files})
        data = r.json()
    except Exception as exc:
        log.warning("Таблица производства недоступна: %s", exc)
        return {"ok": False, "error": str(exc)}
    return data if isinstance(data, dict) else {"ok": False, "error": "непонятный ответ"}
