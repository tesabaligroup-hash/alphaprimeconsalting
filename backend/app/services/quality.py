"""Проверка заполнения CRM: раз в неделю — список сделок с ошибками в группу менеджеров.

Смотрим только сделки, которые клиент видит в приложении (Consulting, этапы с «Ждем $» и дальше, не закрытые).
"""
from datetime import timedelta
from html import escape

from ..kommo.base import KommoClient, KommoLead
from ..kommo.mapping import CLIENT_PIPELINE_IDS, LEAD_FIELDS, NO_PARTNER_VALUES, STATUS_TO_STEP, norm
from ..notify import kommo_lead_url
from ..tariffs import find_tariff
from ..timeutil import utcnow
from .cabinet import field_value

MAX_LINES = 40


def lead_problems(lead: KommoLead) -> list[str]:
    if lead.pipeline_id not in CLIENT_PIPELINE_IDS or norm(lead.status_name) not in STATUS_TO_STEP:
        return []
    out = []
    service = field_value(lead.fields, LEAD_FIELDS["service_type"])
    if not service or norm(str(service)) == "другое" or not find_tariff(str(service)):
        out.append(f"«Тип услуги»: {service or 'пусто'}")
    partner = field_value(lead.fields, LEAD_FIELDS["partner"])
    if partner in (None, ""):
        out.append("«Партнёр» пусто (поставьте кодовое слово или «Нет»)")
    elif norm(str(partner)) == "другое":
        out.append("«Партнёр» = «Другое» — партнёр ничего не получит")
    if not lead.contact_ids:
        out.append("нет контакта")
    return out


def weekly_report(kommo: KommoClient) -> str | None:
    """HTML-текст для группы менеджеров или None, если всё заполнено."""
    rows = []
    for lead in kommo.get_leads_updated_since(utcnow() - timedelta(days=400)):
        problems = lead_problems(lead)
        if problems:
            url = kommo_lead_url(lead.id)
            name = escape(lead.name or f"#{lead.id}")
            link = f'<a href="{url}">{name}</a>' if url else name
            rows.append(f"• {link} ({escape(lead.status_name)}): " + "; ".join(escape(p) for p in problems))
    if not rows:
        return None
    head = f"<b>🧹 Проверка CRM: {len(rows)} сделок нужно дозаполнить</b>\nБез этого клиент видит неполные данные, а партнёр не получает вознаграждение.\n"
    tail = f"\n…и ещё {len(rows) - MAX_LINES}" if len(rows) > MAX_LINES else ""
    return head + "\n".join(rows[:MAX_LINES]) + tail
